-- Additive migration. Existing seasons remain legacy; start a new v1 season.
-- Run after 004_server_game_tables.sql and setup_checkin_photo_storage.sql.
begin;

alter table public.seasons add column if not exists timezone_name text not null default 'Europe/Lisbon';
alter table public.seasons add column if not exists scoring_version text not null default 'legacy';
alter table public.seasons add column if not exists scoring_rules jsonb;
alter table public.drink_entries add column if not exists size text;
alter table public.drink_entries add column if not exists rule_version text not null default 'legacy';
alter table public.drink_entries add column if not exists event_order bigint generated always as identity;
-- Derived from existing accepted membership rows during replay. No second FK
-- to memberships: old PostgREST membership joins must remain unambiguous.
alter table public.drink_entries add column if not exists owner_membership_id uuid;
alter table public.drink_entries add column if not exists owner_bonus_quarters integer not null default 0;
alter table public.drink_entries add column if not exists corrected_at timestamptz;
alter table public.drink_entries add column if not exists revision integer not null default 0;
create index if not exists drink_entries_scoring_order on public.drink_entries(season_id, event_order);

create table if not exists public.drink_entry_revisions (
  id bigint generated always as identity primary key,
  entry_id uuid not null references public.drink_entries(id),
  actor_player_id uuid not null references public.players(id),
  revision integer not null,
  old_drink_type text not null, old_size text,
  new_drink_type text not null, new_size text,
  corrected_at timestamptz not null,
  unique(entry_id, revision)
);
alter table public.drink_entry_revisions enable row level security;
revoke all on public.drink_entry_revisions from public, anon, authenticated;
grant all on public.drink_entry_revisions to service_role;
grant usage, select on sequence public.drink_entry_revisions_id_seq, public.drink_entries_event_order_seq to service_role;

create or replace function public._scoring_points(rules jsonb, drink text, size_key text)
returns integer language plpgsql immutable set search_path = public as $$
declare value text;
begin
  if drink = 'shot' and size_key is not null and size_key <> 'standard' then
    raise exception 'invalid_selection';
  end if;
  value := rules -> 'points' -> drink ->> (case when drink = 'shot' then 'standard' else size_key end);
  if value is null or value !~ '^[1-9][0-9]*$' then raise exception 'invalid_selection'; end if;
  return value::integer;
end;
$$;

create or replace function public._scoring_window_open(at_time timestamptz, zone_name text, rules jsonb)
returns boolean language sql stable set search_path = public as $$
  select (extract(isodow from timezone(zone_name, at_time)) - 1) * 86400
       + extract(hour from timezone(zone_name, at_time)) * 3600
       + extract(minute from timezone(zone_name, at_time)) * 60
       + extract(second from timezone(zone_name, at_time))
    >= (rules ->> 'start_weekday')::integer * 86400 + (rules ->> 'start_hour')::integer * 3600
     and (extract(isodow from timezone(zone_name, at_time)) - 1) * 86400
       + extract(hour from timezone(zone_name, at_time)) * 3600
       + extract(minute from timezone(zone_name, at_time)) * 60
       + extract(second from timezone(zone_name, at_time))
    < (rules ->> 'end_weekday')::integer * 86400 + (rules ->> 'end_hour')::integer * 3600;
$$;

create or replace function public._freeze_scoring_season()
returns trigger language plpgsql set search_path = public as $$
begin
  if old.scoring_version = 'v1' and
     row(new.lobby_id, new.timezone_name, new.scoring_version, new.scoring_rules, new.starts_at, new.ends_at, new.length_choice)
       is distinct from row(old.lobby_id, old.timezone_name, old.scoring_version, old.scoring_rules, old.starts_at, old.ends_at, old.length_choice) then
    raise exception 'season_rules_frozen';
  end if;
  if old.scoring_version = 'legacy' and new.scoring_version <> 'legacy'
      and exists(select 1 from public.drink_entries where season_id = old.id) then
    raise exception 'season_has_legacy_entries';
  end if;
  return new;
end;
$$;
drop trigger if exists freeze_scoring_season on public.seasons;
create trigger freeze_scoring_season before update on public.seasons
  for each row execute function public._freeze_scoring_season();

create or replace function public._guard_entry_scoring_version()
returns trigger language plpgsql set search_path = public as $$
begin
  if new.rule_version is distinct from (select scoring_version from public.seasons where id = new.season_id) then
    raise exception 'scoring_version_mismatch';
  end if;
  return new;
end;
$$;
drop trigger if exists guard_entry_scoring_version on public.drink_entries;
create trigger guard_entry_scoring_version before insert on public.drink_entries
  for each row execute function public._guard_entry_scoring_version();

create or replace function public._replay_scoring_season(target_season uuid)
returns void language plpgsql set search_path = public as $$
declare
  entry public.drink_entries%rowtype;
  rules jsonb;
  totals jsonb := '{}'; owners jsonb := '{}';
  territory text; member text; prior_owner text; points integer; new_total integer;
begin
  select scoring_rules into rules from public.seasons where id = target_season and scoring_version = 'v1';
  if rules is null then raise exception 'scoring_setup_required'; end if;
  for entry in select * from public.drink_entries where season_id = target_season order by event_order loop
    points := public._scoring_points(rules, entry.drink_type, entry.size);
    territory := case when entry.location_check_result = 'matched' then entry.territory_id else null end;
    member := entry.membership_id::text;
    prior_owner := case when territory is not null then owners ->> territory else null end;
    update public.drink_entries set points_awarded = points,
      owner_membership_id = case when prior_owner is not null and prior_owner <> member then prior_owner::uuid else null end,
      owner_bonus_quarters = case when prior_owner is not null and prior_owner <> member then points else 0 end
      where id = entry.id;
    if territory is not null then
      new_total := coalesce((totals -> territory ->> member)::integer, 0) + points;
      totals := jsonb_set(totals, array[territory],
        coalesce(totals -> territory, '{}'::jsonb) || jsonb_build_object(member, new_total), true);
      if prior_owner is null or new_total > (totals -> territory ->> prior_owner)::integer then
        owners := owners || jsonb_build_object(territory, member);
      end if;
    end if;
  end loop;
end;
$$;

create or replace function public.accept_scoring_checkin(
  actor_player uuid, capture_id uuid, member_id uuid, target_season uuid,
  selected_drink text, selected_size text, verified_territory text,
  location_result text, stored_photo text, photo_received_at timestamptz
)
returns setof public.drink_entries language plpgsql set search_path = public as $$
declare
  season public.seasons%rowtype;
  existing public.drink_entries%rowtype;
  received_at timestamptz := statement_timestamp();
  points integer;
  last_submission timestamptz;
  amount_ml double precision;
begin
  select s.* into season from public.seasons s join public.lobby_memberships m on m.lobby_id = s.lobby_id
    where s.id = target_season and m.id = member_id and m.player_id = actor_player;
  if not found then raise exception 'permission_denied'; end if;
  -- One lobby lock also protects the cross-season, per-membership cooldown.
  perform pg_advisory_xact_lock(hashtext(season.lobby_id::text));
  select * into existing from public.drink_entries where id = capture_id;
  if found then
    if existing.membership_id <> member_id or existing.season_id <> target_season then
      raise exception 'permission_denied';
    end if;
    return query select * from public.drink_entries where id = capture_id;
    return;
  end if;
  if season.scoring_version <> 'v1' or season.scoring_rules is null then raise exception 'scoring_setup_required'; end if;
  if received_at < season.starts_at or received_at >= season.ends_at
    or not public._scoring_window_open(received_at, season.timezone_name, season.scoring_rules) then
    raise exception 'scoring_closed';
  end if;
  points := public._scoring_points(season.scoring_rules, selected_drink, selected_size);
  if location_result is null or location_result not in ('matched','outside') then raise exception 'location_unavailable'; end if;
  if (location_result = 'matched' and (verified_territory is null or not exists(select 1 from public.territories where id = verified_territory)))
      or (location_result = 'outside' and verified_territory is not null) then raise exception 'invalid_territory'; end if;
  if stored_photo is distinct from season.lobby_id::text || '/' || capture_id::text || '.jpg' then raise exception 'invalid_photo'; end if;
  if photo_received_at is null or photo_received_at > received_at then raise exception 'invalid_photo'; end if;
  select max(submitted_at) into last_submission from public.drink_entries where membership_id = member_id;
  if last_submission is not null and received_at < last_submission + make_interval(secs => (season.scoring_rules->>'cooldown_seconds')::integer) then
    raise exception 'cooldown';
  end if;
  amount_ml := (season.scoring_rules -> 'volumes' -> selected_drink ->> selected_size)::double precision;
  insert into public.drink_entries(id,membership_id,season_id,drink_type,amount,size,photo_ref,photo_captured_at,
    territory_id,location_check_result,points_awarded,submitted_at,rule_version)
  values(capture_id,member_id,target_season,selected_drink,amount_ml,
    case when selected_drink = 'shot' then null else selected_size end,stored_photo,photo_received_at,
    verified_territory,location_result,points,received_at,'v1');
  perform public._replay_scoring_season(target_season);
  return query select * from public.drink_entries where id = capture_id;
end;
$$;

create or replace function public.correct_scoring_checkin(
  actor_player uuid, target_entry uuid, selected_drink text, selected_size text, expected_revision integer
)
returns setof public.drink_entries language plpgsql set search_path = public as $$
declare
  entry public.drink_entries%rowtype;
  season public.seasons%rowtype;
  received_at timestamptz := statement_timestamp();
  normalized_size text := case when selected_drink = 'shot' then null else selected_size end;
begin
  select s.* into season from public.seasons s join public.drink_entries d on d.season_id = s.id
    join public.lobby_memberships m on m.id = d.membership_id and m.lobby_id = s.lobby_id
    where d.id = target_entry and m.player_id = actor_player;
  if not found then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(season.lobby_id::text));
  select * into entry from public.drink_entries where id = target_entry for update;
  if entry.rule_version <> 'v1' then raise exception 'correction_closed'; end if;
  perform public._scoring_points(season.scoring_rules, selected_drink, selected_size);
  -- Recover a committed correction after its response was lost, even after deadline.
  if entry.drink_type = selected_drink and entry.size is not distinct from normalized_size then
    return query select * from public.drink_entries where id = target_entry;
    return;
  end if;
  if received_at >= entry.submitted_at + make_interval(secs => (season.scoring_rules->>'correction_seconds')::integer)
    or received_at >= season.ends_at then raise exception 'correction_closed'; end if;
  if entry.revision <> expected_revision then raise exception 'correction_conflict'; end if;
  insert into public.drink_entry_revisions(entry_id,actor_player_id,revision,old_drink_type,old_size,
    new_drink_type,new_size,corrected_at)
  values(entry.id,actor_player,entry.revision+1,entry.drink_type,entry.size,selected_drink,normalized_size,received_at);
  update public.drink_entries set drink_type = selected_drink, size = normalized_size,
    amount = (season.scoring_rules -> 'volumes' -> selected_drink ->> normalized_size)::double precision,
    corrected_at = received_at, revision = entry.revision + 1 where id = target_entry;
  perform public._replay_scoring_season(season.id);
  return query select * from public.drink_entries where id = target_entry;
end;
$$;

create or replace function public.start_scoring_season(
  actor_player uuid, target_lobby uuid, length_choice text, zone_name text, frozen_rules jsonb
)
returns setof public.seasons language plpgsql set search_path = public as $$
declare received_at timestamptz := statement_timestamp(); season_days integer; new_id uuid := gen_random_uuid();
begin
  if not exists(select 1 from public.lobby_memberships where lobby_id = target_lobby and player_id = actor_player) then
    raise exception 'permission_denied';
  end if;
  perform pg_advisory_xact_lock(hashtext(target_lobby::text));
  if exists(select 1 from public.seasons where lobby_id = target_lobby and ends_at > received_at) then
    raise exception 'season_still_active';
  end if;
  if not exists(select 1 from pg_timezone_names where name = zone_name) then raise exception 'invalid_timezone'; end if;
  season_days := case length_choice when '1_week' then 7 when '1_month' then 30 when '3_months' then 91 end;
  if season_days is null or frozen_rules->>'version' is distinct from 'v1'
      or frozen_rules->>'owner_bonus_quarters_per_point' is distinct from '1' then raise exception 'invalid_rules'; end if;
  insert into public.seasons(id,lobby_id,starts_at,ends_at,length_choice,timezone_name,scoring_version,scoring_rules)
  values(new_id,target_lobby,received_at,received_at+make_interval(days=>season_days),length_choice,zone_name,'v1',frozen_rules);
  return query select * from public.seasons where id = new_id;
end;
$$;

revoke all on function public._scoring_points(jsonb,text,text),
  public._scoring_window_open(timestamptz,text,jsonb), public._freeze_scoring_season(),
  public._guard_entry_scoring_version(), public._replay_scoring_season(uuid),
  public.accept_scoring_checkin(uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz),
  public.correct_scoring_checkin(uuid,uuid,text,text,integer),
  public.start_scoring_season(uuid,uuid,text,text,jsonb) from public, anon, authenticated;
grant execute on function public._scoring_points(jsonb,text,text),
  public._scoring_window_open(timestamptz,text,jsonb), public._replay_scoring_season(uuid),
  public.accept_scoring_checkin(uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz),
  public.correct_scoring_checkin(uuid,uuid,text,text,integer),
  public.start_scoring_season(uuid,uuid,text,text,jsonb) to service_role;

notify pgrst, 'reload schema';
commit;
