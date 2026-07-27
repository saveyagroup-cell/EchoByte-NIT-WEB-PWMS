# SentinelMRF — Streamlit + Supabase (Anon Key) Edition

The app now connects using the **Supabase Project URL + anon public key** — no database password, direct PostgreSQL connection, or `service_role` key is required.

You only need to create the required tables once by running the provided `schema.sql` script. After that, the application is ready to run.

---

## 🌐 Live Demo

🚀 **PWMS (Plastic Waste Management System)**

Explore the live website here:

👉 https://echobyte-nit-web-pwms.onrender.com

---

## 💻 GitHub Repository

View the source code and contribute to the project:

👉 https://github.com/saveyagroup-cell/EchoByte-NIT-WEB-PWMS.git

---

## Part 1 — Create a Supabase Project

If you already have a Supabase project, you can skip this section.

1. Go to **Supabase** and sign up or log in.
2. Click **"New Project"**.
3. Set the project name, database password, and region.
4. Click **"Create new project"**.
5. Wait approximately 1–2 minutes for the project to be created.

> **Note:** The database password is only required during project setup. The application itself does not use it. We only need the **Project URL** and **anon public key**, which are explained in Part 3.

---

## Part 2 — Run the SQL Script

The next step is to create the required database tables and Storage bucket.

1. Open your Supabase project.
2. From the left sidebar, go to **SQL Editor**.
3. Click **"New query"**.
4. Open the `schema.sql` file included in this repository.
5. Copy its entire contents and paste them into the SQL Editor.
6. Click **"Run"**.

Running this script will automatically:

* Create the `users` table.
* Create the `garbage_reports` table.
* Enable Row Level Security (RLS).
* Give the `anon` role the required access so the application can work using only the anon key.
* Create a public Supabase Storage bucket named `profile-photos`.
* Configure the bucket for storing user profile photos.

This setup only needs to be performed **once**.

---

## Part 3 — Add the Project URL and Anon Key

In the Supabase Dashboard, go to:

**Project Settings (⚙️) → API**

Copy the following two values:

* **Project URL** — for example: `https://abcxyzprojectref.supabase.co`
* **anon public key** — available under the Project API Keys section.

> ⚠️ Do **not** use the `service_role` key. Use the `anon` / `public` key.

There are two ways to configure these values.

### Option A — Edit `supabase_client.py`

This is the fastest method for local testing.

```python
SUPABASE_URL = _get_secret(
    "SUPABASE_URL",
    "https://YOUR-PROJECT-REF.supabase.co"
)

SUPABASE_ANON_KEY = _get_secret(
    "SUPABASE_ANON_KEY",
    "YOUR-ANON-PUBLIC-KEY"
)
```

Replace the placeholder values with your actual Supabase credentials.

### Option B — Use Streamlit Secrets

This method is recommended for deployment.

Create the following file inside your project:

`.streamlit/secrets.toml`

Add:

```toml
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR-ANON-PUBLIC-KEY"
```

The `supabase_client.py` file automatically checks for configuration values in the following order:

1. Streamlit secrets
2. Environment variables
3. Hardcoded default values

### Streamlit Community Cloud

When deploying on Streamlit Community Cloud:

Go to:

**App Settings → Secrets**

Then paste:

```toml
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR-ANON-PUBLIC-KEY"
```

> ⚠️ Do not push `.streamlit/secrets.toml` to a public GitHub repository. Add it to `.gitignore`.

---

## Part 4 — Install and Run

Install all required dependencies:

```bash
pip install -r requirements.txt
```

Run the Streamlit application:

```bash
streamlit run app.py
```

That's it.

There is no separate `init_db()` or migration step because all required tables were already created using the SQL script in Part 2.

---

# 👥 User Roles

The system supports three primary roles:

## 👩‍🌾 SHG — Self-Help Group

SHG users can sign up and log in using their **mobile number and password**.

The garbage reporting form provides a **"Use my current location"** option.

Similar to applications such as Blinkit or Zomato, the browser requests GPS/location permission from the user.

Alternatively, users can manually search for their location using **OpenStreetMap Nominatim**, which is available as a free geocoding service.

An SHG user can submit:

* Location
* Plastic waste quantity
* Description
* Other report information

After submitting the report, the system automatically generates a **4-digit OTP**.

The SHG member provides this OTP to the driver during waste pickup to verify the collection.

---

## 🚚 Driver

Drivers log in using their **mobile number and password**.

The Driver Dashboard includes an:

**"Optimize Route (OSRM)"** button.

When clicked, the system:

1. Retrieves pending garbage reports.
2. Uses their actual latitude and longitude coordinates.
3. Applies a **Nearest-Neighbor route optimization approach**.
4. Uses OSRM to calculate the actual road route.
5. Displays the optimized route on an interactive **Folium map**.

Each collection stop displays important SHG information, including:

* SHG name
* Mobile number
* Location
* Waste quantity
* Collection information

During pickup, the driver enters the OTP provided by the SHG member.

Once the OTP is successfully verified:

* The report is marked as collected.
* The collection is confirmed.
* The SHG wallet is automatically credited.

The current payout rate is:

**₹2 per kg**

This can be modified using the `payout` logic inside `app.py`.

---

## 🏛️ Government

Government users log in using their **email and password**.

The Government Dashboard provides monitoring and analytics features such as:

* Key Performance Indicators (KPIs)
* Daily collection trend charts
* Village-wise collection bar charts
* SHG wallet distribution table
* Recent activity log

This allows government authorities to monitor plastic waste collection activities and overall system performance.

---

# 📸 Profile Photos

All three roles support an optional **profile photo upload** during signup.

The actual image is uploaded to the Supabase Storage bucket:

`profile-photos`

Only the image URL is stored in the database table.

Driver registration also contains an additional:

**Vehicle Number**

field.

---

# 🗄️ Database Schema

The actual database setup is available in `schema.sql`.

For reference, the main tables are:

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
  status text default 'pending'
    check (status in ('pending','assigned','collected')),
  otp text,
  created_at timestamptz default now(),
  collected_at timestamptz
);
```

---

# ⚠️ Security Note

Please read this section carefully.

The `schema.sql` file configures Row Level Security policies for both tables that currently allow the `anon` role **full read/write access** using policies equivalent to:

```sql
using (true)
```

This approach is used because the application operates entirely with the Supabase anon key and does not use a `service_role` key or server-side authenticated database session.

This means that anyone who obtains your **Project URL + anon key** may potentially interact directly with the Supabase REST API and read or modify accessible data.

For an internal Chhattisgarh government pilot or demonstration project, this architecture may provide a simple development setup.

However, for a public-facing or production application, stronger security controls should be implemented.

Recommended improvements include:

* Add row-level ownership checks to RLS policies so SHG users can only access or modify their own data.
* Implement proper Supabase Authentication and user-based RLS policies.
* Alternatively, use a secure server-side backend with the `service_role` key stored only on the server.
* Never expose the `service_role` key in frontend code or a public repository.

---

# 🚀 Recommended Production Improvements

### 1. Stronger Password Hashing

Passwords are currently hashed using plain `SHA-256`.

This may be acceptable for a prototype or demonstration, but it should not be used as a production password-storage mechanism.

For production, use a password hashing algorithm such as:

* `bcrypt`
* `Argon2`

---

### 2. Atomic Wallet Transactions

The current wallet credit process follows this pattern:

```text
Fetch current wallet balance
        ↓
Calculate new balance
        ↓
Update wallet
```

PostgREST's standard query builder does not directly provide an atomic operation such as:

```text
wallet = wallet + amount
```

Under high concurrency, the current implementation could therefore create a **race condition**.

For production, a PostgreSQL function should be created and called through **Supabase RPC** to perform wallet updates atomically.

---

### 3. OTP Purpose

The OTP is used only for **waste pickup verification**.

It is **not** used for login authentication.

Users currently log in using:

**Mobile Number + Password**

Government users use:

**Email + Password**

---

### 4. Geocoding and Route Optimization Limits

The application currently uses:

* **Nominatim** for geocoding and location search.
* **OSRM** for road-based route calculation and optimization.

Both provide public services that are useful for development and prototypes.

However, public instances may enforce rate limits when a large number of requests are made.

For a production deployment with significant traffic, consider:

* Hosting your own OSRM instance.
* Using a production-grade or paid geocoding API.
* Implementing caching to reduce repeated API requests.
* Adding request throttling and retry mechanisms.

---

# 🛠️ Technology Stack

**Frontend / Application**

* Streamlit
* Python

**Database & Storage**

* Supabase
* PostgreSQL
* Supabase Storage
* Row Level Security (RLS)

**Maps & Location**

* Folium
* OpenStreetMap
* Nominatim
* Browser Geolocation

**Route Optimization**

* OSRM
* Nearest-Neighbor Algorithm

**Authentication**

* Role-based login system
* Mobile + Password for SHG and Driver
* Email + Password for Government users

**Waste Collection Verification**

* 4-digit OTP

**Payment / Wallet**

* Automatic SHG wallet credit after successful pickup verification

---

## 🌐 Live Application

**PWMS — Plastic Waste Management System**

https://echobyte-nit-web-pwms.onrender.com

## 💻 Source Code

**GitHub Repository**

https://github.com/saveyagroup-cell/EchoByte-NIT-WEB-PWMS.git
