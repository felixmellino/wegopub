-- Read only the selected season's pending incoming invitations.
begin;

create or replace function public.pending_minigame_invite_count(actor_player uuid, target_season uuid)
returns bigint language sql stable set search_path = public as $$
  with recipient as (
    select m.id, s, statement_timestamp() as at_time
    from public.seasons s
    join public.active_lobby_memberships m on m.lobby_id = s.lobby_id
    where s.id = target_season and m.player_id = actor_player
      and s.scoring_version = 'v1'
      and statement_timestamp() >= s.starts_at and statement_timestamp() < s.ends_at
  )
  select count(*) from (
    select d.id from recipient r
    join public.chug_duels d on d.opponent_id = r.id and d.season_id = (r.s).id
    where d.status = 'invited' and d.expires_at > r.at_time
      and d.game_night = public._chug_night(r.at_time, (r.s).timezone_name)
      and public._scoring_window_open(r.at_time, (r.s).timezone_name, (r.s).scoring_rules)
    union all
    select d.id from recipient r
    join public.quiz_duels d on d.opponent_id = r.id and d.season_id = (r.s).id
    where d.status = 'invited' and d.expires_at > r.at_time
    union all
    select d.id from recipient r
    join public.time_duels d on d.opponent_id = r.id and d.season_id = (r.s).id
    where d.status = 'invited' and d.expires_at > r.at_time
  ) invitations;
$$;

revoke all on function public.pending_minigame_invite_count(uuid, uuid) from public, anon, authenticated;
grant execute on function public.pending_minigame_invite_count(uuid, uuid) to service_role;
notify pgrst, 'reload schema';

commit;
