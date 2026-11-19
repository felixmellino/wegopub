-- Contributor-approved QA exception, 19 November 2026. Apply AFTER 014.
-- Existing frozen snapshots stay untouched. Normal competition stays unchanged.
begin;
create or replace function public._focus_is_test(s public.seasons)
returns boolean language sql immutable set search_path=public as $$
 select s.scoring_version='v1' and coalesce(s.scoring_rules->'test_mode'='true'::jsonb,false)
$$;
-- The fixed v1 fallback is only for pre-Focus QA snapshots. New snapshots keep their own config.
create or replace function public._focus_rules(s public.seasons)
returns jsonb language sql immutable set search_path=public as $$
 select case when s.scoring_version='v1' and s.scoring_rules->'focus_challenge'->>'version'='1'
  then s.scoring_rules->'focus_challenge'
  when public._focus_is_test(s) then '{"version":1,"first_unlock":5,"retry_step":2,"reaction_trials":5,"reaction_median_ms":350,"reaction_wait_min_ms":1500,"reaction_wait_max_ms":4500,"reaction_response_ms":2000,"memory_length":7,"memory_cells":9,"memory_flash_ms":650,"memory_gap_ms":200,"memory_input_ms":15000,"precision_targets":12,"precision_ms":12000,"ready_seconds":30,"attempt_seconds":180,"delivery_grace_ms":2000,"boost_seconds":3600,"multiplier":1.5}'::jsonb else null end
$$;
alter table public.focus_attempts add column if not exists test_mode boolean not null default false;
update public.focus_attempts a set test_mode=public._focus_is_test(s)
 from public.seasons s where s.id=a.season_id and a.test_mode is distinct from public._focus_is_test(s);
create or replace function public._focus_attempt_mode() returns trigger
language plpgsql set search_path=public as $$
begin
 select public._focus_is_test(s) into new.test_mode from public.seasons s where s.id=new.season_id;
 return new;
end $$;
drop trigger if exists focus_attempt_mode on public.focus_attempts;
create trigger focus_attempt_mode before insert or update on public.focus_attempts
 for each row execute function public._focus_attempt_mode();
drop index if exists public.focus_one_win;
create unique index focus_one_win on public.focus_attempts(membership_id,season_id,game_night)
 where status='passed' and not test_mode;


create or replace function public._focus_season(actor_player uuid,target_season uuid)
returns public.seasons language plpgsql set search_path=public as $$
declare s public.seasons%rowtype;
begin
 select season.* into s from public.seasons season join public.lobby_memberships m on m.lobby_id=season.lobby_id
 where season.id=target_season and m.player_id=actor_player;
 if not found then raise exception 'permission_denied'; end if;
 if public._focus_rules(s) is null then
  raise exception 'focus_disabled'; end if;
 return s;
end $$;

create or replace function public._focus_window_end(s public.seasons,at_time timestamptz)
returns timestamptz language sql stable set search_path=public as $$
 select case when public._focus_is_test(s) then s.ends_at else least(s.ends_at,((date_trunc('week',at_time at time zone s.timezone_name)
  + make_interval(days=>(s.scoring_rules->>'end_weekday')::integer,
                   hours=>(s.scoring_rules->>'end_hour')::integer)) at time zone s.timezone_name)) end
$$;

create or replace function public._focus_public(a public.focus_attempts,at_time timestamptz)
returns jsonb language sql stable set search_path=public as $$
 select jsonb_build_object('id',a.id,'status',a.status,'phase',a.phase,'step',a.step,'revision',a.revision,
 'started_at',a.started_at,'expires_at',a.expires_at,'signal_at',a.signal_at,'deadline',a.deadline,
 'reaction_ms',a.reaction_ms,'precision_taps',a.precision_taps,'reason',a.reason,
 'boost_ends_at',a.boost_ends_at,'server_now',at_time,'test_mode',a.test_mode,
 'config',(select public._focus_rules(s) from public.seasons s where id=a.season_id))
 || case when a.status='running' and a.phase='memory' and at_time<a.signal_at
    then jsonb_build_object('memory',a.challenge->'memory') else '{}'::jsonb end
 || case when a.status='running' and a.phase='precision'
    then jsonb_build_object('positions',a.challenge->'positions') else '{}'::jsonb end
$$;

create or replace function public.focus_status(actor_player uuid,target_season uuid) returns jsonb
language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; mid uuid; night date; n integer; failures integer; won boolean;
 a public.focus_attempts%rowtype; active_until timestamptz; at_time timestamptz:=statement_timestamp();
begin
 s:=public._focus_season(actor_player,target_season);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 select id into mid from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 perform public._focus_expire(mid,s.id,at_time);
 night:=public._chug_night(at_time,s.timezone_name);
 select count(*) into n from public.drink_entries where membership_id=mid and season_id=s.id
  and rule_version='v1' and location_check_result in ('matched','outside')
  and public._chug_night(submitted_at,s.timezone_name)=night;
 select count(*) filter(where status='failed'),coalesce(bool_or(status='passed'),false) into failures,won
  from public.focus_attempts where membership_id=mid and season_id=s.id and game_night=night;
 select max(boost_ends_at) into active_until from public.focus_attempts
  where membership_id=mid and season_id=s.id and status='passed' and boost_ends_at>at_time;
 select * into a from public.focus_attempts where membership_id=mid and season_id=s.id order by started_at desc,id desc limit 1;
 return jsonb_build_object('count',n,'unlimited',public._focus_is_test(s),'threshold',case when public._focus_is_test(s) then 0 else (public._focus_rules(s)->>'first_unlock')::integer
  +failures*(public._focus_rules(s)->>'retry_step')::integer end,'won',won,'boost_ends_at',active_until,
  'attempt',case when a.id is not null then public._focus_public(a,at_time) else null end,'server_now',at_time);
end $$;

create or replace function public.start_focus_attempt(actor_player uuid,target_season uuid,request_id uuid)
returns jsonb language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; mid uuid; a public.focus_attempts%rowtype; info jsonb; cfg jsonb;
 at_time timestamptz:=statement_timestamp(); reset_at timestamptz; night date; qa boolean; attempt_no integer;
begin
 s:=public._focus_season(actor_player,target_season); qa:=public._focus_is_test(s);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 select id into mid from public.lobby_memberships where lobby_id=s.lobby_id and player_id=actor_player;
 perform public._focus_expire(mid,s.id,at_time);
 select * into a from public.focus_attempts where id=request_id;
 if found then
  if a.membership_id<>mid or a.season_id<>s.id then raise exception 'permission_denied'; end if;
  return public._focus_public(a,at_time);
 end if;
 select * into a from public.focus_attempts where membership_id=mid and season_id=s.id and status='running';
 if found then return public._focus_public(a,at_time); end if;
 if at_time<s.starts_at or at_time>=s.ends_at or (not qa and not public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules))
  then raise exception 'scoring_closed'; end if;
 info:=public.focus_status(actor_player,s.id);
 if not qa and (info->>'won')::boolean then raise exception 'focus_won'; end if;
 if not qa and info->>'boost_ends_at' is not null then raise exception 'focus_active_boost'; end if;
 if not qa and (info->>'count')::integer<(info->>'threshold')::integer then raise exception 'focus_locked'; end if;
 if exists(select 1 from public.chug_duels where season_id=s.id and status='started'
  and (challenger_id=mid or opponent_id=mid) and started_at+interval '10 minutes'>at_time) then raise exception 'focus_busy'; end if;
 cfg:=public._focus_rules(s); night:=public._chug_night(at_time,s.timezone_name);
 reset_at:=((night+1)::timestamp+interval '6 hours') at time zone s.timezone_name;
 -- The lobby lock serializes this number, including unlimited QA replays.
 select coalesce(max(attempt_number),0)+1 into attempt_no from public.focus_attempts
  where membership_id=mid and season_id=s.id and game_night=night;
 insert into public.focus_attempts(id,membership_id,season_id,game_night,attempt_number,challenge,started_at,expires_at,deadline)
 values(request_id,mid,s.id,night,attempt_no,
  public._focus_generate(cfg),at_time,least(at_time+make_interval(secs=>(cfg->>'attempt_seconds')::integer),reset_at,public._focus_window_end(s,at_time)),
  at_time+make_interval(secs=>(cfg->>'ready_seconds')::integer)) returning * into a;
 return public._focus_public(a,at_time);
end $$;

create or replace function public.focus_attempt_action(actor_player uuid,target_attempt uuid,expected_revision integer,
 selected_action text,evidence jsonb) returns jsonb language plpgsql set search_path=public as $$
declare a public.focus_attempts%rowtype; s public.seasons%rowtype; cfg jsonb;
 at_time timestamptz:=statement_timestamp(); ms integer; cell integer; responses jsonb; median_ms integer;
 taps jsonb; i integer; previous_ms integer:=-1; passed boolean:=false;
begin
 select * into a from public.focus_attempts where id=target_attempt;
 if not found then raise exception 'permission_denied'; end if;
 s:=public._focus_season(actor_player,a.season_id);
 perform pg_advisory_xact_lock(hashtext(s.lobby_id::text));
 if not exists(select 1 from public.lobby_memberships where id=a.membership_id and player_id=actor_player and lobby_id=s.lobby_id)
  then raise exception 'permission_denied'; end if;
 perform public._focus_expire(a.membership_id,s.id,at_time);
 select * into a from public.focus_attempts where id=target_attempt;
 if a.status<>'running' or expected_revision<a.revision then return public._focus_public(a,at_time); end if;
 if expected_revision is distinct from a.revision or jsonb_typeof(evidence) is distinct from 'object'
  or octet_length(evidence::text)>8000 then raise exception 'focus_invalid_action'; end if;
 cfg:=public._focus_rules(s);
 if selected_action='fail' then
  update public.focus_attempts set status='failed',reason='miss',completed_at=at_time,revision=revision+1 where id=a.id;
 elsif selected_action='ready' and a.phase in ('reaction_ready','precision_ready') then
  if a.phase='reaction_ready' then
   update public.focus_attempts set phase='reaction',signal_at=at_time+make_interval(secs=>(a.challenge->'delays'->>0)::numeric/1000),
    deadline=at_time+make_interval(secs=>((a.challenge->'delays'->>0)::numeric+(cfg->>'reaction_response_ms')::numeric)/1000),
    revision=revision+1 where id=a.id;
  else
   update public.focus_attempts set phase='precision',signal_at=at_time,
    deadline=at_time+make_interval(secs=>(cfg->>'precision_ms')::numeric/1000),revision=revision+1 where id=a.id;
  end if;
 elsif selected_action='reaction' and a.phase='reaction' then
  if coalesce(evidence->>'elapsed_ms','') !~ '^[0-9]{1,4}$' then raise exception 'focus_invalid_action'; end if;
  ms:=(evidence->>'elapsed_ms')::integer;
  if ms>(cfg->>'reaction_response_ms')::integer or at_time<a.signal_at then raise exception 'focus_invalid_action'; end if;
  responses:=a.reaction_ms||jsonb_build_array(ms);
  if jsonb_array_length(responses)=(cfg->>'reaction_trials')::integer then
   select (array_agg(value::integer order by value::integer))[3] into median_ms from jsonb_array_elements_text(responses);
   if median_ms>(cfg->>'reaction_median_ms')::integer then
    update public.focus_attempts set status='failed',reason='reaction_slow',completed_at=at_time,
      reaction_ms=responses,revision=revision+1 where id=a.id;
   else
    update public.focus_attempts set phase='memory',step=0,reaction_ms=responses,
      signal_at=at_time+make_interval(secs=>((cfg->>'memory_flash_ms')::numeric+(cfg->>'memory_gap_ms')::numeric)*(cfg->>'memory_length')::numeric/1000),
      deadline=at_time+make_interval(secs=>(((cfg->>'memory_flash_ms')::numeric+(cfg->>'memory_gap_ms')::numeric)*(cfg->>'memory_length')::numeric+(cfg->>'memory_input_ms')::numeric)/1000),
      revision=revision+1 where id=a.id;
   end if;
  else
   update public.focus_attempts set step=step+1,reaction_ms=responses,
    signal_at=at_time+make_interval(secs=>(a.challenge->'delays'->>(a.step+1))::numeric/1000),
    deadline=at_time+make_interval(secs=>((a.challenge->'delays'->>(a.step+1))::numeric+(cfg->>'reaction_response_ms')::numeric)/1000),
    revision=revision+1 where id=a.id;
  end if;
 elsif selected_action='memory' and a.phase='memory' then
  if coalesce(evidence->>'cell','') !~ '^[0-8]$' or at_time<a.signal_at then raise exception 'focus_invalid_action'; end if;
  cell:=(evidence->>'cell')::integer;
  if cell<>(a.challenge->'memory'->>a.step)::integer then
   update public.focus_attempts set status='failed',reason='memory_wrong',completed_at=at_time,revision=revision+1 where id=a.id;
  elsif a.step+1=(cfg->>'memory_length')::integer then
   update public.focus_attempts set phase='precision_ready',step=0,signal_at=null,
    deadline=at_time+make_interval(secs=>(cfg->>'ready_seconds')::integer),revision=revision+1 where id=a.id;
  else
   update public.focus_attempts set step=step+1,revision=revision+1 where id=a.id;
  end if;
 elsif selected_action='precision' and a.phase='precision' then
  taps:=evidence->'taps';
  if jsonb_typeof(taps) is distinct from 'array' or jsonb_array_length(taps) not between 1 and (cfg->>'precision_targets')::integer
   then raise exception 'focus_invalid_action'; end if;
  for i in 0..jsonb_array_length(taps)-1 loop
   if coalesce(taps->>i,'') !~ '^[0-9]{1,5}$' then raise exception 'focus_invalid_action'; end if;
   ms:=(taps->>i)::integer;
   if ms<=previous_ms or ms>(cfg->>'precision_ms')::integer
    or ms>extract(epoch from at_time-a.signal_at)*1000+250 then raise exception 'focus_invalid_action'; end if;
   if i<jsonb_array_length(a.precision_taps) and taps->i<>a.precision_taps->i then raise exception 'focus_invalid_action'; end if;
   previous_ms:=ms;
  end loop;
  if jsonb_array_length(taps)>=jsonb_array_length(a.precision_taps) then
   passed:=jsonb_array_length(taps)=(cfg->>'precision_targets')::integer;
   update public.focus_attempts set precision_taps=taps,
    status=case when passed then 'passed' else status end,
    completed_at=case when passed then at_time else completed_at end,
    boost_ends_at=case when passed then least(at_time+make_interval(secs=>(cfg->>'boost_seconds')::integer),public._focus_window_end(s,at_time)) else null end,
    revision=revision+case when passed then 1 else 0 end where id=a.id;
  end if;
 else raise exception 'focus_invalid_action'; end if;
 select * into a from public.focus_attempts where id=target_attempt;
 return public._focus_public(a,at_time);
end $$;

create or replace function public._snapshot_focus_boost() returns trigger language plpgsql set search_path=public as $$
declare cfg jsonb;
begin
 if tg_op='UPDATE' then
  if new.focus_attempt_id is distinct from old.focus_attempt_id then raise exception 'entry_identity_frozen'; end if;
  return new;
 end if;
 new.focus_attempt_id:=null;
 select public._focus_rules(s) into cfg from public.seasons s where id=new.season_id;
 if new.rule_version='v1' and cfg->>'version'='1' and not exists(select 1 from public.chug_duels
   where challenger_entry_id=new.id or opponent_entry_id=new.id) then
  select id into new.focus_attempt_id from public.focus_attempts where membership_id=new.membership_id
   and season_id=new.season_id and status='passed' and completed_at<=new.submitted_at and new.submitted_at<boost_ends_at
   order by completed_at desc limit 1;
 end if;
 return new;
end $$;


revoke all on function public._focus_is_test(public.seasons),public._focus_rules(public.seasons),
 public._focus_attempt_mode(),public._focus_season(uuid,uuid),
 public._focus_window_end(public.seasons,timestamptz),public._focus_public(public.focus_attempts,timestamptz),
 public.focus_status(uuid,uuid),public.start_focus_attempt(uuid,uuid,uuid),
 public.focus_attempt_action(uuid,uuid,integer,text,jsonb),public._snapshot_focus_boost()
 from public,anon,authenticated;
grant execute on function public._focus_is_test(public.seasons),public._focus_rules(public.seasons),
 public._focus_attempt_mode(),public._focus_season(uuid,uuid),
 public._focus_window_end(public.seasons,timestamptz),public._focus_public(public.focus_attempts,timestamptz),
 public.focus_status(uuid,uuid),public.start_focus_attempt(uuid,uuid,uuid),
 public.focus_attempt_action(uuid,uuid,integer,text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
