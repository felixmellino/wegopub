-- Time Duel invitation inbox, availability and atomic competing-invite cleanup.
-- Requires 017_time_duel.sql. Existing games and rewards are preserved.
begin;
create or replace function public.time_status(actor_player uuid,target_season uuid) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; mid uuid; night date; qa boolean; items jsonb; active_until timestamptz;
 at_time timestamptz:=statement_timestamp();
begin
 s:=public._time_season(actor_player,target_season);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 perform public._time_refresh(s,at_time);
 select id into mid from public.active_lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 night:=public._chug_night(at_time,s.timezone_name); qa:=coalesce(s.scoring_rules->'test_mode'='true'::jsonb,false);
 select coalesce(jsonb_agg(public._time_public(d,mid,at_time)
  order by (d.status in('invited','accepted','playing')) desc,d.created_at desc,d.id),'[]') into items
 from (select * from public.time_duels where season_id=s.id and mid in(challenger_id,opponent_id)
 and (status in('invited','accepted','playing') or id in
  (select id from public.time_duels where season_id=s.id and mid in(challenger_id,opponent_id)
   and status not in('invited','accepted','playing') order by created_at desc,id limit 20))) d;
 select max(boost_ends_at) into active_until from public.time_duels where season_id=s.id and mid in(challenger_id,opponent_id)
 and (winner_id=mid or status='draw') and finished_at<=at_time and boost_ends_at>at_time;
 return jsonb_build_object('duels',items,'boost_ends_at',active_until,'test_mode',qa,'open',public._quiz_open(s,at_time),
 'outgoing',not exists(select 1 from public.time_duels where season_id=s.id and
 (challenger_id=mid and status='invited' or mid in(challenger_id,opponent_id) and status in('accepted','playing')))
 and (qa or not exists(select 1 from public.time_duels where season_id=s.id and game_night=night and challenger_id=mid
 and (status in('accepted','playing') or started_at is not null))),
 'incoming',not exists(select 1 from public.time_duels where season_id=s.id
 and mid in(challenger_id,opponent_id) and status in('accepted','playing'))
 and (qa or not exists(select 1 from public.time_duels where season_id=s.id and game_night=night and opponent_id=mid
 and (status in('accepted','playing') or started_at is not null))));
end $$;
create or replace function public.invite_time_duel(actor_player uuid,target_season uuid,invitation_id uuid,opponent_member uuid)
returns jsonb language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; d public.time_duels%rowtype; cid uuid; at_time timestamptz:=statement_timestamp();
begin
 s:=public._time_season(actor_player,target_season);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text)); perform public._time_refresh(s,at_time);
 select id into cid from public.active_lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 select * into d from public.time_duels where id=invitation_id;
 if found then
  if d.challenger_id<>cid or d.season_id<>s.id or d.opponent_id<>opponent_member then raise exception 'permission_denied'; end if;
  return public._time_public(d,cid,at_time);
 end if;
 if not public._quiz_open(s,at_time) then raise exception 'scoring_closed'; end if;
 perform public._check_chug_pair(cid,opponent_member,s.lobby_id);
 d.id:=invitation_id; d.season_id:=s.id; d.challenger_id:=cid; d.opponent_id:=opponent_member;
 d.game_night:=public._chug_night(at_time,s.timezone_name); perform public._time_slots(d,s);
 perform public._quiz_busy(s.id,cid,opponent_member,d.id);
 if exists(select 1 from public.time_duels where season_id=s.id and status in('accepted','playing')
  and (challenger_id in(cid,opponent_member) or opponent_id in(cid,opponent_member))) then
  raise exception 'time_busy'; end if;
 if exists(select 1 from public.time_duels where season_id=s.id and challenger_id=cid and status='invited') then
  raise exception 'time_pending'; end if;
 insert into public.time_duels(id,season_id,challenger_id,opponent_id,game_night,created_at,expires_at,targets)
 values(d.id,s.id,cid,opponent_member,d.game_night,at_time,least(at_time+interval '10 minutes',public._quiz_end(s,at_time)),
 jsonb_build_array((5+public._focus_int(8))*1000,(5+public._focus_int(8))*1000,(5+public._focus_int(8))*1000)) returning * into d;
 return public._time_public(d,cid,at_time);
end $$;
create or replace function public.time_action(actor_player uuid,target_duel uuid,selected_action text,
 expected_round integer default null,elapsed integer default null) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; d public.time_duels%rowtype; mid uuid; r public.time_rounds%rowtype;
 at_time timestamptz:=statement_timestamp();
begin
 select * into d from public.time_duels where id=target_duel;
 if not found then raise exception 'permission_denied'; end if;
 s:=public._time_season(actor_player,d.season_id);
 select id into mid from public.active_lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 if mid not in(d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text)); perform public._time_refresh(s,at_time);
 select * into d from public.time_duels where id=target_duel;
 if d.status not in('invited','accepted','playing') then return public._time_public(d,mid,at_time); end if;
 if selected_action='accept' and mid=d.opponent_id and d.status='invited' then
  perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
  perform public._time_slots(d,s); perform public._quiz_busy(s.id,d.challenger_id,d.opponent_id,d.id);
  if exists(select 1 from public.time_duels where id<>d.id and season_id=s.id and status in('accepted','playing')
   and (challenger_id in(d.challenger_id,d.opponent_id) or opponent_id in(d.challenger_id,d.opponent_id))) then raise exception 'time_busy'; end if;
  -- Resolve competing invitations atomically with acceptance under the lobby lock.
  -- Outgoing invitations are cancelled; other incoming invitations are declined.
  update public.time_duels set status=case
   when challenger_id in(d.challenger_id,d.opponent_id) then 'cancelled' else 'declined' end,
   finished_at=at_time where season_id=s.id and id<>d.id and status='invited'
   and (challenger_id in(d.challenger_id,d.opponent_id) or opponent_id in(d.challenger_id,d.opponent_id));
  update public.time_duels set status='accepted',expires_at=least(at_time+interval '10 minutes',public._quiz_end(s,at_time)),
   deadline=at_time+interval '60 seconds' where id=d.id returning * into d;
  insert into public.time_rounds(duel_id,round_no,membership_id)
   select d.id,n,m from generate_series(0,2) n cross join unnest(array[d.challenger_id,d.opponent_id]) m;
 elsif selected_action='accept' and mid=d.opponent_id and d.status='accepted' then null;
 elsif selected_action='decline' and mid=d.opponent_id and d.status='invited' then
  update public.time_duels set status='declined',finished_at=at_time where id=d.id returning * into d;
 elsif selected_action='cancel' and d.started_at is null and (mid=d.challenger_id or d.status='accepted') then
  update public.time_duels set status='cancelled',finished_at=at_time where id=d.id returning * into d;
 elsif selected_action in('ready','start','stop','abandon') then
  if expected_round is distinct from d.round_no then return public._time_public(d,mid,at_time); end if;
  select * into r from public.time_rounds where duel_id=d.id and round_no=d.round_no and membership_id=mid;
  if not found then raise exception 'time_action'; end if;
  if r.abandoned or r.elapsed_ms is not null then return public._time_public(d,mid,at_time); end if;
  if selected_action='ready' and d.status='accepted' then
   update public.time_rounds set ready=true where duel_id=d.id and round_no=d.round_no and membership_id=mid;
   if (select count(*) from public.time_rounds where duel_id=d.id and round_no=d.round_no and ready)=2 then
    update public.time_duels set status='playing',started_at=coalesce(started_at,at_time),deadline=at_time+interval '60 seconds'
     where id=d.id returning * into d;
   end if;
  elsif selected_action='ready' and d.status='playing' then null;
  elsif selected_action='start' and d.status='playing' then
   update public.time_rounds set started_at=coalesce(started_at,at_time) where duel_id=d.id and round_no=d.round_no and membership_id=mid;
  elsif selected_action='stop' and d.status='playing' and r.started_at is not null then
   if elapsed is null or elapsed not between 0 and 30000 or elapsed>extract(epoch from at_time-r.started_at)*1000+2000 then
    raise exception 'time_evidence'; end if;
   update public.time_rounds set elapsed_ms=elapsed where duel_id=d.id and round_no=d.round_no and membership_id=mid;
  elsif selected_action='abandon' and d.status='playing' and r.started_at is not null then
   update public.time_rounds set abandoned=true where duel_id=d.id and round_no=d.round_no and membership_id=mid;
  else raise exception 'time_action'; end if;
  d:=public._time_tick(d.id,at_time);
 else raise exception 'time_action'; end if;
 return public._time_public(d,mid,at_time);
end $$;


revoke all on function public.time_status(uuid,uuid), public.invite_time_duel(uuid,uuid,uuid,uuid),
 public.time_action(uuid,uuid,text,integer,integer) from public,anon,authenticated;
grant execute on function public.time_status(uuid,uuid), public.invite_time_duel(uuid,uuid,uuid,uuid),
 public.time_action(uuid,uuid,text,integer,integer) to service_role;
notify pgrst,'reload schema';
commit;
