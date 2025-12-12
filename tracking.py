# tracking.py
import requests
import uuid
from datetime import datetime
import streamlit as st

def track_ga4_event(event_name: str, params: dict, client_id: str | None = None):
    cfg = st.secrets["tracking"]
    measurement_id = cfg["GA4_MEASUREMENT_ID"]
    api_secret = cfg["GA4_API_SECRET"]
    if client_id is None:
        client_id = cfg.get("GA4_CLIENT_ID_FALLBACK", str(uuid.uuid4()))

    url = (
        "https://www.google-analytics.com/mp/collect"
        f"?measurement_id={measurement_id}&api_secret={api_secret}"
    )

    payload = {
        "client_id": client_id,
        "events": [
            {
                "name": event_name,
                "params": params,
            }
        ],
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        # In produzione puoi loggare l'errore, qui silenziamo per non rompere l'app
        pass

def track_facebook_event(event_name: str, data: dict):
    cfg = st.secrets["tracking"]
    pixel_id = cfg["FB_PIXEL_ID"]
    access_token = cfg["FB_ACCESS_TOKEN"]

    url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
    payload = {
        "data": [
            {
                "event_name": event_name,
                "event_time": int(datetime.utcnow().timestamp()),
                "event_source_url": cfg.get("FB_EVENT_SOURCE_URL"),
                "action_source": "website",
                "custom_data": data,
            }
        ]
    }
    params = {"access_token": access_token}

    try:
        requests.post(url, params=params, json=payload, timeout=5)
    except Exception:
        pass