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


def _build_url(debug: bool = False) -> str:
    """Costruisce l'URL Measurement Protocol (normale o debug)."""
    base = "https://www.google-analytics.com/"
    base += "debug/mp/collect" if debug else "mp/collect"
    return f"{base}?measurement_id={GA4_MEASUREMENT_ID}&api_secret={GA4_API_SECRET}"


def track_event(event_name: str, params: dict | None = None, debug: bool = False):
    """Invia un evento custom a GA4 via Measurement Protocol.

    - event_name: nome evento GA4 (es. 'page_view_dashboard').
    - params: dizionario di parametri evento.
    - debug: se True usa l'endpoint di debug e stampa la risposta.
    """
    if not GA4_MEASUREMENT_ID or not GA4_API_SECRET:
        print("GA4: measurement_id o api_secret mancanti, evento NON inviato.")
        return

    try:
        client_id = get_ga_client_id()
    except Exception:
        client_id = GA4_CLIENT_ID_FALLBACK

    # Se chiedi debug, forza anche debug_mode param per DebugView
    params = params.copy() if params else {}
    if debug:
        params.setdefault("debug_mode", 1)

    url = _build_url(debug=debug)

    payload = {
        "client_id": client_id,
        "non_personalized_ads": True,
        "events": [
            {
                "name": event_name,
                "params": params,
            }
        ],
    }

    try:
        resp = requests.post(url, json=payload, timeout=3)
        if debug:
            print("GA4 DEBUG status:", resp.status_code, resp.text)
    except Exception as e:
        # Non blocca la UI, ma logga l'errore
        print("GA4 error:", e)