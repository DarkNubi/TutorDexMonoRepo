-- Migration: Add assignment rating system support
-- Date: 2026-01-09
-- Description: Adds fields to support adaptive assignment threshold based on tutor preferences

-- Add desired assignments per day preference to user_preferences
alter table public.user_preferences
  add column if not exists desired_assignments_per_day integer default 10;

comment on column public.user_preferences.desired_assignments_per_day is 
  'Target number of assignments tutor wants to receive per day. Used to calculate adaptive threshold.';

-- Create table to track assignment ratings sent to tutors
create table if not exists public.tutor_assignment_ratings (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  assignment_id bigint not null references public.assignments(id) on delete cascade,
  rating_score double precision not null,
  distance_km double precision,
  rate_min integer,
  rate_max integer,
  match_score integer not null,
  sent_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

comment on table public.tutor_assignment_ratings is 
  'Tracks assignment ratings for each tutor to enable adaptive threshold calculation';

-- Create indexes for efficient queries
create index if not exists tutor_assignment_ratings_user_id_sent_at_idx 
  on public.tutor_assignment_ratings(user_id, sent_at desc);

create index if not exists tutor_assignment_ratings_assignment_id_idx 
  on public.tutor_assignment_ratings(assignment_id);

create index if not exists tutor_assignment_ratings_user_id_rating_idx 
  on public.tutor_assignment_ratings(user_id, rating_score desc);

-- Add constraint to prevent duplicate entries for same user+assignment
create unique index if not exists tutor_assignment_ratings_user_assignment_unique 
  on public.tutor_assignment_ratings(user_id, assignment_id);

-- RLS policies
alter table public.tutor_assignment_ratings enable row level security;

-- Service role can do everything
do $$ begin
  if not exists (
    select 1 from pg_policies 
    where schemaname='public' 
    and tablename='tutor_assignment_ratings' 
    and policyname='tutor_assignment_ratings_service_role_all'
  ) then
    create policy tutor_assignment_ratings_service_role_all 
      on public.tutor_assignment_ratings 
      for all 
      to service_role 
      using (true) 
      with check (true);
  end if;
end $$;

-- Function to calculate adaptive threshold for a tutor
-- Returns the rating threshold that would give approximately desired_assignments_per_day
-- based on the past 7 days of assignment ratings
create or replace function public.calculate_tutor_rating_threshold(
  p_user_id bigint,
  p_desired_per_day integer default 10,
  p_lookback_days integer default 7
) returns double precision as $$
declare
  v_count integer;
  v_threshold double precision;
  v_total_days double precision;
begin
  -- Calculate total days with data
  select extract(epoch from (max(sent_at) - min(sent_at))) / 86400.0
  into v_total_days
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval;
  
  -- If no history or very little history, return a low threshold to be permissive
  if v_total_days is null or v_total_days < 0.5 then
    return 0.0;
  end if;
  
  -- Count total assignments in lookback period
  select count(*) into v_count
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval;
  
  -- If we have no data, return low threshold
  if v_count = 0 then
    return 0.0;
  end if;
  
  -- Calculate target count for the period
  declare
    v_target_count integer := greatest(1, round(p_desired_per_day * v_total_days));
    v_percentile double precision;
  begin
    -- If we're getting too many, raise the threshold
    -- If we're getting too few, lower the threshold
    if v_count > v_target_count then
      -- Get the Nth percentile where N = (count - target) / count
      -- This gives us the threshold that would cut out the excess
      v_percentile := 1.0 - (v_target_count::double precision / v_count::double precision);
    else
      -- Getting fewer than desired, use a lower threshold
      v_percentile := 0.0;
    end if;
    
    -- Get the rating at the calculated percentile
    select percentile_cont(v_percentile) within group (order by rating_score)
    into v_threshold
    from public.tutor_assignment_ratings
    where user_id = p_user_id
      and sent_at >= now() - (p_lookback_days || ' days')::interval;
    
    return coalesce(v_threshold, 0.0);
  end;
end;
$$ language plpgsql stable;

comment on function public.calculate_tutor_rating_threshold is 
  'Calculate adaptive rating threshold for a tutor based on historical assignment ratings';

-- Function to get tutor's average rate from past assignments
-- This is used to calculate rate bonus for high-paying assignments
create or replace function public.get_tutor_avg_rate(
  p_user_id bigint,
  p_lookback_days integer default 30
) returns double precision as $$
declare
  v_avg_rate double precision;
begin
  select avg((rate_min + coalesce(rate_max, rate_min)) / 2.0)
  into v_avg_rate
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval
    and rate_min is not null
    and rate_min > 0;
  
  return coalesce(v_avg_rate, 0.0);
end;
$$ language plpgsql stable;

comment on function public.get_tutor_avg_rate is 
  'Calculate average rate from past assignments shown to tutor (for rate bonus calculation)';
