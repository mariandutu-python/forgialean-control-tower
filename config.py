import os

# ========================
# DATABASE SQL SERVER
# ========================
DB_CONFIG = {
    "server": "your_server.database.windows.net",  # Azure SQL o locale
    "database": "forgialean_db",
    "username": "user",
    "password": "password",
    "driver": "{ODBC Driver 17 for SQL Server}"
}

# ========================
# STREAMLIT SECRETS (produzione)
# ========================
STREAMLIT_SECRETS = {
    "database_url": os.getenv("DATABASE_URL"),
    "mailchimp_api": os.getenv("MAILCHIMP_API")
}

# ========================
# EMAIL CONFIG (Mailchimp)
# ========================
MAILCHIMP_API = "your_api_key"
MAILCHIMP_LIST_ID = "your_list_id"

# ========================
# CACHING CONFIG (NUOVO!)
# ========================
# TTL = Time To Live (secondi)
# Più basso = dati freschi ma più query al DB
# Più alto = meno query ma dati potenzialmente stali

CACHE_TTL = {
    # Dati volatili - cambiano molto frequentemente (KPI real-time, TimeEntry)
    "volatile": 60,  # 1 minuto
    
    # Dati transazionali - cambiano moderatamente (Fatture, Opportunità, Commesse, Fasi)
    "transactional": 300,  # 5 minuti
    
    # Master data - cambiano raramente (Clienti, Reparti, Persone)
    "static": 3600,  # 1 ora
}

# Disabilitare cache completamente in development (utile per debug)
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"

# ========================
# TRACKING (GA4, Facebook)
# ========================
GA4_MEASUREMENT_ID = "your_ga4_id"
FACEBOOK_PIXEL_ID = "your_facebook_pixel_id"
FACEBOOK_API_TOKEN = "your_facebook_api_token"

# ========================
# APP CONFIG
# ========================
APP_NAME = "ForgiaLean Control Tower"
APP_VERSION = "1.0.0"
LOGO_PATH = "forgialean_logo.png"

# ========================
# DATI AZIENDALI (CEDENTE/PRESTATORE)
# ========================
MY_COMPANY_DATA = {
    "denominazione": "FORGIALEAN DI LICA MARIAN DUTU",
    "piva": "04336611209",
    "codice_fiscale": "DTULMR78B02Z129K",
    "indirizzo": "VIA MEZZO PONENTE 520 INT 02",
    "cap": "40014",
    "comune": "CREVALCORE",
    "provincia": "BO",
    "nazione": "IT",
    # Regime fiscale da confermare con AE/commercialista
    "regime_fiscale": "RF19",
    "id_paese_trasmittente": "IT",
    "id_codice_trasmittente": "DTULMR78B02Z129K",
    "progressivo_invio_prefisso": "FL",
    "formato_trasmissione": "FPR12",
    "pec_mittente": "mariandutu@pec.it",
}

# Ruoli utenti (per access control)
VALID_ROLES = ["admin", "user"]
ADMIN_USERS = {
    "Marian Dutu": "mariand",
    "Demo User": "demo",  # Utente demo per clienti/prove
}

# ========================
# PAGINE VISIBILI PER RUOLO
# ========================
PAGES_BY_ROLE = {
    "admin": [
        "Presentazione",
        "Overview",
        "Clienti",
        "CRM & Vendite",
        "Finanza / Fatture",
        "Incassi / Scadenze",
        "Cashflow proiettato",   # <<< AGGIUNGI QUI
        "Fatture → AE",
        "Fisco & INPS",
        "Operations / Commesse",
        "People & Reparti",
    ],
    "user": [
        "Presentazione",
        "Overview",
        "Clienti",
        "CRM & Vendite",
        "People & Reparti",
    ],
}