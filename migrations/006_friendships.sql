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
