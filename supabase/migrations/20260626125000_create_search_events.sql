create extension if not exists pgcrypto;

create table if not exists public.search_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  code_postal text not null check (code_postal ~ '^[0-9]{5}$'),
  min_area integer not null check (min_area >= 0),
  max_area integer not null check (max_area >= 0),
  limit_requested integer not null check (limit_requested > 0),
  matched_communes integer not null default 0 check (matched_communes >= 0),
  result_count integer check (result_count >= 0),
  status text not null check (status in ('success', 'not_found', 'error')),
  error_message text,
  request_path text,
  request_query text,
  referrer text,
  user_agent text,
  ip_hash text,
  metadata jsonb not null default '{}'::jsonb,
  constraint search_events_area_range_check check (max_area >= min_area)
);

alter table public.search_events enable row level security;

revoke all on table public.search_events from anon, authenticated;
grant insert on table public.search_events to service_role;
grant select on table public.search_events to service_role;

create index if not exists search_events_created_at_idx
  on public.search_events (created_at desc);

create index if not exists search_events_code_postal_created_at_idx
  on public.search_events (code_postal, created_at desc);

create index if not exists search_events_status_created_at_idx
  on public.search_events (status, created_at desc);

comment on table public.search_events is 'Anonymous search analytics for surface-terrain.fr parcel searches.';
comment on column public.search_events.ip_hash is 'Optional salted hash of the client IP; raw IP addresses are not stored.';
