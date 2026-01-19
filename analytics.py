import json
import time
import uuid
import requests
import streamlit as st

# Legge i parametri GA4 da secrets.toml → sezione [tracking]
tracking_conf = st.secrets.get("tracking", {})
GA4_MEASUREMENT_ID = tracking_conf.get("GA4_MEASUREMENT_ID", "")
GA4_API_SECRET = tracking_conf.get("GA4_API_SECRET", "")
GA4_CLIENT_ID_FALLBACK = tracking_conf.get("GA4_CLIENT_ID_FALLBACK", "forgialean-server")


def get_ga_client_id() -> str:
    """Client ID randomico per GA4, persistente nella sessione Streamlit."""
    if "ga_client_id" not in st.session_state:
        st.session_state["ga_client_id"] = str(uuid.uuid4())
    return st.session_state["ga_client_id"]


def get_ga_session_id() -> str:
    """Session ID persistente (timestamp in ms)."""
    if "ga_session_id" not in st.session_state:
        st.session_state["ga_session_id"] = str(int(time.time() * 1000))
    return st.session_state["ga_session_id"]


def _build_url(debug: bool = False) -> str:
    """Costruisce l'URL GA4 Measurement Protocol."""
    base = "https://www.google-analytics.com/"
    base += "debug/mp/collect" if debug else "mp/collect"
    return f"{base}?measurement_id={GA4_MEASUREMENT_ID}&api_secret={GA4_API_SECRET}"


def track_event(event_name: str, params: dict | None = None, debug: bool = False):
    """
    Invia un evento custom a GA4 via Measurement Protocol.

    - Usa client_id e session_id persistenti nella sessione Streamlit.
    - Aggiunge page_location e page_title standard per la Control Tower.
    """
    if not GA4_MEASUREMENT_ID or not GA4_API_SECRET:
        print("GA4: measurement_id o api_secret mancanti, evento NON inviato.")
        return

    try:
        client_id = get_ga_client_id()
        session_id = get_ga_session_id()
    except Exception:
        # fallback se non siamo in un contesto Streamlit valido
        client_id = GA4_CLIENT_ID_FALLBACK
        session_id = str(int(time.time() * 1000))

    params = params.copy() if params else {}

    # Aggiungi session_id e user_id ai parametri evento
    params.setdefault("session_id", session_id)
    params.setdefault("user_id", client_id)

    if debug:
        params.setdefault("debug_mode", 1)

    url = _build_url(debug=False)

    payload = {
        "client_id": client_id,
        "user_id": client_id,
        "non_personalized_ads": True,  # non usato per ads personalizzati [web:302][web:305]
        "timestamp_micros": str(int(time.time() * 1_000_000)),
        "events": [
            {
                "name": event_name,
                "params": {
                    **params,
                    "page_location": "https://forgialean.streamlit.app/",
                    "page_title": "ForgiaLean Control Tower",
                    "session_id": session_id,
                },
            }
        ],
    }

    if debug:
        print(f"GA4 Payload: {json.dumps(payload, indent=2)}")

    try:
        resp = requests.post(url, json=payload, timeout=3)
        if debug:
            print(f"GA4 Response status: {resp.status_code}")
    except Exception as e:
        print("GA4 error:", e)


def track_generate_lead_from_crm(
    opportunity,
    lead_type: str = "web_form",
):
    """
    Traccia in GA4 un lead generato dal CRM (opportunità appena creata).

    Usa l'evento raccomandato 'generate_lead' con parametri value e currency,
    più info su tipo lead e UTM. [web:298][web:306]
    """
    utm_source = getattr(opportunity, "utm_source", "") or ""
    utm_medium = getattr(opportunity, "utm_medium", "") or ""
    utm_campaign = getattr(opportunity, "utm_campaign", "") or ""
    utm_content = getattr(opportunity, "utm_content", "") or ""

    value = float(getattr(opportunity, "valore_stimato", 0.0) or 0.0)

    params = {
        # parametri raccomandati per generate_lead
        "lead_type": lead_type,  # es: web_form / linkedin_lead_gen / google_ads_lead_form
        "value": value,
        "currency": "EUR",
        # info CRM
        "opportunity_id": str(getattr(opportunity, "id", "")),
        "client_name": (getattr(opportunity, "nome_opportunita", "") or "")[:80],
        # UTM come parametri evento, per avere coerenza con la campagna
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_content": utm_content,
    }

    track_event("generate_lead", params=params, debug=False)