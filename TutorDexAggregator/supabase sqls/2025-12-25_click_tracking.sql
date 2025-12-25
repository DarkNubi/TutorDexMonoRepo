-- Click tracking for tracked URLs + broadcast click count rendering.
-- Apply to your Supabase Postgres (public schema).

create table if not exists public.assignment_clicks (
  external_id text primary key,
  original_url text not null,
  clicks integer not null default 0,
  last_click_at timestamptz
);

create table if not exists public.broadcast_messages (
  external_id text primary key references public.assignment_clicks(external_id) on delete cascade,
  original_url text not null,
  sent_chat_id bigint not null,
  sent_message_id bigint not null,
  message_html text not null,
  last_rendered_clicks integer,
  last_edited_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists broadcast_messages_chat_msg_uidx
  on public.broadcast_messages(sent_chat_id, sent_message_id);

create or replace function public.increment_assignment_clicks(
  p_external_id text,
  p_original_url text,
  p_delta integer default 1
)
returns integer
language plpgsql
as $$
declare
  v_clicks integer;
begin
  insert into public.assignment_clicks(external_id, original_url, clicks, last_click_at)
  values (p_external_id, p_original_url, greatest(0, p_delta), now())
  on conflict (external_id) do update
    set clicks = public.assignment_clicks.clicks + greatest(0, p_delta),
        last_click_at = now(),
        original_url = excluded.original_url
  returning clicks into v_clicks;

  update public.broadcast_messages
    set updated_at = now()
    where external_id = p_external_id;

  return v_clicks;
end;
$$;
