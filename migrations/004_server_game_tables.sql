-- Custom player login runs in the app server, which uses service_role.
-- Public Supabase clients must not read invite codes or change game records.
begin;

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

commit;
