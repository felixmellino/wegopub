-- Apply once to an existing database, after 002_remembered_devices.sql.
-- Switches territory ids from generated UUIDs to the short, permanent keys
-- used in data/territories.geojson (e.g. 'rua-da-rosa'), see R-T01.
-- Safe to run while the territories table is still empty and no drink entry
-- has a territory yet. Otherwise it stops at the check below and changes nothing.
begin;
do $$
begin
  if exists (select 1 from territories) or exists (select 1 from drink_entries where territory_id is not null) then
    raise exception 'territories already in use; ask the Location & Territories owner before migrating';
  end if;
end $$;

alter table drink_entries drop constraint drink_entries_territory_id_fkey;
alter table drink_entries alter column territory_id type text using territory_id::text;
alter table territories alter column id drop default;
alter table territories alter column id type text using id::text;
alter table territories add constraint territories_id_format check (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$');
alter table drink_entries add constraint drink_entries_territory_id_fkey
  foreign key (territory_id) references territories(id);
commit;
