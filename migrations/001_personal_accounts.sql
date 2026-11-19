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
