-- Promemoria ricorrenti: daily, weekdays, weekly, monthly, yearly (vuoto = una volta sola)
alter table reminders add column if not exists repeat text;
