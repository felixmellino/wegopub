-- Time Duel. Requires 015, 016_quiz_duel and 016_leave_lobby.
-- Trusted Streamlit service only; timing evidence is honour based.
begin;
create table if not exists public.time_duels (
 id uuid primary key, season_id uuid not null references public.seasons(id),
 challenger_id uuid not null references public.lobby_memberships(id),
 opponent_id uuid not null references public.lobby_memberships(id), game_night date not null,
 status text not null default 'invited' check(status in('invited','accepted','playing','completed','draw','cancelled','declined','expired')),
 created_at timestamptz not null, expires_at timestamptz not null, started_at timestamptz,
 finished_at timestamptz, boost_ends_at timestamptz, winner_id uuid references public.lobby_memberships(id),
 round_no integer not null default 0 check(round_no between 0 and 2), deadline timestamptz,
 targets jsonb not null check(jsonb_array_length(targets)=3),
 check(challenger_id<>opponent_id), check(winner_id is null or winner_id in(challenger_id,opponent_id))
);
create index if not exists time_season on public.time_duels(season_id,created_at desc);
create unique index if not exists time_pending on public.time_duels(challenger_id,season_id) where status='invited';
create table if not exists public.time_rounds (
 duel_id uuid not null references public.time_duels(id), round_no integer not null check(round_no between 0 and 2),
 membership_id uuid not null references public.lobby_memberships(id), ready boolean not null default false,
 started_at timestamptz, elapsed_ms integer check(elapsed_ms between 0 and 30000), abandoned boolean not null default false,
 primary key(duel_id,round_no,membership_id), check(not(abandoned and elapsed_ms is not null))
);
alter table public.time_duels enable row level security;
alter table public.time_rounds enable row level security;
revoke all on public.time_duels,public.time_rounds from public,anon,authenticated;
grant all on public.time_duels,public.time_rounds to service_role;
alter table public.drink_entries add column if not exists time_duel_id uuid references public.time_duels(id);
alter table public.drink_entries add column if not exists time_bonus numeric not null default 0 check(time_bonus>=0);

create or replace function public._time_rules() returns jsonb language sql immutable as $$
 select '{"version":1,"rounds":3,"min_seconds":5,"max_seconds":12,"ready_seconds":60,
 "timer_seconds":30,"invitation_seconds":600,"boost_seconds":3600,"multiplier":1.25}'::jsonb
$$;
create or replace function public._time_season(actor_player uuid,target_season uuid)
returns public.seasons language plpgsql set search_path=public as $$
declare s public.seasons%rowtype;
begin
 select * into s from public.seasons where id=target_season;
 if not found then raise exception 'permission_denied'; end if;
 perform public._require_active_lobby(actor_player,s.lobby_id);
 if s.scoring_version<>'v1' then raise exception 'scoring_closed'; end if;
 return s;
end $$;
create or replace function public._time_slots(d public.time_duels,s public.seasons) returns void
language plpgsql set search_path=public as $$
begin
 if s.scoring_rules->'test_mode'='true'::jsonb then return; end if;
 if exists(select 1 from public.time_duels where season_id=s.id and id<>d.id and game_night=d.game_night
 and (status in('accepted','playing') or started_at is not null)
 and (challenger_id=d.challenger_id or opponent_id=d.opponent_id)) then raise exception 'time_limit'; end if;
end $$;
create or replace function public._time_tick(target_duel uuid,at_time timestamptz)
returns public.time_duels language plpgsql set search_path=public as $$
declare d public.time_duels%rowtype; s public.seasons%rowtype; af integer; bf integer; ae bigint; be bigint;
begin
 select * into d from public.time_duels where id=target_duel for update;
 if d.status not in('invited','accepted','playing') then return d; end if;
 if at_time>=d.expires_at then
  update public.time_duels set status='expired',finished_at=d.expires_at where id=d.id returning * into d;
  return d;
 end if;
 if d.status='invited' then return d; end if;
 -- A running timer has 30 seconds; a whole ready/play phase has 60.
 update public.time_rounds set abandoned=true where duel_id=d.id and round_no=d.round_no
 and elapsed_ms is null and not abandoned and
 (at_time>=d.deadline or (started_at is not null and at_time>=started_at+interval '30 seconds'));
 if (select count(*) from public.time_rounds where duel_id=d.id and round_no=d.round_no
     and (elapsed_ms is not null or abandoned))<2 then return d; end if;
 if d.round_no<2 then
  update public.time_duels set status='accepted',round_no=round_no+1,deadline=at_time+interval '60 seconds'
   where id=d.id returning * into d;
 else
  select count(*) filter(where abandoned),coalesce(sum(abs(elapsed_ms-(d.targets->>round_no)::integer)),0)
   into af,ae from public.time_rounds where duel_id=d.id and membership_id=d.challenger_id;
  select count(*) filter(where abandoned),coalesce(sum(abs(elapsed_ms-(d.targets->>round_no)::integer)),0)
   into bf,be from public.time_rounds where duel_id=d.id and membership_id=d.opponent_id;
  select * into s from public.seasons where id=d.season_id;
  update public.time_duels set status=case when (af,ae)=(bf,be) then 'draw' else 'completed' end,
   winner_id=case when (af,ae)<(bf,be) then d.challenger_id when (bf,be)<(af,ae) then d.opponent_id end,
   finished_at=at_time,
   boost_ends_at=case when (af,ae)<>(bf,be) or af=0 then
    least(at_time+interval '1 hour',public._focus_window_end(s,at_time)) end
   where id=d.id returning * into d;
 end if;
 return d;
end $$;
create or replace function public._time_refresh(s public.seasons,at_time timestamptz) returns void
language plpgsql set search_path=public as $$
declare did uuid;
begin
 perform public._quiz_refresh(s,at_time);
 for did in select id from public.time_duels where season_id=s.id and status in('invited','accepted','playing')
  order by created_at,id loop perform public._time_tick(did,at_time); end loop;
end $$;
create or replace function public._time_public(d public.time_duels,viewer uuid,at_time timestamptz)
returns jsonb language sql stable set search_path=public as $$
 select (to_jsonb(d)-'targets')||jsonb_build_object('server_now',at_time,'config',public._time_rules(),
 'target_ms',case when d.status<>'invited' and (d.status<>'accepted' or
   exists(select 1 from public.time_rounds where duel_id=d.id and round_no=d.round_no and started_at is not null))
   then d.targets->d.round_no end,
 'rounds',coalesce((select jsonb_agg(jsonb_build_object('round_no',r.round_no,'membership_id',r.membership_id,
 'ready',r.ready,'started',r.started_at is not null,'abandoned',r.abandoned,
 'elapsed_ms',case when r.membership_id=viewer or r.round_no<d.round_no or d.status in('completed','draw','expired')
 or exists(select 1 from public.time_rounds own where own.duel_id=d.id and own.round_no=r.round_no
 and own.membership_id=viewer and own.started_at is not null) then r.elapsed_ms end,
 'target_ms',case when r.round_no<d.round_no or d.status in('completed','draw','expired') then d.targets->r.round_no end)
 order by r.round_no,r.membership_id) from public.time_rounds r where r.duel_id=d.id and r.round_no<=d.round_no),'[]'))
$$;
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
 select coalesce(jsonb_agg(public._time_public(d,mid,at_time) order by d.created_at desc),'[]') into items
 from (select * from public.time_duels where season_id=s.id and mid in(challenger_id,opponent_id)
 order by (status in('invited','accepted','playing')) desc,created_at desc,id limit 20) d;
 select max(boost_ends_at) into active_until from public.time_duels where season_id=s.id and mid in(challenger_id,opponent_id)
 and (winner_id=mid or status='draw') and finished_at<=at_time and boost_ends_at>at_time;
 return jsonb_build_object('duels',items,'boost_ends_at',active_until,'test_mode',qa,'open',public._quiz_open(s,at_time),
 'outgoing',qa or not exists(select 1 from public.time_duels where season_id=s.id and game_night=night and challenger_id=mid
 and (status in('accepted','playing') or started_at is not null)),
 'incoming',qa or not exists(select 1 from public.time_duels where season_id=s.id and game_night=night and opponent_id=mid
 and (status in('accepted','playing') or started_at is not null)));
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
  if d.challenger_id<>cid or d.season_id<>s.id then raise exception 'permission_denied'; end if;
  return public._time_public(d,cid,at_time);
 end if;
 if not public._quiz_open(s,at_time) then raise exception 'scoring_closed'; end if;
 perform public._check_chug_pair(cid,opponent_member,s.lobby_id);
 d.id:=invitation_id; d.season_id:=s.id; d.challenger_id:=cid; d.opponent_id:=opponent_member;
 d.game_night:=public._chug_night(at_time,s.timezone_name); perform public._time_slots(d,s);
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

-- Symmetric shared-game and membership guards, serialized by the lobby lock.
create or replace function public._time_guard() returns trigger language plpgsql set search_path=public as $$
declare cid uuid; oid uuid; sid uuid; lid uuid; s public.seasons%rowtype; now_at timestamptz:=statement_timestamp();
begin
 if tg_table_name='lobby_memberships' then
  if new.team_id is not distinct from old.team_id and new.left_at is not distinct from old.left_at then return new; end if;
  cid:=old.id;oid:=old.id;lid:=old.lobby_id;
 else
  sid:=new.season_id;
  if tg_table_name='focus_attempts' then
   if new.status<>'running' then return new; end if;
   cid:=new.membership_id;oid:=cid;
  else
   if new.status not in('accepted','started','playing','between') then return new; end if;
   cid:=new.challenger_id;oid:=new.opponent_id;
  end if;
  select lobby_id into lid from public.seasons where id=sid;
 end if;
 perform pg_advisory_xact_lock(hashtext(lid::text));
 for s in select * from public.seasons where lobby_id=lid loop
  perform public._time_tick(d.id,now_at) from public.time_duels d
   where d.season_id=s.id and d.status in('invited','accepted','playing');
 end loop;
 if exists(select 1 from public.time_duels d join public.seasons season on season.id=d.season_id where season.lobby_id=lid
 and d.status in('accepted','playing') and (d.challenger_id in(cid,oid) or d.opponent_id in(cid,oid))) then
  raise exception 'time_busy'; end if;
 return new;
end $$;
drop trigger if exists time_busy_chug on public.chug_duels;
create trigger time_busy_chug before insert or update of status on public.chug_duels for each row execute function public._time_guard();
drop trigger if exists time_busy_focus on public.focus_attempts;
create trigger time_busy_focus before insert on public.focus_attempts for each row execute function public._time_guard();
drop trigger if exists time_busy_quiz on public.quiz_duels;
create trigger time_busy_quiz before insert or update of status on public.quiz_duels for each row execute function public._time_guard();
drop trigger if exists time_membership on public.lobby_memberships;
create trigger time_membership before update on public.lobby_memberships for each row execute function public._time_guard();

-- Preserve provenance at receipt, never at replay/correction time.
create or replace function public._snapshot_time_boost() returns trigger language plpgsql set search_path=public as $$
begin
 if tg_op='UPDATE' then
  if new.time_duel_id is distinct from old.time_duel_id then raise exception 'entry_identity_frozen'; end if;
  return new;
 end if;
 new.time_duel_id:=null;new.time_bonus:=0;
 if new.rule_version='v1' and not exists(select 1 from public.chug_duels
  where challenger_entry_id=new.id or opponent_entry_id=new.id) then
  select id into new.time_duel_id from public.time_duels where season_id=new.season_id
  and new.membership_id in(challenger_id,opponent_id) and (winner_id=new.membership_id or status='draw')
  and finished_at<=new.submitted_at and new.submitted_at<boost_ends_at order by finished_at desc,id limit 1;
 end if;
 return new;
end $$;
drop trigger if exists snapshot_time_boost on public.drink_entries;
create trigger snapshot_time_boost before insert or update on public.drink_entries for each row execute function public._snapshot_time_boost();

create or replace function public._replay_scoring_season(target_season uuid)
returns void language plpgsql set search_path = public as $$
declare
  entry public.drink_entries%rowtype; rules jsonb;
  totals jsonb := '{}'; owners jsonb := '{}';
  territory text; member text; prior_owner text; points numeric; new_total numeric;
begin
  select scoring_rules into rules from public.seasons where id = target_season and scoring_version = 'v1';
  if rules is null then raise exception 'scoring_setup_required'; end if;
  for entry in select * from public.drink_entries where season_id = target_season order by event_order loop
    points := public._scoring_points(rules, entry.drink_type, entry.size) * case when entry.focus_attempt_id is not null then 1.5 else 1 end;
    territory := case when entry.location_check_result = 'matched' then entry.territory_id else null end;
    member := coalesce(entry.team_id,entry.membership_id)::text;
    prior_owner := case when territory is not null then owners ->> territory else null end;
    update public.drink_entries set points_awarded = points,
      time_bonus = case when entry.time_duel_id is not null and entry.focus_attempt_id is null
        then public._scoring_points(rules,entry.drink_type,entry.size)*0.25 else 0 end,
      owner_membership_id = case when entry.team_id is null and prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then prior_owner::uuid else null end,
      owner_team_id = case when entry.team_id is not null and prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then prior_owner::uuid else null end,
      owner_bonus_quarters = case when prior_owner is not null and prior_owner <> member
        and (entry.team_id is not null or not (prior_owner::uuid = any(entry.absent_member_ids))) then points else 0 end
      where id = entry.id;
    if territory is not null then
      new_total := coalesce((totals -> territory ->> member)::numeric, 0) + points;
      totals := jsonb_set(totals, array[territory],
        coalesce(totals -> territory, '{}'::jsonb) || jsonb_build_object(member,new_total),true);
      if prior_owner is null or new_total > (totals -> territory ->> prior_owner)::numeric then
        owners := owners || jsonb_build_object(territory,member);
      end if;
    end if;
  end loop;
end $$;
create or replace function public._quiz_balance(sid uuid,account uuid) returns numeric
language sql stable set search_path=public as $$
 select coalesce((select sum(points_awarded+time_bonus) from public.drink_entries where season_id=sid
 and coalesce(team_id,membership_id)=account and location_check_result in('matched','outside')),0)
 +coalesce((select sum(owner_bonus_quarters)/4 from public.drink_entries where season_id=sid
 and coalesce(owner_team_id,owner_membership_id)=account),0)
 +coalesce((select sum(case when duel_transfer_to=account then points_awarded else 0 end
 -case when coalesce(team_id,membership_id)=account then points_awarded else 0 end)
 from public.drink_entries where season_id=sid and duel_transfer_to is not null),0)
 +coalesce((select sum(case when target_id=account then points else 0 end
 -case when source_id=account then points else 0 end) from public.quiz_transfers where season_id=sid),0)
$$;

-- RPCs run as the existing trusted service role; no browser role has access.
do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace
 and (proname like '\_time\_%' escape '\' or proname in('time_status','invite_time_duel','time_action','_snapshot_time_boost')) loop
  execute format('revoke all on function %s from public,anon,authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;
notify pgrst,'reload schema';
commit;
