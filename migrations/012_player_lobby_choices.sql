-- Account-wide navigation preference. Apply after the existing migrations.
-- The server authenticates the player; this preference grants no lobby access.
begin;
create table public.player_lobby_choices (
  player_id uuid primary key references public.players(id) on delete cascade,
  lobby_id uuid not null references public.lobbies(id) on delete cascade
);
alter table public.player_lobby_choices enable row level security;
revoke all on public.player_lobby_choices from public, anon, authenticated;
grant all on public.player_lobby_choices to service_role;
commit;
