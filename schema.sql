-- ============================================================
-- EchoByte — Supabase SQL Setup
--
-- HOW TO USE (brand-new project):
--   1. Open your Supabase project → SQL Editor.
--   2. Paste this entire file and click "Run".
--   3. Done — all tables, seed data, security policies, and storage
--      buckets are created in one go. No other setup step is needed.
--
-- Safe to re-run: every statement uses "if not exists" / "on conflict
-- do nothing", so running this file again later won't delete or
-- duplicate anything.
-- ============================================================

-- ===== Tables =====

create table if not exists users (
  id serial primary key,
  role text not null check (role in ('shg','driver','govt')),
  full_name text not null,
  mobile text unique,
  village text,
  email text unique,
  password_hash text not null,
  wallet numeric(10,2) default 0,
  photo_url text,
  vehicle_no text,
  current_lat double precision,
  current_lng double precision,
  location_updated_at timestamptz,
  service_radius_km numeric(5,2) default 3,
  pwm_unit_id integer,
  training_video_completed boolean default false,
  created_at timestamptz default now()
);

create table if not exists garbage_reports (
  id serial primary key,
  shg_id integer not null references users(id) on delete cascade,
  village text,
  location_name text,
  lat double precision,
  lng double precision,
  quantity_kg numeric(10,2) not null,
  description text,
  plastic_type text default 'Mixed Plastic',
  status text default 'pending' check (status in ('pending','assigned','collected')),
  otp text,
  pickup_photo_url text,
  created_at timestamptz default now(),
  collected_at timestamptz
);

-- Govt-controlled rate card: how much ₹/kg the SHG and Driver each earn
-- per plastic type. Wallets are calculated from this table once a
-- collection is verified.
create table if not exists plastic_rates (
  type text primary key,
  shg_rate_per_kg numeric(10,2) not null default 2,
  driver_rate_per_kg numeric(10,2) not null default 0.5
);

insert into plastic_rates (type, shg_rate_per_kg, driver_rate_per_kg) values
  ('PET Bottles', 3.00, 0.75),
  ('Mixed Plastic', 2.00, 0.50),
  ('E-Waste', 5.00, 1.00),
  ('Other Dry Waste', 1.50, 0.40)
on conflict (type) do nothing;

-- Wallet withdrawal requests (SHG + Driver) — UPI / Bank / Card
create table if not exists withdrawals (
  id serial primary key,
  user_id integer not null references users(id) on delete cascade,
  role text not null check (role in ('shg','driver')),
  amount numeric(10,2) not null,
  method text not null check (method in ('upi','bank','card')),
  details text,
  status text not null default 'pending' check (status in ('pending','paid','rejected')),
  approved_by integer references users(id),
  approved_at timestamptz,
  created_at timestamptz default now()
);

-- SHG can raise a dispute/complaint about a specific pickup (e.g. wrong
-- weight, driver misbehaviour, payment mismatch, etc). Govt reviews these.
create table if not exists disputes (
  id serial primary key,
  report_id integer not null references garbage_reports(id) on delete cascade,
  shg_id integer not null references users(id) on delete cascade,
  reason text not null,
  status text not null default 'open' check (status in ('open','resolved')),
  resolution_note text,
  created_at timestamptz default now(),
  resolved_at timestamptz
);

-- Driver SOS / vehicle-breakdown alerts — raising one releases all of that
-- driver's currently-assigned stops back to the pending pool so another
-- driver can pick them up.
create table if not exists sos_alerts (
  id serial primary key,
  driver_id integer not null references users(id) on delete cascade,
  reason text not null,
  note text,
  lat double precision,
  lng double precision,
  stops_released integer default 0,
  status text not null default 'open' check (status in ('open','resolved')),
  created_at timestamptz default now(),
  resolved_at timestamptz
);

-- Plastic Waste Management (PWM) units / recycler centres — govt manages
-- this list from the admin panel (dynamic CRUD, not hardcoded).
create table if not exists pwm_units (
  id serial primary key,
  name text not null,
  location_name text,
  lat double precision,
  lng double precision,
  capacity_kg numeric(10,2) default 0,
  contact_person text,
  contact_mobile text,
  status text not null default 'active' check (status in ('active','inactive')),
  created_at timestamptz default now()
);

-- Seed the two starting PWM units (Bhilai + Raipur) so SHG/Driver signup has
-- something to choose from on day one. Govt can add more anytime from the
-- admin panel — new units show up in the signup dropdown automatically.
insert into pwm_units (name, location_name, lat, lng, capacity_kg, status)
select 'Bhilai PWM Unit', 'Bhilai, Chhattisgarh', 21.2094, 81.4285, 5000, 'active'
where not exists (select 1 from pwm_units where name = 'Bhilai PWM Unit');

insert into pwm_units (name, location_name, lat, lng, capacity_kg, status)
select 'Raipur PWM Unit', 'Raipur, Chhattisgarh', 21.2514, 81.6296, 5000, 'active'
where not exists (select 1 from pwm_units where name = 'Raipur PWM Unit');

-- ============================================================
-- Row Level Security
--
-- This app runs entirely from Streamlit (server-side) and only uses the
-- anon public key (no service_role/password) — so we grant the anon
-- role full read/write access on these tables.
--
-- ⚠️ IMPORTANT: This means anyone who knows your Project URL + anon key
-- can read/write this data directly via the Supabase REST API (the anon
-- key is normally considered public/client-safe, but here we're giving
-- it full table access, which typical client-side apps don't do). This
-- is acceptable for an internal government pilot tool, but if this ever
-- becomes public-facing, tighten RLS (add row-level ownership checks, or
-- use service_role + your own server-side auth layer).
-- ============================================================

alter table users enable row level security;
alter table garbage_reports enable row level security;

drop policy if exists "anon full access users" on users;
create policy "anon full access users" on users
  for all
  to anon
  using (true)
  with check (true);

drop policy if exists "anon full access garbage_reports" on garbage_reports;
create policy "anon full access garbage_reports" on garbage_reports
  for all
  to anon
  using (true)
  with check (true);

alter table plastic_rates enable row level security;
drop policy if exists "anon full access plastic_rates" on plastic_rates;
create policy "anon full access plastic_rates" on plastic_rates
  for all
  to anon
  using (true)
  with check (true);

alter table withdrawals enable row level security;
drop policy if exists "anon full access withdrawals" on withdrawals;
create policy "anon full access withdrawals" on withdrawals
  for all
  to anon
  using (true)
  with check (true);

alter table disputes enable row level security;
drop policy if exists "anon full access disputes" on disputes;
create policy "anon full access disputes" on disputes
  for all
  to anon
  using (true)
  with check (true);

alter table sos_alerts enable row level security;
drop policy if exists "anon full access sos_alerts" on sos_alerts;
create policy "anon full access sos_alerts" on sos_alerts
  for all
  to anon
  using (true)
  with check (true);

alter table pwm_units enable row level security;
drop policy if exists "anon full access pwm_units" on pwm_units;
create policy "anon full access pwm_units" on pwm_units
  for all
  to anon
  using (true)
  with check (true);

-- ============================================================
-- Storage buckets — profile photos + pickup-proof photos
-- (The SHG training video is NOT stored here — it's hosted on Google
-- Drive and linked via a constant in supabase_client.py, so no storage
-- bucket or table is needed for it.)
-- ============================================================

insert into storage.buckets (id, name, public)
values ('profile-photos', 'profile-photos', true)
on conflict (id) do nothing;

drop policy if exists "anon can upload profile photos" on storage.objects;
create policy "anon can upload profile photos"
  on storage.objects for insert
  to anon
  with check (bucket_id = 'profile-photos');

drop policy if exists "anon can read profile photos" on storage.objects;
create policy "anon can read profile photos"
  on storage.objects for select
  to anon
  using (bucket_id = 'profile-photos');

-- Pickup-proof photos — driver camera-capture before OTP verification
insert into storage.buckets (id, name, public)
values ('pickup-photos', 'pickup-photos', true)
on conflict (id) do nothing;

drop policy if exists "anon can upload pickup photos" on storage.objects;
create policy "anon can upload pickup photos"
  on storage.objects for insert
  to anon
  with check (bucket_id = 'pickup-photos');

drop policy if exists "anon can read pickup photos" on storage.objects;
create policy "anon can read pickup photos"
  on storage.objects for select
  to anon
  using (bucket_id = 'pickup-photos');

-- ============================================================
-- Done! For a brand-new project, this single run is all you need.
-- Next steps:
--   1. Set SUPABASE_URL and SUPABASE_ANON_KEY in supabase_client.py
--      (Project Settings → API in your Supabase dashboard).
--   2. Set TRAINING_VIDEO_DRIVE_URL in supabase_client.py to your
--      Google Drive share link for the SHG training video.
--   3. Run: streamlit run app.py
--
-- ------------------------------------------------------------
-- MIGRATION NOTES (only relevant for an EXISTING/older Supabase project
-- that already had these tables before this version of the schema —
-- a brand-new project can ignore everything below this line):
--
-- "create table if not exists" does NOT add new columns to a table
-- that already exists. If your users/garbage_reports/withdrawals tables
-- were created by an older version of this file, run these separately:
--
--   alter table garbage_reports add column if not exists
--     plastic_type text default 'Mixed Plastic';
--
--   alter table users add column if not exists current_lat double precision;
--   alter table users add column if not exists current_lng double precision;
--   alter table users add column if not exists location_updated_at timestamptz;
--   alter table users add column if not exists service_radius_km numeric(5,2) default 3;
--
--   alter table garbage_reports add column if not exists pickup_photo_url text;
--
--   alter table withdrawals add column if not exists approved_by integer references users(id);
--   alter table withdrawals add column if not exists approved_at timestamptz;
--   alter table withdrawals drop constraint if exists withdrawals_status_check;
--   alter table withdrawals add constraint withdrawals_status_check
--     check (status in ('pending','paid','rejected'));
--
--   alter table users add column if not exists pwm_unit_id integer;
--
--   alter table users add column if not exists training_video_completed boolean default false;
--
-- (disputes / sos_alerts / pwm_units already use "create table if not
-- exists", so nothing extra is needed for them — just re-running this
-- whole file will also seed "Bhilai PWM Unit" and "Raipur PWM Unit" if
-- they aren't already there.)
--
-- service_radius_km = a Zomato/Blinkit-style "delivery zone" — each
-- driver has their own radius (km); only pending reports within that
-- radius are considered in their "Optimize Route" batch (see
-- select_batch_for_driver in app.py). NULL/0 falls back to the app's
-- default (3km), so this migration is safe for old rows too.
-- ============================================================
