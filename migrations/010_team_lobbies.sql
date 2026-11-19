-- Apply after 005 and 009. Existing lobbies and scores remain individual.
begin;
alter table public.lobbies add column if not exists game_mode text not null default 'individual';
alter table public.lobbies add column if not exists team_count integer;
alter table public.lobbies add column if not exists team_capacity integer;
alter table public.lobbies add column if not exists team_assignment text;
alter table public.lobbies drop constraint if exists lobby_team_config;
alter table public.lobbies add constraint lobby_team_config check (
  (game_mode = 'individual' and team_count is null and team_capacity is null and team_assignment is null)
  or (game_mode = 'team' and team_count is not null and team_count between 2 and 16
      and team_capacity is not null and team_capacity between 1 and 20
      and team_assignment is not null and team_assignment in ('manual','random')));
create table if not exists public.lobby_teams (
  id uuid primary key default gen_random_uuid(),
  lobby_id uuid not null references public.lobbies(id),
  number integer not null,
  name text not null check (length(btrim(name)) between 1 and 40 and name !~ '[[:cntrl:]]'),
  photo_base64 text check (length(photo_base64) <= 524288),
  unique(lobby_id, number), unique(lobby_id, id)
);
create unique index if not exists lobby_team_names on public.lobby_teams(lobby_id, lower(btrim(name)));
alter table public.lobby_teams enable row level security;
revoke all on public.lobby_teams from public, anon, authenticated;
grant all on public.lobby_teams to service_role;
alter table public.lobby_memberships add column if not exists team_id uuid;
-- Composite FK prevents a membership referring to another lobby's team.
do $$ begin
  if not exists(select 1 from pg_constraint where conname = 'membership_lobby_team') then
    alter table public.lobby_memberships add constraint membership_lobby_team
      foreign key(lobby_id,team_id) references public.lobby_teams(lobby_id,id);
  end if;
end $$;
alter table public.drink_entries add column if not exists team_id uuid references public.lobby_teams(id);
alter table public.drink_entries add column if not exists owner_team_id uuid references public.lobby_teams(id);
create index if not exists memberships_team on public.lobby_memberships(team_id);

create or replace function public._configure_lobby_teams()
returns trigger language plpgsql set search_path = public as $$
begin
  if tg_op = 'UPDATE' then
    if row(new.game_mode,new.team_count,new.team_capacity,new.team_assignment)
       is distinct from row(old.game_mode,old.team_count,old.team_capacity,old.team_assignment) then
      raise exception 'team_settings_frozen';
    end if;
  elsif new.game_mode = 'team' then
    insert into public.lobby_teams(lobby_id,number,name)
      select new.id,n,'Team ' || n from generate_series(1,new.team_count) n;
  end if;
  return new;
end $$;
drop trigger if exists configure_lobby_teams on public.lobbies;
create trigger configure_lobby_teams after insert or update on public.lobbies
  for each row execute function public._configure_lobby_teams();

create or replace function public._guard_team_membership()
returns trigger language plpgsql set search_path = public as $$
declare config public.lobbies%rowtype; lid uuid; chosen uuid;
begin
  lid := case when tg_op = 'DELETE' then old.lobby_id else new.lobby_id end;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  select * into config from public.lobbies where id = lid;
  if tg_op in ('UPDATE','DELETE') then
    if tg_op = 'UPDATE' and row(new.id,new.player_id,new.lobby_id) is distinct from row(old.id,old.player_id,old.lobby_id) then
      raise exception 'membership_identity_frozen';
    end if;
    if config.game_mode = 'team' and exists(select 1 from public.drink_entries where membership_id = old.id) then
      if tg_op = 'DELETE' then raise exception 'team_locked'; end if;
      if new.team_id is distinct from old.team_id then raise exception 'team_locked'; end if;
    end if;
  end if;
  if tg_op = 'DELETE' then return old; end if;
  if config.game_mode = 'individual' then
    if new.team_id is not null then raise exception 'invalid_team'; end if;
    return new;
  end if;
  if tg_op = 'UPDATE' and new.team_id is not distinct from old.team_id then return new; end if;
  if exists(select 1 from public.seasons where lobby_id = lid and ends_at <= statement_timestamp()) then
    raise exception 'lobby_finished';
  end if;
  if tg_op = 'INSERT' then
    if (select count(*) from public.lobby_memberships where lobby_id = lid) >= config.team_count * config.team_capacity then
      raise exception 'lobby_full';
    end if;
    if config.team_assignment = 'random' then
      select t.id into chosen from public.lobby_teams t
        left join public.lobby_memberships m on m.team_id = t.id
        where t.lobby_id = lid group by t.id having count(m.id) < config.team_capacity
        order by count(m.id),random() limit 1;
      if chosen is null then raise exception 'lobby_full'; end if;
      new.team_id := chosen;
    end if;
  elsif config.team_assignment = 'random' then
    raise exception 'random_team_locked';
  end if;
  if new.team_id is not null then
    if not exists(select 1 from public.lobby_teams where id = new.team_id and lobby_id = lid) then
      raise exception 'invalid_team';
    end if;
    if (select count(*) from public.lobby_memberships where team_id = new.team_id and id <> new.id) >= config.team_capacity then
      raise exception 'team_full';
    end if;
  end if;
  return new;
end $$;
drop trigger if exists guard_team_membership on public.lobby_memberships;
create trigger guard_team_membership before insert or update or delete on public.lobby_memberships
  for each row execute function public._guard_team_membership();

create or replace function public.choose_lobby_team(actor_player uuid,target_lobby uuid,target_team uuid)
returns void language plpgsql set search_path = public as $$
begin
  perform pg_advisory_xact_lock(hashtext(target_lobby::text));
  if target_team is null then raise exception 'invalid_team'; end if;
  update public.lobby_memberships set team_id = target_team where player_id = actor_player and lobby_id = target_lobby;
  if not found then raise exception 'permission_denied'; end if;
end $$;

create or replace function public.edit_lobby_team(actor_player uuid,target_team uuid,new_name text,new_photo text,change_photo boolean)
returns void language plpgsql set search_path = public as $$
declare lid uuid;
begin
  select lobby_id into lid from public.lobby_teams where id = target_team;
  if lid is null then raise exception 'permission_denied'; end if;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  if not exists(select 1 from public.lobby_memberships where player_id = actor_player and lobby_id = lid and team_id = target_team) then
    raise exception 'permission_denied';
  end if;
  if new_name is null or length(btrim(new_name)) not between 1 and 40 or new_name ~ '[[:cntrl:]]' then raise exception 'invalid_team_name'; end if;
  update public.lobby_teams set name = btrim(new_name),
    photo_base64 = case when change_photo then new_photo else photo_base64 end where id = target_team;
end $$;

create or replace function public._snapshot_entry_team()
returns trigger language plpgsql set search_path = public as $$
declare lid uuid; mode text; assigned uuid; member_lobby uuid;
begin
  if tg_op = 'UPDATE' then
    if row(new.team_id,new.membership_id,new.season_id) is distinct from row(old.team_id,old.membership_id,old.season_id) then
      raise exception 'entry_identity_frozen';
    end if;
    return new;
  end if;
  select s.lobby_id,l.game_mode into lid,mode from public.seasons s join public.lobbies l on l.id = s.lobby_id where s.id = new.season_id;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  select team_id,lobby_id into assigned,member_lobby from public.lobby_memberships where id = new.membership_id;
  if member_lobby is distinct from lid then raise exception 'permission_denied'; end if;
  if mode = 'team' then
    if assigned is null then raise exception 'team_required'; end if;
    if new.rule_version <> 'v1' then raise exception 'scoring_setup_required'; end if;
    new.team_id := assigned;
  else
    new.team_id := null;
  end if;
  return new;
end $$;
drop trigger if exists snapshot_entry_team on public.drink_entries;
create trigger snapshot_entry_team before insert or update on public.drink_entries
  for each row execute function public._snapshot_entry_team();

-- Same replay algorithm as 005, using the saved team as the competitor.
create or replace function public._replay_scoring_season(target_season uuid)
returns void language plpgsql set search_path = public as $$
declare
  entry public.drink_entries%rowtype; rules jsonb;
  totals jsonb := '{}'; owners jsonb := '{}';
  territory text; member text; prior_owner text; points integer; new_total integer;
begin
  select scoring_rules into rules from public.seasons where id = target_season and scoring_version = 'v1';
  if rules is null then raise exception 'scoring_setup_required'; end if;
  for entry in select * from public.drink_entries where season_id = target_season order by event_order loop
    points := public._scoring_points(rules, entry.drink_type, entry.size);
    territory := case when entry.location_check_result = 'matched' then entry.territory_id else null end;
    member := coalesce(entry.team_id,entry.membership_id)::text;
    prior_owner := case when territory is not null then owners ->> territory else null end;
    update public.drink_entries set points_awarded = points,
      owner_membership_id = case when entry.team_id is null and prior_owner is not null and prior_owner <> member then prior_owner::uuid else null end,
      owner_team_id = case when entry.team_id is not null and prior_owner is not null and prior_owner <> member then prior_owner::uuid else null end,
      owner_bonus_quarters = case when prior_owner is not null and prior_owner <> member then points else 0 end
      where id = entry.id;
    if territory is not null then
      new_total := coalesce((totals -> territory ->> member)::integer, 0) + points;
      totals := jsonb_set(totals, array[territory],
        coalesce(totals -> territory, '{}'::jsonb) || jsonb_build_object(member,new_total),true);
      if prior_owner is null or new_total > (totals -> territory ->> prior_owner)::integer then
        owners := owners || jsonb_build_object(territory,member);
      end if;
    end if;
  end loop;
end $$;
revoke all on function public._configure_lobby_teams(), public._guard_team_membership(),
  public._snapshot_entry_team(), public.choose_lobby_team(uuid,uuid,uuid),
  public.edit_lobby_team(uuid,uuid,text,text,boolean) from public, anon, authenticated;
grant execute on function public.choose_lobby_team(uuid,uuid,uuid),
  public.edit_lobby_team(uuid,uuid,text,text,boolean) to service_role;
notify pgrst, 'reload schema';
commit;
