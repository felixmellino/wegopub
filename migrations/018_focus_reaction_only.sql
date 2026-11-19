-- Apply after 017. The Reaction Test is now only the reaction tries.
-- 1) Passing the median check wins at once (boost, same rule as before); Memory and
--    Precision are no longer played. Attempts already waiting in those stages simply
--    expire or end; their saved history is untouched.
-- 2) The median was hard-wired to the 3rd value (right for five tries). New seasons
--    play three tries, so take the middle value of however many tries the season
--    froze: (n+1)/2. Five tries still give the 3rd value.
begin;
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
   select (array_agg(value::integer order by value::integer))[(jsonb_array_length(responses)+1)/2] into median_ms from jsonb_array_elements_text(responses);
   if median_ms>(cfg->>'reaction_median_ms')::integer then
    update public.focus_attempts set status='failed',reason='reaction_slow',completed_at=at_time,
      reaction_ms=responses,revision=revision+1 where id=a.id;
   else
    update public.focus_attempts set status='passed',reaction_ms=responses,completed_at=at_time,
      boost_ends_at=least(at_time+make_interval(secs=>(cfg->>'boost_seconds')::integer),public._focus_window_end(s,at_time)),
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
notify pgrst,'reload schema';
commit;
