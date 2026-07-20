-- ============================================================
-- SentinelMRF — Supabase SQL Setup
-- Ise Supabase Dashboard -> SQL Editor mein paste karke "Run" karein.
-- Ek hi baar chalana hai (project setup ke waqt).
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

-- Govt-controlled rate card: har plastic type ke liye SHG aur Driver ko
-- kitna ₹/kg milega, yeh govt yahan se set karti hai. Collection verify
-- hone par isi table se dono ke wallet calculate hote hain.
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
-- Yeh app poora Streamlit (server-side) se chalta hai aur sirf anon public
-- key use karta hai (koi service_role/password nahi) — isliye anon role ko
-- in tables par pura read/write access de rahe hain.
--
-- ⚠️ IMPORTANT: Iska matlab hai ki jo bhi tumhari Project URL + anon key
-- jaanta hai, woh Supabase REST API se seedha yeh data padh/likh sakta hai
-- (anon key already public/client-safe maani jaati hai, lekin yahan hum
-- usse full table access de rahe hain, jo normally client-side apps mein
-- nahi karte). Ek internal government pilot tool ke liye yeh acceptable
-- hai, lekin agar aage chalke isse public-facing banana ho, to RLS ko
-- tighten karna (row-level ownership checks add karna, ya service_role +
-- apna khud ka server-side auth layer use karna).
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
-- Storage bucket — profile photos
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
-- Done! Ab app.py chalao — SUPABASE_URL aur SUPABASE_ANON_KEY sahi
-- daalne ke baad seedha kaam karega, koi aur SQL/setup step nahi chahiye.
--
-- NOTE: Agar tumhara Supabase project PEHLE se bana hua hai (purana data
-- already hai), to yeh poora file dobara "Run" karna safe hai — sab
-- "if not exists" / "on conflict do nothing" hai, kuch delete nahi hoga.
-- Bas ek cheez manually check kar lena: agar garbage_reports/users table
-- pehle se hai to naye columns apne aap add nahi honge ("create table
-- if not exists" purane table ko touch nahi karta). Us case mein neeche
-- wali lines alag se Supabase SQL editor mein chala dena:
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
-- (disputes / sos_alerts / pwm_units khud "create table if not exists" hain,
-- unke liye alag se kuch nahi chalana — bas poora file dobara Run kar dena,
-- isse "Bhilai PWM Unit" aur "Raipur PWM Unit" bhi seed ho jaayenge agar
-- pehle se nahi hain.)
--
-- service_radius_km = Zomato/Blinkit-style "delivery zone" — har driver ka
-- apna radius (km) hota hai; sirf usi radius ke andar wale pending reports
-- uski "Optimize Route" batch mein consider hote hain (dekho app.py mein
-- select_batch_for_driver). NULL/0 rehne par app khud fallback default
-- (3km) use kar leta hai, isliye yeh migration purane rows ke liye bhi safe hai.
-- ============================================================