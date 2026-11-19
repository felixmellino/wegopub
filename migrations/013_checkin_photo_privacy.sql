-- Apply before deploying photo sharing. No row means OFF, including old accounts.
begin;
create table if not exists public.player_photo_preferences (
  player_id uuid primary key references public.players(id) on delete cascade,
  share_checkin_photos boolean not null default false
);
alter table public.player_photo_preferences enable row level security;
revoke all on public.player_photo_preferences from public, anon, authenticated;
grant all on public.player_photo_preferences to service_role;
commit;
