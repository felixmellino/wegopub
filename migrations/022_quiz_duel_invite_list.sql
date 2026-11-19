-- Keep every pending and active duel visible inside Quiz Duel.
-- Time Duel already returns all open duels after 021_time_duel_invitations.sql.
begin;

create or replace function public.quiz_status(actor_player uuid,target_season uuid) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; mid uuid; account uuid; night date; outgoing boolean; incoming boolean; items jsonb;
 at_time timestamptz:=statement_timestamp(); qa boolean;
begin
 s:=public._quiz_season(actor_player,target_season);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 perform public._quiz_refresh(s,at_time);
 select id,coalesce(team_id,id) into mid,account from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 night:=public._chug_night(at_time,s.timezone_name); qa:=coalesce(s.scoring_rules->>'test_mode'='true',false);
 select not exists(select 1 from public.quiz_duels where season_id=s.id and game_night=night and challenger_id=mid
 and (status in('accepted','playing','between') or started_at is not null)) into outgoing;
 select not exists(select 1 from public.quiz_duels where season_id=s.id and game_night=night and opponent_id=mid
 and (status in('accepted','playing','between') or started_at is not null)) into incoming;
 select coalesce(jsonb_agg(public._quiz_public(d,mid,at_time) order by d.created_at desc),'[]') into items from
 (select * from public.quiz_duels where season_id=s.id and mid in(challenger_id,opponent_id)
 order by (status in('invited','accepted','playing','between')) desc,created_at desc,id
 limit greatest(20,(select count(*) from public.quiz_duels
  where season_id=s.id and mid in(challenger_id,opponent_id)
  and status in('invited','accepted','playing','between')))) d;
 return jsonb_build_object('duels',items,'available_points',public._quiz_balance(s.id,account)-public._quiz_reserved(s.id,account),
 'outgoing',qa or outgoing,'incoming',qa or incoming,'test_mode',qa,'open',public._quiz_open(s,at_time),'server_now',at_time,'config',public._quiz_rules());
end $$;

commit;
