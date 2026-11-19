-- Focus Challenge. Apply after 013_checkin_photo_privacy.sql (and 011/012 QA minigames). No existing snapshot is changed.
begin;
alter table public.drink_entries alter column points_awarded type numeric(14,3);
alter table public.drink_entries alter column owner_bonus_quarters type numeric(14,3);
create table if not exists public.focus_attempts (
 id uuid primary key, membership_id uuid not null references public.lobby_memberships(id),
 season_id uuid not null references public.seasons(id), game_night date not null,
 attempt_number integer not null, status text not null default 'running' check(status in ('running','failed','passed')),
 phase text not null default 'reaction_ready', step integer not null default 0,
 revision integer not null default 0, challenge jsonb not null,
 reaction_ms jsonb not null default '[]', precision_taps jsonb not null default '[]',
 started_at timestamptz not null, expires_at timestamptz not null,
 signal_at timestamptz, deadline timestamptz not null, completed_at timestamptz,
 boost_ends_at timestamptz, reason text,
 unique(membership_id,season_id,game_night,attempt_number)
);
create unique index if not exists focus_one_running on public.focus_attempts(membership_id,season_id) where status='running';
create unique index if not exists focus_one_win on public.focus_attempts(membership_id,season_id,game_night) where status='passed';
alter table public.focus_attempts enable row level security;
revoke all on public.focus_attempts from public,anon,authenticated;
grant all on public.focus_attempts to service_role;
alter table public.drink_entries add column if not exists focus_attempt_id uuid references public.focus_attempts(id);

create or replace function public._focus_int(bound integer) returns integer language plpgsql set search_path=public as $$
declare n bigint; ceiling bigint := 4294967296 - (4294967296 % bound);
begin
 loop
  n := ('x'||substr(replace(gen_random_uuid()::text,'-',''),1,8))::bit(32)::bigint;
  if n<ceiling then return (n % bound)::integer; end if;
 end loop;
end $$;
create or replace function public._focus_generate(cfg jsonb) returns jsonb language plpgsql set search_path=public as $$
declare delays jsonb:='[]'; memory jsonb:='[]'; positions jsonb:='[]'; cell integer; previous integer:=-1;
 x integer; y integer; px integer:=-1000; py integer:=-1000; i integer;
begin
 for i in 1..(cfg->>'reaction_trials')::integer loop
  delays:=delays||jsonb_build_array((cfg->>'reaction_wait_min_ms')::integer+public._focus_int(
   (cfg->>'reaction_wait_max_ms')::integer-(cfg->>'reaction_wait_min_ms')::integer+1));
 end loop;
 for i in 1..(cfg->>'memory_length')::integer loop
  loop cell:=public._focus_int((cfg->>'memory_cells')::integer); exit when cell<>previous; end loop;
  memory:=memory||jsonb_build_array(cell); previous:=cell;
 end loop;
 for i in 1..(cfg->>'precision_targets')::integer loop
  loop
   x:=120+public._focus_int(761); y:=120+public._focus_int(761);
   exit when (x-px)^2+(y-py)^2>=250^2;
  end loop;
  positions:=positions||jsonb_build_array(jsonb_build_object('x',x,'y',y)); px:=x; py:=y;
 end loop;
 return jsonb_build_object('delays',delays,'memory',memory,'positions',positions);
end $$;
create or replace function public._focus_season(actor_player uuid,target_season uuid)
returns public.seasons language plpgsql set search_path=public as $$
declare s public.seasons%rowtype;
begin
 select season.* into s from public.seasons season join public.lobby_memberships m on m.lobby_id=season.lobby_id
 where season.id=target_season and m.player_id=actor_player;
 if not found then raise exception 'permission_denied'; end if;
 if s.scoring_version<>'v1' or s.scoring_rules->'focus_challenge'->>'version' is distinct from '1' then
  raise exception 'focus_disabled'; end if;
 return s;
end $$;
create or replace function public._focus_window_end(s public.seasons,at_time timestamptz)
returns timestamptz language sql stable set search_path=public as $$
 select least(s.ends_at,((date_trunc('week',at_time at time zone s.timezone_name)
  + make_interval(days=>(s.scoring_rules->>'end_weekday')::integer,
                   hours=>(s.scoring_rules->>'end_hour')::integer)) at time zone s.timezone_name))
$$;
create or replace function public._focus_expire(mid uuid,sid uuid,at_time timestamptz) returns void
language plpgsql set search_path=public as $$
begin
 update public.focus_attempts set status='failed',reason='timeout',completed_at=at_time,revision=revision+1
 where membership_id=mid and season_id=sid and status='running'
 and (at_time>=expires_at or at_time>deadline+interval '2 seconds');
end $$;
create or replace function public._focus_public(a public.focus_attempts,at_time timestamptz)
returns jsonb language sql stable set search_path=public as $$
 select jsonb_build_object('id',a.id,'status',a.status,'phase',a.phase,'step',a.step,'revision',a.revision,
 'started_at',a.started_at,'expires_at',a.expires_at,'signal_at',a.signal_at,'deadline',a.deadline,
 'reaction_ms',a.reaction_ms,'precision_taps',a.precision_taps,'reason',a.reason,
 'boost_ends_at',a.boost_ends_at,'server_now',at_time,
 'config',(select scoring_rules->'focus_challenge' from public.seasons where id=a.season_id))
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
 return jsonb_build_object('count',n,'threshold',(s.scoring_rules->'focus_challenge'->>'first_unlock')::integer
  +failures*(s.scoring_rules->'focus_challenge'->>'retry_step')::integer,'won',won,'boost_ends_at',active_until,
  'attempt',case when a.id is not null then public._focus_public(a,at_time) else null end,'server_now',at_time);
end $$;
create or replace function public.start_focus_attempt(actor_player uuid,target_season uuid,request_id uuid)
returns jsonb language plpgsql set search_path=public as $$
declare s public.seasons%rowtype; mid uuid; a public.focus_attempts%rowtype; info jsonb; cfg jsonb;
 at_time timestamptz:=statement_timestamp(); reset_at timestamptz; night date;
begin
 s:=public._focus_season(actor_player,target_season);
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
 if at_time<s.starts_at or at_time>=s.ends_at or not public._scoring_window_open(at_time,s.timezone_name,s.scoring_rules)
  then raise exception 'scoring_closed'; end if;
 info:=public.focus_status(actor_player,s.id);
 if (info->>'won')::boolean then raise exception 'focus_won'; end if;
 if info->>'boost_ends_at' is not null then raise exception 'focus_active_boost'; end if;
 if (info->>'count')::integer<(info->>'threshold')::integer then raise exception 'focus_locked'; end if;
 if exists(select 1 from public.chug_duels where season_id=s.id and status='started'
  and (challenger_id=mid or opponent_id=mid) and started_at+interval '10 minutes'>at_time) then raise exception 'focus_busy'; end if;
 cfg:=s.scoring_rules->'focus_challenge'; night:=public._chug_night(at_time,s.timezone_name);
 reset_at:=((night+1)::timestamp+interval '6 hours') at time zone s.timezone_name;
 insert into public.focus_attempts(id,membership_id,season_id,game_night,attempt_number,challenge,started_at,expires_at,deadline)
 values(request_id,mid,s.id,night,1+((info->>'threshold')::integer-(cfg->>'first_unlock')::integer)/(cfg->>'retry_step')::integer,
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
 cfg:=s.scoring_rules->'focus_challenge';
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
 select scoring_rules->'focus_challenge' into cfg from public.seasons where id=new.season_id;
 if new.rule_version='v1' and cfg->>'version'='1' and not exists(select 1 from public.chug_duels
   where challenger_entry_id=new.id or opponent_entry_id=new.id) then
  select id into new.focus_attempt_id from public.focus_attempts where membership_id=new.membership_id
   and season_id=new.season_id and status='passed' and completed_at<=new.submitted_at and new.submitted_at<boost_ends_at
   order by completed_at desc limit 1;
 end if;
 return new;
end $$;
drop trigger if exists snapshot_focus_boost on public.drink_entries;
create trigger snapshot_focus_boost before insert or update on public.drink_entries
 for each row execute function public._snapshot_focus_boost();

create or replace function public._guard_focus_chug() returns trigger language plpgsql set search_path=public as $$
begin
 if new.status='started' and old.status<>'started' and exists(select 1 from public.focus_attempts
  where season_id=new.season_id and membership_id in (new.challenger_id,new.opponent_id) and status='running'
  and expires_at>statement_timestamp() and deadline+interval '2 seconds'>statement_timestamp()) then
  raise exception 'focus_busy';
 end if;
 return new;
end $$;
drop trigger if exists guard_focus_chug on public.chug_duels;
create trigger guard_focus_chug before update on public.chug_duels for each row execute function public._guard_focus_chug();
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
      owner_membership_id = case when entry.team_id is null and prior_owner is not null and prior_owner <> member then prior_owner::uuid else null end,
      owner_team_id = case when entry.team_id is not null and prior_owner is not null and prior_owner <> member then prior_owner::uuid else null end,
      owner_bonus_quarters = case when prior_owner is not null and prior_owner <> member then points else 0 end
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

revoke all on function public._focus_int(integer), public._focus_generate(jsonb),
 public._focus_season(uuid,uuid),public._focus_window_end(public.seasons,timestamptz),
 public._focus_expire(uuid,uuid,timestamptz),public._focus_public(public.focus_attempts,timestamptz),
 public.focus_status(uuid,uuid),public.start_focus_attempt(uuid,uuid,uuid),
 public.focus_attempt_action(uuid,uuid,integer,text,jsonb),public._snapshot_focus_boost(),public._guard_focus_chug()
 from public,anon,authenticated;
grant execute on function public.focus_status(uuid,uuid),public.start_focus_attempt(uuid,uuid,uuid),
 public.focus_attempt_action(uuid,uuid,integer,text,jsonb) to service_role;
grant execute on function public._focus_int(integer),public._focus_generate(jsonb),
 public._focus_season(uuid,uuid),public._focus_window_end(public.seasons,timestamptz),
 public._focus_expire(uuid,uuid,timestamptz),public._focus_public(public.focus_attempts,timestamptz) to service_role;
notify pgrst,'reload schema';
commit;
