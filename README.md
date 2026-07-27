# ♻️ EchoByte — Plastic Waste Management System (PWMS)

### Government of Chhattisgarh · Urban Administration & Development

> **Connecting SHGs, Drivers, and Government for Smarter Plastic Waste Management**

EchoByte is a digital **Plastic Waste Management System (PWMS)** designed to connect Self-Help Groups (SHGs), waste collection drivers, and government authorities on a single platform.

---

# 1. 📖 Project Overview

Plastic waste collection in rural and urban communities often faces challenges such as unstructured reporting, inefficient collection routes, lack of pickup verification, and limited visibility for government authorities.

**EchoByte** provides a technology-driven platform to simplify and digitize this process.

The system connects three major stakeholders:

* 👩‍🌾 **Self-Help Groups (SHGs)** — Report plastic waste and receive payments.
* 🚚 **Drivers** — Collect reported waste using optimized routes.
* 🏛️ **Government Authorities** — Monitor collection activities and system performance.

## 👩‍🌾 SHG Module

SHG members can:

* Sign up and log in using a mobile number and password
* Upload an optional profile photo
* Report available plastic waste
* Enter waste quantity and description
* Use the device's current GPS location
* Search for locations manually
* Generate a **4-digit pickup verification OTP**
* Track submitted waste reports
* Receive payment in their wallet after successful collection

## 🚚 Driver Module

Drivers can:

* Sign up and log in using a mobile number and password
* Register their vehicle number
* View pending waste collection requests
* View SHG details and waste quantity
* Access pickup locations
* Optimize collection routes
* View routes on an interactive map
* Verify collection using the SHG's OTP
* Mark waste reports as collected

The route optimization system uses actual latitude and longitude coordinates with a **Nearest-Neighbor approach and OSRM** for road-based routing.

## 🏛️ Government Module

Government authorities can access a centralized monitoring dashboard containing:

* Key Performance Indicators (KPIs)
* Plastic waste collection statistics
* Daily collection trends
* Village-wise collection analysis
* SHG wallet distribution
* Recent collection activities
* Overall system monitoring

## 💰 SHG Wallet System

After successful OTP verification, the collected waste is confirmed and the SHG wallet is automatically credited.

The current payout is:

**₹2 per kg of collected plastic waste**

## 🗺️ Location & Route Optimization

EchoByte integrates:

* Browser Geolocation
* OpenStreetMap
* Nominatim
* Folium
* OSRM
* Nearest-Neighbor Route Optimization

These technologies help identify collection points and generate efficient road-based collection routes for drivers.

## 🛠️ Technology Stack

| Category             | Technology                 |
| -------------------- | -------------------------- |
| Programming Language | Python                     |
| Web Framework        | Streamlit                  |
| Database             | PostgreSQL / Supabase      |
| Backend Service      | Supabase                   |
| Storage              | Supabase Storage           |
| Maps                 | Folium / OpenStreetMap     |
| Geocoding            | Nominatim                  |
| Routing              | OSRM                       |
| Route Optimization   | Nearest-Neighbor Algorithm |
| Location             | Browser Geolocation        |
| Authentication       | Role-Based Login           |
| Pickup Verification  | 4-Digit OTP                |
| Deployment           | Render                     |

---

# 2. ⚙️ Installation Guide

## Prerequisites

Before installing the project, make sure you have:

* Python installed
* Git installed
* pip installed
* A Supabase account
* A Supabase project

## Step 1 — Clone the Repository

```bash
git clone https://github.com/saveyagroup-cell/EchoByte-Uniceff-WEB-PWMS.git
```

Navigate to the project directory:

```bash
cd EchoByte-Uniceff-WEB-PWMS
```

## Step 2 — Create a Virtual Environment

```bash
python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

### Linux / macOS

```bash
source venv/bin/activate
```

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4 — Configure Supabase

Create a new project in Supabase.

After creating the project:

1. Open the **SQL Editor**
2. Click **New Query**
3. Open the `schema.sql` file from this repository
4. Copy the complete SQL script
5. Paste it into the Supabase SQL Editor
6. Click **Run**

The SQL script creates the required:

* `users` table
* `garbage_reports` table
* Row Level Security policies
* `profile-photos` Storage bucket

The database setup only needs to be performed once.

## Step 5 — Run the Application

```bash
streamlit run app.py
```

The application should now start on your local machine.

---

# 3. 🔐 Environment Variables

EchoByte connects to Supabase using:

* `SUPABASE_URL`
* `SUPABASE_ANON_KEY`

The application does **not** require a direct PostgreSQL connection or `service_role` key.

## Get Supabase Credentials

Open your Supabase project and navigate to the API settings.

Copy your:

```text
Project URL
Anon / Public Key
```

> ⚠️ Use the **anon/public key**, not the `service_role` key.

## Option 1 — Streamlit Secrets

Create:

```text
.streamlit/secrets.toml
```

Add:

```toml
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR-ANON-PUBLIC-KEY"
```

Add the secrets file to `.gitignore`:

```gitignore
.streamlit/secrets.toml
```

> ⚠️ Never commit credentials or secret configuration files to a public GitHub repository.

## Option 2 — Environment Variables

You can also configure:

```text
SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_ANON_KEY=YOUR-ANON-PUBLIC-KEY
```

The application automatically reads the Supabase configuration through `supabase_client.py`.

---

# 4. 🚀 Deployment Instructions

The application can be deployed using **Render**.

## Step 1 — Push the Project to GitHub

Make sure the latest version of the application is available in the repository:

```bash
git add .
git commit -m "Update EchoByte PWMS"
git push origin main
```

## Step 2 — Create a Render Web Service

1. Log in to Render
2. Select **New Web Service**
3. Connect your GitHub account
4. Select:

```text
EchoByte-Uniceff-WEB-PWMS
```

## Step 3 — Build Command

Configure the build command as:

```bash
pip install -r requirements.txt
```

## Step 4 — Start Command

Configure the start command as:

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Step 5 — Add Environment Variables

Inside the Render Environment settings, add:

```text
SUPABASE_URL = YOUR_SUPABASE_PROJECT_URL
SUPABASE_ANON_KEY = YOUR_SUPABASE_ANON_KEY
```

## Step 6 — Deploy

Click **Deploy**.

Render will install the dependencies and start the Streamlit application.

---

# 5. 👥 Team Members

| Team Member       | Role      | Responsibility                   |
| ----------------- | --------- | -------------------------------- |
| **Nomend Kumar Sahu** | Team Lead | Project Management & Development |
| **Yogesh Kumar Yadav** | Developer | Backend & Supabase Integration   |
| **Harsha Sahu** | Developer | Frontend & UI/UX                 |
| **Dagendra Kumar Sahu** | Developer | Maps & Route Optimization        |
| **Jayant Verma** | Developer | Maps & Route Optimization        |


---

# 6. 📸 System Screenshots

The following section demonstrates the major modules and interfaces of the EchoByte platform.

## 🏠 Main Page

**Government of Chhattisgarh · Urban Administration & Development**
<img width="1315" height="595" alt="image" src="https://github.com/user-attachments/assets/98f3488d-24fb-48f3-b99a-92ab424ac590" />


### EchoByte

**Connecting SHGs, Drivers, and Government for Smarter Plastic Waste Management**

```text
Add Main Page Screenshot Here
```

---

## 🔐 Login & Registration

Users can select their role and either log in to an existing account or create a new account.

```text
Add Login / Signup Screenshot Here
```

---

## 👩‍🌾 SHG Dashboard

The SHG Dashboard allows users to report plastic waste, manage reports, check pickup status, and monitor their wallet.

```text
Add SHG Dashboard Screenshot Here
```

---

## 🗑️ Garbage Reporting System

SHG members can submit:

* Waste quantity
* Description
* Village
* Collection location
* GPS coordinates

```text
Add Garbage Reporting Screenshot Here
```

---

## 📍 Current Location Detection

Users can select **"Use My Current Location"** and allow browser location permission to automatically identify the collection location.

```text
Add Location Screenshot Here
```

---

## 🔢 Pickup OTP

A 4-digit OTP is generated when a waste report is successfully submitted.

The SHG member provides this OTP to the driver during collection.

```text
Add OTP Screenshot Here
```

---

## 🚚 Driver Dashboard

Drivers can view pending waste collection requests along with:

* SHG name
* Mobile number
* Location
* Waste quantity
* Collection status

```text
Add Driver Dashboard Screenshot Here
```

---

## 🗺️ Optimized Collection Route

The system uses location coordinates and OSRM to display an optimized road-based collection route.

```text
Add Route Optimization Screenshot Here
```

---

## ✅ Pickup Verification

The driver enters the OTP provided by the SHG.

After successful verification:

```text
OTP Verified
      ↓
Waste Collected
      ↓
Report Updated
      ↓
SHG Wallet Credited
```

```text
Add Pickup Verification Screenshot Here
```

---

## 🏛️ Government Dashboard

Government authorities can monitor the plastic waste management ecosystem through analytics and reports.

The dashboard includes:

* KPIs
* Collection statistics
* Daily trends
* Village-wise analysis
* Wallet distribution
* Recent activities

```text
Add Government Dashboard Screenshot Here
```

---

# 7. 🌐 Live Demo

Experience the deployed **EchoByte — Plastic Waste Management System (PWMS)**:

### 🚀 Live Application

https://echobyte-nit-web-pwms.onrender.com

### 💻 GitHub Repository

https://github.com/saveyagroup-cell/EchoByte-Uniceff-WEB-PWMS

---

# 🔒 Security Note

The current version is designed primarily as a pilot/prototype.

The Supabase configuration uses an anon key with RLS policies that provide the application with the required database access.

For a production deployment, recommended improvements include:

* Supabase Authentication
* User-specific Row Level Security policies
* `bcrypt` or `Argon2` password hashing
* Secure server-side authentication
* Atomic PostgreSQL RPC functions for wallet transactions
* Rate limiting
* Production-grade geocoding services
* Self-hosted or production routing infrastructure

Never expose a Supabase `service_role` key in frontend code or a public repository.

---

# 🔮 Future Scope

Future versions of EchoByte can include:

* 🤖 AI-based plastic waste classification
* 📷 Image-based waste verification
* 🚛 Advanced multi-vehicle route optimization
* 📱 Dedicated Android/iOS application
* 📊 Advanced government analytics
* 🔔 Real-time pickup notifications
* 💳 Digital payment integration
* 🛰️ GIS-based waste hotspot monitoring
* 📈 Predictive waste generation analytics
* 🏆 SHG reward and incentive system

---

# ♻️ EchoByte

### Connecting Communities. Optimizing Collection. Building a Cleaner Chhattisgarh.

**Chhattisgarh · EchoByte Pilot**
