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

-- Ricordi: indice cieco per cercare senza decifrare (HMAC delle parole, calcolato dal server).
alter table memories add column if not exists terms text[] not null default '{}';
create index if not exists memories_terms_idx on memories using gin (terms);

-- Attività e liste (spesa, da fare...).
create table if not exists tasks (
  id bigint generated always as identity primary key,
  list text not null default 'attività',
  text text not null,
  done boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists tasks_open_idx on tasks (list) where not done;
alter table tasks enable row level security;
revoke all on public.tasks from anon, authenticated;

-- Secondo cervello (RAG): documenti, frammenti con embedding cifrato e indice cieco, entità. Tutti i testi sono cifrati dal server.
create table if not exists brain_docs (
  id bigint generated always as identity primary key,
  source text not null default 'note',
  uri_hash text,
  title text not null default '',
  uri text not null default '',
  summary text not null default '',
  tags text not null default '',
  tag_terms text[] not null default '{}',
  entities text not null default '',
  content_hash text not null default '',
  importance real not null default 0.5,
  pinned boolean not null default false,
  accessed_at timestamptz,
  access_count int not null default 0,
  enriched boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists brain_docs_uri_idx on brain_docs (uri_hash) where uri_hash is not null;
create index if not exists brain_docs_created_idx on brain_docs (created_at desc);
create table if not exists brain_chunks (
  id bigint generated always as identity primary key,
  doc_id bigint not null references brain_docs(id) on delete cascade,
  idx int not null default 0,
  text text not null,
  terms text[] not null default '{}',
  emb text not null default '',
  emb_model text not null default '',
  created_at timestamptz not null default now()
);
create index if not exists brain_chunks_doc_idx on brain_chunks (doc_id, idx);
create table if not exists brain_entities (
  id bigint generated always as identity primary key,
  kind text not null default 'topic',
  key_hash text not null unique,
  name text not null,
  mentions int not null default 1,
  updated_at timestamptz not null default now()
);
create table if not exists brain_doc_entities (
  doc_id bigint not null references brain_docs(id) on delete cascade,
  entity_id bigint not null references brain_entities(id) on delete cascade,
  primary key (doc_id, entity_id)
);
create index if not exists brain_doc_entities_ent_idx on brain_doc_entities (entity_id);
alter table brain_docs enable row level security;
alter table brain_chunks enable row level security;
alter table brain_entities enable row level security;
alter table brain_doc_entities enable row level security;
revoke all on public.brain_docs, public.brain_chunks, public.brain_entities, public.brain_doc_entities from anon, authenticated;

-- Notifiche: metadati cifrati (azioni, percorso nell'app); consumo giornaliero dei modelli.
alter table notifications add column if not exists meta text not null default '';
create table if not exists usage_daily (
  day date not null,
  kind text not null,
  model text not null default '',
  requests int not null default 0,
  errors int not null default 0,
  prompt_tokens bigint not null default 0,
  completion_tokens bigint not null default 0,
  latency_ms bigint not null default 0,
  primary key (day, kind, model)
);
alter table usage_daily enable row level security;
revoke all on public.usage_daily from anon, authenticated;
