# SentinelMRF — Streamlit + Supabase (anon key) Edition

Ab app **Supabase Project URL + anon public key** se connect hota hai — koi
database password, direct Postgres connection, ya service_role key nahi
chahiye. Tables tum khud ek SQL script chala ke banaoge (`schema.sql`), aur
uske baad app seedha chalega.

---

## 🌐 Live Demo

🚀 **PWMS(Plastic Waste Management System)**

Explore the live website here:

👉 **https://echobyte-nit-web-pwms.onrender.com**


## 💻 GitHub Repository

View the source code and contribute to the project:

👉 **https://github.com/saveyagroup-cell/EchoByte-NIT-WEB-PWMS.git**

## Part 1 — Supabase Project Banayein (agar pehle se nahi hai)

1. [supabase.com](https://supabase.com) par jaake **sign up / login** karein.
2. **"New Project"** dabayein, naam/password/region set karke **"Create new
   project"** dabayein — 1-2 minute mein ban jayega.
   (Yeh database password sirf project setup ke liye hai, app mein nahi
   lagega — humein sirf URL aur anon key chahiye, neeche Part 3 mein.)

---

## Part 2 — SQL Chalayein (Tables + Storage Bucket Banayein)

1. Project ke andar bayi taraf **SQL Editor** par jayein.
2. **"New query"** dabayein.
3. Is repo ki `schema.sql` file ka poora content copy karke wahan paste karein.
4. **"Run"** dabayein.

Yeh ek hi click mein:
- `users` aur `garbage_reports` tables bana dega
- Row Level Security enable karke `anon` role ko access dega (isliye app
  bina password ke, sirf anon key se kaam kar payega)
- `profile-photos` naam ka ek **public Storage bucket** bana dega, jisme
  profile photos upload hongi

Bas — ab dobara yeh step karne ki zarurat nahi, sirf ek baar ka setup hai.

---

## Part 3 — Project URL + Anon Key App Mein Daalein

1. Supabase Dashboard mein: **Project Settings (⚙️)** → **API**.
2. Yahan se 2 values note karein:
   - **Project URL** — jaise `https://abcxyzprojectref.supabase.co`
   - **anon public** key (Project API keys section mein — `service_role`
     wali key **nahi**, `anon` `public` wali)

Do tarike hain inhe app mein daalne ke:

### Option A — Seedha `supabase_client.py` mein edit karein (sabse fast)

```python
SUPABASE_URL = _get_secret("SUPABASE_URL", "https://YOUR-PROJECT-REF.supabase.co")
SUPABASE_ANON_KEY = _get_secret("SUPABASE_ANON_KEY", "YOUR-ANON-PUBLIC-KEY")
```
Placeholder values ko apni actual values se replace kar dein.

### Option B — Streamlit secrets file (deployment ke liye recommended)

Project folder mein `.streamlit/secrets.toml` banayein:
```toml
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR-ANON-PUBLIC-KEY"
```
`supabase_client.py` khud pehle secrets file check karta hai, phir
environment variables, phir hardcoded default.

**Streamlit Community Cloud par deploy karte waqt:** App settings →
**"Secrets"** tab mein yehi 2 lines paste kar dein.

⚠️ `.streamlit/secrets.toml` ko GitHub par public push na karein (`.gitignore`
mein add kar dein).

---

## Part 4 — Install &amp; Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Bas. Koi `init_db()` ya migration step nahi hai — tables Part 2 mein SQL se
hi ban chuke hain.

---

## Roles

- **SHG** (👩‍🌾) — Mobile number + password se signup/login. Report garbage
  form mein **"Use my current location"** button hai (jaise Blinkit/Zomato —
  browser GPS permission mangega), ya manual location search (OpenStreetMap
  Nominatim, free) bhi available hai. Quantity, description ke saath submit
  karte hi ek 4-digit OTP generate hota hai jo driver ko pickup ke waqt dena hai.
- **Driver** (🚚) — Mobile number + password se login. "Optimize Route (OSRM)"
  button pending reports ko real lat/lng se Nearest-Neighbor order deta hai,
  phir OSRM se asli road route map (Folium) par khींचता hai. Har stop card par
  SHG ka **naam aur mobile number** bhi dikhta hai. OTP verify hote hi SHG ka
  wallet automatically credit hota hai (₹2/kg — `app.py` mein `payout` line se
  badal sakte hain).
- **Government** (🏛️) — Email + password se login. KPIs, daily trend chart,
  village-wise bar chart, wallet distribution table, recent activity log.

Teeno roles ke signup form mein **profile photo upload (optional)** hai —
photo Supabase Storage bucket mein jaati hai, table mein sirf uska URL save
hota hai. Driver signup mein ek extra **Vehicle Number** field bhi hai.

---

## Schema (reference ke liye — asli file `schema.sql` hai)

```sql
create table users (
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
  created_at timestamptz default now()
);

create table garbage_reports (
  id serial primary key,
  shg_id integer not null references users(id) on delete cascade,
  village text,
  location_name text,
  lat double precision,
  lng double precision,
  quantity_kg numeric(10,2) not null,
  description text,
  status text default 'pending' check (status in ('pending','assigned','collected')),
  otp text,
  created_at timestamptz default now(),
  collected_at timestamptz
);
```

---

## ⚠️ Security Note (zaroor padhein)

`schema.sql` in dono tables par RLS policy set karta hai jo `anon` role ko
**pura read/write access** deti hai (`using (true)`) — kyunki yeh app sirf
anon key use karta hai, koi service_role ya server-side session nahi.

Iska matlab: jo bhi tumhari Project URL + anon key jaanta hai, woh Supabase
REST API se seedha is data ko padh/likh sakta hai (anon key GitHub jaisi
public jagah par kabhi na daalein, phir bhi ise "secret" jaisa treat karein).
Ek internal Chhattisgarh government pilot tool ke liye yeh acceptable trade-off
hai (simplicity ke liye). Agar aage chalke isse zyada public-facing/sensitive
banana ho, to consider karein:
- Row-level ownership checks add karna RLS policies mein (e.g. SHG sirf apna
  data dekh/badal sake)
- Ya phir service_role key + apna khud ka server-side auth layer

---

## Notes / production ke liye aage kya sudharein

- Password hashing abhi plain `sha256` hai (demo ke liye theek hai). Production
  mein `bcrypt` ya `argon2` use karein.
- Wallet credit "fetch current value, phir update" pattern se ho raha hai
  (Postgrest mein seedha `wallet = wallet + x` jaisa atomic increment query-builder
  se nahi hota) — bahut high concurrency mein race condition ban sakti hai;
  production ke liye ek Postgres function (RPC) banana better hoga.
- OTP sirf pickup-verification ke liye hai, login ke liye nahi (login
  mobile+password se hai).
- Nominatim aur OSRM dono free public services hain — bahut zyada requests
  bhejne par rate-limit ho sakta hai; production ke liye apna khud ka hosted
  OSRM instance ya paid geocoding service consider karein.
