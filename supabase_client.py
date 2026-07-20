"""
supabase_client.py — Supabase client (Project URL + anon public key)

Tables are NOT created from this file — run `schema.sql` in the Supabase
Dashboard's SQL Editor instead (one-time setup). This file only provides a
connected client that the whole app (SHG/Driver/Govt) uses to read/write
tables, and uploads profile photos to the "profile-photos" Storage bucket.

No Postgres password is needed here — just the Project URL and the anon
public key (found under Project Settings -> API).
"""
import os
import uuid
from supabase import create_client, Client


def _get_secret(key: str, default: str) -> str:
    """Checks Streamlit secrets first, then the environment variable, then falls back to the hardcoded default."""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


# ============================================================
# Supabase Dashboard -> Project Settings -> API se yeh 2 values milengi
# ============================================================
SUPABASE_URL = _get_secret("SUPABASE_URL", "https://lduyyzlulwlomhwfvzud.supabase.co")
SUPABASE_ANON_KEY = _get_secret("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkdXl5emx1bHdsb21od2Z2enVkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMwNDg4ODYsImV4cCI6MjA5ODYyNDg4Nn0.XtMZwLAJcMjM_SkZozPJwDit-ATmOWOQomMPvvOVzAE")

BUCKET_NAME = "profile-photos"
PICKUP_BUCKET_NAME = "pickup-photos"

_client: Client | None = None


def get_client() -> Client:
    """Creates a single shared client (reused across the whole app)."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client


def upload_photo(file_bytes: bytes, original_filename: str, role: str, bucket: str = None):
    """Uploads the photo to the given bucket (default 'profile-photos') and
    returns its public URL. Returns None on failure (the photo is optional,
    so the calling code can continue without it)."""
    if not file_bytes:
        return None

    bucket = bucket or BUCKET_NAME
    ext = original_filename.split(".")[-1].lower() if "." in original_filename else "jpg"
    path = f"{role}/{uuid.uuid4().hex}.{ext}"

    try:
        client = get_client()
        client.storage.from_(bucket).upload(
            path, file_bytes, file_options={"content-type": f"image/{ext}"}
        )
        return client.storage.from_(bucket).get_public_url(path)
    except Exception as e:
        print(f"[supabase_client] Photo upload failed: {e}")
        return None