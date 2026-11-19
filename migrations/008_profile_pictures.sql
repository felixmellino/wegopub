-- Data owner: apply after account setup; friend visibility also needs
-- 006_friendships.sql. Safe to re-run. Does not alter Player or game records.
begin;

create table if not exists public.profile_pictures (
  player_id uuid primary key references public.players(id) on delete cascade,
  photo_ref text not null,
  updated_at timestamptz not null default now()
);
alter table public.profile_pictures enable row level security;
revoke all on public.profile_pictures from public, anon, authenticated;
grant all on public.profile_pictures to service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('profile-pictures', 'profile-pictures', false, 10485760, array['image/jpeg'])
on conflict (id) do nothing;
do $$
begin
  if exists (select 1 from storage.buckets
             where id = 'profile-pictures' and public is distinct from false) then
    raise exception 'The existing profile-pictures bucket must be private.';
  end if;
end;
$$;

drop policy if exists profile_pictures_server_only on storage.objects;
create policy profile_pictures_server_only on storage.objects
  as restrictive for all to anon, authenticated
  using (bucket_id <> 'profile-pictures')
  with check (bucket_id <> 'profile-pictures');

commit;
