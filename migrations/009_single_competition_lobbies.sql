-- A lobby runs once. Existing multi-season history is retained unchanged.
-- Apply after 005_scoring_v1.sql. Safe to run again.
begin;
create or replace function public._one_competition_per_lobby()
returns trigger language plpgsql set search_path = public as $$
begin
  -- Match start_scoring_season's lock, including direct concurrent inserts.
  perform pg_advisory_xact_lock(hashtext(new.lobby_id::text));
  if tg_op = 'UPDATE' and new.lobby_id = old.lobby_id then
    return new;
  end if;
  if exists(select 1 from public.seasons where lobby_id = new.lobby_id and id <> new.id) then
    raise exception 'lobby_already_started';
  end if;
  return new;
end;
$$;
drop trigger if exists one_competition_per_lobby on public.seasons;
create trigger one_competition_per_lobby before insert or update of lobby_id on public.seasons
for each row execute function public._one_competition_per_lobby();
revoke all on function public._one_competition_per_lobby() from public, anon, authenticated;
notify pgrst, 'reload schema';
commit;
