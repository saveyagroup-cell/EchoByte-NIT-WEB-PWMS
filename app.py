"""
EchoByte — Connecting SHGs, Drivers, and Governments for Smarter Plastic Waste Management
Streamlit + AWS (RDS Postgres + S3) version

Before running:
    1. Run schema.sql on your RDS Postgres instance (one time only)
    2. Set DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/S3_BUCKET in db_client.py (or Streamlit secrets / env vars)
    3. pip install -r requirements.txt
    4. streamlit run app.py

The full setup guide is in README.md.
"""
import streamlit as st

# set_page_config() MUST be the very first Streamlit command — that's why
# this is here, before any other import (especially db_client, which
# touches st.secrets). Do not move this below or after another import,
# otherwise you'll get a "set_page_config() can only be called once..." error.
st.set_page_config(page_title="EchoByte", page_icon="🗑️", layout="wide")

import pandas as pd
import hashlib
import random
import math
import os
import base64
import re
import requests
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", message=".*only supports SQLAlchemy.*")
import folium
from folium.plugins import AntPath, HeatMap
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation
from fpdf import FPDF
import tempfile
import matplotlib
matplotlib.use("Agg")  # headless rendering — no GUI display server needed
import matplotlib.pyplot as plt

import httpx

import streamlit.components.v1 as components
from supabase_client import get_client, upload_photo, PICKUP_BUCKET_NAME, get_training_video_url

# ============================================================
# Setup
# ============================================================
sb = get_client()

DEPOT = {"lat": 21.2350, "lng": 81.6420, "name": "Mathpurena Depot"}
OSRM_URL = "https://router.project-osrm.org"

# Zomato/Blinkit-style delivery zones: every driver has their own "service
# radius" — only pending reports inside that radius are considered when
# building their route batch. DEFAULT_SERVICE_RADIUS_KM is used when a
# driver hasn't set/selected a radius yet (new driver, or an old row where
# the column is still NULL).
DEFAULT_SERVICE_RADIUS_KM = 3
SERVICE_RADIUS_OPTIONS_KM = [2, 3, 4, 5, 6, 8, 10]

# ============================================================
# Global error handling
#
# Any unexpected error (Supabase/network issues, timeouts, no internet,
# etc.) is caught and shown to the user as a short popup instead of a
# raw Python traceback.
# ============================================================
_NETWORK_ERRORS = (
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
    httpx.WriteTimeout, httpx.WriteError, httpx.ReadError,
    httpx.RemoteProtocolError, httpx.NetworkError, httpx.TimeoutException,
    ConnectionError, TimeoutError, OSError,
)


def _is_streamlit_control_flow(exc: BaseException) -> bool:
    """Streamlit raises internal exceptions for st.rerun()/st.stop(); these
    must always be allowed to propagate and never be treated as errors."""
    return exc.__class__.__name__ in ("RerunException", "StopException")


def _friendly_error_message(exc: Exception) -> str:
    """Turns a technical exception into a short, user-facing message."""
    if isinstance(exc, _NETWORK_ERRORS):
        return "No internet connection. Please check your network and try again."
    return "Something went wrong. Please try again in a moment."


@st.dialog("Notice")
def _error_popup(message: str):
    st.warning(message)
    if st.button("OK", use_container_width=True):
        st.rerun()


def show_error(exc: Exception):
    """Shows a friendly popup for an exception (re-raises Streamlit's own
    internal control-flow exceptions so rerun/stop keep working)."""
    if _is_streamlit_control_flow(exc):
        raise exc
    _error_popup(_friendly_error_message(exc))


def safe_call(fn, *args, **kwargs):
    """Runs fn(*args, **kwargs); on failure, shows a popup instead of
    crashing the app with a traceback."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        show_error(e)
        st.stop()


# ---- Environmental Impact estimates (SHG dashboard) ----
# Rough, commonly-cited awareness-level factors (not a precise LCA study):
# ~1.5 kg CO2 avoided per kg of plastic diverted from landfill/burning, and
# roughly 1 tree absorbs ~20kg CO2/year, so kg_recycled * 1.5 / 20 ≈ "trees saved".
CO2_KG_SAVED_PER_KG_PLASTIC = 1.5
CO2_KG_ABSORBED_PER_TREE_PER_YEAR = 20

# ---- Live ETA estimate (SHG dashboard) ----
# Simple average speed assumption for rural CG roads — used only for a
# rough "X min away" indicator, not turn-by-turn accuracy.
AVG_DRIVER_SPEED_KMPH = 25

ROLE_LABELS = {"shg": "👩‍🌾 SHG", "driver": "🚚 Driver", "govt": "🏛️ Government"}

# ============================================================
# Logo placeholder — drop your combined image with this exact filename
# into the assets/ folder and it will show up automatically.
# ============================================================
LOGO_HEADER_PATH = "assets/header_logo.png"   # combined NIT Raipur + CG Govt + UNICEF logo

# ============================================================
# Multi-language support — English (default), Hindi, Chhattisgarhi
# ============================================================
LANGS = {"en": "English", "hi": "हिंदी", "cg": "छत्तीसगढ़ी"}

TRANSLATIONS = {
    "en": {
        "app_title": "EchoByte", "app_tagline": "Connecting SHGs, Drivers, and Governments for Smarter Plastic Waste Management",
        "dept_line": "Government of Chhattisgarh · Urban Administration & Development",
        "role_shg": "👩‍🌾 SHG", "role_driver": "🚚 Driver", "role_govt": "🏛️ Government",
        "login": "Login", "signup": "Sign Up", "mobile": "Mobile Number", "email": "Email",
        "password": "Password", "full_name": "Full Name", "village": "Village Name",
        "vehicle_no": "Vehicle Number", "photo_optional": "Profile Photo (optional)",
        "create_account": "Create Account", "logout": "Logout",
        "fill_all_fields": "Please fill all fields.", "wrong_credentials": "Wrong mobile/email or password.",
        "shg_portal": "SHG Portal", "profile": "Profile", "name": "Name",
        "wallet": "Wallet", "balance": "Balance", "withdraw": "Withdraw Funds",
        "withdraw_amount": "Amount (₹)", "withdraw_method": "Withdraw to",
        "upi": "UPI", "bank": "Bank Account", "card": "Card",
        "withdraw_details": "Account details", "submit_withdraw": "Request Withdrawal",
        "withdraw_success": "Withdrawal request submitted!", "insufficient_balance": "Amount exceeds wallet balance.",
        "withdraw_history": "Withdrawal History", "no_withdrawals": "No withdrawals yet.",
        "training_gate_title": "📹 Training Video (Required)",
        "training_gate_msg": "Please watch the training video first. Once you confirm below, you'll be able to submit your collection reports.",
        "training_gate_no_video": "Training video is not set up yet. Please contact the admin.",
        "training_gate_done": "✅ Training completed! You can now submit reports below.",
        "training_gate_confirm_checkbox": "I have watched the complete training video",
        "training_gate_confirm_btn": "✅ Mark Training as Complete",
        "report_garbage": "Report Garbage", "quantity_kg": "Quantity (kg)", "plastic_type": "Plastic Type",
        "description": "Description", "submit_report": "Submit Report", "your_reports": "Your Reports",
        "driver_dashboard": "Driver Dashboard", "my_profile": "My Profile", "active_stops": "Active Stops",
        "fuel_optimized": "Fuel Optimized", "optimize_route": "Optimize Route (OSRM)", "otp": "OTP",
        "verify_collect": "Verify & Collect", "wrong_otp": "Wrong OTP.",
        "govt_dashboard": "Government Dashboard",
        "govt_caption": "Chhattisgarh EchoByte Pilot — SHG, Driver, and Village-wise aggregate view.",
        "total_collected": "Total Collected (kg)", "pending": "Pending", "collected": "Collected",
        "shgs_registered": "SHGs Registered", "drivers_registered": "Drivers Registered",
        "trend_daily": "Trend — Daily Collection (kg)", "village_wise": "Village-wise Quantity (kg)",
        "wallet_distribution": "Wallet Distribution (SHGs)", "recent_activity": "Recent Activity",
        "plastic_rate_settings": "Plastic Rate Settings", "shg_rate": "SHG Rate", "driver_rate": "Driver Rate",
        "save_rates": "Save Rates", "rates_saved": "Rates updated.",
        "withdrawal_requests": "Withdrawal Requests", "mark_paid": "Mark Paid",
        "status": "Status", "method": "Method", "amount": "Amount (₹)",
        "download_pdf_report": "Download PDF Report",
        "language": "Language",
    },
    "hi": {
        "app_title": "EchoByte", "app_tagline": "SHG, चालकों और सरकार को जोड़कर बेहतर प्लास्टिक कचरा प्रबंधन",
        "dept_line": "छत्तीसगढ़ सरकार · नगरीय प्रशासन एवं विकास विभाग",
        "role_shg": "👩‍🌾 स्वयं सहायता समूह", "role_driver": "🚚 चालक", "role_govt": "🏛️ सरकार",
        "login": "लॉगिन", "signup": "नया खाता बनाएं", "mobile": "मोबाइल नंबर", "email": "ईमेल",
        "password": "पासवर्ड", "full_name": "पूरा नाम", "village": "गांव का नाम",
        "vehicle_no": "वाहन नंबर", "photo_optional": "प्रोफ़ाइल फोटो (वैकल्पिक)",
        "create_account": "खाता बनाएं", "logout": "लॉगआउट",
        "fill_all_fields": "कृपया सभी जानकारी भरें।", "wrong_credentials": "गलत मोबाइल/ईमेल या पासवर्ड।",
        "shg_portal": "स्वयं सहायता समूह पोर्टल", "profile": "प्रोफ़ाइल", "name": "नाम",
        "wallet": "वॉलेट", "balance": "बैलेंस", "withdraw": "पैसे निकालें",
        "withdraw_amount": "राशि (₹)", "withdraw_method": "निकालने का तरीका",
        "upi": "यूपीआई", "bank": "बैंक खाता", "card": "कार्ड",
        "withdraw_details": "खाता विवरण", "submit_withdraw": "निकासी का अनुरोध करें",
        "withdraw_success": "निकासी का अनुरोध भेज दिया गया!", "insufficient_balance": "राशि वॉलेट बैलेंस से ज्यादा है।",
        "withdraw_history": "निकासी इतिहास", "no_withdrawals": "अभी तक कोई निकासी नहीं हुई।",
        "training_gate_title": "📹 प्रशिक्षण वीडियो (आवश्यक)",
        "training_gate_msg": "कृपया पहले प्रशिक्षण वीडियो देखें। नीचे कन्फर्म करते ही आप अपनी रिपोर्ट भेज सकेंगी।",
        "training_gate_no_video": "प्रशिक्षण वीडियो अभी सेट नहीं हुआ है। कृपया एडमिन से संपर्क करें।",
        "training_gate_done": "✅ प्रशिक्षण पूरा हुआ! अब आप नीचे रिपोर्ट भेज सकती हैं।",
        "training_gate_confirm_checkbox": "मैंने पूरा प्रशिक्षण वीडियो देख लिया है",
        "training_gate_confirm_btn": "✅ प्रशिक्षण पूर्ण के रूप में चिह्नित करें",
        "report_garbage": "कचरा रिपोर्ट करें", "quantity_kg": "मात्रा (किग्रा)", "plastic_type": "प्लास्टिक का प्रकार",
        "description": "विवरण", "submit_report": "रिपोर्ट भेजें", "your_reports": "आपकी रिपोर्ट्स",
        "driver_dashboard": "चालक डैशबोर्ड", "my_profile": "मेरी प्रोफ़ाइल", "active_stops": "सक्रिय स्टॉप",
        "fuel_optimized": "ईंधन बचत", "optimize_route": "मार्ग अनुकूलित करें (OSRM)", "otp": "ओटीपी",
        "verify_collect": "सत्यापित करें और लें", "wrong_otp": "गलत ओटीपी।",
        "govt_dashboard": "सरकारी डैशबोर्ड",
        "govt_caption": "छत्तीसगढ़ EchoByte पायलट — SHG, चालक और गांव-वार सारांश।",
        "total_collected": "कुल संग्रहित (किग्रा)", "pending": "लंबित", "collected": "संग्रहित",
        "shgs_registered": "पंजीकृत SHG", "drivers_registered": "पंजीकृत चालक",
        "trend_daily": "दैनिक संग्रह प्रवृत्ति (किग्रा)", "village_wise": "गांव-वार मात्रा (किग्रा)",
        "wallet_distribution": "वॉलेट वितरण (SHG)", "recent_activity": "हाल की गतिविधि",
        "plastic_rate_settings": "प्लास्टिक दर सेटिंग्स", "shg_rate": "SHG दर", "driver_rate": "चालक दर",
        "save_rates": "दरें सहेजें", "rates_saved": "दरें अपडेट हो गईं।",
        "withdrawal_requests": "निकासी अनुरोध", "mark_paid": "भुगतान हुआ अंकित करें",
        "status": "स्थिति", "method": "तरीका", "amount": "राशि (₹)",
        "download_pdf_report": "पीडीएफ रिपोर्ट डाउनलोड करें",
        "language": "भाषा",
    },
    "cg": {
        "app_title": "EchoByte", "app_tagline": "SHG, ड्राइवर अउ सरकार ला जोड़के बढ़िया प्लास्टिक कचरा प्रबंधन",
        "dept_line": "छत्तीसगढ़ सरकार · नगरीय प्रशासन अउ विकास विभाग",
        "role_shg": "👩‍🌾 स्वयं सहायता समूह", "role_driver": "🚚 ड्राइवर", "role_govt": "🏛️ सरकार",
        "login": "लॉगिन", "signup": "नवा खाता बनाव", "mobile": "मोबाइल नंबर", "email": "ईमेल",
        "password": "पासवर्ड", "full_name": "पूरा नांव", "village": "गांव के नांव",
        "vehicle_no": "गाड़ी नंबर", "photo_optional": "फोटो (जरूरी नई हे)",
        "create_account": "खाता बनाव", "logout": "लॉगआउट",
        "fill_all_fields": "कृपया सब जानकारी भरव।", "wrong_credentials": "गलत मोबाइल/ईमेल या पासवर्ड।",
        "shg_portal": "स्वयं सहायता समूह पोर्टल", "profile": "प्रोफाइल", "name": "नांव",
        "wallet": "वॉलेट", "balance": "बैलेंस", "withdraw": "पईसा निकालव",
        "withdraw_amount": "राशि (₹)", "withdraw_method": "कोन तरीका ले निकालना हे",
        "upi": "यूपीआई", "bank": "बैंक खाता", "card": "कार्ड",
        "withdraw_details": "खाता के जानकारी", "submit_withdraw": "निकासी बर आवेदन करव",
        "withdraw_success": "निकासी के आवेदन भेज दे गे हे!", "insufficient_balance": "राशि वॉलेट ले जादा हे।",
        "withdraw_history": "निकासी के इतिहास", "no_withdrawals": "अभी तक कोई निकासी नई होय हे।",
        "training_gate_title": "📹 प्रशिक्षण वीडियो (जरूरी हे)",
        "training_gate_msg": "पहिली प्रशिक्षण वीडियो देखव। नीचे कन्फर्म करते ही तुंहर रिपोर्ट भेज सकबे।",
        "training_gate_no_video": "प्रशिक्षण वीडियो अभी सेट नई होय हे। एडमिन ले संपर्क करव।",
        "training_gate_done": "✅ प्रशिक्षण पूरा होगे! अब तुंहर रिपोर्ट नीचे भेज सकत हव।",
        "training_gate_confirm_checkbox": "मैं पूरा प्रशिक्षण वीडियो देख डारे हंव",
        "training_gate_confirm_btn": "✅ प्रशिक्षण पूर्ण मार्क करव",
        "report_garbage": "कचरा के रिपोर्ट करव", "quantity_kg": "मात्रा (किग्रा)", "plastic_type": "प्लास्टिक के किसम",
        "description": "विवरण", "submit_report": "रिपोर्ट भेजव", "your_reports": "तुंहर रिपोर्ट",
        "driver_dashboard": "ड्राइवर डैशबोर्ड", "my_profile": "मोर प्रोफाइल", "active_stops": "चालू स्टॉप",
        "fuel_optimized": "तेल के बचत", "optimize_route": "रस्ता सुधारव (OSRM)", "otp": "ओटीपी",
        "verify_collect": "जांचव अउ लेवव", "wrong_otp": "गलत ओटीपी।",
        "govt_dashboard": "सरकारी डैशबोर्ड",
        "govt_caption": "छत्तीसगढ़ EchoByte पायलट — SHG, ड्राइवर अउ गांव के सारांश।",
        "total_collected": "कुल जमा (किग्रा)", "pending": "बाकी", "collected": "जमा होगे",
        "shgs_registered": "दर्ज SHG", "drivers_registered": "दर्ज ड्राइवर",
        "trend_daily": "रोज के जमा (किग्रा)", "village_wise": "गांव के मुताबिक मात्रा (किग्रा)",
        "wallet_distribution": "वॉलेट के बंटवारा (SHG)", "recent_activity": "हाल के काम-बूता",
        "plastic_rate_settings": "प्लास्टिक दर सेटिंग", "shg_rate": "SHG दर", "driver_rate": "ड्राइवर दर",
        "save_rates": "दर सहेजव", "rates_saved": "दर अपडेट होगे।",
        "withdrawal_requests": "निकासी के आवेदन", "mark_paid": "भुगतान होगे लिखव",
        "status": "स्थिति", "method": "तरीका", "amount": "राशि (₹)",
        "download_pdf_report": "पीडीएफ रिपोर्ट डाउनलोड करव",
        "language": "भाषा",
    },
}


def T(key: str) -> str:
    """Returns the translated string for the current session language (fallback: English)."""
    lang = st.session_state.get("lang", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))


# ============================================================
# Govt-portal styling (navy + eco green — matches the web version)
# ============================================================
st.markdown("""
<style>
:root{
  --color-primary:#0B3D62; --color-primary-dark:#072A44; --color-primary-soft:#E4ECF3;
  --color-accent:#1E7A46; --color-accent-soft:#E4F3EA;
  --color-warn:#B7791B; --color-warn-soft:#FBF0DA;
  --color-line:#DCE3E9;
}
.stApp{ background:#EEF2F6; }
.identity-strip{ height:5px; width:100%; display:flex; margin-bottom:0; }
.identity-strip span{ flex:1; }
.identity-strip .saffron{ background:#E8862E; }
.identity-strip .white{ background:#FFFFFF; }
.identity-strip .green{ background:#1E7A46; }
.gov-header{ text-align:center; padding: 6px 0 14px; }
.gov-header .emblem{
  width:52px; height:52px; border-radius:50%; background:var(--color-primary); color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.85rem;
  margin:0 auto 8px;
}
.gov-header .dept{ font-size:.75rem; text-transform:uppercase; letter-spacing:.06em; color:#55636F; font-weight:600; }
.gov-header h1{ margin:4px 0 0; color:var(--color-primary-dark); }
.ledger-card{
  background:#fff; border:1px solid var(--color-line); border-radius:8px;
  padding:18px 20px; margin-bottom:14px; box-shadow:0 1px 2px rgba(15,35,55,.05), 0 6px 16px rgba(15,35,55,.05);
  border-left:3px solid var(--color-primary);
}
.eyebrow{ font-size:.68rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--color-primary); margin-bottom:6px; }
.badge{ display:inline-block; padding:3px 10px; border-radius:4px; font-size:.7rem; font-weight:700; text-transform:uppercase; }
.badge.pending{ background:var(--color-warn-soft); color:#8A5A19; }
.badge.progress{ background:var(--color-primary-soft); color:var(--color-primary); }
.badge.done{ background:var(--color-accent-soft); color:#1E5C34; }
div[data-testid="stMetric"]{
  background:#fff; border:1px solid var(--color-line); border-radius:8px; padding:14px 16px;
  border-left:3px solid var(--color-primary);
}
.org-header{
  display:flex; align-items:center; justify-content:center;
  padding:10px 6px 4px;
}
.org-logo{
  display:block; height:80px; max-height:80px; width:auto;
  max-width:520px; object-fit:contain;
}
.logo-placeholder{
  width:64px; height:64px; border:2px dashed var(--color-line); border-radius:8px;
  display:flex; align-items:center; justify-content:center; font-size:.6rem;
  color:#8B98A3; text-align:center; background:#fff;
}
.lang-select-wrap{ max-width:190px; margin-left:auto; }
.lang-select-wrap div[data-testid="stSelectbox"] label{ font-size:.72rem; }
</style>
<div class="identity-strip"><span class="saffron"></span><span class="white"></span><span class="green"></span></div>
""", unsafe_allow_html=True)


def _img_to_data_uri(path: str) -> str:
    """Converts the logo to a base64 data-URI so we have full control over
    size and quality via an HTML <img> tag (Streamlit's st.image() sometimes
    renders blurry/soft at small widths)."""
    ext = path.rsplit(".", 1)[-1].lower()
    mime = "image/png" if ext == "png" else f"image/{ext}"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def render_org_header():
    """Site-wide header: shows a single combined logo image (NIT Raipur | Govt
    of CG | UNICEF) centered. Drop your actual combined logo into
    assets/header_logo.png."""
    if os.path.exists(LOGO_HEADER_PATH):
        logo_html = f'<img class="org-logo" src="{_img_to_data_uri(LOGO_HEADER_PATH)}" />'
    else:
        logo_html = '<div class="logo-placeholder">LOGO<br/>NIT&nbsp;Raipur&nbsp;|&nbsp;CG&nbsp;Govt&nbsp;|&nbsp;UNICEF</div>'
    st.markdown(f"""
    <div class="org-header">
      {logo_html}
    </div>
    """, unsafe_allow_html=True)


def render_lang_selector(where: str):
    """Language dropdown — shown in the 'sidebar' (logged-in screens) or 'main'
    (auth screen). On 'main' it renders as a compact, right-aligned dropdown
    (doesn't take the full width)."""
    target = st.sidebar if where == "sidebar" else st
    keys = list(LANGS.keys())
    if where == "main":
        target.markdown('<div class="lang-select-wrap">', unsafe_allow_html=True)
    choice = target.selectbox(
        "🌐 " + T("language"), options=keys, format_func=lambda k: LANGS[k],
        index=keys.index(st.session_state.lang), key=f"lang_select_{where}",
    )
    if where == "main":
        target.markdown('</div>', unsafe_allow_html=True)
    if choice != st.session_state.lang:
        st.session_state.lang = choice
        st.rerun()


# ============================================================
# Helpers: auth, otp, distance, geocoding, OSRM
# ============================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def random_otp() -> str:
    return str(random.randint(1000, 9999))


def haversine(a, b) -> float:
    """Distance in km between two {lat,lng} points."""
    R = 6371
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def geocode_location(query: str, village_hint: str = ""):
    """Free location search via OpenStreetMap Nominatim (no API key needed).
    First tries with the village hint; if nothing is found, falls back to a
    broader search with just 'Chhattisgarh'. Returns a (query, error_message)
    tuple — error_message is None if everything went fine (even if results
    came back as 0)."""

    def _search(q):
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"format": "json", "q": q, "limit": 5},
            headers={"User-Agent": "EchoByte-Streamlit/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        results = []
        if village_hint:
            results = _search(f"{query}, {village_hint}, Chhattisgarh")
        if not results:
            results = _search(f"{query}, Chhattisgarh")
        return results, None
    except Exception as e:
        return [], str(e)


def reverse_geocode(lat: float, lng: float) -> str:
    """Builds a readable location name from GPS coordinates (Nominatim reverse
    lookup). Falls back to just the coordinates on failure, so the flow
    doesn't get stuck."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "json", "lat": lat, "lon": lng},
            headers={"User-Agent": "EchoByte-Streamlit/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        display = data.get("display_name")
        if display:
            return ", ".join(display.split(",")[:2])
    except Exception:
        pass
    return f"{lat:.5f}, {lng:.5f}"



# ============================================================
# Route optimization + multi-driver dispatch (Zomato/Rapido-style logic)
# ============================================================
# GARBAGE_PRIORITY_WEIGHT: the higher this is, the stronger the "pull" toward
# a large garbage pile (it gets visited earlier even if a bit farther away).
# Setting it to 0 makes this behave like plain nearest-neighbor.
GARBAGE_PRIORITY_WEIGHT = 0.12  # km-equivalent per kg

# How much a driver can carry in one trip (vehicle/time capacity) — similar
# to how Zomato/Swiggy batch a limited number of orders per rider at a time.
MAX_STOPS_PER_ROUTE = 8
MAX_KG_PER_ROUTE = 150

# Max allowed detour (km) for inserting an "on the way" garbage report into the route
ENROUTE_MAX_DETOUR_KM = 1.5


def nearest_neighbor_order(stops, start=None):
    """Greedy nearest-neighbor stop ordering — but weighted by garbage
    quantity, not just distance. Score = distance - (weight * qty), so a
    nearby small pile and a slightly farther large pile compete with each
    other — the one with more garbage gets a light pull toward the front,
    exactly like how delivery apps prioritize higher-value orders.

    'start' is where the driver currently is (falls back to DEPOT if not
    given/known) — this is what makes the ordering start from the driver's
    real position instead of always the depot."""
    remaining = stops.copy()
    ordered = []
    current = start or DEPOT
    while remaining:
        best_idx, best_score = 0, float("inf")
        for i, s in enumerate(remaining):
            d = haversine(current, {"lat": s["lat"], "lng": s["lng"]})
            qty = float(s.get("quantity_kg", 0) or 0)
            score = d - GARBAGE_PRIORITY_WEIGHT * qty
            if score < best_score:
                best_score, best_idx = score, i
        nxt = remaining.pop(best_idx)
        ordered.append(nxt)
        current = {"lat": nxt["lat"], "lng": nxt["lng"]}
    return ordered


def select_batch_for_driver(candidates, driver_location=None, radius_km=None):
    """Picks a 'batch' out of all pending reports for this driver's trip —
    exactly like Zomato/Blinkit's zone-based order allocation:

    1) ZONE FILTER — only reports that fall inside THIS driver's own
       'service_radius_km' (their personal delivery-zone radius, e.g. a
       2km-zone driver vs a 4km-zone driver) are even considered. A report
       10km away can never land on a driver whose zone is 2km, no matter how
       close it is relative to other drivers.
    2) SCORING — among the in-zone reports, closer + higher-garbage stops
       are preferred (falls back to the depot if the driver's location isn't
       known yet).
    3) CAPACITY — batch stays within vehicle capacity (MAX_STOPS_PER_ROUTE /
       MAX_KG_PER_ROUTE).

    Whatever doesn't make it into the batch simply stays 'pending' — so if
    several drivers hit 'Optimize Route' at the same time, no two drivers
    double-assign the same report, and each driver naturally gravitates
    toward the reports nearest to (and within-zone of) THEM."""
    origin = driver_location or DEPOT
    zone_radius = radius_km if radius_km and radius_km > 0 else DEFAULT_SERVICE_RADIUS_KM

    in_zone = [
        s for s in candidates
        if haversine(origin, {"lat": s["lat"], "lng": s["lng"]}) <= zone_radius
    ]

    scored = []
    for s in in_zone:
        d = haversine(origin, {"lat": s["lat"], "lng": s["lng"]})
        qty = float(s.get("quantity_kg", 0) or 0)
        score = d - GARBAGE_PRIORITY_WEIGHT * qty
        scored.append((score, s))
    scored.sort(key=lambda x: x[0])

    batch, total_kg = [], 0.0
    for _, s in scored:
        if len(batch) >= MAX_STOPS_PER_ROUTE:
            break
        qty = float(s.get("quantity_kg", 0) or 0)
        if batch and total_kg + qty > MAX_KG_PER_ROUTE:
            continue  # skip this stop and try the next one instead of breaking capacity
        batch.append(s)
        total_kg += qty
    return batch


def cheapest_insertion(path_points, candidate):
    """Finds the cheapest (least extra-distance) point to insert a candidate
    stop into a given path (list of {lat,lng} waypoints). Returns
    (insert_index, extra_km)."""
    best_idx, best_extra = len(path_points), float("inf")
    for i in range(len(path_points) - 1):
        a, b = path_points[i], path_points[i + 1]
        c = {"lat": candidate["lat"], "lng": candidate["lng"]}
        extra = haversine(a, c) + haversine(c, b) - haversine(a, b)
        if extra < best_extra:
            best_extra, best_idx = extra, i + 1
    return best_idx, best_extra


def build_route_segments(ordered_stops, start=None):
    """Fetches a separate OSRM 'leg' from the starting point (driver's
    current location, or the depot if unknown) to each stop, so the map can
    distinguish 'distance already covered' (solid green) from 'where to go
    next' (animated dashed). Falls back to a straight line if OSRM fails."""
    points = [start or DEPOT] + [{"lat": s["lat"], "lng": s["lng"]} for s in ordered_stops]
    segments = []
    for i in range(len(points) - 1):
        coords = fetch_osrm_route([points[i], points[i + 1]])
        if not coords:
            coords = [[points[i]["lat"], points[i]["lng"]], [points[i + 1]["lat"], points[i + 1]["lng"]]]
        segments.append(coords)
    return segments


def route_length(stops, start=DEPOT) -> float:
    total, cur = 0.0, start
    for s in stops:
        total += haversine(cur, {"lat": s["lat"], "lng": s["lng"]})
        cur = {"lat": s["lat"], "lng": s["lng"]}
    return total


def fetch_osrm_route(points):
    """Fetches real road route geometry from OSRM. Returns None on failure
    (caller can fall back to straight lines)."""
    coord_str = ";".join(f"{p['lng']},{p['lat']}" for p in points)
    url = f"{OSRM_URL}/route/v1/driving/{coord_str}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=8)
        data = r.json()
        if data.get("routes"):
            return [[pt[1], pt[0]] for pt in data["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        pass
    return None


def _flatten_shg(rows):
    """Flattens the embedded relation from
    'select(*, shg:users!garbage_reports_shg_id_fkey(full_name,mobile))' into
    flat shg_name/shg_mobile keys, so the rest of the code can just use
    s['shg_name'] directly."""
    out = []
    for r in rows:
        shg = r.pop("shg", None) or {}
        r["shg_name"] = shg.get("full_name", "—")
        r["shg_mobile"] = shg.get("mobile", "—")
        out.append(r)
    return out


# ============================================================
# Auth (Supabase table `users` — we handle our own password hashing here
# instead of using Supabase Auth, since SHGs/Drivers log in with
# mobile+password, not email)
# ============================================================
def signup(role, full_name, mobile, village, email, password, photo_url=None, vehicle_no=None, pwm_unit_id=None):
    try:
        sb.table("users").insert({
            "role": role,
            "full_name": full_name,
            "mobile": mobile or None,
            "village": village or None,
            "email": email or None,
            "password_hash": hash_password(password),
            "photo_url": photo_url,
            "vehicle_no": vehicle_no or None,
            "pwm_unit_id": pwm_unit_id,
        }).execute()
        return True, "Account created! You can log in now."
    except Exception as e:
        return False, _friendly_error_message(e)


def login(role, identifier, password):
    field = "email" if role == "govt" else "mobile"
    res = sb.table("users").select("*").eq(field, identifier).eq("role", role).execute()
    rows = res.data
    if rows and rows[0]["password_hash"] == hash_password(password):
        return rows[0]
    return None


# ============================================================
# Session state
# ============================================================
if "user" not in st.session_state:
    st.session_state.user = None
if "lang" not in st.session_state:
    st.session_state.lang = "en"  # default: English
if "signup_role" not in st.session_state:
    st.session_state.signup_role = "shg"
if "loc_candidates" not in st.session_state:
    st.session_state.loc_candidates = []
if "selected_location" not in st.session_state:
    st.session_state.selected_location = None
if "route_stops" not in st.session_state:
    st.session_state.route_stops = None
if "route_coords" not in st.session_state:
    st.session_state.route_coords = None
if "route_segments" not in st.session_state:
    st.session_state.route_segments = None  # per-leg OSRM coords: [depot->stop1, stop1->stop2, ...]
if "current_stop_idx" not in st.session_state:
    st.session_state.current_stop_idx = 0  # which stop in the route the driver has reached so far
if "just_completed_route" not in st.session_state:
    st.session_state.just_completed_route = False
if "fuel_saved_pct" not in st.session_state:
    st.session_state.fuel_saved_pct = None
if "last_gps" not in st.session_state:
    st.session_state.last_gps = None
if "pending_gps_name" not in st.session_state:
    st.session_state.pending_gps_name = None
if "driver_last_gps" not in st.session_state:
    st.session_state.driver_last_gps = None
if "driver_pending_gps_name" not in st.session_state:
    st.session_state.driver_pending_gps_name = None


def do_logout():
    st.session_state.user = None
    st.session_state.route_stops = None
    st.session_state.route_coords = None
    st.session_state.route_segments = None
    st.session_state.current_stop_idx = 0
    st.rerun()


# ============================================================
# AUTH SCREEN — Login / Sign Up
# ============================================================
def render_auth():
    render_org_header()

    lc1, lc2 = st.columns([4, 1])
    with lc2:
        render_lang_selector("main")

    st.markdown(f"""
    <div class="gov-header">
        <div class="dept">{T('dept_line')}</div>
        <h1>{T('app_title')}</h1>
        <p style="color:#55636F;">{T('app_tagline')}</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            role = st.radio(
                "Role", options=list(ROLE_LABELS.keys()),
                format_func=lambda r: T(f"role_{r}"), horizontal=True, key="role_choice"
            )
            login_tab, signup_tab = st.tabs([T("login"), T("signup")])

            # -------- LOGIN --------
            with login_tab:
                with st.form("login_form"):
                    if role == "govt":
                        identifier = st.text_input(T("email"))
                    else:
                        identifier = st.text_input(T("mobile"))
                    password = st.text_input(T("password"), type="password")
                    submitted = st.form_submit_button(T("login"), use_container_width=True)

                if submitted:
                    if not identifier or not password:
                        st.error(T("fill_all_fields"))
                    else:
                        user = login(role, identifier.strip(), password)
                        if user:
                            st.session_state.user = user
                            st.rerun()
                        else:
                            st.error(T("wrong_credentials"))

            # -------- SIGN UP --------
            with signup_tab:
                pwm_options = {}
                if role in ("shg", "driver"):
                    pwm_res = sb.table("pwm_units").select("id,name,location_name").eq("status", "active").order("name").execute()
                    pwm_options = {f"{u['name']} ({u.get('location_name') or '—'})": u["id"] for u in pwm_res.data}

                with st.form("signup_form"):
                    full_name = st.text_input(T("full_name"))
                    if role == "govt":
                        email = st.text_input(T("email"))
                        mobile, village, vehicle_no = "", "", ""
                    elif role == "driver":
                        mobile = st.text_input(T("mobile"))
                        village = st.text_input(T("village"))
                        vehicle_no = st.text_input(T("vehicle_no"), placeholder="e.g. CG04 AB 1234")
                        email = ""
                    else:
                        mobile = st.text_input(T("mobile"))
                        village = st.text_input(T("village"))
                        vehicle_no = ""
                        email = ""

                    pwm_pick = None
                    if role in ("shg", "driver"):
                        if pwm_options:
                            pwm_pick = st.selectbox("PWM Unit (your assigned collection center)", options=list(pwm_options.keys()))
                        else:
                            st.caption("No PWM units available yet — contact your admin.")

                    password = st.text_input(T("password"), type="password", key="signup_pw")
                    photo_file = st.file_uploader(T("photo_optional"), type=["jpg", "jpeg", "png"])
                    submitted_signup = st.form_submit_button(T("create_account"), use_container_width=True)

                if submitted_signup:
                    if not full_name or not password or (role == "govt" and not email) or (role != "govt" and (not mobile or not village)):
                        st.error(T("fill_all_fields"))
                    else:
                        photo_url = None
                        if photo_file is not None:
                            with st.spinner("Uploading photo..."):
                                photo_url = upload_photo(photo_file.getvalue(), photo_file.name, role)
                            if photo_url is None:
                                st.warning("Photo upload failed — the account is still being created; you can add a photo later.")
                        pwm_unit_id = pwm_options.get(pwm_pick) if pwm_pick else None
                        ok, msg = signup(role, full_name, mobile, village, email, password, photo_url, vehicle_no, pwm_unit_id)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

        st.markdown(
            "<p style='text-align:center; color:#55636F; font-size:.8rem; margin-top:10px;'>"
            "Chhattisgarh · EchoByte Pilot</p>", unsafe_allow_html=True
        )


# ============================================================
# SHG TRAINING VIDEO GATE — SHG apna data (garbage report) tabhi submit
# kar payegi jab wo yeh video dekh legi. Video Google Drive pe hai (link
# supabase_client.py ke TRAINING_VIDEO_DRIVE_URL constant me daala hai —
# jab bhi video badalni ho bas wo ek line edit kar dena, koi SQL/DB
# change nahi chahiye).
#
# NOTE: Drive ka video ek iframe me dikhta hai (Google ke apne player
# se), isliye humara app "video pura khatam hui ya nahi" khud check
# NAHI kar sakta (cross-origin restriction — koi bhi website doosri
# website ke andar chal rahe video ko JS se control nahi kar sakti).
# Isliye yahan HONOR-SYSTEM hai: SHG khud checkbox tick karke confirm
# karti hai ki usne video dekh li, phir "Training Complete" button se
# aage badhti hai. Agar future me strict auto-detect chahiye (bina
# checkbox ke, video khatam hote hi automatic unlock), video ko kisi
# direct-file host (Supabase Storage / Cloudflare R2 / S3) pe daalna
# hoga — Drive ke saath ye possible nahi hai.
#
# Returns True agar training complete ho chuki hai (form dikhana hai),
# False agar abhi video hi dikhana hai (form chhupana hai).
# ============================================================
def _to_drive_embed_url(url: str) -> str:
    """Google Drive ka normal 'share' link (.../file/d/FILE_ID/view) ko
    embeddable '/preview' link me convert karta hai. Agar link already
    kisi aur format ka hai (ya Drive ka hi nahi hai), usko waisa hi
    wapas kar deta hai."""
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/file/d/{m.group(1)}/preview"
    return url


def render_shg_training_gate(user) -> bool:
    if user.get("training_video_completed"):
        return True

    video_url = get_training_video_url()
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("training_gate_title")}</div>', unsafe_allow_html=True)
    st.info(T("training_gate_msg"))

    if not video_url:
        st.warning(T("training_gate_no_video"))
    else:
        embed_url = _to_drive_embed_url(video_url)
        components.html(f"""
            <iframe src="{embed_url}" width="100%" height="420"
                    allow="autoplay" style="border-radius:12px;border:none;"
                    allowfullscreen></iframe>
        """, height=430)

    st.markdown("</div>", unsafe_allow_html=True)

    confirmed = st.checkbox(T("training_gate_confirm_checkbox"), key="training_confirm_checkbox")
    if st.button(T("training_gate_confirm_btn"), disabled=not confirmed, use_container_width=True):
        sb.table("users").update({"training_video_completed": True}).eq("id", user["id"]).execute()
        st.session_state.user["training_video_completed"] = True
        st.success(T("training_gate_done"))
        st.rerun()

    return False


# ============================================================
# WALLET WITHDRAW — shared by SHG and Driver dashboards
# ============================================================
def render_wallet_withdraw(user):
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("withdraw")}</div>', unsafe_allow_html=True)

    wallet_balance = float(user["wallet"])
    with st.form(f"withdraw_form_{user['id']}"):
        amt = st.number_input(
            T("withdraw_amount"), min_value=0.0,
            max_value=wallet_balance if wallet_balance > 0 else 0.0,
            step=1.0,
        )
        method = st.radio(
            T("withdraw_method"), options=["upi", "bank", "card"],
            format_func=lambda m: T(m), horizontal=True, key=f"method_{user['id']}",
        )
        details = st.text_input(
            T("withdraw_details"),
            placeholder="UPI ID (name@upi)" if method == "upi"
            else "Account No. + IFSC" if method == "bank"
            else "Card number (last 4 digits ok)",
            key=f"details_{user['id']}",
        )
        submit_w = st.form_submit_button(T("submit_withdraw"), use_container_width=True)

    if submit_w:
        if wallet_balance <= 0 or amt <= 0:
            st.error(T("insufficient_balance"))
        elif amt > wallet_balance:
            st.error(T("insufficient_balance"))
        elif not details.strip():
            st.error(T("fill_all_fields"))
        else:
            new_balance = round(wallet_balance - amt, 2)
            sb.table("users").update({"wallet": new_balance}).eq("id", user["id"]).execute()
            sb.table("withdrawals").insert({
                "user_id": user["id"], "role": user["role"], "amount": amt,
                "method": method, "details": details.strip(), "status": "pending",
            }).execute()
            st.session_state.user["wallet"] = new_balance
            st.success(T("withdraw_success"))
            st.rerun()

    hist_res = (
        sb.table("withdrawals").select("*")
        .eq("user_id", user["id"]).order("created_at", desc=True).execute()
    )
    hist = pd.DataFrame(hist_res.data)
    if hist.empty:
        st.caption(T("no_withdrawals"))
    else:
        hist = hist[["amount", "method", "status", "created_at"]].rename(columns={
            "amount": T("amount"), "method": T("method"), "status": T("status"), "created_at": "Date",
        })
        st.dataframe(hist, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# SHG DASHBOARD
# ============================================================
def render_shg(user):
    render_lang_selector("sidebar")
    st.sidebar.markdown(f"### 👩‍🌾 {user['full_name']}")
    st.sidebar.caption(f"{user['mobile']} · {user['village']}")
    if user.get("photo_url"):
        st.sidebar.image(user["photo_url"], width=80)
    if st.sidebar.button(T("logout"), use_container_width=True):
        do_logout()

    render_org_header()
    st.title(T("shg_portal"))

    # ---- Profile + wallet ----
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("profile")}</div>', unsafe_allow_html=True)
        if user.get("photo_url"):
            st.image(user["photo_url"], width=90)
        st.write(f"**{T('name')}:** {user['full_name']}")
        st.write(f"**{T('mobile')}:** {user['mobile']}")
        st.write(f"**{T('village')}:** {user['village']}")
        if user.get("pwm_unit_id"):
            pwm_info = sb.table("pwm_units").select("name").eq("id", user["pwm_unit_id"]).execute()
            if pwm_info.data:
                st.write(f"**🏭 PWM Unit:** {pwm_info.data[0]['name']}")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("wallet")}</div>', unsafe_allow_html=True)
        st.metric(T("balance"), f"₹ {user['wallet']}")
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- Environmental Impact Dashboard — quick awareness metrics built
    # from THIS SHG's own collected reports so far. Factors used are rough,
    # commonly-cited estimates (see CO2_KG_SAVED_PER_KG_PLASTIC /
    # CO2_KG_ABSORBED_PER_TREE_PER_YEAR at the top of the file), meant for
    # motivation/awareness — not a precise scientific lifecycle assessment. ----
    shg_reports_res = (
        sb.table("garbage_reports").select("*")
        .eq("shg_id", user["id"]).order("created_at", desc=True).execute()
    )
    shg_reports_df = pd.DataFrame(shg_reports_res.data)
    collected_df = shg_reports_df[shg_reports_df["status"] == "collected"] if not shg_reports_df.empty else pd.DataFrame()
    total_kg_recycled = float(collected_df["quantity_kg"].astype(float).sum()) if not collected_df.empty else 0.0
    co2_saved_kg = round(total_kg_recycled * CO2_KG_SAVED_PER_KG_PLASTIC, 1)
    trees_saved = round(co2_saved_kg / CO2_KG_ABSORBED_PER_TREE_PER_YEAR, 1)

    st.markdown(f'<div class="ledger-card"><div class="eyebrow">🌍 Environmental Impact</div>', unsafe_allow_html=True)
    ei1, ei2, ei3 = st.columns(3)
    ei1.metric("♻️ Total Recycled", f"{total_kg_recycled:,.0f} kg")
    ei2.metric("🌫️ CO₂ Offset (approx.)", f"{co2_saved_kg:,.1f} kg")
    ei3.metric("🌳 Trees Saved (approx.)", f"{trees_saved:,.1f}")
    st.caption("Estimates based on standard awareness-level conversion factors — meant to show your SHG's contribution, not a precise measurement.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Live Driver ETA — for any of THIS SHG's reports that are
    # currently 'assigned' to a driver, show how far that driver currently
    # is and a rough ETA (haversine distance / assumed average speed). ----
    assigned_df = shg_reports_df[shg_reports_df["status"] == "assigned"] if not shg_reports_df.empty else pd.DataFrame()
    if not assigned_df.empty:
        eta_res = (
            sb.table("garbage_reports")
            .select("*, driver:users!garbage_reports_driver_id_fkey(full_name,mobile,current_lat,current_lng)")
            .eq("shg_id", user["id"]).eq("status", "assigned").execute()
        )
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">🚚 Live Driver ETA</div>', unsafe_allow_html=True)
        for r in eta_res.data:
            drv = r.get("driver") or {}
            with st.container(border=True):
                dc1, dc2 = st.columns([3, 2])
                dc1.markdown(f"**{r.get('location_name') or r.get('village')}** · {r['quantity_kg']} kg")
                dc1.caption(f"Driver: {drv.get('full_name', '—')} · 📞 {drv.get('mobile', '—')}")
                if drv.get("current_lat") and r.get("lat"):
                    dist_km = haversine(
                        {"lat": float(drv["current_lat"]), "lng": float(drv["current_lng"])},
                        {"lat": float(r["lat"]), "lng": float(r["lng"])},
                    )
                    eta_min = round((dist_km / AVG_DRIVER_SPEED_KMPH) * 60)
                    dc2.metric("Distance", f"{dist_km:.1f} km")
                    dc2.caption(f"⏱️ ETA ~{eta_min} min (approx.)")
                else:
                    dc2.caption("Driver location not available yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- Withdraw ----
    render_wallet_withdraw(user)

    if render_shg_training_gate(user):
        # ---- Report garbage form ----
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("report_garbage")}</div>', unsafe_allow_html=True)

        st.markdown("**📍 Use my current location** — this will ask for browser permission.")
        gps = streamlit_geolocation()
        if gps and gps.get("latitude"):
            coords = (gps["latitude"], gps["longitude"])
            # There's no auto st.rerun() here — the GPS component can give a
            # slightly different reading on every rerun, which used to cause a
            # loop. Now it only confirms when the user explicitly clicks
            # "Use this location".
            if st.session_state.last_gps != coords:
                st.session_state.last_gps = coords
                with st.spinner("Fetching your location..."):
                    st.session_state.pending_gps_name = reverse_geocode(*coords)

            if st.session_state.get("pending_gps_name"):
                st.info(f"📍 GPS location found: **{st.session_state.pending_gps_name}**")
                if st.button("✅ Use this location"):
                    st.session_state.selected_location = {
                        "lat": coords[0], "lng": coords[1], "name": st.session_state.pending_gps_name
                    }
                    st.session_state.loc_candidates = []
                    st.session_state.pending_gps_name = None

        with st.expander("Or search for a location manually"):
            search_col, btn_col = st.columns([4, 1])
            query = search_col.text_input("Exact Pickup Location", placeholder="e.g. Raipura Chowk", label_visibility="visible")
            if btn_col.button("🔍 Search", use_container_width=True):
                if len(query.strip()) < 3:
                    st.warning("Please enter at least 3 letters.")
                else:
                    with st.spinner("Searching for location..."):
                        results, err = geocode_location(query.strip(), user["village"])
                    st.session_state.selected_location = None
                    if err:
                        st.session_state.loc_candidates = []
                        st.error(f"Search failed: {err}. Please check your internet connection and try again.")
                    elif not results:
                        st.session_state.loc_candidates = []
                        st.warning("No location found. Try a slightly different or more specific name (e.g. just the village name).")
                    else:
                        st.session_state.loc_candidates = results

            if st.session_state.loc_candidates:
                options = {
                    f"{c['display_name'].split(',')[0]}, {c['display_name'].split(',')[1] if ',' in c['display_name'] else ''}": c
                    for c in st.session_state.loc_candidates
                }
                pick = st.selectbox("Search results — choose one", list(options.keys()), key="loc_pick")
                if st.button("✅ Confirm this location"):
                    chosen = options[pick]
                    st.session_state.selected_location = {
                        "lat": float(chosen["lat"]), "lng": float(chosen["lon"]), "name": pick.strip()
                    }

        if st.session_state.selected_location:
            loc = st.session_state.selected_location
            st.success(f"📍 Selected: {loc['name']}")
            m = folium.Map(location=[loc["lat"], loc["lng"]], zoom_start=16)
            folium.Marker([loc["lat"], loc["lng"]]).add_to(m)
            st_folium(m, height=180, width=None, returned_objects=[])

        rates_res = sb.table("plastic_rates").select("type").order("type").execute()
        plastic_types = [r["type"] for r in rates_res.data] or ["Mixed Plastic"]

        with st.form("report_form"):
            qty = st.number_input(T("quantity_kg"), min_value=1, step=1)
            ptype = st.selectbox(T("plastic_type"), options=plastic_types)
            desc = st.text_input(T("description"), placeholder="e.g. plastic + organic mix")
            submit_report = st.form_submit_button(T("submit_report"), use_container_width=True)

        if submit_report:
            if not st.session_state.selected_location:
                st.error("Please search and select a location first — the driver's route depends on it.")
            else:
                loc = st.session_state.selected_location
                sb.table("garbage_reports").insert({
                    "shg_id": user["id"],
                    "village": user["village"],
                    "location_name": loc["name"],
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "quantity_kg": qty,
                    "description": desc,
                    "plastic_type": ptype,
                    "status": "pending",
                    "otp": random_otp(),
                }).execute()
                st.success("Report submitted. It will now appear on a driver's route.")
                st.session_state.selected_location = None
                st.session_state.loc_candidates = []
                st.session_state.last_gps = None
                st.session_state.pending_gps_name = None
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ---- History table (reuses the same query already fetched above for
    # the Environmental Impact / ETA cards — no need to hit the DB twice) ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("your_reports")}</div>', unsafe_allow_html=True)
    res = shg_reports_res
    df = shg_reports_df.copy()
    if df.empty:
        st.info("No reports submitted yet.")
    else:
        display_df = df.copy()
        display_df["otp"] = display_df.apply(lambda r: "—" if r["status"] == "pending" else r["otp"], axis=1)
        display_df = display_df[["location_name", "quantity_kg", "description", "status", "otp", "created_at"]].rename(columns={
            "location_name": "Location", "quantity_kg": "Qty (kg)", "description": "Description",
            "status": "Status", "otp": "OTP", "created_at": "Date",
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    if st.button(f"📄 {T('download_pdf_report')}", key="shg_pdf_btn"):
        with st.spinner("Generating report (with charts, this may take a moment)..."):
            raw_df = pd.DataFrame(res.data)  # 'res' is the original untouched query result (the df above was renamed for display)
            pdf_bytes = generate_shg_pdf_report(user, raw_df)
        st.download_button(
            "⬇️ Download PDF", data=pdf_bytes,
            file_name=f"EchoByte_SHG_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf", key="shg_pdf_dl",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Report Issue / Dispute System ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">⚠️ Report an Issue</div>', unsafe_allow_html=True)
    if df.empty:
        st.caption("No reports yet to raise an issue against.")
    else:
        disputable = df[df["status"].isin(["assigned", "collected"])]
        if disputable.empty:
            st.caption("You can report an issue once a pickup is assigned or collected.")
        else:
            options = {
                f"#{r['id']} · {r.get('location_name') or r.get('village')} · {r['quantity_kg']}kg · {r['status']}": r["id"]
                for _, r in disputable.iterrows()
            }
            with st.form("dispute_form"):
                pick = st.selectbox("Which pickup is the issue about?", list(options.keys()))
                reason = st.text_area("What went wrong?", placeholder="e.g. weight mismatch, driver didn't show up, wrong amount credited...")
                submit_dispute = st.form_submit_button("🚩 Submit Issue", use_container_width=True)
            if submit_dispute:
                if not reason.strip():
                    st.error("Please describe the issue.")
                else:
                    sb.table("disputes").insert({
                        "report_id": options[pick], "shg_id": user["id"],
                        "reason": reason.strip(), "status": "open",
                    }).execute()
                    st.success("Issue reported — the government team will review it.")
                    st.rerun()

    disputes_res = (
        sb.table("disputes").select("*, report:garbage_reports(location_name,village)")
        .eq("shg_id", user["id"]).order("created_at", desc=True).execute()
    )
    if disputes_res.data:
        st.caption("Your reported issues:")
        for d in disputes_res.data:
            rep = d.get("report") or {}
            status_icon = "🟢 Resolved" if d["status"] == "resolved" else "🟠 Open"
            with st.container(border=True):
                st.markdown(f"**{rep.get('location_name') or rep.get('village') or '—'}** — {status_icon}")
                st.caption(d["reason"])
                if d.get("resolution_note"):
                    st.caption(f"Govt response: {d['resolution_note']}")
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# DRIVER DASHBOARD
# ============================================================
def render_driver(user):
    render_lang_selector("sidebar")
    st.sidebar.markdown(f"### 🚚 {user['full_name']}")
    st.sidebar.caption(user["mobile"])
    if user.get("photo_url"):
        st.sidebar.image(user["photo_url"], width=80)
    if user.get("vehicle_no"):
        st.sidebar.caption(f"🚛 Vehicle: {user['vehicle_no']}")
    if st.sidebar.button(T("logout"), use_container_width=True):
        do_logout()

    render_org_header()
    st.title(T("driver_dashboard"))
    st.caption("Your optimized route is built from nearby pending reports (closer + higher-garbage stops first), "
               "navigate it step-by-step on the map, and each stop unlocks the next only after OTP verification.")

    if st.session_state.pop("just_completed_route", False):
        st.success("🎉 Route complete! Click 'Optimize Route' to get your next batch.")

    with st.expander(f"👤 {T('my_profile')}"):
        pc1, pc2 = st.columns([1, 3])
        if user.get("photo_url"):
            pc1.image(user["photo_url"], width=90)
        pc2.write(f"**{T('name')}:** {user['full_name']}")
        pc2.write(f"**{T('mobile')}:** {user['mobile']}")
        pc2.write(f"**Vehicle No.:** {user.get('vehicle_no') or '—'}")
        pc2.write(f"**🎯 Service Zone:** {float(user.get('service_radius_km') or DEFAULT_SERVICE_RADIUS_KM):.0f} km")
        if user.get("pwm_unit_id"):
            pwm_info = sb.table("pwm_units").select("name").eq("id", user["pwm_unit_id"]).execute()
            if pwm_info.data:
                pc2.write(f"**🏭 PWM Unit:** {pwm_info.data[0]['name']}")

    # ---- Wallet + withdraw ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("wallet")}</div>', unsafe_allow_html=True)
    st.metric(T("balance"), f"₹ {user['wallet']}")
    st.markdown("</div>", unsafe_allow_html=True)
    render_wallet_withdraw(user)

    # ---- Driver's current location — GPS by default, manual search as
    # fallback (same idea as the SHG "Use my current location" flow). This
    # is what makes route assignment favor stops near THIS driver instead of
    # always starting from the fixed depot. ----
    with st.expander("📍 My current location", expanded=not user.get("current_lat")):
        st.caption("Optimize Route' will prioritize pickups near this location instead of the depot.")
        gps = streamlit_geolocation()
        if gps and gps.get("latitude"):
            coords = (gps["latitude"], gps["longitude"])
            if st.session_state.driver_last_gps != coords:
                st.session_state.driver_last_gps = coords
                with st.spinner("Fetching your location..."):
                    st.session_state.driver_pending_gps_name = reverse_geocode(*coords)
            if st.session_state.get("driver_pending_gps_name"):
                st.info(f"📍 GPS location found: **{st.session_state.driver_pending_gps_name}**")
                if st.button("✅ Use this location", key="driver_use_gps"):
                    sb.table("users").update({
                        "current_lat": coords[0], "current_lng": coords[1],
                        "location_updated_at": datetime.now().isoformat(),
                    }).eq("id", user["id"]).execute()
                    st.session_state.user["current_lat"] = coords[0]
                    st.session_state.user["current_lng"] = coords[1]
                    st.session_state.driver_pending_gps_name = None
                    st.success("Location updated!")
                    st.rerun()

        with st.form("driver_manual_location_form"):
            manual_query = st.text_input("Or type your area/village manually", placeholder="e.g. Kumhari Chowk")
            manual_submit = st.form_submit_button("🔍 Search & use")
        if manual_submit and manual_query.strip():
            with st.spinner("Searching for location..."):
                results, err = geocode_location(manual_query.strip())
            if err:
                st.error(f"Search failed: {err}")
            elif not results:
                st.warning("No location found. Try a different name.")
            else:
                r = results[0]
                sb.table("users").update({
                    "current_lat": float(r["lat"]), "current_lng": float(r["lon"]),
                    "location_updated_at": datetime.now().isoformat(),
                }).eq("id", user["id"]).execute()
                st.session_state.user["current_lat"] = float(r["lat"])
                st.session_state.user["current_lng"] = float(r["lon"])
                st.success(f"Location set to: {r['display_name'].split(',')[0]}")
                st.rerun()

        if user.get("current_lat"):
            st.caption(f"Current: {user['current_lat']:.5f}, {user['current_lng']:.5f}")

        st.divider()
        st.caption("🎯 Your service zone — 'Optimize Route' will only pick up reports that fall inside this radius "
                   "from your current location (just like how Zomato/Blinkit gives each rider their own delivery zone).")
        current_radius = float(user.get("service_radius_km") or DEFAULT_SERVICE_RADIUS_KM)
        radius_options = sorted(set(SERVICE_RADIUS_OPTIONS_KM + [current_radius]))
        new_radius = st.selectbox(
            "Service radius (km)", options=radius_options,
            index=radius_options.index(current_radius),
            key="driver_radius_select",
        )
        if new_radius != current_radius:
            sb.table("users").update({"service_radius_km": new_radius}).eq("id", user["id"]).execute()
            st.session_state.user["service_radius_km"] = new_radius
            st.success(f"Service zone updated to {new_radius} km!")
            st.rerun()

    # Where THIS driver currently is — used as the routing origin. NO fallback
    # to DEPOT anymore: if the driver hasn't set a location yet, driver_location
    # stays None, and route optimization is blocked until they set one (see
    # the "Optimize Route" button below).
    has_location = bool(user.get("current_lat") and user.get("current_lng"))
    driver_location = (
        {"lat": float(user["current_lat"]), "lng": float(user["current_lng"])}
        if has_location else None
    )

    if not has_location:
        st.warning("📍 Please set your current location above — route optimization is disabled until you do.")

    # ---- Load already-assigned stops FOR THIS DRIVER ONLY (persisted across
    # reruns) so the page survives a refresh — the driver_id filter is
    # essential, otherwise a driver could see another driver's assigned stops. ----
    assigned_res = (
        sb.table("garbage_reports")
        .select("*, shg:users!garbage_reports_shg_id_fkey(full_name,mobile)")
        .eq("status", "assigned")
        .eq("driver_id", user["id"])
        .order("created_at")
        .execute()
    )
    assigned_rows = _flatten_shg(assigned_res.data)
    for s in assigned_rows:
        s["lat"] = float(s["lat"]) if s["lat"] is not None else DEPOT["lat"]
        s["lng"] = float(s["lng"]) if s["lng"] is not None else DEPOT["lng"]

    if st.session_state.route_stops is None and assigned_rows:
        # Rebuild the same (garbage-priority) order even after an app
        # restart/refresh, and refetch the OSRM legs since those don't persist.
        # Use the driver's live location if known; otherwise fall back to the
        # first assigned stop's own position just so a refresh doesn't crash
        # (this can only happen if location was set, a route was built, then
        # somehow cleared — the "Optimize Route" button itself always requires
        # a location before assigning anything in the first place).
        reload_start = driver_location or {"lat": assigned_rows[0]["lat"], "lng": assigned_rows[0]["lng"]}
        ordered = nearest_neighbor_order(assigned_rows, start=reload_start)
        st.session_state.route_stops = ordered
        st.session_state.current_stop_idx = 0
        with st.spinner("Reloading route..."):
            st.session_state.route_segments = build_route_segments(ordered, start=reload_start)

    m1, m2, m3 = st.columns(3)
    total_stops = len(st.session_state.route_stops or [])
    m1.metric(T("active_stops"), total_stops)
    m2.metric("Progress", f"{st.session_state.current_stop_idx}/{total_stops}" if total_stops else "0/0")
    m3.metric(T("fuel_optimized"), f"{st.session_state.fuel_saved_pct or 0}%")

    # ---- SOS / Vehicle Breakdown — releases every stop currently assigned
    # to THIS driver (that hasn't been collected yet) back to the pending
    # pool so another driver can pick it up, and logs an sos_alerts row for
    # the govt dashboard to see. ----
    if total_stops > 0:
        with st.expander("🆘 SOS / Vehicle Breakdown"):
            st.caption("Vehicle broke down or an emergency came up? This will immediately release all your remaining stops back to the pending pool so another driver can pick them up.")
            sos_reason = st.selectbox("Reason", ["Vehicle breakdown", "Accident", "Medical emergency", "Fuel shortage", "Other"], key="sos_reason")
            sos_note = st.text_input("Additional note (optional)", key="sos_note")
            if st.button("🆘 Raise SOS & Release My Stops", type="secondary", use_container_width=True):
                remaining_stops = (st.session_state.route_stops or [])[st.session_state.current_stop_idx:]
                remaining_ids = [s["id"] for s in remaining_stops]
                if remaining_ids:
                    sb.table("garbage_reports").update({
                        "status": "pending", "driver_id": None,
                    }).in_("id", remaining_ids).execute()
                sb.table("sos_alerts").insert({
                    "driver_id": user["id"], "reason": sos_reason, "note": sos_note.strip() or None,
                    "lat": driver_location["lat"] if driver_location else None,
                    "lng": driver_location["lng"] if driver_location else None,
                    "stops_released": len(remaining_ids), "status": "open",
                }).execute()
                st.session_state.route_stops = None
                st.session_state.route_segments = None
                st.session_state.current_stop_idx = 0
                st.session_state.fuel_saved_pct = None
                st.success(f"SOS raised. {len(remaining_ids)} stop(s) released back to the pending pool.")
                st.rerun()

    if st.button(f"✓ {T('optimize_route')}", type="primary", disabled=not has_location,
                 help=None if has_location else "Please set your current location first (📍 section above)"):
        if not has_location:
            st.error("📍 Please set your current location before optimizing a route.")
            st.stop()
        # Only truly-unclaimed pending reports (not already assigned to
        # another driver) — this ensures multiple drivers never double-assign
        # the same report.
        pending_res = (
            sb.table("garbage_reports")
            .select("*, shg:users!garbage_reports_shg_id_fkey(full_name,mobile)")
            .eq("status", "pending")
            .order("created_at")
            .execute()
        )
        candidates = _flatten_shg(pending_res.data)
        if not candidates:
            st.warning("No pending reports to optimize.")
        else:
            for s in candidates:
                s["lat"] = float(s["lat"]) if s["lat"] is not None else DEPOT["lat"]
                s["lng"] = float(s["lng"]) if s["lng"] is not None else DEPOT["lng"]

            driver_radius = float(user.get("service_radius_km") or DEFAULT_SERVICE_RADIUS_KM)

            # 1) Pick a capacity-aware batch for THIS driver's trip — Zomato/
            #    Blinkit-style zone allocation: only reports inside the
            #    driver's own service_radius_km are eligible, scored by
            #    closer-to-driver + higher-garbage first, within vehicle
            #    capacity — so each driver naturally claims what's near AND
            #    within their own zone.
            batch = select_batch_for_driver(candidates, driver_location=driver_location, radius_km=driver_radius)
            if not batch:
                st.warning(
                    f"📭 No pending reports inside your {driver_radius:.0f} km zone right now. "
                    f"({len(candidates)} report(s) pending overall, but they're all outside your zone.) "
                    f"Try increasing your service radius above (📍 section), or check back shortly."
                )
                st.stop()
            # 2) Find the best visiting order within that batch, starting
            #    from the driver's current location.
            optimized = nearest_neighbor_order(batch, start=driver_location)

            naive_len = route_length(batch, start=driver_location)
            opt_len = route_length(optimized, start=driver_location)
            fuel_saved = max(0, round((1 - opt_len / naive_len) * 100)) if naive_len > 0 else 0

            ids = [s["id"] for s in optimized]
            sb.table("garbage_reports").update({
                "status": "assigned", "driver_id": user["id"],
            }).in_("id", ids).execute()

            st.session_state.route_stops = optimized
            st.session_state.current_stop_idx = 0
            st.session_state.fuel_saved_pct = fuel_saved

            with st.spinner("Fetching road route (OSRM)..."):
                st.session_state.route_segments = build_route_segments(optimized, start=driver_location)
            st.rerun()

    stops = st.session_state.route_stops or []
    current_idx = st.session_state.current_stop_idx

    # Safety net: stops can exist (reloaded from DB) even if driver_location is
    # currently None (e.g. app was restarted and location wasn't re-set yet).
    # In that case fall back to the first stop's own position for display
    # only — this never affects NEW route optimization, which is fully
    # blocked above until a real location is set.
    origin_for_display = driver_location or (
        {"lat": stops[0]["lat"], "lng": stops[0]["lng"]} if stops else DEPOT
    )

    if stops:
        # ---- "On the way" garbage — uses cheapest-insertion to add newly
        # reported garbage into the remaining route (like how delivery apps
        # add an 'on the way' pickup) ----
        if st.button("🔄 Check for new garbage along the way", use_container_width=True):
            with st.spinner("Checking nearby pending reports..."):
                fresh_res = (
                    sb.table("garbage_reports")
                    .select("*, shg:users!garbage_reports_shg_id_fkey(full_name,mobile)")
                    .eq("status", "pending")
                    .order("created_at")
                    .execute()
                )
                fresh_candidates = _flatten_shg(fresh_res.data)
                for c in fresh_candidates:
                    c["lat"] = float(c["lat"]) if c["lat"] is not None else DEPOT["lat"]
                    c["lng"] = float(c["lng"]) if c["lng"] is not None else DEPOT["lng"]

                vehicle_pos = origin_for_display if current_idx == 0 else {
                    "lat": stops[current_idx - 1]["lat"], "lng": stops[current_idx - 1]["lng"]
                }
                future_stops = stops[current_idx:]
                path_points = [vehicle_pos] + [{"lat": s["lat"], "lng": s["lng"]} for s in future_stops]

                inserted = []
                for c in fresh_candidates:
                    if len(stops) >= MAX_STOPS_PER_ROUTE + 3:
                        break
                    idx_in_future, extra_km = cheapest_insertion(path_points, c)
                    if extra_km <= ENROUTE_MAX_DETOUR_KM:
                        insert_at = current_idx + idx_in_future - 1
                        stops.insert(insert_at, c)
                        path_points.insert(idx_in_future, {"lat": c["lat"], "lng": c["lng"]})
                        sb.table("garbage_reports").update({
                            "status": "assigned", "driver_id": user["id"],
                        }).eq("id", c["id"]).execute()
                        inserted.append(c)

            if inserted:
                st.session_state.route_stops = stops
                st.session_state.route_segments = build_route_segments(stops, start=origin_for_display)
                st.success(f"{len(inserted)} new garbage point(s) added along the route!")
                st.rerun()
            else:
                st.info("No new pending garbage found near the route right now.")

        # ---- Map: driver's current position + completed (green) vs
        # in-progress (animated dashed) vs upcoming (light dashed) legs ----
        vehicle_pos = origin_for_display if current_idx == 0 else {
            "lat": stops[current_idx - 1]["lat"], "lng": stops[current_idx - 1]["lng"]
        }
        m = folium.Map(location=[vehicle_pos["lat"], vehicle_pos["lng"]], zoom_start=12)

        folium.Marker(
            [DEPOT["lat"], DEPOT["lng"]], tooltip=DEPOT["name"],
            icon=folium.Icon(color="darkblue", icon="home"),
        ).add_to(m)

        for idx, s in enumerate(stops):
            if idx < current_idx:
                color, icon_name = "green", "check"
            elif idx == current_idx:
                color, icon_name = "red", "flag-checkered"
            else:
                color, icon_name = "orange", "trash"
            folium.Marker(
                [float(s["lat"]), float(s["lng"])],
                tooltip=(f"Stop {idx + 1}: {s.get('location_name') or s.get('village')} ({s['quantity_kg']} kg)"
                         f" — {s.get('shg_name', '')} · {s.get('shg_mobile', '')}"),
                icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
            ).add_to(m)

        # Vehicle's (driver's) current position — a larger, distinct icon
        folium.Marker(
            [vehicle_pos["lat"], vehicle_pos["lng"]], tooltip="🚚 You are here",
            icon=folium.Icon(color="black", icon="truck", prefix="fa"),
        ).add_to(m)

        segments = st.session_state.route_segments or []
        all_pts = [[vehicle_pos["lat"], vehicle_pos["lng"]]]
        for i, seg in enumerate(segments):
            if i < current_idx:
                folium.PolyLine(seg, color="#1E7A46", weight=5, opacity=0.85).add_to(m)  # already completed
            elif i == current_idx:
                AntPath(seg, color="#0B3D62", weight=5, opacity=0.9, delay=800).add_to(m)  # currently heading this way
            else:
                folium.PolyLine(seg, color="#8B98A3", weight=3, opacity=0.5, dash_array="4,8").add_to(m)  # still upcoming
            all_pts.extend(seg)
        if all_pts:
            m.fit_bounds(all_pts)
        st_folium(m, height=400, width=None, returned_objects=[])
        st.caption("🟢 Complete · 🔵 Currently on this leg (animated) · ⚪ Upcoming — 🚚 your current position")

        # ---- Plastic-type rate card (govt-controlled) — both SHG and driver
        # payouts are calculated from this, based on quantity ----
        rates_res = sb.table("plastic_rates").select("*").execute()
        rate_map = {
            r["type"]: (float(r["shg_rate_per_kg"]), float(r["driver_rate_per_kg"]))
            for r in rates_res.data
        }
        default_rate = (2.0, 0.5)  # fallback if a type has no rate configured

        # ---- Stop list — only the CURRENT stop is interactive; completed
        # stops are shown (read-only), and upcoming stops stay locked until
        # the current one is OTP-verified. ----
        for idx, s in enumerate(stops):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**Stop {idx + 1}: {s.get('location_name') or s.get('village')}**")
                c1.caption(f"{s['quantity_kg']} kg · {s.get('plastic_type', 'Mixed Plastic')} · {s.get('description') or 'no description'}")
                c1.markdown(f"👤 **{s.get('shg_name', '—')}** &nbsp; 📞 **{s.get('shg_mobile', '—')}**")

                if idx < current_idx:
                    c2.success("✅ Collected")
                elif idx > current_idx:
                    c2.caption("🔒 Complete the current stop first")
                else:
                    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lng']}&travelmode=driving"
                    c1.link_button("🧭 Start Navigation", maps_url, use_container_width=True)
                    pickup_photo = c1.camera_input(
                        "📸 Proof of Pickup (optional)", key=f"photo_{s['id']}",
                        label_visibility="visible",
                    )
                    otp_input = c2.text_input(T("otp"), max_chars=4, key=f"otp_{s['id']}",
                                               label_visibility="collapsed", placeholder="4-digit OTP")
                    if c3.button(T("verify_collect"), key=f"verify_{s['id']}", use_container_width=True):
                        if otp_input.strip() == str(s["otp"]):
                            shg_rate, driver_rate = rate_map.get(s.get("plastic_type"), default_rate)
                            qty = float(s["quantity_kg"])
                            payout_shg = round(qty * shg_rate, 2)
                            payout_driver = round(qty * driver_rate, 2)

                            pickup_photo_url = None
                            if pickup_photo is not None:
                                with st.spinner("Uploading proof of pickup..."):
                                    pickup_photo_url = upload_photo(
                                        pickup_photo.getvalue(), "pickup.jpg", "pickup", bucket=PICKUP_BUCKET_NAME
                                    )

                            sb.table("garbage_reports").update({
                                "status": "collected",
                                "collected_at": datetime.now().isoformat(),
                                "pickup_photo_url": pickup_photo_url,
                            }).eq("id", s["id"]).execute()

                            # PostgREST doesn't support an atomic "wallet = wallet + x"
                            # increment via the query builder, so we fetch-then-update.
                            wallet_res = sb.table("users").select("wallet").eq("id", s["shg_id"]).execute()
                            current_wallet = float(wallet_res.data[0]["wallet"]) if wallet_res.data else 0.0
                            sb.table("users").update({"wallet": current_wallet + payout_shg}).eq("id", s["shg_id"]).execute()

                            # The driver's own wallet is credited using the same rate card too
                            driver_wallet_res = sb.table("users").select("wallet").eq("id", user["id"]).execute()
                            driver_current_wallet = float(driver_wallet_res.data[0]["wallet"]) if driver_wallet_res.data else 0.0
                            new_driver_wallet = round(driver_current_wallet + payout_driver, 2)
                            sb.table("users").update({"wallet": new_driver_wallet}).eq("id", user["id"]).execute()
                            st.session_state.user["wallet"] = new_driver_wallet

                            st.success(f"Verified! ₹{payout_shg} → SHG wallet, ₹{payout_driver} → your wallet.")

                            if current_idx + 1 >= len(stops):
                                # Route complete — clear state so the next click starts a fresh batch
                                st.session_state.route_stops = None
                                st.session_state.route_segments = None
                                st.session_state.current_stop_idx = 0
                                st.session_state.just_completed_route = True
                            else:
                                st.session_state.current_stop_idx = current_idx + 1
                            st.rerun()
                        else:
                            st.error(T("wrong_otp"))
    else:
        st.info("No active route — click 'Optimize Route' to get started.")


# ============================================================
# PDF REPORT — shared helpers (KPI cards, charts, banner, table)
# in navy/green govt-theme colors matching the web version — both the govt
# and SHG reports reuse this same look-and-feel.
# ============================================================
_PDF_NAVY = (11, 61, 98)
_PDF_GREEN = (30, 122, 70)
_PDF_WARN = (183, 121, 27)
_PDF_GREY = (85, 99, 111)
_PDF_ROW_TINT = (228, 236, 243)


def _pdf_output_bytes(pdf) -> bytes:
    """Converts the PDF to bytes — works with both legacy PyFPDF and fpdf2
    (their output() APIs differ)."""
    try:
        out = pdf.output(dest="S")  # legacy PyFPDF: forces string return
    except TypeError:
        out = pdf.output()  # fpdf2: no 'dest' kwarg, already returns bytearray
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1")


def _pdf_header_banner(pdf, title: str, subtitle: str):
    """Full-width colored banner — title, subtitle, and a generated-at timestamp."""
    pdf.set_fill_color(*_PDF_NAVY)
    pdf.rect(0, 0, 210, 27, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 6)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 9, title)
    pdf.set_xy(10, 15.5)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(0, 6, subtitle)
    pdf.set_xy(10, 21)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    pdf.set_text_color(0, 0, 0)


def _pdf_kpi_card(pdf, x: float, y: float, w: float, h: float, label: str, value: str, color: tuple):
    """A small colored KPI box — a large number with a small label above it."""
    pdf.set_fill_color(*color)
    pdf.rect(x, y, w, h, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_xy(x, y + h * 0.20)
    pdf.cell(w, h * 0.38, value, align="C")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(x, y + h * 0.62)
    pdf.cell(w, h * 0.28, label.upper(), align="C")
    pdf.set_text_color(0, 0, 0)


def _pdf_kpi_row(pdf, kpis: list, y: float) -> float:
    """kpis = [(value, label, color), ...] — fits them all into one row, returns the new Y."""
    x0, card_h, gap = 10, 22, 3.5
    n = len(kpis)
    card_w = (190 - (n - 1) * gap) / n
    for i, (value, label, color) in enumerate(kpis):
        _pdf_kpi_card(pdf, x0 + i * (card_w + gap), y, card_w, card_h, label, value, color)
    return y + card_h + 9


def _chart_line(x_labels: list, y_values: list, path: str, color: str, title: str):
    """A small, clean line/area chart — used for the daily trend."""
    fig, ax = plt.subplots(figsize=(9.4, 2.7), dpi=150)
    xs = list(range(len(x_labels)))
    ax.plot(xs, y_values, color=color, linewidth=2.4, marker="o", markersize=4.5,
            markerfacecolor=color, markeredgecolor="white", markeredgewidth=0.8, zorder=3)
    ax.fill_between(xs, y_values, color=color, alpha=0.10, zorder=2)
    ax.set_xticks(xs)
    ax.set_xticklabels(x_labels, fontsize=7.5, color="#55636F")
    ax.tick_params(axis="y", labelsize=7.5, colors="#55636F")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#DCE3E9")
    ax.grid(axis="y", color="#DCE3E9", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=10, color="#0B3D62", fontweight="bold", loc="left", pad=8)
    fig.patch.set_alpha(0)
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


def _chart_bar(labels: list, values: list, path: str, color: str, title: str, horizontal: bool = False):
    """Vertical or horizontal bar chart — used for village/wallet comparisons."""
    fig, ax = plt.subplots(figsize=(9.4, 3.0 if horizontal else 2.8), dpi=150)
    if horizontal:
        ypos = range(len(labels))
        ax.barh(list(ypos), values, color=color, height=0.55, zorder=3)
        ax.set_yticks(list(ypos))
        ax.set_yticklabels(labels, fontsize=8, color="#33414B")
        ax.invert_yaxis()
        ax.tick_params(axis="x", labelsize=7.5, colors="#55636F")
        ax.grid(axis="x", color="#DCE3E9", linewidth=0.7, zorder=0)
    else:
        xpos = range(len(labels))
        ax.bar(list(xpos), values, color=color, width=0.55, zorder=3)
        ax.set_xticks(list(xpos))
        ax.set_xticklabels(labels, fontsize=7.5, color="#55636F", rotation=20, ha="right")
        ax.tick_params(axis="y", labelsize=7.5, colors="#55636F")
        ax.grid(axis="y", color="#DCE3E9", linewidth=0.7, zorder=0)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#DCE3E9")
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=10, color="#0B3D62", fontweight="bold", loc="left", pad=8)
    fig.patch.set_alpha(0)
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


def _pdf_table(pdf, headers: list, col_widths: list, rows: list):
    """A colored header + zebra-striped rows table (govt navy theme)."""
    pdf.set_x(10)
    pdf.set_fill_color(*_PDF_NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 7, h, border=0, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 7.5)
    for i, row in enumerate(rows):
        pdf.set_x(10)
        pdf.set_fill_color(*(_PDF_ROW_TINT if i % 2 == 0 else (255, 255, 255)))
        for val, w in zip(row, col_widths):
            pdf.cell(w, 6.4, str(val), border=0, align="C", fill=True)
        pdf.ln()


# ============================================================
# PDF REPORT — downloadable interactive-style summary for Government
# ============================================================
def generate_govt_pdf_report(reports, users_df, total_kg, pending_ct, collected_ct, shg_ct, driver_ct):
    tmp_dir = tempfile.mkdtemp(prefix="echobyte_")
    chart_paths = []

    pdf = FPDF()
    pdf.add_page()
    _pdf_header_banner(pdf, "EchoByte - Government Report",
                        "Government of Chhattisgarh - Rural Waste Management Pilot")

    y = _pdf_kpi_row(pdf, [
        (f"{total_kg:,.0f} kg", "Total Collected", _PDF_NAVY),
        (str(int(pending_ct)), "Pending", _PDF_WARN),
        (str(int(collected_ct)), "Collected", _PDF_GREEN),
        (str(int(shg_ct)), "SHGs Registered", _PDF_NAVY),
        (str(int(driver_ct)), "Drivers Registered", _PDF_NAVY),
    ], y=33)
    pdf.set_y(y)

    if not reports.empty:
        reports = reports.copy()
        reports["date"] = pd.to_datetime(reports["created_at"]).dt.date.astype(str)
        trend = reports.groupby("date")["quantity_kg"].sum().astype(float).sort_index()
        if len(trend) >= 1:
            path = os.path.join(tmp_dir, "trend.png")
            _chart_line([d[5:] for d in trend.index], trend.values.tolist(), path,
                        color="#0B3D62", title="Daily Collection Trend (kg)")
            chart_paths.append(path)
            pdf.image(path, x=10, y=pdf.get_y(), w=190)
            pdf.set_y(pdf.get_y() + 58)

        village_totals = reports.groupby("village")["quantity_kg"].sum().astype(float).sort_values(ascending=False).head(10)
        if not village_totals.empty:
            if pdf.get_y() > 225:
                pdf.add_page()
                pdf.set_y(14)
            path = os.path.join(tmp_dir, "village.png")
            _chart_bar(list(village_totals.index), village_totals.values.tolist(), path,
                       color="#1E7A46", title="Village-wise Quantity (kg)")
            chart_paths.append(path)
            pdf.image(path, x=10, y=pdf.get_y(), w=190)
            pdf.set_y(pdf.get_y() + 60)

        if not users_df.empty:
            shg_wallets = users_df[users_df["role"] == "shg"][["full_name", "wallet"]].copy()
            if not shg_wallets.empty:
                shg_wallets["wallet"] = shg_wallets["wallet"].astype(float)
                shg_wallets = shg_wallets.sort_values("wallet", ascending=False).head(8)
                if pdf.get_y() > 210:
                    pdf.add_page()
                    pdf.set_y(14)
                path = os.path.join(tmp_dir, "wallet.png")
                _chart_bar(list(shg_wallets["full_name"]), shg_wallets["wallet"].tolist(), path,
                           color="#B7791B", title="Top SHG Wallet Balances (Rs.)", horizontal=True)
                chart_paths.append(path)
                pdf.image(path, x=10, y=pdf.get_y(), w=190)
                pdf.set_y(pdf.get_y() + 66)

        if pdf.get_y() > 225:
            pdf.add_page()
            pdf.set_y(14)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*_PDF_NAVY)
        pdf.set_x(10)
        pdf.cell(0, 8, "Recent Activity (latest 20)", ln=True)
        pdf.set_text_color(0, 0, 0)
        recent = reports.sort_values("created_at", ascending=False).head(20)
        rows = [
            [str(r.get("village") or "-")[:16], str(r.get("location_name") or "-")[:22],
             f"{float(r.get('quantity_kg') or 0):.1f}", str(r.get("status") or "-"),
             str(r.get("created_at") or "-")[:16]]
            for _, r in recent.iterrows()
        ]
        _pdf_table(pdf, ["Village", "Location", "Qty(kg)", "Status", "Date"], [35, 55, 20, 25, 45], rows)
    else:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(10)
        pdf.cell(0, 8, "No data available yet.", ln=True)

    pdf_bytes = _pdf_output_bytes(pdf)

    for p in chart_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    return pdf_bytes


# ============================================================
# PDF REPORT — downloadable interactive-style summary for an SHG's own collections
# ============================================================
def generate_shg_pdf_report(user, df):
    tmp_dir = tempfile.mkdtemp(prefix="echobyte_shg_")
    chart_paths = []

    total_reports = len(df)
    total_kg = df["quantity_kg"].astype(float).sum() if not df.empty else 0.0
    pending_ct = (df["status"] == "pending").sum() if not df.empty else 0
    collected_ct = (df["status"] == "collected").sum() if not df.empty else 0

    pdf = FPDF()
    pdf.add_page()
    _pdf_header_banner(pdf, "EchoByte - SHG Collection Report",
                        f"{user['full_name']} - {user.get('village', '-')}")

    y = _pdf_kpi_row(pdf, [
        (str(int(total_reports)), "Total Reports", _PDF_NAVY),
        (f"{total_kg:,.1f} kg", "Qty Reported", _PDF_GREEN),
        (f"Rs.{float(user['wallet']):,.0f}", "Wallet Balance", _PDF_WARN),
        (str(int(pending_ct)), "Pending", _PDF_NAVY),
        (str(int(collected_ct)), "Collected", _PDF_GREEN),
    ], y=33)
    pdf.set_y(y)

    if not df.empty:
        d = df.copy()
        d["date"] = pd.to_datetime(d["created_at"]).dt.date.astype(str)
        trend = d.groupby("date")["quantity_kg"].sum().astype(float).sort_index()
        if len(trend) >= 1:
            path = os.path.join(tmp_dir, "shg_trend.png")
            _chart_line([dt[5:] for dt in trend.index], trend.values.tolist(), path,
                        color="#1E7A46", title="Your Collection Trend (kg)")
            chart_paths.append(path)
            pdf.image(path, x=10, y=pdf.get_y(), w=190)
            pdf.set_y(pdf.get_y() + 58)

        if pdf.get_y() > 225:
            pdf.add_page()
            pdf.set_y(14)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*_PDF_NAVY)
        pdf.set_x(10)
        pdf.cell(0, 8, "Your Reports", ln=True)
        pdf.set_text_color(0, 0, 0)
        recent = df.sort_values("created_at", ascending=False).head(25)
        rows = [
            [str(r.get("location_name") or "-")[:22], f"{float(r.get('quantity_kg') or 0):.1f}",
             str(r.get("plastic_type") or "-")[:16], str(r.get("status") or "-"),
             str(r.get("created_at") or "-")[:16]]
            for _, r in recent.iterrows()
        ]
        _pdf_table(pdf, ["Location", "Qty(kg)", "Type", "Status", "Date"], [50, 25, 40, 30, 45], rows)
    else:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(10)
        pdf.cell(0, 8, "No reports submitted yet.", ln=True)

    pdf_bytes = _pdf_output_bytes(pdf)

    for p in chart_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    return pdf_bytes


# ============================================================
# GOVERNMENT DASHBOARD
# ============================================================
def render_govt(user):
    render_lang_selector("sidebar")
    st.sidebar.markdown(f"### 🏛️ {user['full_name']}")
    st.sidebar.caption(user["email"])
    if user.get("photo_url"):
        st.sidebar.image(user["photo_url"], width=80)
    if st.sidebar.button(T("logout"), use_container_width=True):
        do_logout()

    render_org_header()
    st.title(T("govt_dashboard"))
    st.caption(T("govt_caption"))

    reports_res = sb.table("garbage_reports").select("*").execute()
    users_res = sb.table("users").select("*").execute()
    reports = pd.DataFrame(reports_res.data)
    users_df = pd.DataFrame(users_res.data)

    total_kg = reports["quantity_kg"].astype(float).sum() if not reports.empty else 0
    pending_ct = (reports["status"] == "pending").sum() if not reports.empty else 0
    collected_ct = (reports["status"] == "collected").sum() if not reports.empty else 0
    shg_ct = (users_df["role"] == "shg").sum() if not users_df.empty else 0
    driver_ct = (users_df["role"] == "driver").sum() if not users_df.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(T("total_collected"), f"{total_kg:,.0f}")
    k2.metric(T("pending"), int(pending_ct))
    k3.metric(T("collected"), int(collected_ct))
    k4.metric(T("shgs_registered"), int(shg_ct))
    k5.metric(T("drivers_registered"), int(driver_ct))

    if st.button(f"📄 {T('download_pdf_report')}"):
        with st.spinner("Generating report (with charts, this may take a moment)..."):
            pdf_bytes = generate_govt_pdf_report(reports, users_df, total_kg, pending_ct, collected_ct, shg_ct, driver_ct)
        st.download_button(
            "⬇️ Download PDF", data=pdf_bytes,
            file_name=f"EchoByte_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
        )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("trend_daily")}</div>', unsafe_allow_html=True)
        if not reports.empty:
            reports["date"] = pd.to_datetime(reports["created_at"]).dt.date.astype(str)
            trend = (
                reports.groupby("date")["quantity_kg"]
                .sum().astype(float)
                .reset_index()
                .rename(columns={"quantity_kg": "kg"})
                .set_index("date")
            )
            # Using bar_chart here because line_chart doesn't visually show
            # anything meaningful with only one or two days of data (a line
            # needs 2+ points to draw)
            st.bar_chart(trend, y="kg")
        else:
            st.info("No data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("village_wise")}</div>', unsafe_allow_html=True)
        if not reports.empty:
            village_totals = reports.groupby("village")["quantity_kg"].sum().astype(float).sort_values(ascending=False)
            st.bar_chart(village_totals)
        else:
            st.info("No data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("wallet_distribution")}</div>', unsafe_allow_html=True)
    shg_wallets = users_df[users_df["role"] == "shg"][["full_name", "village", "wallet"]] if not users_df.empty else pd.DataFrame()
    if shg_wallets.empty:
        st.info("No SHGs registered yet.")
    else:
        st.dataframe(shg_wallets.rename(columns={"full_name": "Name", "village": "Village", "wallet": "Wallet (₹)"}),
                     use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Plastic Waste Heatmap — density of garbage_reports weighted by
    # quantity_kg, to visually spot collection hotspots across the pilot area. ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">🗺️ Plastic Waste Heatmap</div>', unsafe_allow_html=True)
    geo_reports = reports.dropna(subset=["lat", "lng"]) if not reports.empty else pd.DataFrame()
    if geo_reports.empty:
        st.info("No geo-tagged reports yet.")
    else:
        heat_points = [
            [float(r["lat"]), float(r["lng"]), float(r["quantity_kg"])]
            for _, r in geo_reports.iterrows()
        ]
        center_lat = geo_reports["lat"].astype(float).mean()
        center_lng = geo_reports["lng"].astype(float).mean()
        hm = folium.Map(location=[center_lat, center_lng], zoom_start=10)
        HeatMap(heat_points, radius=18, blur=22, max_zoom=13).add_to(hm)
        st_folium(hm, height=420, width=None, returned_objects=[])
        st.caption("Brighter/denser areas = more plastic waste reported there — useful for planning new PWM units or extra driver zones.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Plastic rate settings — govt sets the SHG/Driver rate (₹/kg) for
    # each plastic type here; wallets are built from this on verified collection ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("plastic_rate_settings")}</div>', unsafe_allow_html=True)
    rates_res = sb.table("plastic_rates").select("*").order("type").execute()
    rates_df = pd.DataFrame(rates_res.data)
    if rates_df.empty:
        st.info("No plastic type configured yet.")
    else:
        col_type, col_shg, col_drv = T("plastic_type"), f"{T('shg_rate')} (₹/kg)", f"{T('driver_rate')} (₹/kg)"
        display_df = rates_df[["type", "shg_rate_per_kg", "driver_rate_per_kg"]].rename(columns={
            "type": col_type, "shg_rate_per_kg": col_shg, "driver_rate_per_kg": col_drv,
        })
        edited = st.data_editor(
            display_df, hide_index=True, use_container_width=True,
            key="rate_editor", disabled=[col_type],
        )
        if st.button(T("save_rates")):
            for _, row in edited.iterrows():
                sb.table("plastic_rates").update({
                    "shg_rate_per_kg": float(row[col_shg]),
                    "driver_rate_per_kg": float(row[col_drv]),
                }).eq("type", row[col_type]).execute()
            st.success(T("rates_saved"))
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Payout Approval Queue — govt reviews each withdrawal request and
    # either Approves (marks paid — actual money movement still happens via
    # their own bank/UPI system outside this app) or Rejects it (in which
    # case the amount is refunded back into the user's in-app wallet, since
    # render_wallet_withdraw() already deducted it at request time). ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">💳 Payout Approval Queue</div>', unsafe_allow_html=True)
    wd_res = (
        sb.table("withdrawals").select("*, u:users!withdrawals_user_id_fkey(full_name)")
        .order("created_at", desc=True).execute()
    )
    wd_rows = wd_res.data
    if not wd_rows:
        st.info(T("no_withdrawals"))
    else:
        pending_wd = [w for w in wd_rows if w["status"] == "pending"]
        st.caption(f"{len(pending_wd)} request(s) awaiting approval")
        for w in wd_rows:
            name = (w.get("u") or {}).get("full_name", "—")
            with st.container(border=True):
                wc1, wc2, wc3, wc4 = st.columns([3, 2, 1, 1])
                wc1.markdown(f"**{name}** ({w['role']}) &nbsp; ₹{w['amount']} via **{T(w['method'])}**")
                wc1.caption(w.get("details") or "—")
                status_badge = {"pending": "🟠 pending", "paid": "🟢 approved & paid", "rejected": "🔴 rejected"}.get(w["status"], w["status"])
                wc2.markdown(f"`{status_badge}`")
                if w["status"] == "pending":
                    if wc3.button("✅ Approve", key=f"approve_{w['id']}", use_container_width=True):
                        sb.table("withdrawals").update({
                            "status": "paid", "approved_by": user["id"],
                            "approved_at": datetime.now().isoformat(),
                        }).eq("id", w["id"]).execute()
                        st.rerun()
                    if wc4.button("❌ Reject", key=f"reject_{w['id']}", use_container_width=True):
                        # Refund: the amount was already deducted from the
                        # user's wallet when they submitted the request.
                        u_res = sb.table("users").select("wallet").eq("id", w["user_id"]).execute()
                        cur_wallet = float(u_res.data[0]["wallet"]) if u_res.data else 0.0
                        sb.table("users").update({"wallet": round(cur_wallet + float(w["amount"]), 2)}).eq("id", w["user_id"]).execute()
                        sb.table("withdrawals").update({
                            "status": "rejected", "approved_by": user["id"],
                            "approved_at": datetime.now().isoformat(),
                        }).eq("id", w["id"]).execute()
                        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Disputes raised by SHGs — govt can review and mark resolved ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">⚠️ Reported Issues (Disputes)</div>', unsafe_allow_html=True)
    disp_res = (
        sb.table("disputes")
        .select("*, shg:users(full_name,mobile), report:garbage_reports(location_name,village,quantity_kg)")
        .order("created_at", desc=True).execute()
    )
    if not disp_res.data:
        st.info("No issues reported yet.")
    else:
        open_ct = sum(1 for d in disp_res.data if d["status"] == "open")
        st.caption(f"{open_ct} open issue(s)")
        for d in disp_res.data:
            shg = d.get("shg") or {}
            rep = d.get("report") or {}
            with st.container(border=True):
                dc1, dc2 = st.columns([3, 1])
                dc1.markdown(f"**{shg.get('full_name', '—')}** · {rep.get('location_name') or rep.get('village') or '—'} ({rep.get('quantity_kg', '—')} kg)")
                dc1.caption(d["reason"])
                if d["status"] == "open":
                    dc2.markdown("🟠 Open")
                    note = dc1.text_input("Resolution note", key=f"note_{d['id']}", label_visibility="collapsed", placeholder="Resolution note...")
                    if dc2.button("Mark Resolved", key=f"resolve_{d['id']}", use_container_width=True):
                        sb.table("disputes").update({
                            "status": "resolved", "resolution_note": note.strip() or None,
                            "resolved_at": datetime.now().isoformat(),
                        }).eq("id", d["id"]).execute()
                        st.rerun()
                else:
                    dc2.markdown("🟢 Resolved")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Dynamic PWM Unit Management — full CRUD from the admin panel
    # (add / edit / deactivate / delete recycler / plastic-waste-management
    # units), instead of these being hardcoded anywhere in the app. ----
    st.markdown(f'<div class="ledger-card"><div class="eyebrow">🏭 PWM Unit Management</div>', unsafe_allow_html=True)
    with st.expander("➕ Add new PWM unit"):
        with st.form("add_pwm_unit_form"):
            pu_name = st.text_input("Unit Name")
            pu_loc_query = st.text_input("Location (village/area — will be geocoded)", placeholder="e.g. Mathpurena, Raipur")
            pu_capacity = st.number_input("Capacity (kg)", min_value=0.0, step=50.0)
            pu_contact_person = st.text_input("Contact Person")
            pu_contact_mobile = st.text_input("Contact Mobile")
            pu_submit = st.form_submit_button("Add Unit", use_container_width=True)
        if pu_submit:
            if not pu_name or not pu_loc_query:
                st.error(T("fill_all_fields"))
            else:
                with st.spinner("Locating..."):
                    results, err = geocode_location(pu_loc_query.strip())
                if err or not results:
                    st.error(f"Could not locate '{pu_loc_query}'. Try a more specific name.")
                else:
                    r = results[0]
                    sb.table("pwm_units").insert({
                        "name": pu_name.strip(), "location_name": pu_loc_query.strip(),
                        "lat": float(r["lat"]), "lng": float(r["lon"]),
                        "capacity_kg": pu_capacity, "contact_person": pu_contact_person.strip() or None,
                        "contact_mobile": pu_contact_mobile.strip() or None, "status": "active",
                    }).execute()
                    st.success(f"PWM unit '{pu_name}' added.")
                    st.rerun()

    pwm_res = sb.table("pwm_units").select("*").order("created_at", desc=True).execute()
    if not pwm_res.data:
        st.caption("No PWM units added yet.")
    else:
        for pu in pwm_res.data:
            with st.container(border=True):
                puc1, puc2, puc3, puc4 = st.columns([3, 2, 1, 1])
                puc1.markdown(f"**{pu['name']}** · {pu.get('location_name') or '—'}")
                puc1.caption(f"Capacity: {pu.get('capacity_kg', 0):.0f} kg · Contact: {pu.get('contact_person') or '—'} ({pu.get('contact_mobile') or '—'})")
                puc2.markdown(f"`{pu['status']}`")
                toggle_label = "Deactivate" if pu["status"] == "active" else "Activate"
                if puc3.button(toggle_label, key=f"toggle_pwm_{pu['id']}", use_container_width=True):
                    new_status = "inactive" if pu["status"] == "active" else "active"
                    sb.table("pwm_units").update({"status": new_status}).eq("id", pu["id"]).execute()
                    st.rerun()
                if puc4.button("🗑️ Delete", key=f"delete_pwm_{pu['id']}", use_container_width=True):
                    sb.table("pwm_units").delete().eq("id", pu["id"]).execute()
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f'<div class="ledger-card"><div class="eyebrow">{T("recent_activity")}</div>', unsafe_allow_html=True)
    if reports.empty:
        st.info("No reports yet.")
    else:
        recent = reports.sort_values("created_at", ascending=False).head(15)[
            ["village", "location_name", "quantity_kg", "status", "created_at"]
        ].rename(columns={
            "village": "Village", "location_name": "Location", "quantity_kg": "Qty (kg)",
            "status": "Status", "created_at": "Date"
        })
        st.dataframe(recent, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ROUTER
# ============================================================
if st.session_state.user is None:
    safe_call(render_auth)
else:
    u = st.session_state.user
    if u["role"] == "shg":
        safe_call(render_shg, u)
    elif u["role"] == "driver":
        safe_call(render_driver, u)
    elif u["role"] == "govt":
        safe_call(render_govt, u)
