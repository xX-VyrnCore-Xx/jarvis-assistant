-- Token dei dispositivi ed etichette ora cifrati: il confronto avviene sull'HMAC (token_hash), non sul testo.
alter table devices add column if not exists token_hash text;
create unique index if not exists devices_token_hash_idx on devices (token_hash);
