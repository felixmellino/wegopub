-- Quiz Duel. Requires migrations through 014; compatible with 015 QA Focus.
-- Trusted Streamlit service only. Never expose the service key to the browser.
begin;
create table if not exists public.quiz_duels (
 id uuid primary key, season_id uuid not null references public.seasons(id),
 challenger_id uuid not null references public.lobby_memberships(id),
 opponent_id uuid not null references public.lobby_memberships(id), game_night date not null,
 stake integer not null check(stake between 3 and 10),
 status text not null default 'invited' check(status in
 ('invited','accepted','playing','between','completed','forfeited','draw','declined','cancelled','expired')),
 created_at timestamptz not null, expires_at timestamptz not null,
 accepted_at timestamptz, started_at timestamptz, finished_at timestamptz,
 challenger_account uuid, opponent_account uuid,
 challenger_ready boolean not null default false, opponent_ready boolean not null default false,
 round_no integer not null default 0 check(round_no between 0 and 5),
 challenger_score integer not null default 0, opponent_score integer not null default 0,
 round_starts_at timestamptz, deadline timestamptz, next_round_at timestamptz,
 winner_id uuid references public.lobby_memberships(id), reason text,
 questions jsonb not null, round_results jsonb not null default '[]',
 check(challenger_id<>opponent_id),
 check(winner_id is null or winner_id in(challenger_id,opponent_id)),
 check(status not in('completed','forfeited') or winner_id is not null)
);
create index if not exists quiz_season on public.quiz_duels(season_id,created_at desc);
create unique index if not exists quiz_pending on public.quiz_duels(challenger_id,season_id) where status='invited';
create table if not exists public.quiz_answers (
 duel_id uuid not null references public.quiz_duels(id), round_no integer not null check(round_no between 0 and 5),
 membership_id uuid not null references public.lobby_memberships(id),
 choice integer not null check(choice between 0 and 3), received_at timestamptz not null,
 primary key(duel_id,round_no,membership_id)
);
create table if not exists public.quiz_transfers (
 id uuid primary key references public.quiz_duels(id), season_id uuid not null references public.seasons(id),
 source_id uuid not null, target_id uuid not null,
 source_membership_id uuid not null references public.lobby_memberships(id),
 target_membership_id uuid not null references public.lobby_memberships(id),
 points integer not null check(points between 3 and 10),
 event_order bigint not null default nextval('public.drink_entries_event_order_seq'),
 created_at timestamptz not null, check(source_id<>target_id)
);
create index if not exists quiz_transfer_season on public.quiz_transfers(season_id,event_order);
alter table public.quiz_duels enable row level security;
alter table public.quiz_answers enable row level security;
alter table public.quiz_transfers enable row level security;
revoke all on public.quiz_duels,public.quiz_answers,public.quiz_transfers from public,anon,authenticated;
grant all on public.quiz_duels,public.quiz_answers,public.quiz_transfers to service_role;

create or replace function public._quiz_rules() returns jsonb language sql immutable as $$
 select '{"version":1,"min_stake":3,"max_stake":10,"round_seconds":20,"countdown_seconds":3,
 "result_seconds":3,"invitation_seconds":600,"setup_seconds":600,"game_seconds":600,"max_deciders":3}'::jsonb
$$;
create or replace function public._quiz_season(actor_player uuid,target_season uuid)
returns public.seasons language plpgsql set search_path=public as $$
declare s public.seasons%rowtype;
begin
 select season.* into s from public.seasons season join public.lobby_memberships m on m.lobby_id=season.lobby_id
 where season.id=target_season and m.player_id=actor_player;
 if not found then raise exception 'permission_denied'; end if;
 if s.scoring_version<>'v1' then raise exception 'scoring_closed'; end if;
 return s;
end $$;
create or replace function public._quiz_end(s public.seasons,at_time timestamptz)
returns timestamptz language sql stable set search_path=public as $$
 select least(s.ends_at,((public._chug_night(at_time,s.timezone_name)+1)::timestamp+interval '6 hours')
 at time zone s.timezone_name,case when s.scoring_rules->>'test_mode'='true' then s.ends_at
 else public._focus_window_end(s,at_time) end)
$$;
create or replace function public._quiz_open(s public.seasons,at_time timestamptz)
returns boolean language sql stable set search_path=public as $$
 select at_time>=s.starts_at and at_time<s.ends_at and
 (coalesce(s.scoring_rules->>'test_mode'='true',false) or public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules))
$$;
create or replace function public._quiz_balance(sid uuid,account uuid) returns numeric
language sql stable set search_path=public as $$
 select coalesce((select sum(points_awarded) from public.drink_entries where season_id=sid
 and coalesce(team_id,membership_id)=account and location_check_result in('matched','outside')),0)
 +coalesce((select sum(owner_bonus_quarters)/4 from public.drink_entries where season_id=sid
 and coalesce(owner_team_id,owner_membership_id)=account),0)
 +coalesce((select sum(case when duel_transfer_to=account then points_awarded else 0 end
 -case when coalesce(team_id,membership_id)=account then points_awarded else 0 end)
 from public.drink_entries where season_id=sid and duel_transfer_to is not null),0)
 +coalesce((select sum(case when target_id=account then points else 0 end
 -case when source_id=account then points else 0 end) from public.quiz_transfers where season_id=sid),0)
$$;
create or replace function public._quiz_reserved(sid uuid,account uuid) returns numeric
language sql stable set search_path=public as $$
 select coalesce(sum(stake),0) from public.quiz_duels where season_id=sid
 and status in('accepted','playing','between') and account in(challenger_account,opponent_account)
$$;
create or replace function public._quiz_slots(d public.quiz_duels,s public.seasons)
returns void language plpgsql set search_path=public as $$
begin
 if coalesce(s.scoring_rules->>'test_mode'='true',false) then return; end if;
 if exists(select 1 from public.quiz_duels where season_id=s.id and id<>d.id and game_night=d.game_night
 and (status in('accepted','playing','between') or started_at is not null)
 and (challenger_id=d.challenger_id or opponent_id=d.opponent_id)) then raise exception 'quiz_limit'; end if;
end $$;
create or replace function public._quiz_busy(sid uuid,cid uuid,oid uuid,except_id uuid)
returns void language plpgsql set search_path=public as $$
begin
 if exists(select 1 from public.quiz_duels where season_id=sid and id<>except_id
 and status in('accepted','playing','between') and (challenger_id in(cid,oid) or opponent_id in(cid,oid)))
 or exists(select 1 from public.chug_duels where season_id=sid and status in('accepted','started')
 and (challenger_id in(cid,oid) or opponent_id in(cid,oid)))
 or exists(select 1 from public.focus_attempts where season_id=sid and membership_id in(cid,oid)
 and status='running' and expires_at>statement_timestamp() and deadline+interval '2 seconds'>statement_timestamp())
 then raise exception 'quiz_busy'; end if;
end $$;
create or replace function public._quiz_settle(d public.quiz_duels,winner uuid,new_status text,at_time timestamptz,why text)
returns public.quiz_duels language plpgsql set search_path=public as $$
begin
 update public.quiz_duels set status=new_status,winner_id=winner,finished_at=at_time,reason=why where id=d.id returning * into d;
 if winner is not null then
  insert into public.quiz_transfers(id,season_id,source_id,target_id,source_membership_id,target_membership_id,points,created_at)
  values(d.id,d.season_id,case when winner=d.challenger_id then d.opponent_account else d.challenger_account end,
  case when winner=d.challenger_id then d.challenger_account else d.opponent_account end,
  case when winner=d.challenger_id then d.opponent_id else d.challenger_id end,winner,d.stake,at_time)
  on conflict(id) do nothing;
 end if;
 return d;
end $$;
create or replace function public._quiz_tick(target_duel uuid,at_time timestamptz)
returns public.quiz_duels language plpgsql set search_path=public as $$
declare d public.quiz_duels%rowtype; a public.quiz_answers%rowtype; b public.quiz_answers%rowtype;
 correct integer; winner uuid; resolved_at timestamptz; effective_now timestamptz; i integer; result jsonb;
begin
 select * into d from public.quiz_duels where id=target_duel for update;
 effective_now:=least(at_time,d.expires_at);
 for i in 1..14 loop
  if d.status='playing' then
   select * into a from public.quiz_answers where duel_id=d.id and round_no=d.round_no and membership_id=d.challenger_id;
   select * into b from public.quiz_answers where duel_id=d.id and round_no=d.round_no and membership_id=d.opponent_id;
   if (a.membership_id is null or b.membership_id is null) and effective_now<d.deadline then exit; end if;
   -- At a hard boundary an incomplete question is void, rather than shortened.
   if d.deadline>d.expires_at and (a.membership_id is null or b.membership_id is null) then exit; end if;
   resolved_at:=case when a.membership_id is not null and b.membership_id is not null
    then greatest(a.received_at,b.received_at) else d.deadline end;
   correct:=(d.questions->d.round_no->>'correct_index')::integer; winner:=null;
   if a.choice=correct and (b.choice is distinct from correct or a.received_at<b.received_at) then winner:=d.challenger_id;
   elsif b.choice=correct and (a.choice is distinct from correct or b.received_at<a.received_at) then winner:=d.opponent_id; end if;
   d.challenger_score:=d.challenger_score+case when winner=d.challenger_id then 1 else 0 end;
   d.opponent_score:=d.opponent_score+case when winner=d.opponent_id then 1 else 0 end;
   result:=jsonb_build_object('round_no',d.round_no,'winner_id',winner,'correct_index',correct,
    'explanation',d.questions->d.round_no->>'explanation','question',d.questions->d.round_no->>'question',
    'options',d.questions->d.round_no->'options','challenger_choice',a.choice,'opponent_choice',b.choice);
   update public.quiz_duels set challenger_score=d.challenger_score,opponent_score=d.opponent_score,
    round_results=round_results||jsonb_build_array(result) where id=d.id returning * into d;
   if (d.round_no>=2 or greatest(d.challenger_score,d.opponent_score)=2) and d.challenger_score<>d.opponent_score then
    return public._quiz_settle(d,case when d.challenger_score>d.opponent_score then d.challenger_id else d.opponent_id end,
     'completed',resolved_at,'rounds');
   elsif d.round_no=5 then return public._quiz_settle(d,null,'draw',resolved_at,'decider_limit'); end if;
   update public.quiz_duels set status='between',next_round_at=resolved_at+interval '3 seconds' where id=d.id returning * into d;
  elsif d.status='between' and effective_now>=d.next_round_at then
   update public.quiz_duels set status='playing',round_no=round_no+1,
    round_starts_at=next_round_at+interval '3 seconds',deadline=next_round_at+interval '23 seconds',next_round_at=null
    where id=d.id returning * into d;
  else exit;
  end if;
 end loop;
 if at_time>=d.expires_at and d.status in('invited','accepted','playing','between') then
  return public._quiz_settle(d,null,case when d.started_at is not null then 'draw' else 'expired' end,d.expires_at,'timeout');
 end if;
 return d;
end $$;
create or replace function public._quiz_refresh(s public.seasons,at_time timestamptz) returns void
language plpgsql set search_path=public as $$
declare duel uuid;
begin
 perform public._expire_chug_duels(s.lobby_id,at_time);
 for duel in select id from public.quiz_duels where season_id=s.id and status in('invited','accepted','playing','between') order by created_at,id loop
  perform public._quiz_tick(duel,at_time);
 end loop;
end $$;
create or replace function public._quiz_public(d public.quiz_duels,viewer uuid,at_time timestamptz)
returns jsonb language sql stable set search_path=public as $$
 select (to_jsonb(d)-'questions'-'challenger_account'-'opponent_account')
 ||jsonb_build_object('server_now',at_time,'config',public._quiz_rules(),
 'answered',exists(select 1 from public.quiz_answers where duel_id=d.id and round_no=d.round_no and membership_id=viewer),
 'other_answered',exists(select 1 from public.quiz_answers where duel_id=d.id and round_no=d.round_no and membership_id<>viewer),
 'question',case when d.status='playing' then jsonb_build_object('id',d.questions->d.round_no->>'id',
 'category',d.questions->d.round_no->>'category','question',d.questions->d.round_no->>'question',
 'options',d.questions->d.round_no->'options') else null end)
$$;
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
 order by (status in('invited','accepted','playing','between')) desc,created_at desc limit 20) d;
 return jsonb_build_object('duels',items,'available_points',public._quiz_balance(s.id,account)-public._quiz_reserved(s.id,account),
 'outgoing',qa or outgoing,'incoming',qa or incoming,'test_mode',qa,'open',public._quiz_open(s,at_time),'server_now',at_time,'config',public._quiz_rules());
end $$;
create or replace function public.invite_quiz_duel(actor_player uuid,target_season uuid,invitation_id uuid,
 opponent_member uuid,selected_stake integer,private_questions jsonb) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; d public.quiz_duels%rowtype; cid uuid; ca uuid; oa uuid; item jsonb; i integer:=0;
 at_time timestamptz:=statement_timestamp();
begin
 s:=public._quiz_season(actor_player,target_season);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 perform public._quiz_refresh(s,at_time);
 select id,coalesce(team_id,id) into cid,ca from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 select * into d from public.quiz_duels where id=invitation_id;
 if found then
  if d.challenger_id<>cid or d.season_id<>s.id then raise exception 'permission_denied'; end if;
  return public._quiz_public(d,cid,at_time);
 end if;
 if not public._quiz_open(s,at_time) then raise exception 'scoring_closed'; end if;
 if selected_stake is null or selected_stake not between 3 and 10 then raise exception 'quiz_stake'; end if;
 begin perform public._check_chug_pair(cid,opponent_member,s.lobby_id);
 exception when raise_exception then if sqlerrm='duel_team' then raise exception 'quiz_team'; else raise; end if; end;
 select coalesce(team_id,id) into oa from public.lobby_memberships where id=opponent_member;
 d.id:=invitation_id;d.season_id:=s.id;d.challenger_id:=cid;d.opponent_id:=opponent_member;d.game_night:=public._chug_night(at_time,s.timezone_name);
 perform public._quiz_slots(d,s);
 if exists(select 1 from public.quiz_duels where challenger_id=cid and season_id=s.id and status='invited') then raise exception 'quiz_pending'; end if;
 if public._quiz_balance(s.id,ca)-public._quiz_reserved(s.id,ca)<selected_stake
 or public._quiz_balance(s.id,oa)-public._quiz_reserved(s.id,oa)<selected_stake then raise exception 'quiz_funds'; end if;
 if jsonb_typeof(private_questions) is distinct from 'array' or jsonb_array_length(private_questions)<>6
 or octet_length(private_questions::text)>30000 then raise exception 'quiz_questions'; end if;
 for item in select value from jsonb_array_elements(private_questions) loop
  if item->>'schema_version' is distinct from '1' or jsonb_typeof(item->'correct_index') is distinct from 'number'
  or item->>'correct_index' not in('0','1','2','3') or jsonb_typeof(item->'options') is distinct from 'array'
  or jsonb_array_length(item->'options')<>4 or length(coalesce(item->>'question','')) not between 1 and 650
  or length(coalesce(item->>'explanation','')) not between 1 and 650
  or item->>'category' is distinct from (case i when 1 then 'math' when 2 then 'logic' else 'general' end)
  or (select count(distinct lower(btrim(value#>>'{}'))) from jsonb_array_elements(item->'options')
   where jsonb_typeof(value)='string' and length(btrim(value#>>'{}')) between 1 and 160)<>4
  then raise exception 'quiz_questions'; end if; i:=i+1;
 end loop;
 if (select count(distinct value->>'id') from jsonb_array_elements(private_questions))<>6 then raise exception 'quiz_questions'; end if;
 insert into public.quiz_duels(id,season_id,challenger_id,opponent_id,game_night,stake,created_at,expires_at,questions)
 values(d.id,s.id,cid,opponent_member,d.game_night,selected_stake,at_time,least(at_time+interval '10 minutes',public._quiz_end(s,at_time)),private_questions)
 returning * into d;
 return public._quiz_public(d,cid,at_time);
end $$;
create or replace function public.quiz_action(actor_player uuid,target_duel uuid,selected_action text,
 expected_round integer default null,selected_choice integer default null) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; d public.quiz_duels%rowtype; mid uuid; ca uuid; oa uuid; old_choice integer;
 at_time timestamptz:=statement_timestamp();
begin
 select * into d from public.quiz_duels where id=target_duel;
 if not found then raise exception 'permission_denied'; end if;
 s:=public._quiz_season(actor_player,d.season_id);
 select id into mid from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 if mid not in(d.challenger_id,d.opponent_id) then raise exception 'permission_denied'; end if;
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 perform public._quiz_refresh(s,at_time);
 select * into d from public.quiz_duels where id=target_duel;
 if d.status not in('invited','accepted','playing','between') then return public._quiz_public(d,mid,at_time); end if;
 if selected_action='accept' and mid=d.opponent_id and d.status='invited' then
  begin perform public._check_chug_pair(d.challenger_id,d.opponent_id,s.lobby_id);
  exception when raise_exception then if sqlerrm='duel_team' then raise exception 'quiz_team'; else raise; end if; end;
  perform public._quiz_slots(d,s); perform public._quiz_busy(s.id,d.challenger_id,d.opponent_id,d.id);
  select coalesce(team_id,id) into ca from public.lobby_memberships where id=d.challenger_id;
  select coalesce(team_id,id) into oa from public.lobby_memberships where id=d.opponent_id;
  if public._quiz_balance(s.id,ca)-public._quiz_reserved(s.id,ca)<d.stake
   or public._quiz_balance(s.id,oa)-public._quiz_reserved(s.id,oa)<d.stake then raise exception 'quiz_funds'; end if;
  update public.quiz_duels set status='accepted',accepted_at=at_time,challenger_account=ca,opponent_account=oa,
   expires_at=least(at_time+interval '10 minutes',public._quiz_end(s,at_time)) where id=d.id returning * into d;
 elsif selected_action='decline' and mid=d.opponent_id and d.status='invited' then
  d:=public._quiz_settle(d,null,'declined',at_time,'declined');
 elsif selected_action='cancel' and d.started_at is null and (mid=d.challenger_id or d.status='accepted') then
  d:=public._quiz_settle(d,null,'cancelled',at_time,'cancelled');
 elsif selected_action='ready' and d.status='accepted' then
  update public.quiz_duels set challenger_ready=challenger_ready or mid=challenger_id,
   opponent_ready=opponent_ready or mid=opponent_id where id=d.id returning * into d;
  if d.challenger_ready and d.opponent_ready then
   update public.quiz_duels set status='playing',started_at=at_time,round_starts_at=at_time+interval '3 seconds',
    deadline=at_time+interval '23 seconds',expires_at=least(at_time+interval '10 minutes',public._quiz_end(s,at_time))
    where id=d.id returning * into d;
  end if;
 elsif selected_action='answer' then
  -- Retries after a round transition never become an answer to the next question.
  if expected_round is null or expected_round<>d.round_no or d.status<>'playing' then return public._quiz_public(d,mid,at_time); end if;
  if selected_choice is null or selected_choice not between 0 and 3 then raise exception 'quiz_invalid_answer'; end if;
  if at_time<d.round_starts_at then raise exception 'quiz_early'; end if;
  select choice into old_choice from public.quiz_answers where duel_id=d.id and round_no=d.round_no and membership_id=mid;
  if found then
   if old_choice<>selected_choice then raise exception 'quiz_answer_locked'; end if;
  else
   insert into public.quiz_answers values(d.id,d.round_no,mid,selected_choice,at_time);
  end if;
  d:=public._quiz_tick(d.id,at_time);
 elsif selected_action='forfeit' and d.started_at is not null then
  d:=public._quiz_settle(d,case when mid=d.challenger_id then d.opponent_id else d.challenger_id end,'forfeited',at_time,'forfeit');
 elsif selected_action='accept' and d.status='accepted' and mid=d.opponent_id then null;
 elsif selected_action='ready' and d.started_at is not null then null;
 else raise exception 'quiz_unavailable'; end if;
 return public._quiz_public(d,mid,at_time);
end $$;

-- Corrections and Chug transfers must not spend committed/already-transferred points.
-- Deferred checks run after the scoring replay has recalculated every owner's income.
create or replace function public._quiz_check_account(sid uuid,account uuid) returns void
language plpgsql set search_path=public as $$
begin
 if account is null then return; end if;
 if exists(select 1 from public.quiz_duels where season_id=sid and status in('accepted','playing','between')
  and account in(challenger_account,opponent_account)) or exists(select 1 from public.quiz_transfers
  where season_id=sid and account in(source_id,target_id)) then
  if public._quiz_balance(sid,account)<public._quiz_reserved(sid,account) then raise exception 'quiz_reserved_points'; end if;
 end if;
end $$;
create or replace function public._quiz_guard_balance() returns trigger language plpgsql set search_path=public as $$
declare row_data jsonb; sid uuid; account uuid; lid uuid; s public.seasons%rowtype;
begin
 for row_data in select to_jsonb(new) where tg_op<>'DELETE' union all select to_jsonb(old) where tg_op<>'INSERT' loop
  sid:=(row_data->>'season_id')::uuid; select lobby_id into lid from public.seasons where id=sid;
  perform pg_advisory_xact_lock(hashtext(lid::text));
  -- A scoring correction can be the first activity after a game expired.
  -- Resolve it before checking its hold, just as the quiz RPCs do.
  if exists(select 1 from public.quiz_duels where season_id=sid
   and status in('invited','accepted','playing','between') and expires_at<=statement_timestamp()) then
   select * into s from public.seasons where id=sid;
   perform public._quiz_refresh(s,statement_timestamp());
  end if;
  for account in select distinct value::uuid from unnest(array[
   coalesce(row_data->>'team_id',row_data->>'membership_id'),coalesce(row_data->>'owner_team_id',row_data->>'owner_membership_id'),
   row_data->>'duel_transfer_to',row_data->>'source_id',row_data->>'target_id']) value where value is not null loop
   perform public._quiz_check_account(sid,account);
  end loop;
 end loop;
 return null;
end $$;
drop trigger if exists quiz_balance_drinks on public.drink_entries;
create constraint trigger quiz_balance_drinks after insert or update or delete on public.drink_entries
 deferrable initially deferred for each row execute function public._quiz_guard_balance();
drop trigger if exists quiz_balance_transfers on public.quiz_transfers;
create constraint trigger quiz_balance_transfers after insert or update or delete on public.quiz_transfers
 deferrable initially deferred for each row execute function public._quiz_guard_balance();

create or replace function public._quiz_guard_other_games() returns trigger language plpgsql set search_path=public as $$
declare cid uuid; oid uuid; lid uuid; now_at timestamptz:=statement_timestamp();
begin
 if tg_table_name='chug_duels' then
  if new.status not in('accepted','started') then return new; end if;
  cid:=new.challenger_id;oid:=new.opponent_id;
 else
  if new.status<>'running' then return new; end if;
  cid:=new.membership_id;oid:=cid;
 end if;
 select lobby_id into lid from public.seasons where id=new.season_id;
 perform pg_advisory_xact_lock(hashtext(lid::text));
 if exists(select 1 from public.quiz_duels where season_id=new.season_id and status in('accepted','playing','between')
  and expires_at>now_at and (challenger_id in(cid,oid) or opponent_id in(cid,oid))) then raise exception 'quiz_busy'; end if;
 return new;
end $$;
drop trigger if exists quiz_busy_chug on public.chug_duels;
create trigger quiz_busy_chug before insert or update on public.chug_duels for each row execute function public._quiz_guard_other_games();
drop trigger if exists quiz_busy_focus on public.focus_attempts;
create trigger quiz_busy_focus before insert on public.focus_attempts for each row execute function public._quiz_guard_other_games();
create or replace function public._quiz_guard_team() returns trigger language plpgsql set search_path=public as $$
begin
 if tg_op='UPDATE' and new.team_id is not distinct from old.team_id then return new; end if;
 perform pg_advisory_xact_lock(hashtext(old.lobby_id::text));
 if exists(select 1 from public.quiz_duels where old.id in(challenger_id,opponent_id)
 and status in('accepted','playing','between') and expires_at>statement_timestamp()) then raise exception 'quiz_busy'; end if;
 if tg_op='DELETE' then return old; end if; return new;
end $$;
drop trigger if exists quiz_team_locked on public.lobby_memberships;
create trigger quiz_team_locked before update or delete on public.lobby_memberships for each row execute function public._quiz_guard_team();

-- Keep every helper and RPC private, including future overloads in this migration.
do $$ declare f record; begin
 for f in select oid::regprocedure signature from pg_proc where pronamespace='public'::regnamespace
 and (proname like '\_quiz\_%' escape '\' or proname in('quiz_status','invite_quiz_duel','quiz_action')) loop
  execute format('revoke all on function %s from public,anon,authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;
commit;
