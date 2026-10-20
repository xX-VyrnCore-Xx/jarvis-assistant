-- Notifiche in tempo reale e dispositivi push.
create table if not exists notifications (
  id bigint generated always as identity primary key,
  kind text not null default 'info',
  title text not null,
  body text not null default '',
  read boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists notifications_created_idx on notifications (created_at desc);

create table if not exists devices (
  id bigint generated always as identity primary key,
  platform text not null check (platform in ('android','windows','web')),
  token text not null unique,
  label text not null default '',
  created_at timestamptz not null default now(),
  last_seen timestamptz not null default now()
);

create index if not exists messages_created_idx on messages (created_at);

alter table notifications enable row level security;
alter table devices enable row level security;
revoke all on public.notifications, public.devices from anon, authenticated;

-- La pulizia dei dati vecchi (retention) la esegue il server ogni notte via PostgREST (vedi server/app/memory.py: prune).

-- Impostazioni del server (es. refresh token Google, cifrato).
create table if not exists app_settings (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);
alter table app_settings enable row level security;
revoke all on public.app_settings from anon, authenticated;
