-- Run after schema.sql on the Supabase project used by the app.
begin;

alter table public.drink_entries add column if not exists photo_captured_at timestamptz;

-- Verification has already finished for saved entries. Preserve their scores
-- and territory assignment while removing legacy exact-coordinate evidence.
update public.drink_entries
set device_gps_lat = null, device_gps_lng = null,
    photo_gps_lat = null, photo_gps_lng = null
where device_gps_lat is not null or device_gps_lng is not null
   or photo_gps_lat is not null or photo_gps_lng is not null;

-- The app authenticates players on its server and uses a service-role key.
-- Membership and season records are the source of photo access decisions.
alter table public.lobby_memberships enable row level security;
alter table public.seasons enable row level security;
alter table public.drink_entries enable row level security;
revoke all on public.lobby_memberships, public.seasons, public.drink_entries from anon, authenticated;

insert into storage.buckets (id, name, public)
values ('check-in-photos', 'check-in-photos', false)
on conflict (id) do nothing;

do $$
begin
  if exists (select 1 from storage.buckets where id = 'check-in-photos' and public is distinct from false) then
    raise exception 'The existing check-in-photos bucket must be private.';
  end if;
end;
$$;

-- Keep this bucket server-only even if another bucket has broader policies.
drop policy if exists checkin_photos_server_only on storage.objects;
create policy checkin_photos_server_only on storage.objects
  as restrictive for all to anon, authenticated
  using (bucket_id <> 'check-in-photos')
  with check (bucket_id <> 'check-in-photos');

commit;
