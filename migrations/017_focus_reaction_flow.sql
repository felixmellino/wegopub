-- Focus: one fast reaction and explicit memory handoff. Apply after 015 (016 optional).
-- Existing season snapshots and in-progress attempt rules are preserved.
begin;
alter table public.focus_attempts add column if not exists config jsonb;
update public.focus_attempts a set config=public._focus_rules(s) from public.seasons s
 where s.id=a.season_id and a.config is null;
alter table public.focus_attempts alter column config set not null;

create or replace function public._focus_rules(s public.seasons)
returns jsonb language sql immutable set search_path=public as $$
 select case when s.scoring_version='v1' and s.scoring_rules->'focus_challenge'->>'version'='1'
  then s.scoring_rules->'focus_challenge'
  when public._focus_is_test(s) then '{"version":1,"first_unlock":5,"retry_step":2,"reaction_trials":5,"reaction_median_ms":350,"reaction_wait_min_ms":1500,"reaction_wait_max_ms":4500,"reaction_response_ms":2000,"memory_length":7,"memory_cells":9,"memory_flash_ms":650,"memory_gap_ms":200,"memory_input_ms":15000,"precision_targets":12,"precision_ms":12000,"ready_seconds":30,"attempt_seconds":180,"delivery_grace_ms":2000,"boost_seconds":3600,"multiplier":1.5}'::jsonb else null end || '{"reaction_trials":1,"reaction_median_ms":220,"reaction_response_ms":500,"flow_version":2}'::jsonb
$$;
create or replace function public._focus_public(a public.focus_attempts,at_time timestamptz)
returns jsonb language sql stable set search_path=public as $$
 select jsonb_build_object('id',a.id,'status',a.status,'phase',a.phase,'step',a.step,'revision',a.revision,
 'started_at',a.started_at,'expires_at',a.expires_at,'signal_at',a.signal_at,'deadline',a.deadline,
 'reaction_ms',a.reaction_ms,'precision_taps',a.precision_taps,'reason',a.reason,
 'boost_ends_at',a.boost_ends_at,'server_now',at_time,'test_mode',a.test_mode,
 'config',a.config)
 || case when a.status='running' and a.phase='memory' and at_time<a.signal_at
    then jsonb_build_object('memory',a.challenge->'memory') else '{}'::jsonb end
 || case when a.status='running' and a.phase='precision'
    then jsonb_build_object('positions',a.challenge->'positions') else '{}'::jsonb end
$$;
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
 cfg:=a.config;
 if selected_action='fail' then
  update public.focus_attempts set status='failed',reason='miss',completed_at=at_time,revision=revision+1 where id=a.id;
 elsif selected_action='ready' and a.phase in ('reaction_ready','memory_ready','precision_ready') then
  if a.phase='reaction_ready' then
   update public.focus_attempts set phase='reaction',signal_at=at_time+make_interval(secs=>(a.challenge->'delays'->>0)::numeric/1000),
    deadline=at_time+make_interval(secs=>((a.challenge->'delays'->>0)::numeric+(cfg->>'reaction_response_ms')::numeric)/1000),
    revision=revision+1 where id=a.id;
  elsif a.phase='memory_ready' then
   update public.focus_attempts set phase='memory',step=0,
    signal_at=at_time+interval '1 second'+make_interval(secs=>((cfg->>'memory_flash_ms')::numeric+(cfg->>'memory_gap_ms')::numeric)*(cfg->>'memory_length')::numeric/1000),
    deadline=at_time+interval '1 second'+make_interval(secs=>(((cfg->>'memory_flash_ms')::numeric+(cfg->>'memory_gap_ms')::numeric)*(cfg->>'memory_length')::numeric+(cfg->>'memory_input_ms')::numeric)/1000),
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
   select (array_agg(value::integer order by value::integer))[(jsonb_array_length(responses)+1)/2] into median_ms from jsonb_array_elements_text(responses);
   if median_ms>(cfg->>'reaction_median_ms')::integer then
    update public.focus_attempts set status='failed',reason='reaction_slow',completed_at=at_time,
      reaction_ms=responses,revision=revision+1 where id=a.id;
   elsif cfg->>'flow_version'='2' then
    update public.focus_attempts set phase='memory_ready',step=0,reaction_ms=responses,signal_at=null,
      deadline=at_time+make_interval(secs=>(cfg->>'ready_seconds')::integer),revision=revision+1 where id=a.id;
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

create or replace function public._focus_snapshot_config() returns trigger language plpgsql set search_path=public as $$
begin
 if tg_op='UPDATE' then
  if new.config is distinct from old.config then raise exception 'focus_config_frozen'; end if;
 else
  select public._focus_rules(s) into new.config from public.seasons s where s.id=new.season_id;
 end if;
 return new;
end $$;
drop trigger if exists focus_snapshot_config on public.focus_attempts;
create trigger focus_snapshot_config before insert or update on public.focus_attempts
 for each row execute function public._focus_snapshot_config();
revoke all on function public._focus_snapshot_config() from public,anon,authenticated;
notify pgrst,'reload schema';
commit;
