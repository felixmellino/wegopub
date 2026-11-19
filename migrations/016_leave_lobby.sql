-- Apply after 015. Departures revoke access but never delete score identities.
begin;
alter table public.lobby_memberships add column if not exists left_at timestamptz;
alter table public.drink_entries add column if not exists absent_member_ids uuid[] not null default '{}';

-- Same roster columns, restricted to current participants. Historical rows stay
-- in lobby_memberships for profile totals, standings, team capacity and FKs.
create or replace view public.active_lobby_memberships with (security_invoker=true) as
 select * from public.lobby_memberships where left_at is null with local check option;
revoke all on public.active_lobby_memberships from public,anon,authenticated;
grant select,update on public.active_lobby_memberships to service_role;

create or replace function public._require_active_lobby(actor_player uuid,target_lobby uuid)
returns void language plpgsql set search_path=public as $$
begin
 if target_lobby is null then raise exception 'permission_denied'; end if;
 perform pg_advisory_xact_lock(hashtext(target_lobby::text));
 if not exists(select 1 from public.active_lobby_memberships
               where player_id=actor_player and lobby_id=target_lobby) then
  raise exception 'permission_denied';
 end if;
end $$;

create or replace function public.leave_lobby(actor_player uuid,target_lobby uuid)
returns void language plpgsql set search_path=public as $$
declare m public.lobby_memberships%rowtype; season_record public.seasons%rowtype;
 at_time timestamptz:=statement_timestamp();
begin
 perform pg_advisory_xact_lock(hashtext(target_lobby::text));
 select * into m from public.lobby_memberships where player_id=actor_player and lobby_id=target_lobby;
 if not found then raise exception 'permission_denied'; end if;
 if m.left_at is not null then return; end if; -- safe retry after a lost response
 perform public._expire_chug_duels(target_lobby,at_time);
 for season_record in select * from public.seasons where lobby_id=target_lobby loop
  perform public._focus_expire(m.id,season_record.id,at_time);
 end loop;
 if exists(select 1 from public.chug_duels d join public.seasons s on s.id=d.season_id
           where s.lobby_id=target_lobby and m.id in (d.challenger_id,d.opponent_id)
             and d.status in ('accepted','started'))
    or exists(select 1 from public.focus_attempts where membership_id=m.id and status='running') then
  raise exception 'minigame_active';
 end if;
 -- Unaccepted invitations do not trap a member or survive a departure/rejoin.
 update public.chug_duels d set status='cancelled',finished_at=at_time
  from public.seasons s where s.id=d.season_id and s.lobby_id=target_lobby
   and m.id in (d.challenger_id,d.opponent_id) and d.status='invited';
 update public.lobby_memberships set left_at=at_time where id=m.id;
 delete from public.player_lobby_choices where player_id=actor_player and lobby_id=target_lobby;
end $$;

create or replace function public.rejoin_lobby(actor_player uuid,target_lobby uuid)
returns void language plpgsql set search_path=public as $$
begin
 perform pg_advisory_xact_lock(hashtext(target_lobby::text));
 update public.lobby_memberships set left_at=null where player_id=actor_player and lobby_id=target_lobby;
 if not found then raise exception 'permission_denied'; end if;
end $$;

-- Snapshot departures under the SAME lobby lock as scoring and leaving.
-- Corrections retain the snapshot, even when replay changes the prior owner.
create or replace function public._snapshot_absent_members()
returns trigger language plpgsql set search_path=public as $$
declare lid uuid;
begin
 if tg_op='UPDATE' then
  if new.absent_member_ids is distinct from old.absent_member_ids then
   raise exception 'entry_identity_frozen';
  end if;
  return new;
 end if;
 select lobby_id into lid from public.seasons where id=new.season_id;
 perform pg_advisory_xact_lock(hashtext(lid::text));
 if not exists(select 1 from public.active_lobby_memberships where id=new.membership_id and lobby_id=lid) then
  raise exception 'permission_denied';
 end if;
 select coalesce(array_agg(id),'{}'::uuid[]) into new.absent_member_ids
  from public.lobby_memberships where lobby_id=lid and left_at is not null;
 return new;
end $$;
drop trigger if exists snapshot_absent_members on public.drink_entries;
create trigger snapshot_absent_members before insert or update on public.drink_entries
 for each row execute function public._snapshot_absent_members();

-- Existing RPC bodies below keep their rules and signatures. Their membership
-- reads now use the active view. Checks that formerly preceded a lock acquire
-- it before authorization, so departure cannot race an already-open page.

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
  perform public._require_active_lobby(actor_player,(select lobby_id from public.seasons where id=target_season));
  select s.* into season from public.seasons s join public.active_lobby_memberships m on m.lobby_id = s.lobby_id
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
  perform public._require_active_lobby(actor_player,(select s.lobby_id from public.seasons s join public.drink_entries d on d.season_id=s.id where d.id=target_entry));
  select s.* into season from public.seasons s join public.drink_entries d on d.season_id = s.id
    join public.active_lobby_memberships m on m.id = d.membership_id and m.lobby_id = s.lobby_id
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
  perform public._require_active_lobby(actor_player,target_lobby);
  if not exists(select 1 from public.active_lobby_memberships where lobby_id = target_lobby and player_id = actor_player) then
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

create or replace function public.choose_lobby_team(actor_player uuid,target_lobby uuid,target_team uuid)
returns void language plpgsql set search_path = public as $$
begin
  perform pg_advisory_xact_lock(hashtext(target_lobby::text));
  if target_team is null then raise exception 'invalid_team'; end if;
  update public.active_lobby_memberships set team_id = target_team where player_id = actor_player and lobby_id = target_lobby;
  if not found then raise exception 'permission_denied'; end if;
end $$;

create or replace function public.edit_lobby_team(actor_player uuid,target_team uuid,new_name text,new_photo text,change_photo boolean)
returns void language plpgsql set search_path = public as $$
declare lid uuid;
begin
  select lobby_id into lid from public.lobby_teams where id = target_team;
  if lid is null then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  if not exists(select 1 from public.active_lobby_memberships where player_id = actor_player and lobby_id = lid and team_id = target_team) then
    raise exception 'permission_denied';
  end if;
  if new_name is null or length(btrim(new_name)) not between 1 and 40 or new_name ~ '[[:cntrl:]]' then raise exception 'invalid_team_name'; end if;
  update public.lobby_teams set name = btrim(new_name),
    photo_base64 = case when change_photo then new_photo else photo_base64 end where id = target_team;
end $$;

create or replace function public._check_chug_pair(cid uuid,oid uuid,lid uuid)
returns void language plpgsql set search_path = public as $$
declare c public.active_lobby_memberships%rowtype; o public.active_lobby_memberships%rowtype; mode text;
begin
  select * into c from public.active_lobby_memberships where id=cid and lobby_id=lid;
  if not found then raise exception 'permission_denied'; end if;
  select * into o from public.active_lobby_memberships where id=oid and lobby_id=lid;
  if not found or c.player_id=o.player_id then raise exception 'permission_denied'; end if;
  select game_mode into mode from public.lobbies where id=lid;
  if mode='team' and (c.team_id is null or o.team_id is null or c.team_id=o.team_id) then
    raise exception 'duel_team';
  end if;
end $$;

create or replace function public.list_chug_duels(actor_player uuid,target_season uuid)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare lid uuid; mid uuid;
begin
  perform public._require_active_lobby(actor_player,(select lobby_id from public.seasons where id=target_season));
  select s.lobby_id,m.id into lid,mid from public.seasons s join public.active_lobby_memberships m on m.lobby_id=s.lobby_id
    where s.id=target_season and m.player_id=actor_player;
  if not found then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  perform public._expire_chug_duels(lid,statement_timestamp());
  return query select * from public.chug_duels where season_id=target_season
    and (challenger_id=mid or opponent_id=mid) order by created_at desc;
end $$;

create or replace function public.invite_chug_duel(actor_player uuid,target_season uuid,
  invitation_id uuid,opponent_member uuid,selected_drink text,selected_size text)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare s public.seasons%rowtype; cid uuid; at_time timestamptz := statement_timestamp(); night date;
  old public.chug_duels%rowtype;
begin
  select * into s from public.seasons where id=target_season;
  if not found then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  select id into cid from public.active_lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
  if cid is null then raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into old from public.chug_duels where id=invitation_id;
  if found then
    if old.challenger_id<>cid or old.season_id<>target_season or old.opponent_id<>opponent_member
      or old.drink_type is distinct from selected_drink or old.size is distinct from selected_size then
      raise exception 'permission_denied';
    end if;
    return query select * from public.chug_duels where id=invitation_id; return;
  end if;
  if s.scoring_version<>'v1' or s.scoring_rules is null then raise exception 'scoring_setup_required'; end if;
  if at_time<s.starts_at or at_time>=s.ends_at or not public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules) then
    raise exception 'scoring_closed'; end if;
  perform public._scoring_points(s.scoring_rules,selected_drink,selected_size);
  perform public._check_chug_pair(cid,opponent_member,s.lobby_id);
  night := public._chug_night(at_time,s.timezone_name);
  perform public._check_chug_slots(cid,opponent_member,night,invitation_id);
  if exists(select 1 from public.chug_duels where challenger_id=cid and status='invited') then raise exception 'duel_pending'; end if;
  insert into public.chug_duels(id,season_id,challenger_id,opponent_id,game_night,drink_type,size,created_at,expires_at)
    values(invitation_id,target_season,cid,opponent_member,night,selected_drink,selected_size,at_time,at_time+interval '10 minutes');
  return query select * from public.chug_duels where id=invitation_id;
end $$;

create or replace function public.chug_duel_action(actor_player uuid,target_duel uuid,
  selected_action text,winning_member uuid default null)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare d public.chug_duels%rowtype; s public.seasons%rowtype; mid uuid;
  at_time timestamptz := statement_timestamp(); losing_entry uuid; winner_account uuid;
begin
  select * into d from public.chug_duels where id=target_duel;
  if not found then raise exception 'permission_denied'; end if;
  select * into s from public.seasons where id=d.season_id;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  select id into mid from public.active_lobby_memberships where player_id=actor_player and lobby_id=s.lobby_id;
  if mid is null or mid not in (d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
  if selected_action in ('accept','decline') and mid<>d.opponent_id then raise exception 'permission_denied'; end if;
  if selected_action in ('cancel','arm','finish') and mid<>d.challenger_id then raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into d from public.chug_duels where id=target_duel for update;
  -- Terminal outcomes are immutable, including retries after a lost response.
  if d.status in ('completed','aborted','declined','cancelled','expired') then
    return query select * from public.chug_duels where id=target_duel; return;
  end if;
  if selected_action='accept' then
    if d.status='invited' then
      perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
      perform public._check_chug_slots(d.challenger_id,d.opponent_id,d.game_night,d.id);
      update public.chug_duels set status='accepted',accepted_at=at_time,expires_at=at_time+interval '10 minutes' where id=d.id;
    end if;
  elsif selected_action='decline' and d.status='invited' then
    update public.chug_duels set status='declined',finished_at=at_time where id=d.id;
  elsif selected_action='cancel' and d.status in ('invited','accepted') then
    update public.chug_duels set status='cancelled',finished_at=at_time where id=d.id;
  elsif selected_action='abort' then
    update public.chug_duels set status=case when d.status='started' then 'aborted' else 'cancelled' end,
      finished_at=at_time where id=d.id;
  elsif selected_action='arm' and d.status='started' then
    update public.chug_duels set play_at=coalesce(play_at,at_time+interval '3 seconds') where id=d.id;
  elsif selected_action='finish' and d.status='started' then
    if winning_member is null or winning_member not in (d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
    if d.play_at is null or at_time<d.play_at then raise exception 'duel_early'; end if;
    losing_entry := case when winning_member=d.challenger_id then d.opponent_entry_id else d.challenger_entry_id end;
    select coalesce(team_id,membership_id) into winner_account from public.drink_entries
      where id=case when winning_member=d.challenger_id then d.challenger_entry_id else d.opponent_entry_id end;
    if winner_account is null then raise exception 'duel_unavailable'; end if;
    update public.drink_entries set duel_transfer_to=winner_account,
      duel_transfer_order=nextval('public.drink_entries_event_order_seq') where id=losing_entry;
    update public.chug_duels set status='completed',winner_id=winning_member,finished_at=at_time where id=d.id;
  else raise exception 'duel_unavailable';
  end if;
  return query select * from public.chug_duels where id=target_duel;
end $$;

create or replace function public.start_chug_duel(actor_player uuid,target_duel uuid,
  verified_territory text,location_result text,photo_received_at timestamptz)
returns setof public.chug_duels language plpgsql set search_path = public as $$
declare d public.chug_duels%rowtype; s public.seasons%rowtype; opponent_player uuid;
  at_time timestamptz := statement_timestamp();
begin
  select * into d from public.chug_duels where id=target_duel;
  if not found then raise exception 'permission_denied'; end if;
  select * into s from public.seasons where id=d.season_id;
  perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
  if not exists(select 1 from public.active_lobby_memberships where id=d.challenger_id and player_id=actor_player and lobby_id=s.lobby_id) then
    raise exception 'permission_denied'; end if;
  perform public._expire_chug_duels(s.lobby_id,at_time);
  select * into d from public.chug_duels where id=target_duel for update;
  if d.status in ('started','completed','aborted') then
    return query select * from public.chug_duels where id=target_duel; return;
  end if;
  if d.status<>'accepted' then raise exception 'duel_unavailable'; end if;
  perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
  perform public._check_chug_slots(d.challenger_id,d.opponent_id,d.game_night,d.id);
  if photo_received_at is null or photo_received_at<d.accepted_at or photo_received_at>at_time
    then raise exception 'invalid_photo'; end if;
  -- Python verifies the shared camera bytes and current phone GPS. Only the
  -- server service role can call this RPC, like accept_scoring_checkin.
  select player_id into opponent_player from public.active_lobby_memberships where id=d.opponent_id;
  perform public.accept_scoring_checkin(actor_player,d.challenger_entry_id,d.challenger_id,s.id,
    d.drink_type,d.size,verified_territory,location_result,s.lobby_id::text||'/'||d.challenger_entry_id::text||'.jpg',photo_received_at);
  perform public.accept_scoring_checkin(opponent_player,d.opponent_entry_id,d.opponent_id,s.id,
    d.drink_type,d.size,verified_territory,location_result,s.lobby_id::text||'/'||d.opponent_entry_id::text||'.jpg',photo_received_at);
  update public.drink_entries set duel_id=d.id where id in (d.challenger_entry_id,d.opponent_entry_id);
  update public.chug_duels set status='started',started_at=at_time,expires_at=at_time+interval '10 minutes' where id=d.id;
  return query select * from public.chug_duels where id=target_duel;
end $$;

create or replace function public._focus_season(actor_player uuid,target_season uuid)
returns public.seasons language plpgsql set search_path=public as $$
declare s public.seasons%rowtype;
begin
  perform public._require_active_lobby(actor_player,(select lobby_id from public.seasons where id=target_season));
 select season.* into s from public.seasons season join public.active_lobby_memberships m on m.lobby_id=season.lobby_id
 where season.id=target_season and m.player_id=actor_player;
 if not found then raise exception 'permission_denied'; end if;
 if public._focus_rules(s) is null then
  raise exception 'focus_disabled'; end if;
 return s;
end $$;

-- Team income belongs to the team; only personal owner income is paused.
create or replace function public._replay_scoring_season(target_season uuid)
returns void language plpgsql set search_path = public as $$
declare
  entry public.drink_entries%rowtype; rules jsonb;
  totals jsonb := '{}'; owners jsonb := '{}';
  territory text; member text; prior_owner text; points numeric; new_total numeric;
begin
  select scoring_rules into rules from public.seasons where id = target_season and scoring_version = 'v1';
  if rules is null then raise exception 'scoring_setup_required'; end if;
  for entry in select * from public.drink_entries where season_id = target_season order by event_order loop
    points := public._scoring_points(rules, entry.drink_type, entry.size) * case when entry.focus_attempt_id is not null then 1.5 else 1 end;
    territory := case when entry.location_check_result = 'matched' then entry.territory_id else null end;
    member := coalesce(entry.team_id,entry.membership_id)::text;
    prior_owner := case when territory is not null then owners ->> territory else null end;
    update public.drink_entries set points_awarded = points,
      owner_membership_id = case when entry.team_id is null and prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then prior_owner::uuid else null end,
      owner_team_id = case when entry.team_id is not null and prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then prior_owner::uuid else null end,
      owner_bonus_quarters = case when prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then points else 0 end
      where id = entry.id;
    if territory is not null then
      new_total := coalesce((totals -> territory ->> member)::numeric, 0) + points;
      totals := jsonb_set(totals, array[territory],
        coalesce(totals -> territory, '{}'::jsonb) || jsonb_build_object(member,new_total),true);
      if prior_owner is null or new_total > (totals -> territory ->> prior_owner)::numeric then
        owners := owners || jsonb_build_object(territory,member);
      end if;
    end if;
  end loop;
end $$;

revoke all on function public._require_active_lobby(uuid,uuid),public.leave_lobby(uuid,uuid),
 public.rejoin_lobby(uuid,uuid),public._snapshot_absent_members() from public,anon,authenticated;
grant execute on function public._require_active_lobby(uuid,uuid),public.leave_lobby(uuid,uuid),
 public.rejoin_lobby(uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
