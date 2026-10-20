-- Anti-sleep per Render Free: Supabase chiama /health ogni 10 minuti.
-- Sostituisci l'URL, poi esegui nello SQL editor di Supabase.
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
  'jarvis-keepalive',
  '*/10 * * * *',
  $$ select net.http_get('https://TUO-SERVIZIO.onrender.com/health', timeout_milliseconds := 60000); $$
);
-- Per rimuoverlo: select cron.unschedule('jarvis-keepalive');
