-- JARVIS: schema iniziale. Accesso solo via service key dal server (RLS attiva, nessuna policy).
create table if not exists messages (
  id bigint generated always as identity primary key,
  session_id text not null,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists messages_session_idx on messages (session_id, created_at desc);

create table if not exists memories (
  id bigint generated always as identity primary key,
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists memories_fts_idx on memories using gin (to_tsvector('italian', content));

create table if not exists reminders (
  id bigint generated always as identity primary key,
  text text not null,
  due_at timestamptz not null,
  done boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists reminders_due_idx on reminders (due_at) where not done;

alter table messages enable row level security;
alter table memories enable row level security;
alter table reminders enable row level security;

-- Hardening: anon/authenticated non possono toccare nulla; accede solo il server con la service_role key.
revoke all on public.messages, public.memories, public.reminders from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;
