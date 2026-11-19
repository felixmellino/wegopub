-- WeGoPub database schema (Supabase / Postgres).
-- Run once against your Supabase project's SQL editor.
-- This file already includes migrations 001-004 and 006. A new project
-- still needs, in order: setup_checkin_photo_storage.sql, then
-- 005_scoring_v1.sql, 007_lobby_battles.sql, 008_profile_pictures.sql,
-- 009_single_competition_lobbies.sql and 010_team_lobbies.sql -- see
-- README.md for the exact sequence. Each migration is additive and versioned.

create extension if not exists pgcrypto;

create table players (
  id uuid primary key default gen_random_uuid(),
  display_name text unique not null,
  first_name text not null,
  last_name text not null,
  pin_hash text not null
);

create table lobbies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  invite_code text unique not null
);

create table lobby_memberships (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references players(id),
  lobby_id uuid not null references lobbies(id),
  joined_at timestamptz not null default now(),
  unique (player_id, lobby_id)
);

create table seasons (
  id uuid primary key default gen_random_uuid(),
  lobby_id uuid not null references lobbies(id),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  length_choice text not null
);

-- Copied from data/territories.geojson by the app on start (R-T01).
-- id is the territory's short, permanent key, e.g. 'rua-da-rosa'.
-- boundary is a GeoJSON Polygon, e.g. {"type":"Polygon","coordinates":[[[lng,lat],...]]}
create table territories (
  id text primary key check (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  name text not null,
  boundary jsonb not null
);

create table drink_entries (
  id uuid primary key default gen_random_uuid(),
  membership_id uuid not null references lobby_memberships(id),
  season_id uuid not null references seasons(id),
  drink_type text not null,
  amount double precision,
  photo_ref text not null,
  photo_captured_at timestamptz,
  device_gps_lat double precision,
  device_gps_lng double precision,
  photo_gps_lat double precision,
  photo_gps_lng double precision,
  territory_id text references territories(id),
  location_check_result text not null,
  points_awarded integer not null,
  submitted_at timestamptz not null
);

create index drink_entries_duplicate_check
  on drink_entries (membership_id, drink_type, submitted_at);
create index drink_entries_season on drink_entries (season_id);
create index drink_entries_territory on drink_entries (territory_id);

-- GeoJSON Point, e.g. {"type":"Point","coordinates":[lng,lat]}
create table arenas (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  map_point jsonb not null
);

create table minigame_attempts (
  id uuid primary key default gen_random_uuid(),
  membership_id uuid not null references lobby_memberships(id),
  season_id uuid not null references seasons(id),
  arena_id uuid not null references arenas(id),
  game_type text not null,
  game_window_id text not null,
  started_at timestamptz not null,
  status text not null,
  result text
);

create index minigame_attempts_window
  on minigame_attempts (membership_id, game_window_id);

-- Public clients cannot read invite codes or change game state. The app
-- validates its custom player sessions before using its server service key.
alter table public.lobbies enable row level security;
alter table public.lobby_memberships enable row level security;
alter table public.seasons enable row level security;
alter table public.territories enable row level security;
alter table public.drink_entries enable row level security;
alter table public.arenas enable row level security;
alter table public.minigame_attempts enable row level security;
revoke all on public.lobbies, public.lobby_memberships, public.seasons,
  public.territories, public.drink_entries, public.arenas, public.minigame_attempts
  from public, anon, authenticated;
grant all on public.lobbies, public.lobby_memberships, public.seasons,
  public.territories, public.drink_entries, public.arenas, public.minigame_attempts
  to service_role;

-- Personal account support (also provided separately for existing databases).
-- Apply ONCE to an existing database. All player IDs and game records survive.
-- Case-insensitive duplicates must be resolved by the team before proceeding.
begin;
alter table players add column email text;
create unique index players_username_case_insensitive on players (lower(btrim(display_name)));
create unique index players_email_case_insensitive on players (lower(btrim(email))) where email is not null;
alter table players add constraint players_email_normalized
  check (email is null or (email = lower(btrim(email)) and email <> ''));

create table password_resets (
  player_id uuid primary key references players(id) on delete cascade,
  code_hash text not null,
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null
);

-- Credentials and recovery codes are accessible only to the server's service key.
alter table players enable row level security;
alter table password_resets enable row level security;
revoke all on players, password_resets from anon, authenticated;

create function issue_password_reset(target_player uuid, new_code_hash text)
returns boolean language plpgsql set search_path = public as $$
begin
  perform 1 from players where id = target_player and email is not null for update;
  if not found then return false; end if;
  if exists (select 1 from password_resets where player_id = target_player
             and issued_at > now() - interval '1 minute') then
    return false;
  end if;
  insert into password_resets (player_id, code_hash, issued_at, expires_at)
    values (target_player, new_code_hash, now(), now() + interval '15 minutes')
    on conflict (player_id) do update set code_hash = excluded.code_hash,
      issued_at = excluded.issued_at, expires_at = excluded.expires_at;
  return true;
end;
$$;

create function consume_password_reset(target_email text, supplied_code_hash text, new_password_hash text)
returns boolean language plpgsql set search_path = public as $$
declare target uuid;
begin
  select id into target from players where lower(email) = lower(btrim(target_email)) for update;
  if target is null then return false; end if;
  delete from password_resets where player_id = target and code_hash = supplied_code_hash
    and expires_at > now();
  if not found then return false; end if;
  update players set pin_hash = new_password_hash where id = target;
  return true;
end;
$$;

revoke all on function issue_password_reset(uuid, text) from public, anon, authenticated;
revoke all on function consume_password_reset(text, text, text) from public, anon, authenticated;
grant execute on function issue_password_reset(uuid, text) to service_role;
grant execute on function consume_password_reset(text, text, text) to service_role;
-- Persist login throttling across browser sessions and application restarts.
create table login_attempts (
  player_id uuid primary key references players(id) on delete cascade,
  window_start timestamptz not null,
  attempts integer not null
);
alter table login_attempts enable row level security;
revoke all on login_attempts from anon, authenticated;
create function allow_login_attempt(target_player uuid)
returns boolean language plpgsql set search_path = public as $$
declare attempt_count integer;
begin
  insert into login_attempts (player_id, window_start, attempts)
    values (target_player, now(), 1)
    on conflict (player_id) do update set
      attempts = case when login_attempts.window_start <= now() - interval '15 minutes'
        then 1 else least(login_attempts.attempts + 1, 11) end,
      window_start = case when login_attempts.window_start <= now() - interval '15 minutes'
        then now() else login_attempts.window_start end
    returning attempts into attempt_count;
  return attempt_count <= 10;
end;
$$;
revoke all on function allow_login_attempt(uuid) from public, anon, authenticated;
grant execute on function allow_login_attempt(uuid) to service_role;
grant all on players, password_resets, login_attempts to service_role;
commit;

-- Apply after 001_personal_accounts.sql; existing accounts and points are unchanged.
begin;
create table remembered_sessions (
  token_hash text primary key,
  player_id uuid not null references players(id) on delete cascade,
  credential_version text not null,
  expires_at timestamptz not null
);
create index remembered_sessions_player on remembered_sessions(player_id);
alter table remembered_sessions enable row level security;
revoke all on remembered_sessions from anon, authenticated;
grant all on remembered_sessions to service_role;
commit;

-- Friend requests and accepted friends (migration 005).
-- Apply once in Supabase SQL editor. Custom login is enforced by the
-- Streamlit server; browsers never receive the service role key.
begin;
create table public.friendships (
  sender_id uuid not null references public.players(id) on delete cascade,
  recipient_id uuid not null references public.players(id) on delete cascade,
  pair_low uuid generated always as (least(sender_id, recipient_id)) stored,
  pair_high uuid generated always as (greatest(sender_id, recipient_id)) stored,
  status text not null check (status in ('pending', 'accepted', 'declined', 'cancelled', 'removed')),
  updated_at timestamptz not null default now(),
  version uuid not null default gen_random_uuid(),
  primary key (pair_low, pair_high),
  check (sender_id <> recipient_id)
);
create index friendships_recipient on public.friendships (recipient_id);
alter table public.friendships enable row level security;
revoke all on public.friendships from public, anon, authenticated;
grant all on public.friendships to service_role;

-- Rules are evaluated in core/friends.py. Compare-and-swap prevents two
-- server sessions from overwriting a request/response they have not seen.
-- Database time is used for the decline timer, including across restarts.
create function public.save_friendship(
  sender uuid, recipient uuid, next_status text, expected_version uuid
) returns void language plpgsql set search_path = public as $$
declare actual_version uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(
    least(sender, recipient)::text || ':' || greatest(sender, recipient)::text, 0));
  select version into actual_version from friendships
    where pair_low = least(sender, recipient) and pair_high = greatest(sender, recipient);
  if actual_version is distinct from expected_version then
    raise exception 'Friendship changed. Refresh and try again.' using errcode = '40001';
  end if;
  insert into friendships (sender_id, recipient_id, status)
    values (sender, recipient, next_status)
    on conflict (pair_low, pair_high) do update set
      sender_id = excluded.sender_id, recipient_id = excluded.recipient_id,
      status = excluded.status, updated_at = clock_timestamp(), version = gen_random_uuid();
end;
$$;
revoke all on function public.save_friendship(uuid, uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.save_friendship(uuid, uuid, text, uuid) to service_role;
commit;
