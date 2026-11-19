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
