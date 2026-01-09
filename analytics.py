import json
import uuid
import requests
import streamlit as st

# Legge i parametri GA4 da secrets.toml → sezione [tracking]
tracking_conf = st.secrets.get("tracking", {})
GA4_MEASUREMENT_ID = tracking_conf.get("GA4_MEASUREMENT_ID", "")
GA4_API_SECRET = tracking_conf.get("GA4_API_SECRET", "")
GA4_CLIENT_ID_FALLBACK = tracking_conf.get("GA4_CLIENT_ID_FALLBACK", "forgialean-server")


def get_ga_client_id() -> str:
    """Client ID anonimo per GA4, persistente nella sessione Streamlit."""
    if "ga_client_id" not in st.session_state:
        st.session_state["ga_client_id"] = str(uuid.uuid4())
    return st.session_state["ga_client_id"]


def track_event(event_name: str, params: dict | None = None):
    """Invia un evento custom a GA4 via Measurement Protocol."""
    if not GA4_MEASUREMENT_ID or not GA4_API_SECRET:
        return  # se non configurato, esce silenziosamente

    try:
        client_id = get_ga_client_id()
    except Exception:
        client_id = GA4_CLIENT_ID_FALLBACK

    url = (
        "https://www.google-analytics.com/mp/collect"
        f"?measurement_id={GA4_MEASUREMENT_ID}&api_secret={GA4_API_SECRET}"
    )

    payload = {
        "client_id": client_id,
        "non_personalized_ads": True,
        "events": [
            {
                "name": event_name,
                "params": params or {},
            }
        ],
    }

    try:
        requests.post(url, json=payload, timeout=1.5)
    except Exception:
        # puoi aggiungere logging se vuoi, ma non blocchiamo la UI
        pass
