from datetime import date, timedelta, datetime
import time
from pathlib import Path
import io
import urllib.parse 
import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
from sqlmodel import SQLModel, Field, Session, select, delete
from finance_utils import build_full_management_balance
from config import CACHE_TTL, PAGES_BY_ROLE, APP_NAME, LOGO_PATH, MY_COMPANY_DATA
from enum import Enum

from db import (
    init_db,
    get_session,
    Client,
    Opportunity,
    Invoice,
    Payment,
    ProjectCommessa,
    TaskFase,
    TimeEntry,
    Department,
    Employee,
    KpiDepartmentTimeseries,
    KpiEmployeeTimeseries,
    LoginEvent,
    TaxConfig,
    InpsContribution,
    TaxDeadline,
    InvoiceTransmission,
    Vendor,
    ExpenseCategory,
    Account,
    Expense,
    CashflowBudget, 
    CashflowEvent,
)

from cache_functions import (
    get_all_clients,
    get_all_opportunities,
    get_all_invoices,
    get_all_commesse,
    get_all_task_fasi,
    get_all_departments,
    get_all_employees,
    get_all_timeentries,
    get_all_kpi_department_timeseries,
    get_all_kpi_employee_timeseries,
    invalidate_volatile_cache,
    invalidate_transactional_cache,
    invalidate_static_cache,
    invalidate_all_cache,
)

from tracking import track_ga4_event, track_facebook_event
from streamlit_calendar import calendar
import requests
import smtplib
from email.mime.text import MIMEText

# === LETTURA SECRETS ===
TELEGRAM_BOT_TOKEN = st.secrets["tracking"]["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["tracking"]["TELEGRAM_CHAT_ID"]

SMTP_SERVER = st.secrets["email"]["SMTP_SERVER"]
SMTP_PORT = int(st.secrets["email"]["SMTP_PORT"])
SMTP_USER = st.secrets["email"]["SMTP_USER"]
SMTP_PASSWORD = st.secrets["email"]["SMTP_PASSWORD"]
FROM_ADDRESS = st.secrets["email"]["FROM_ADDRESS"]

init_db()

LOGO_PATH = Path("forgialean_logo.png")

def capture_utm_params():
    """Legge i parametri UTM dall'URL e li mette in session_state."""
    params = st.query_params

    st.session_state["utm_source"] = params.get("utm_source", "")
    st.session_state["utm_medium"] = params.get("utm_medium", "")
    st.session_state["utm_campaign"] = params.get("utm_campaign", "")
    st.session_state["utm_content"] = params.get("utm_content", "")


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.get(url, params=params, timeout=10)
    except Exception:
        # opzionale: puoi loggare su file o ignorare in silenzio
        pass

from datetime import date

def get_opps_di_oggi(session):
    """Opportunità con data_prossima_azione oggi."""
    return session.exec(
        select(Opportunity).where(
            Opportunity.data_prossima_azione == date.today()
        )
    ).all()
def send_agenda_oggi_telegram():
    """Manda su Telegram la lista delle azioni di oggi."""
    with get_session() as session:
        opps_oggi = get_opps_di_oggi(session)

    if not opps_oggi:
        return

    lines = []
    for o in opps_oggi:
        riga = f"- {o.nome_opportunita} ({o.data_prossima_azione})"
        if o.tipo_prossima_azione:
            riga += f" – {o.tipo_prossima_azione}"
        if o.note_prossima_azione:
            riga += f" – {o.note_prossima_azione}"
        lines.append(riga)

    testo = "Agenda CRM di oggi:\n" + "\n".join(lines)
    send_telegram_message(testo)

def build_email_body(nome, azienda, email, oee_perc, perdita_euro_turno, fascia):
    if fascia == "critica":
        intro_fascia = (
            "Questo valore ti colloca in una <b>fascia critica</b>: una quota importante della capacità "
            "della linea si sta perdendo ogni giorno tra fermi, velocità sotto target e scarti. "
            "Di fatto stai pagando impianti, persone e straordinari per una capacità che non arriva mai al cliente."
        )
        proposta = (
            "In casi come il tuo l’obiettivo è recuperare una parte significativa di questa perdita, "
            "portando l’OEE verso valori più vicini al 75–80% e liberando ore equivalenti di produzione "
            "senza nuovi investimenti in macchine."
        )
    elif fascia == "intermedia":
        intro_fascia = (
            "Questo valore ti colloca in una <b>fascia intermedia</b>: la linea lavora, ma ci sono ancora "
            "margini importanti dovuti a setup, organizzazione del lavoro, micro‑fermi e variazioni di velocità. "
            "Ogni giorno una parte della capacità che stai pagando non si traduce in pezzi buoni fatturabili."
        )
        proposta = (
            "In situazioni come la tua il potenziale tipico è un +10–15 punti OEE, lavorando in modo mirato "
            "sulle cause principali invece che su interventi generici."
        )
    else:
        intro_fascia = (
            "Questo valore ti colloca in una <b>fascia alta</b>: sei già in un contesto ben strutturato "
            "e sopra la media di molte PMI del settore. Le perdite non sono più ‘disastrose’, ma ogni punto OEE "
            "che riesci a recuperare vale molto in termini di €/anno."
        )
        proposta = (
            "In questi contesti il lavoro non è spegnere incendi, ma fare fine‑tuning: stabilità, setup rapidi, "
            "gestione mix e variabilità, concentrandosi dove ogni ora equivalente recuperata ha il massimo impatto economico."
        )

    # Turni/anno ipotizzati (es. 250 giorni lavorativi)
    turni_anno = 250
    perdita_annua_1t = perdita_euro_turno * turni_anno
    perdita_annua_2t = perdita_euro_turno * 2 * turni_anno
    perdita_annua_3t = perdita_euro_turno * 3 * turni_anno

    # URL della pagina/step successivo
    cta_url = (
        "https://forgialean.streamlit.app/"
        f"?step=call_oee&nome={urllib.parse.quote(nome)}"
        f"&azienda={urllib.parse.quote(azienda)}"
        f"&email={urllib.parse.quote(email)}"
    )

    corpo = f"""
<p>Ciao {nome},</p>

<p>grazie per aver condiviso i dati della tua linea.</p>

<p>In base alle informazioni che hai inserito, la stima è:</p>

<ul>
  <li>OEE stimato: <b>{oee_perc:.1f}%</b></li>
  <li>Capacità persa: circa <b>€ {perdita_euro_turno:,.0f} per turno</b> su una macchina/linea</li>
  <li>Se lavori a 1 turno (8 h): perdita annua ≈ <b>€ {perdita_annua_1t:,.0f}</b></li>
  <li>Se lavori a 2 turni (16 h): perdita annua ≈ <b>€ {perdita_annua_2t:,.0f}</b></li>
  <li>Se lavori a 3 turni (24 h): perdita annua ≈ <b>€ {perdita_annua_3t:,.0f}</b></li>
</ul>

<p>{intro_fascia}</p>

<p>{proposta}</p>

<p>A questo punto hai due opzioni:</p>

<ul>
  <li><b>Lasciare le cose come sono</b>, accettando che questi circa <b>€ {perdita_euro_turno:,.0f} per turno</b>
      restino un costo fisso nascosto.</li>
  <li><b>Lavorarci in modo strutturato</b> per trasformare una parte di quella perdita in capacità e margine.</li>
</ul>

<p>
Se vuoi valutare seriamente come recuperare una parte di questi importi,
clicca sul pulsante qui sotto e compila il form con il tuo <b>numero diretto</b> e la <b>fascia oraria</b> in cui preferisci essere richiamato.
</p>

<p>
  <a href="{cta_url}" style="
      display:inline-block;
      padding:10px 18px;
      background-color:#27AE60;
      color:#ffffff;
      text-decoration:none;
      border-radius:4px;
      font-weight:bold;
  " role="button">
    Completa il passo successivo
  </a>
</p>

<p>
Se in questo momento decidi di non intervenire, puoi utilizzare il mini‑report come base di confronto interna
e condividerlo con chi presidia budget e investimenti, per rendere chiaro l’impatto economico delle perdite di OEE.
</p>

<p>Un saluto,<br>
Marian Dutu – Operations &amp; OEE Improvement<br>
ForgiaLean <br>
P.IVA: 04336611209 <br>
<a href="mailto:info@forgialean.it">info@forgialean.it</a>
</p>
"""
    return corpo

def calcola_oee_e_perdita(ore_turno, ore_fermi, scarti, velocita, valore_orario):
    """
    Calcola:
    - OEE in percentuale
    - Perdita economica per turno in €
    - Fascia OEE: 'critica', 'intermedia', 'alta'
    """
    if ore_turno <= 0:
        return 0.0, 0.0, "critica"

    # Availability, Performance, Quality
    availability = max(0.0, 1.0 - (ore_fermi / ore_turno))
    performance = velocita / 100.0
    quality = max(0.0, 1.0 - scarti / 100.0)

    oee = availability * performance * quality
    oee_target = 0.85
    gap_oee = max(0.0, oee_target - oee)

    capacita_persa_turno = gap_oee * ore_turno
    perdita_euro_turno = capacita_persa_turno * valore_orario

    # Classificazione fascia OEE
    if oee < 0.60:
        fascia = "critica"
    elif oee < 0.80:
        fascia = "intermedia"
    else:
        fascia = "alta"

    return oee * 100.0, perdita_euro_turno, fascia

def invia_minireport_oee(email_destinatario: str, subject: str, body: str):
    """
    Invia il mini‑report OEE via email in formato testo/HTML semplice.
    """
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FROM_ADDRESS
    msg["To"] = email_destinatario

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)

# === FUNZIONE SALDO CASSA GESTIONALE ===
from datetime import date
from sqlmodel import select

def calcola_saldo_cassa(data_rif: date, account_id: int | None = None) -> float:
    """
    Saldo cassa complessivo (o per singolo conto) alla data_rif.

    Formula: saldo_iniziale + incassi - uscite_spese - uscite_fisco_inps
    """
    with get_session() as session:
        # 1) Saldo iniziale conti
        q_acc = select(Account)
        if account_id is not None:
            q_acc = q_acc.where(Account.account_id == account_id)
        accounts = session.exec(q_acc).all()
        saldo_iniziale = sum(a.saldo_iniziale or 0.0 for a in (accounts or []))

        # 2) Incassi clienti (Payment) fino a data_rif
        pays = session.exec(
            select(Payment).where(
                Payment.payment_date.is_not(None),
                Payment.payment_date <= data_rif,
            )
        ).all()
        incassi = sum(p.amount or 0.0 for p in (pays or []))

        # 3) Uscite operative (Expense pagate) fino a data_rif
        exps = session.exec(
            select(Expense).where(
                Expense.pagata == True,
                Expense.data_pagamento.is_not(None),
                Expense.data_pagamento <= data_rif,
            )
        ).all()
        uscite_spese = sum(e.importo_totale or 0.0 for e in (exps or []))

        # 4) Uscite fiscali/INPS (TaxDeadline pagate) fino a data_rif
        tax_pays = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                TaxDeadline.payment_date <= data_rif,
            )
        ).all()
        uscite_fisco_inps = sum(t.amount_paid or 0.0 for t in (tax_pays or []))

    saldo = saldo_iniziale + incassi - uscite_spese - uscite_fisco_inps
    return float(saldo)

def build_income_statement(anno_sel: int) -> pd.DataFrame:
    """Conto Economico gestionale semplice per anno: Proventi, Costi, Netto."""
    with get_session() as session:
        # Ricavi: imponibile fatture per anno selezionato (data_fattura)
        invoices = session.exec(
            select(Invoice).where(
                Invoice.data_fattura.is_not(None),
                Invoice.data_fattura >= date(anno_sel, 1, 1),
                Invoice.data_fattura <= date(anno_sel, 12, 31),
            )
        ).all()

        # Costi operativi: imponibile spese nell'anno (data)
        expenses = session.exec(
            select(Expense).where(
                Expense.data.is_not(None),
                Expense.data >= date(anno_sel, 1, 1),
                Expense.data <= date(anno_sel, 12, 31),
            )
        ).all()

        # Contributi INPS pagati nell'anno
        inps = session.exec(
            select(InpsContribution).where(
                InpsContribution.payment_date.is_not(None),
                InpsContribution.payment_date >= date(anno_sel, 1, 1),
                InpsContribution.payment_date <= date(anno_sel, 12, 31),
            )
        ).all()

        # Imposte pagate nell'anno
        taxes = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                TaxDeadline.payment_date >= date(anno_sel, 1, 1),
                TaxDeadline.payment_date <= date(anno_sel, 12, 31),
            )
        ).all()

    # DataFrame e somme
    df_inv = pd.DataFrame([i.__dict__ for i in invoices]) if invoices else pd.DataFrame()
    ricavi = df_inv["importo_imponibile"].sum() if not df_inv.empty else 0.0

    df_exp = pd.DataFrame([e.__dict__ for e in expenses]) if expenses else pd.DataFrame()
    costi_spese = df_exp["importo_imponibile"].sum() if not df_exp.empty else 0.0

    df_inps = pd.DataFrame([c.__dict__ for c in inps]) if inps else pd.DataFrame()
    costi_inps = df_inps["amount_paid"].sum() if not df_inps.empty else 0.0

    df_tax = pd.DataFrame([t.__dict__ for t in taxes]) if taxes else pd.DataFrame()
    costi_tasse = df_tax["amount_paid"].sum() if not df_tax.empty else 0.0

    proventi = ricavi
    costi_totali = costi_spese + costi_inps + costi_tasse
    risultato_netto = proventi - costi_totali

    data = [
        {"Voce": "Proventi", "Importo": proventi},
        {"Voce": "Costi operativi (spese)", "Importo": -costi_spese},
        {"Voce": "Costi INPS", "Importo": -costi_inps},
        {"Voce": "Imposte", "Importo": -costi_tasse},
        {"Voce": "Risultato netto", "Importo": risultato_netto},
    ]
    return pd.DataFrame(data)

def export_all_to_excel(dfs: dict, filename: str):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for sheet_name, df in dfs.items():
            if df is not None and not df.empty:
                safe_name = sheet_name[:31]
                df.to_excel(writer, index=False, sheet_name=safe_name)
    buffer.seek(0)
    st.download_button(
        label="⬇️ Esporta tutto in Excel",
        data=buffer,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.set_page_config(
    page_title=APP_NAME,
    layout="wide",
    initial_sidebar_state="collapsed",
)

def build_income_statement_monthly(anno_sel: int) -> pd.DataFrame:
    """Conto Economico gestionale per mese: Proventi, Costi, Netto."""
    with get_session() as session:
        invoices = session.exec(
            select(Invoice).where(
                Invoice.data_fattura.is_not(None),
                SQLModel.raw_column("strftime('%Y', data_fattura) = :anno")
            ).params(anno=str(anno_sel))
        ).all()
        expenses = session.exec(
            select(Expense).where(
                Expense.data.is_not(None),
                SQLModel.raw_column("strftime('%Y', data) = :anno")
            ).params(anno=str(anno_sel))
        ).all()
        inps = session.exec(
            select(InpsContribution).where(
                InpsContribution.payment_date.is_not(None),
                SQLModel.raw_column("strftime('%Y', payment_date) = :anno")
            ).params(anno=str(anno_sel))
        ).all()
        taxes = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                SQLModel.raw_column("strftime('%Y', payment_date) = :anno")
            ).params(anno=str(anno_sel))
        ).all()

    df_inv = pd.DataFrame([i.__dict__ for i in invoices]) if invoices else pd.DataFrame()
    df_exp = pd.DataFrame([e.__dict__ for e in expenses]) if expenses else pd.DataFrame()
    df_inps = pd.DataFrame([c.__dict__ for c in inps]) if inps else pd.DataFrame()
    df_tax = pd.DataFrame([t.__dict__ for t in taxes]) if taxes else pd.DataFrame()

    # Proventi per mese (competenza: data_fattura)
    if not df_inv.empty:
        df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")
        df_inv["mese"] = df_inv["data_fattura"].dt.month
        ricavi_mese = (
            df_inv.groupby("mese")["importo_imponibile"]
            .sum()
            .rename("Proventi")
            .reset_index()
        )
    else:
        ricavi_mese = pd.DataFrame(columns=["mese", "Proventi"])

    # Costi operativi (spese) per mese
    if not df_exp.empty:
        df_exp["data"] = pd.to_datetime(df_exp["data"], errors="coerce")
        df_exp["mese"] = df_exp["data"].dt.month
        costi_spese_mese = (
            df_exp.groupby("mese")["importo_imponibile"]
            .sum()
            .rename("Costi_spese")
            .reset_index()
        )
    else:
        costi_spese_mese = pd.DataFrame(columns=["mese", "Costi_spese"])

    # INPS per mese (pagamento)
    if not df_inps.empty:
        df_inps["payment_date"] = pd.to_datetime(df_inps["payment_date"], errors="coerce")
        df_inps["mese"] = df_inps["payment_date"].dt.month
        costi_inps_mese = (
            df_inps.groupby("mese")["amount_paid"]
            .sum()
            .rename("Costi_inps")
            .reset_index()
        )
    else:
        costi_inps_mese = pd.DataFrame(columns=["mese", "Costi_inps"])

    # Imposte per mese (pagamento)
    if not df_tax.empty:
        df_tax["payment_date"] = pd.to_datetime(df_tax["payment_date"], errors="coerce")
        df_tax["mese"] = df_tax["payment_date"].dt.month
        costi_tasse_mese = (
            df_tax.groupby("mese")["amount_paid"]
            .sum()
            .rename("Costi_tasse")
            .reset_index()
        )
    else:
        costi_tasse_mese = pd.DataFrame(columns=["mese", "Costi_tasse"])

    mesi_df = pd.DataFrame({"mese": list(range(1, 13))})

    df_ce_mese = (
        mesi_df
        .merge(ricavi_mese, on="mese", how="left")
        .merge(costi_spese_mese, on="mese", how="left")
        .merge(costi_inps_mese, on="mese", how="left")
        .merge(costi_tasse_mese, on="mese", how="left")
        .fillna(0.0)
    )

    df_ce_mese["Costi_totali"] = (
        df_ce_mese["Costi_spese"] + df_ce_mese["Costi_inps"] + df_ce_mese["Costi_tasse"]
    )
    df_ce_mese["Risultato_netto"] = df_ce_mese["Proventi"] - df_ce_mese["Costi_totali"]
    df_ce_mese["Mese"] = df_ce_mese["mese"].apply(lambda m: f"{m:02d}/{anno_sel}")

    return df_ce_mese[
        ["Mese", "Proventi", "Costi_spese", "Costi_inps", "Costi_tasse", "Costi_totali", "Risultato_netto"]
    ]

def build_cashflow_monthly(anno: int) -> pd.DataFrame:
    """
    Cashflow operativo mensile:
    - Incassi clienti (Payment)
    - Uscite spese (Expense pagate)
    - Uscite fisco/INPS (TaxDeadline pagate)
    """
    with get_session() as session:
        # Incassi clienti
        pays = session.exec(
            select(Payment).where(
                Payment.payment_date.is_not(None),
                SQLModel.raw_column("strftime('%Y', payment_date) = :anno"),
            ).params(anno=str(anno))
        ).all()

        # Spese pagate
        exps = session.exec(
            select(Expense).where(
                Expense.pagata == True,
                Expense.data_pagamento.is_not(None),
                SQLModel.raw_column("strftime('%Y', data_pagamento) = :anno"),
            ).params(anno=str(anno))
        ).all()

        # Fisco / INPS pagati
        taxes = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                SQLModel.raw_column("strftime('%Y', payment_date) = :anno"),
            ).params(anno=str(anno))
        ).all()

    # DataFrame incassi
    df_p = pd.DataFrame(
        [
            {"data": p.payment_date, "Incassi_clienti": p.amount or 0.0}
            for p in (pays or [])
        ]
    )
    if not df_p.empty:
        df_p["data"] = pd.to_datetime(df_p["data"], errors="coerce")
        df_p["mese"] = df_p["data"].dt.month
        df_p = (
            df_p.groupby("mese")["Incassi_clienti"]
            .sum()
            .reset_index()
        )
    else:
        df_p = pd.DataFrame(columns=["mese", "Incassi_clienti"])

    # DataFrame uscite spese
    df_e = pd.DataFrame(
        [
            {"data": e.data_pagamento, "Uscite_spese": e.importo_totale or 0.0}
            for e in (exps or [])
        ]
    )
    if not df_e.empty:
        df_e["data"] = pd.to_datetime(df_e["data"], errors="coerce")
        df_e["mese"] = df_e["data"].dt.month
        df_e = (
            df_e.groupby("mese")["Uscite_spese"]
            .sum()
            .reset_index()
        )
    else:
        df_e = pd.DataFrame(columns=["mese", "Uscite_spese"])

    # DataFrame uscite fisco/INPS
    df_t = pd.DataFrame(
        [
            {"data": t.payment_date, "Uscite_fisco_inps": t.amount_paid or 0.0}
            for t in (taxes or [])
        ]
    )
    if not df_t.empty:
        df_t["data"] = pd.to_datetime(df_t["data"], errors="coerce")
        df_t["mese"] = df_t["data"].dt.month
        df_t = (
            df_t.groupby("mese")["Uscite_fisco_inps"]
            .sum()
            .reset_index()
        )
    else:
        df_t = pd.DataFrame(columns=["mese", "Uscite_fisco_inps"])

    # Merge sui 12 mesi
    mesi_df = pd.DataFrame({"mese": list(range(1, 13))})

    df_cf = (
        mesi_df
        .merge(df_p, on="mese", how="left")
        .merge(df_e, on="mese", how="left")
        .merge(df_t, on="mese", how="left")
        .fillna(0.0)
    )

    df_cf["Net_cash_flow"] = (
        df_cf["Incassi_clienti"]
        - df_cf["Uscite_spese"]
        - df_cf["Uscite_fisco_inps"]
    )
    df_cf["Mese"] = df_cf["mese"].apply(lambda m: f"{m:02d}/{anno}")

    return df_cf[
        ["Mese", "Incassi_clienti", "Uscite_spese", "Uscite_fisco_inps", "Net_cash_flow"]
    ]

def build_balance_sheet(data_rif: date, saldo_cassa: float) -> pd.DataFrame:
    """Stato Patrimoniale minimale alla data: Attività, Passività, Patrimonio Netto."""
    data_rif_dt = pd.to_datetime(data_rif)

    with get_session() as session:
        # Fatture emesse fino a data_rif
        invoices = session.exec(
            select(Invoice).where(Invoice.data_fattura <= data_rif)
        ).all()
        # Pagamenti incassi fatture fino a data_rif
        payments = session.exec(
            select(Payment).where(Payment.payment_date <= data_rif)
        ).all()
        # Spese registrate fino a data_rif
        expenses = session.exec(
            select(Expense).where(Expense.data <= data_rif)
        ).all()
        # Spese pagate fino a data_rif
        expenses_paid = session.exec(
            select(Expense).where(
                Expense.data_pagamento.is_not(None),
                Expense.data_pagamento <= data_rif
            )
        ).all()
        # INPS con scadenza fino a data_rif
        inps = session.exec(
            select(InpsContribution).where(InpsContribution.due_date <= data_rif)
        ).all()
        # INPS pagati fino a data_rif
        inps_paid = session.exec(
            select(InpsContribution).where(
                InpsContribution.payment_date.is_not(None),
                InpsContribution.payment_date <= data_rif
            )
        ).all()
        # Fisco con scadenza fino a data_rif
        taxes = session.exec(
            select(TaxDeadline).where(TaxDeadline.due_date <= data_rif)
        ).all()
        # Fisco pagato fino a data_rif
        taxes_paid = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                TaxDeadline.payment_date <= data_rif
            )
        ).all()

        # INPS con scadenza fino a data_rif
        inps = session.exec(
            select(InpsContribution).where(InpsContribution.due_date <= data_rif)
        ).all()
        # INPS pagati fino a data_rif
        inps_paid = session.exec(
            select(InpsContribution).where(
                InpsContribution.payment_date.is_not(None),
                InpsContribution.payment_date <= data_rif
            )
        ).all()

        # Fisco con scadenza fino a data_rif
        taxes = session.exec(
            select(TaxDeadline).where(TaxDeadline.due_date <= data_rif)
        ).all()
        # Fisco pagato fino a data_rif
        taxes_paid = session.exec(
            select(TaxDeadline).where(
                TaxDeadline.payment_date.is_not(None),
                TaxDeadline.payment_date <= data_rif
            )
        ).all()

    # DataFrame
    df_inv = pd.DataFrame([i.__dict__ for i in invoices]) if invoices else pd.DataFrame()
    df_pay = pd.DataFrame([p.__dict__ for p in payments]) if payments else pd.DataFrame()
    df_exp = pd.DataFrame([e.__dict__ for e in expenses]) if expenses else pd.DataFrame()
    df_exp_paid = pd.DataFrame([e.__dict__ for e in expenses_paid]) if expenses_paid else pd.DataFrame()
    df_inps = pd.DataFrame([c.__dict__ for c in inps]) if inps else pd.DataFrame()
    df_inps_paid = pd.DataFrame([c.__dict__ for c in inps_paid]) if inps_paid else pd.DataFrame()
    df_tax = pd.DataFrame([t.__dict__ for t in taxes]) if taxes else pd.DataFrame()
    df_tax_paid = pd.DataFrame([t.__dict__ for t in taxes_paid]) if taxes_paid else pd.DataFrame()

    # Crediti verso clienti = fatture emesse fino a data_rif - incassi fino a data_rif
    crediti_clienti = 0.0
    if not df_inv.empty:
        totale_fatture = df_inv["importo_totale"].sum()
        if not df_pay.empty:
            incassi = df_pay["importo_pagato"].sum()
        else:
            incassi = 0.0
        crediti_clienti = max(totale_fatture - incassi, 0.0)

    # Debiti verso fornitori = spese registrate fino a data_rif - spese pagate fino a data_rif
    debiti_fornitori = 0.0
    if not df_exp.empty:
        totale_spese = df_exp["importo_totale"].sum()
        if not df_exp_paid.empty:
            pagato_spese = df_exp_paid["importo_totale"].sum()
        else:
            pagato_spese = 0.0
        debiti_fornitori = max(totale_spese - pagato_spese, 0.0)

    # Debiti INPS = contributi dovuti fino a data_rif - contributi pagati fino a data_rif
    debiti_inps = 0.0
    if not df_inps.empty:
        inps_dovuto = df_inps["amount_due"].sum()
        if not df_inps_paid.empty:
            inps_pagato = df_inps_paid["amount_paid"].sum()
        else:
            inps_pagato = 0.0
        debiti_inps = max(inps_dovuto - inps_pagato, 0.0)

    # Debiti Fisco = imposte dovute fino a data_rif - imposte pagate fino a data_rif
    debiti_fisco = 0.0
    if not df_tax.empty:
        tasse_dovute = df_tax["estimated_amount"].sum()
        if not df_tax_paid.empty:
            tasse_pagate = df_tax_paid["amount_paid"].sum()
        else:
            tasse_pagate = 0.0
        debiti_fisco = max(tasse_dovute - tasse_pagate, 0.0)

    # Attività totali e Passività totali
    attivita_totali = saldo_cassa + crediti_clienti
    passivita_totali = debiti_fornitori + debiti_inps + debiti_fisco
    patrimonio_netto = attivita_totali - passivita_totali

    data = [
        {"Sezione": "Attività", "Voce": "Cassa", "Importo": saldo_cassa},
        {"Sezione": "Attività", "Voce": "Crediti verso clienti", "Importo": crediti_clienti},
        {"Sezione": "Passività", "Voce": "Debiti verso fornitori", "Importo": debiti_fornitori},
        {"Sezione": "Passività", "Voce": "Debiti INPS", "Importo": debiti_inps},
        {"Sezione": "Passività", "Voce": "Debiti Fisco", "Importo": debiti_fisco},
        {"Sezione": "Patrimonio Netto", "Voce": "Patrimonio netto gestionale", "Importo": patrimonio_netto},
    ]
    return pd.DataFrame(data)


# =========================
# SUPPORTO PER NOTA INTEGRATIVA
# =========================

def get_conto_economico_summary(anno_sel: int) -> dict:
    """
    Riepilogo Conto Economico gestionale per Nota Integrativa.
    Usa build_income_statement(anno_sel).
    """
    df_ce = build_income_statement(anno_sel)
    if df_ce is None or df_ce.empty:
        return {
            "anno_rif": anno_sel,
            "ricavi_totali": 0.0,
            "costi_totali": 0.0,
            "utile_netto": 0.0,
        }

    proventi = df_ce.loc[df_ce["Voce"] == "Proventi", "Importo"].sum()
    # tutti i costi sono negativi, quindi sommo e poi prendo il valore assoluto
    costi_totali = (
        df_ce.loc[
            df_ce["Voce"].isin(
                ["Costi operativi (spese)", "Costi INPS", "Imposte"]
            ),
            "Importo",
        ]
        .sum()
        * -1
    )
    risultato_netto = df_ce.loc[df_ce["Voce"] == "Risultato netto", "Importo"].sum()

    return {
        "anno_rif": anno_sel,
        "ricavi_totali": float(proventi),
        "costi_totali": float(costi_totali),
        "utile_netto": float(risultato_netto),
    }


def get_stato_patrimoniale_minimale(data_rif: date, saldo_cassa: float) -> dict:
    """
    Riepilogo Stato Patrimoniale minimale per Nota Integrativa.
    Usa build_balance_sheet(data_rif, saldo_cassa).
    """
    df_sp = build_balance_sheet(data_rif, saldo_cassa)
    if df_sp is None or df_sp.empty:
        return {
            "data_rif": data_rif.strftime("%d/%m/%Y"),
            "cassa": saldo_cassa,
            "crediti_clienti": 0.0,
            "debiti_fornitori": 0.0,
            "debiti_inps": 0.0,
            "debiti_fisco": 0.0,
            "patrimonio_netto": 0.0,
        }

    def _sum_voce(sezione: str, voce: str) -> float:
        return float(
            df_sp.loc[
                (df_sp["Sezione"] == sezione) & (df_sp["Voce"] == voce),
                "Importo",
            ].sum()
        )

    cassa = _sum_voce("Attività", "Cassa")
    crediti_clienti = _sum_voce("Attività", "Crediti verso clienti")
    debiti_fornitori = _sum_voce("Passività", "Debiti verso fornitori")
    debiti_inps = _sum_voce("Passività", "Debiti INPS")
    debiti_fisco = _sum_voce("Passività", "Debiti Fisco")
    patrimonio_netto = _sum_voce(
        "Patrimonio Netto", "Patrimonio netto gestionale"
    )

    return {
        "data_rif": data_rif.strftime("%d/%m/%Y"),
        "cassa": cassa,
        "crediti_clienti": crediti_clienti,
        "debiti_fornitori": debiti_fornitori,
        "debiti_inps": debiti_inps,
        "debiti_fisco": debiti_fisco,
        "patrimonio_netto": patrimonio_netto,
    }


# =========================
# PAGINA NOTA INTEGRATIVA
# =========================

def page_nota_integrativa():
    st.title("📄 Nota integrativa gestionale – ForgiaLean")

    # Parametri base (puoi anche prenderli da sidebar o config)
    today = date.today()
    anno_sel = today.year

    # saldo cassa gestionale calcolato automaticamente alla data di oggi
    saldo_cassa = calcola_saldo_cassa(today)

    ce = get_conto_economico_summary(anno_sel)
    sp = get_stato_patrimoniale_minimale(today, saldo_cassa)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Conto Economico gestionale")
        st.metric("Anno di riferimento", ce["anno_rif"])
        st.metric(
            "Ricavi totali",
            f"{ce['ricavi_totali']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Costi totali",
            f"{ce['costi_totali']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Utile netto",
            f"{ce['utile_netto']:,.0f} €".replace(",", "."),
        )
    with col2:
        st.subheader("Stato Patrimoniale minimale")
        st.metric("Data di riferimento", sp["data_rif"])
        st.metric("Cassa", f"{sp['cassa']:,.0f} €".replace(",", "."))
        st.metric(
            "Crediti verso clienti",
            f"{sp['crediti_clienti']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Debiti verso fornitori",
            f"{sp['debiti_fornitori']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Debiti INPS",
            f"{sp['debiti_inps']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Debiti fisco",
            f"{sp['debiti_fisco']:,.0f} €".replace(",", "."),
        )
        st.metric(
            "Patrimonio netto gestionale",
            f"{sp['patrimonio_netto']:,.0f} €".replace(",", "."),
        )

    st.markdown("---")
    st.subheader("Testo Nota Integrativa gestionale")

    st.markdown(
        """
**Attività e modello di business**  
ForgiaLean è uno studio di consulenza aziendale specializzato nel miglioramento delle performance operative delle PMI manifatturiere e di servizio. L’attività è svolta da un consulente certificato Lean Six Sigma Black Belt, con esperienza in Operations Management e come IPC Trainer su processi di assemblaggio elettronico e qualità dei prodotti. I servizi offerti comprendono progetti di miglioramento delle performance di reparto (produttività, ritardi, scarti), programmi Lean Six Sigma (DMAIC) su processi produttivi e di servizio, formazione tecnica e manageriale in ambito operations e qualità, oltre allo sviluppo di cruscotti e sistemi di monitoraggio KPI per decisioni basate sui dati. [web:1322][web:1348]

**Criteri di rilevazione e struttura del bilancio gestionale**  
Il presente bilancio gestionale è redatto con finalità interne di pianificazione e controllo di gestione, a supporto delle decisioni operative e strategiche. Lo schema si basa su un Conto Economico gestionale che aggrega i ricavi per linee di servizio (ad esempio progetti di miglioramento performance, formazione, sviluppo dashboard) e i costi per natura (ad esempio consulenze, software, trasferte, marketing, contributi previdenziali e imposte), e su uno Stato Patrimoniale minimale focalizzato su cassa e capitale circolante operativo. A seconda delle esigenze, i ricavi e i costi possono essere analizzati sia secondo il principio di competenza economica (fatture emesse/spese maturate) sia secondo il principio di cassa (incassi e pagamenti effettivi), mantenendo coerenza tra le informazioni utilizzate per analisi e previsioni. [web:1307][web:1350]

**Stato Patrimoniale minimale**  
Lo Stato Patrimoniale gestionale si concentra sugli elementi più rilevanti per la liquidità e il rischio operativo. All’attivo sono esposti la cassa (saldo dei conti correnti e delle disponibilità liquide) e i crediti verso clienti derivanti da fatture emesse e non ancora incassate. Al passivo sono esposti i debiti verso fornitori per spese registrate e non ancora pagate, nonché le passività verso INPS e fisco, calcolate in coerenza con il risultato gestionale dell’esercizio e con le aliquote applicabili al regime fiscale adottato. Questo approccio essenziale consente di monitorare rapidamente la posizione finanziaria netta, il capitale circolante e la capacità dell’attività di consulenza di generare cassa. [web:1307][web:1347]

**Collegamento con il Rendiconto Finanziario / Cashflow**  
A partire dal Conto Economico e dallo Stato Patrimoniale minimale, la dashboard ForgiaLean calcola un rendiconto finanziario gestionale e proiezioni di cashflow. I flussi di cassa sono distinti per categorie operative (incassi da clienti e pagamenti a fornitori e altri costi), fiscali e previdenziali (versamenti di imposte e contributi INPS) e di investimento (acquisti di beni e strumenti per l’attività). Le proiezioni tengono conto dei tempi di incasso e pagamento, così da evidenziare per ciascun periodo il saldo di cassa atteso, il fabbisogno o l’eccedenza di liquidità, e supportare le decisioni su prezzi, carico di lavoro e investimenti. [web:1308][web:1312]

**Utilizzo gestionale delle informazioni**  
Le informazioni aggregate in questa Nota Integrativa gestionale, insieme ai prospetti di Conto Economico, Stato Patrimoniale e Rendiconto Finanziario, sono utilizzate per monitorare l’andamento dell’attività di consulenza, valutare la redditività delle diverse linee di servizio e misurare l’impatto delle iniziative di miglioramento proposte ai clienti. L’approccio Lean Six Sigma, basato su dati e indicatori, guida sia l’analisi interna sia la progettazione delle dashboard e dei KPI offerti ai clienti, con l’obiettivo di garantire risultati misurabili e sostenibili nel tempo. [web:1322][web:1348]
        """
    )

def page_presentation():
    from datetime import date, timedelta
    from sqlmodel import select

    # 1) Leggo lo step dalla URL
    query_params = st.query_params.to_dict()
    step = query_params.get("step", "")

    # 2) Se arrivo dallo step "call_oee" → mostro SOLO il form telefono
    if step == "call_oee":
        st.title("📞 Richiesta call OEE")
        st.info("👋 Grazie per l'interesse! Inserisci i dati per essere ricontattato.")

        with st.form("call_oee_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("👤 Nome completo *")
                telefono = st.text_input("📱 Telefono *")
            with col2:
                email = st.text_input("📧 Email *")
                disponibilita = st.selectbox(
                    "🕒 Quando chiamarmi?",
                    ["Oggi entro le 18", "Domani mattina", "Domani pomeriggio", "Questa settimana"],
                )

            note = st.text_area("💬 Note / richieste")

            submitted_call = st.form_submit_button("🚀 Contattami subito", type="primary")

        if submitted_call:
            if not nome.strip() or not telefono.strip() or not email.strip():
                st.warning("Compila nome, telefono ed email per poter essere ricontattato.")
            else:
                with get_session() as session:
                    # 1) Trova il client per email (se esiste)
                    client = session.exec(
                        select(Client).where(Client.email == email)
                    ).first()

                    # 2) Trova l'ultima Opportunity Lead OEE collegata a quel client
                    opp = None
                    if client:
                        opp = session.exec(
                            select(Opportunity)
                            .where(Opportunity.client_id == client.client_id)
                            .where(Opportunity.nome_opportunita.ilike("%Lead OEE%"))
                            .order_by(Opportunity.data_apertura.desc())
                        ).first()

                    if opp:
                        # Aggiorna a Lead qualificato (SQL)
                        opp.fase_pipeline = "Lead qualificato (SQL)"
                        opp.probabilita = 50.0
                        opp.owner = "Marian Dutu"
                        # se in modello hai data_prossima_azione, puoi usare disponibilita per decidere la data
                        if hasattr(opp, "data_prossima_azione"):
                            opp.data_prossima_azione = date.today()

                        extra = (
                            f"\n\n--- Step call OEE ---\n"
                            f"Nome: {nome}\n"
                            f"Telefono: {telefono}\n"
                            f"Disponibilità: {disponibilita}\n"
                        )
                        if note.strip():
                            extra += f"Note: {note.strip()}\n"

                        if hasattr(opp, "note"):
                            opp.note = (opp.note or "") + extra

                        session.add(opp)
                        session.commit()

                st.session_state.call_data = {
                    "nome": nome,
                    "telefono": telefono,
                    "email": email,
                    "disponibilita": disponibilita,
                    "note": note,
                }

                st.success("✅ Perfetto! Ti contatterò entro 24h secondo la tua disponibilità!")
                st.balloons()
                st.markdown(
                    "### 📋 Prossimi passi:\n"
                    "1. **Ricevi la chiamata**\n"
                    "2. **Demo personalizzata**\n"
                    "3. **Dashboard attiva**"
                )
                st.stop()
        st.stop()
        return

    # HERO: chi sei e che beneficio dai
    st.title("🏭 Turni lunghi, OEE basso e margini sotto pressione?")

    st.markdown("""
**Da qui inizia il tuo check OEE in 3 minuti.**

Se gestisci **impianti o linee automatiche** (elettronica, metalmeccanico, packaging, food, ecc.)
e vedi che produzione e margini non tornano, probabilmente ti ritrovi in almeno uno di questi punti:
- L'OEE reale delle tue linee è tra **60% e 80%**, oppure nessuno sa dirti il valore.
- Fermi, cambi formato/setup, lotti urgenti e scarti stanno mangiando capacità ogni giorno.
- Straordinari continui, ma clienti comunque insoddisfatti e margini sotto pressione.
""")

    # PAIN: rendere esplicito il dolore quotidiano
    st.subheader("Il problema reale: sprechi invisibili e margini erosi")

    st.markdown("""
- Fermi macchina ricorrenti che equivalgono anche a **4 ore/giorno perse**.
- Cambi setup che bloccano le linee e generano ritardi a catena.
- Lotti urgenti che mandano in caos il piano e fanno salire gli scarti (anche **8–10%**).
- Excel, riunioni e report che richiedono tempo ma non dicono chiaramente **dove** intervenire.

Risultato: impianti da **centinaia di migliaia di euro** che lavorano sotto il 70–75% di OEE e margini che si assottigliano.
""")

    # SOLUZIONE: cosa fa ForgiaLean
    st.subheader("La nostra proposta: +16% OEE in 90 giorni")

    st.markdown("""
ForgiaLean unisce **Black Belt Lean Six Sigma**, **Operations Management** e **Dashboard Real‑Time Industry 4.0** per:

- Rendere visibili le perdite principali (fermi, velocità, scarti) per linea e per turno.
- Tradurre l'OEE in **€/giorno di spreco** comprensibili per il management.
- Costruire un piano d'azione mirato per recuperare capacità, ridurre straordinari e migliorare il livello di servizio.

**Caso reale – elettronica (EMS):**
- OEE da **68% → 86%**.
- Fermi **-82%**.
- Circa **28.000 €/anno** di capacità recuperata, scarti dal 9% al 2%.
""")

    # GRAFICI PRIMA / DOPO (esempio fittizio)
    st.subheader("Come cambia la situazione: prima e dopo il progetto")

    col_g1, col_g2 = st.columns(2)

    df_oee = pd.DataFrame(
        {
            "Fase": ["Prima", "Dopo"],
            "OEE": [68, 86],
        }
    )
    df_fermi = pd.DataFrame(
        {
            "Fase": ["Prima", "Dopo"],
            "Fermi orari/turno": [4.0, 0.7],
        }
    )

    with col_g1:
        fig_oee = px.bar(
            df_oee,
            x="Fase",
            y="OEE",
            title="OEE medio linea",
            text="OEE",
            range_y=[0, 100],
            color="Fase",
            color_discrete_map={"Prima": "#E74C3C", "Dopo": "#27AE60"},
        )
        fig_oee.update_traces(texttemplate="%{y}%", textposition="outside")
        fig_oee.update_layout(showlegend=False)
        st.plotly_chart(fig_oee, use_container_width=True)

    with col_g2:
        fig_fermi = px.bar(
            df_fermi,
            x="Fase",
            y="Fermi orari/turno",
            title="Ore di fermo per turno",
            text="Fermi orari/turno",
            color="Fase",
            color_discrete_map={"Prima": "#E74C3C", "Dopo": "#27AE60"},
        )
        fig_fermi.update_traces(texttemplate="%{y:.1f} h", textposition="outside")
        fig_fermi.update_layout(showlegend=False)
        st.plotly_chart(fig_fermi, use_container_width=True)

    # DIFFERENZIAZIONE: perché voi
    st.subheader("Perché scegliere ForgiaLean rispetto ad altre soluzioni")

    st.markdown("""
- **Non è solo software**: integriamo analisi dati, miglioramento continuo e coaching operativo in reparto.
- **Parliamo la lingua degli impianti**: lavoriamo su fermi, setup, scarti e flussi reali, non solo su KPI teorici.
- **Focus su risultati misurabili**: OEE, capacità recuperata e margine in € sono il centro del progetto.
- **Rischio ribaltato**: obiettivo tipico **+16% OEE in 90 giorni**; se il progetto non genera valore, lo mettiamo nero su bianco.
""")

    # OFFERTA: lead magnet
    st.subheader("Mini‑report OEE gratuito in 3 minuti")

    st.markdown("""
Compilando il form qui sotto riceverai via email un **mini‑report OEE** con:
- Una stima del tuo **OEE reale** sulla tua linea o macchina principale.
- Una quantificazione in **€/giorno** della capacità che stai perdendo **per una macchina/linea**.
- Una stima dell'impatto se hai **più macchine/linee simili** (es. 3 linee = circa 3× perdita €/giorno).
- **3 leve di miglioramento immediate** su cui iniziare a lavorare.

Fai il primo passo: Prenotare un **Audit 30 minuti + piano personalizzato**.
""")

    st.subheader("Un vantaggio in più: bandi e incentivi 4.0")

    st.markdown("""
Oltre al recupero di capacità e margini, in molti casi gli investimenti su impianti, digitalizzazione e analisi dati possono rientrare tra quelli **agevolabili** da bandi **Industria 4.0** e iniziative regionali.

Durante il progetto:
- Ti segnalo i principali **bandi e incentivi** potenzialmente rilevanti per il tuo caso (nazionali e/o regionali).
- Ti aiuto a **tradurre il progetto operativo** in termini di obiettivi, deliverable e risultati attesi, così da semplificare il lavoro con il tuo consulente di finanza agevolata o con il commercialista.
- Mettiamo in evidenza i **benefici misurabili** (OEE, capacità recuperata, margini) che possono rafforzare la richiesta di contributo.

In questo modo hai sia un **miglioramento operativo concreto**, sia la possibilità di **ridurre l’esborso netto** se l’azienda decide di attivarsi sui bandi disponibili.
""")

    # TESTIMONIANZE / SOCIAL PROOF
    st.subheader("Cosa dicono le aziende che hanno lavorato con noi")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("""
> *"Prima avevamo tre linee che correvano tutto il giorno ma non sapevamo dove perdevamo tempo.  
> In 3 mesi abbiamo ridotto gli sprechi sugli impianti chiave e oggi l'OEE è finalmente sotto controllo."*

**Direttore di stabilimento – PMI metalmeccanica (Nord Italia)**
""")

    with col_t2:
        st.markdown("""
> *"Il lavoro con ForgiaLean ci ha permesso di tradurre i fermi e gli scarti in **€/giorno**.  
> Questo ha cambiato il modo in cui il management decide le priorità."*

**COO – Azienda elettronica (EMS)**
""")

    st.markdown("""
Risultati ottenibili quando c'è impegno congiunto 
tra direzione, produzione e miglioramento continuo.
""")

    # =====================
    # FORM: RICHIEDI REPORT OEE (visibile a tutti)
    # =====================
    st.markdown("---")
    st.subheader("Richiedi il tuo mini‑report OEE ForgiaLean")

    with st.form("lead_oee_form"):
        nome = st.text_input("Nome e cognome")
        azienda = st.text_input("Azienda")
        email = st.text_input("Email aziendale")
        descrizione = st.text_area("Descrizione impianto / linea principale")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            ore_fermi = st.number_input(
                "Ore di fermo macchina per turno (stima)",
                min_value=0.0,
                step=0.5,
            )
            scarti = st.number_input(
                "Percentuale scarti / rilavorazioni (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
            )
        with col_f2:
            velocita = st.number_input(
                "Velocità reale vs nominale (%)",
                min_value=0.0,
                max_value=200.0,
                step=1.0,
            )
            valore_orario = st.number_input(
                "Valore economico di 1 ora di produzione (€ / ora, stima)",
                min_value=0.0,
                step=10.0,
            )

        submitted = st.form_submit_button("Ottieni il mini‑report OEE")

    if submitted:
        if not (nome and azienda and email):
            st.error("Nome, azienda ed email sono obbligatori.")
        else:
            # 1) Notifica Telegram
            msg = (
                "🟢 Nuova richiesta mini‑report OEE ForgiaLean\n"
                f"Nome: {nome}\n"
                f"Azienda: {azienda}\n"
                f"Email: {email}\n"
                f"Ore fermi/turno: {ore_fermi}\n"
                f"Scarti (%): {scarti}\n"
                f"Velocità reale vs nominale (%): {velocita}\n"
                f"Valore orario (€): {valore_orario}\n"
                f"Descrizione impianto: {descrizione[:200]}..."
            )
            send_telegram_message(msg)

            try:
                with get_session() as session:
                    # 2) Trova o crea Client
                    client = session.exec(
                        select(Client).where(Client.email == email)
                    ).first()

                    if not client:
                        client = Client(
                            ragione_sociale=azienda,
                            email=email,
                            canale_acquisizione="Landing OEE",
                            segmento_cliente="PMI manifatturiera",
                            data_creazione=date.today(),
                            stato_cliente="prospect",
                            paese=None,
                            settore=None,
                            piva=None,
                            cod_fiscale=None,
                        )
                        session.add(client)
                        session.commit()
                        session.refresh(client)

                    # 3) Crea Opportunity come lead pre-qualificato (MQL)
                    new_opp = Opportunity(
                        client_id=client.client_id,
                        nome_opportunita=f"Lead OEE - {nome}",
                        fase_pipeline="Lead pre-qualificato (MQL)",
                        owner="Marian Dutu",
                        valore_stimato=0.0,
                        probabilita=30.0,
                        data_apertura=date.today(),
                        stato_opportunita="aperta",
                        data_chiusura_prevista=None,
                    )
                    session.add(new_opp)
                    session.commit()

                # 4) Calcolo OEE e perdita per il mini‑report
                oee_perc, perdita_euro_turno, fascia = calcola_oee_e_perdita(
                    ore_turno=8.0,
                    ore_fermi=ore_fermi,
                    scarti=scarti,
                    velocita=velocita,
                    valore_orario=valore_orario,
                )

                subject = "Il tuo mini‑report OEE e il prossimo passo"
                body = build_email_body(nome, azienda, email, oee_perc, perdita_euro_turno, fascia)

                # 5) Invio automatico email mini‑report
                invia_minireport_oee(email, subject, body)

                st.success(
                    "**GRAZIE!!!** Richiesta ricevuta. Riceverai entro **2 ore lavorative** una mail da "
                    "**info@forgialean.it** con il tuo mini‑report OEE: stima degli sprechi €/giorno "
                    "per una macchina/linea e 3 leve operative su cui intervenire.\n\n"
                    "_Se non la vedi in posta in arrivo, controlla anche la **cartella spam/indesiderata**._"
                )

                st.markdown("""
Turni lunghi, impianti sotto il loro potenziale e margini che si assottigliano **non sono sostenibili a lungo**.

Quando riceverai la mail da **info@forgialean.it**, se vuoi davvero intervenire su questi problemi,
segui le istruzioni e completa il **passo successivo** lasciando i dati richiesti per essere contattato.
È pensato per chi vuole trasformare il check OEE in un miglioramento concreto, non solo in un numero da guardare.
""")

            except Exception as e:
                st.error("Si è verificato un errore nel salvataggio del lead OEE.")
                st.text(str(e))

    # =====================
    # CALCOLATORE OEE & PERDITA € - SOLO ADMIN (uso interno)
    # =====================
    role = st.session_state.get("role", "user")
    if role != "admin":
        st.markdown("""
Se hai linee o impianti che lavorano sotto l'80% di OEE, **continuare così è la scelta più costosa**.

Compila il form qui sopra per il mini‑report OEE gratuito: sarà la base per valutare
se un progetto ForgiaLean può portarti **+16% OEE e più margine**, senza perdere altro tempo in riunioni sterili.
""")
        return

    st.markdown("---")
    st.subheader("Calcolatore rapido OEE e perdita economica (uso interno)")

    with st.expander("Calcolatore interno ForgiaLean"):
        col1, col2 = st.columns(2)
        with col1:
            ore_turno = st.number_input(
                "Ore teoriche per turno",
                min_value=0.0,
                value=8.0,
                step=0.5,
                key="oee_ore_turno",
            )
            ore_fermi_calc = st.number_input(
                "Ore di fermo per turno",
                min_value=0.0,
                value=1.0,
                step=0.5,
                key="oee_ore_fermi",
            )
        with col2:
            scarti_calc = st.number_input(
                "Scarti / rilavorazioni (%)",
                min_value=0.0,
                max_value=100.0,
                value=2.0,
                step=0.5,
                key="oee_scarti",
            )
            velocita_calc = st.number_input(
                "Velocità reale vs nominale (%)",
                min_value=0.0,
                max_value=200.0,
                value=90.0,
                step=1.0,
                key="oee_velocita",
            )

        valore_orario_calc = st.number_input(
            "Valore economico 1 ora produzione (€ / ora)",
            min_value=0.0,
            value=200.0,
            step=10.0,
            key="oee_valore_orario",
        )

        turni_anno = st.number_input(
            "Turni/anno (stima)",
            min_value=0,
            value=250,
            step=10,
            key="oee_turni_anno",
        )

        if st.button("Calcola OEE e perdita in €", key="oee_calcola"):
            if ore_turno <= 0 or valore_orario_calc <= 0:
                st.warning("Imposta ore teoriche per turno e valore orario maggiori di zero.")
            else:
                availability = max(0.0, 1.0 - (ore_fermi_calc / ore_turno))
                performance = velocita_calc / 100.0
                quality = max(0.0, 1.0 - scarti_calc / 100.0)

                oee = availability * performance * quality
                oee_target = 0.85
                gap_oee = max(0.0, oee_target - oee)

                capacita_persa_turno = gap_oee * ore_turno
                perdita_euro_turno = capacita_persa_turno * valore_orario_calc

                st.write(f"OEE stimato: **{oee*100:.1f}%** (target {oee_target*100:.0f}%)")
                st.write(f"Gap OEE: **{gap_oee*100:.1f} punti**")
                st.write(f"Capacità persa per turno (1 macchina/linea): **{capacita_persa_turno:.2f} ore equivalenti**")
                st.write(f"Perdita economica per turno (1 macchina/linea): **€ {perdita_euro_turno:,.0f}**")

                st.write(
                    "⚠️ Nota: questi calcoli si riferiscono a **una macchina/linea**. "
                    "Se hai N macchine/linee simili, l'impatto potenziale è circa N× queste cifre."
                )
                if turni_anno > 0:
                    perdita_annua = perdita_euro_turno * turni_anno
                    st.write(f"Perdita economica stimata per anno (1 macchina/linea): **€ {perdita_annua:,.0f}**")
                    st.write("Per più macchine/linee simili moltiplica questa stima per il numero di asset.")

# =========================
# PAGINA: OVERVIEW
# =========================

def page_overview():
    st.title(f"🏢 {APP_NAME} Overview")
    
    # ✅ USA LE FUNZIONI CACHED
    clients = get_all_clients()
    opps = get_all_opportunities()
    invoices = get_all_invoices()
    commesse = get_all_commesse()
    
    # Converti in DataFrame
    df_clients = pd.DataFrame(clients) if clients else pd.DataFrame()
    df_opps = pd.DataFrame(opps) if opps else pd.DataFrame()
    df_invoices = pd.DataFrame(invoices) if invoices else pd.DataFrame()
    df_commesse = pd.DataFrame(commesse) if commesse else pd.DataFrame()

    # Mostra metriche
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Clienti", len(clients))
    with col2:
        st.metric("Opportunità", len(opps))
    with col3:
        st.metric("Fatture", len(invoices))
    with col4:
        st.metric("Commesse", len(commesse))

    st.markdown("---")
    st.subheader("📈 KPI reparto (se presenti)")

    # ✅ USA LA FUNZIONE CACHED
    kpi_dept = get_all_kpi_department_timeseries()

    if kpi_dept:
        df = pd.DataFrame(kpi_dept)
        df["data"] = pd.to_datetime(df["data"])
        kpi_sel = st.selectbox("Seleziona KPI", sorted(df["kpi_name"].unique()))
        df_f = df[df["kpi_name"] == kpi_sel].sort_values("data")
        fig = px.line(df_f, x="data", y=["valore", "target"], title=f"KPI reparto: {kpi_sel}")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nessun KPI reparto ancora registrato.")

    # ---- EXPORT COMPLETO ----
    st.markdown("---")
    st.subheader("📥 Export completo")

    export_all_to_excel(
        {
            "Clienti": df_clients,
            "Opportunita": df_opps,
            "Fatture": df_invoices,
            "Commesse": df_commesse,
        },
        "forgialean_control_tower.xlsx",
    )

# =========================
# PAGINA: CLIENTI – CRUD
# =========================


def page_clients():
    st.title("🤝 Anagrafica")
    role = st.session_state.get("role", "user")

    # =========================
    # INSERIMENTO NUOVO CLIENTE (tutti i ruoli)
    # =========================
    st.subheader("➕ Inserisci nuovo cliente")

    with st.form("new_client"):
        col1, col2 = st.columns(2)
        with col1:
            ragione_sociale = st.text_input("Ragione sociale", "")
            piva = st.text_input("Partita IVA", "")
            cod_fiscale = st.text_input("Codice fiscale", "")
            settore = st.text_input("Settore", "")
            paese = st.text_input("Paese", "Italia")
            segmento_cliente = st.text_input("Segmento cliente (es. A/B/C)", "")
        with col2:
            indirizzo = st.text_input("Indirizzo (via e nr.)", "")
            cap = st.text_input("CAP", "")
            comune = st.text_input("Comune", "")
            provincia = st.text_input("Provincia (es. BO)", "")
            canale_acquisizione = st.text_input("Canale acquisizione", "")
            stato_cliente = st.selectbox(
                "Stato cliente",
                ["attivo", "prospect", "perso"],
                index=0,
            )
            data_creazione = st.date_input("Data creazione", value=date.today())
            codice_destinatario = st.text_input("Codice destinatario (7 char)", "")
            pec_fatturazione = st.text_input("PEC fatturazione", "")

        submitted = st.form_submit_button("Salva cliente")

    # ⬇️ TUTTA LA LOGICA DI SALVATAGGIO DOPO IL FORM
    if submitted:
        if not ragione_sociale.strip():
            st.warning("La ragione sociale è obbligatoria.")
        else:
            try:
                with get_session() as session:
                    new_client = Client(
                        ragione_sociale=ragione_sociale.strip(),
                        email=None,
                        piva=piva.strip() or None,
                        cod_fiscale=cod_fiscale.strip() or None,
                        settore=settore.strip() or None,
                        paese=paese.strip() or None,
                        canale_acquisizione=canale_acquisizione.strip() or None,
                        segmento_cliente=segmento_cliente.strip() or None,
                        data_creazione=data_creazione,
                        stato_cliente=stato_cliente,
                        indirizzo=indirizzo.strip() or None,
                        cap=cap.strip() or None,
                        comune=comune.strip() or None,
                        provincia=provincia.strip() or None,
                        codice_destinatario=codice_destinatario.strip() or None,
                        pec_fatturazione=pec_fatturazione.strip() or None,
                    )
                    session.add(new_client)
                    session.commit()
                    session.refresh(new_client)

                st.success(f"Cliente creato con ID {new_client.client_id}")
                st.rerun()
            except Exception as e:
                st.error("Errore nel salvataggio del cliente.")
                st.write(f"DEBUG EXCEPTION: {e}")

    st.markdown("---")
    st.subheader("📋 Elenco clienti")

    with get_session() as session:
        clients = session.exec(select(Client)).all()

    if not clients:
        st.info("Nessun cliente presente. Inseriscine uno con il form sopra.")
        return

    df_clients = pd.DataFrame([c.__dict__ for c in clients])
    st.dataframe(df_clients)

    # =========================
    # SEZIONE EDIT / DELETE (solo admin)
    # =========================
    if role != "admin":
        st.info("Modifica ed eliminazione clienti disponibili solo per ruolo 'admin'.")
        return

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina cliente (solo admin)")

    # Selezione cliente per ID
    client_ids = df_clients["client_id"].tolist()
    client_id_sel = st.selectbox("Seleziona ID cliente", client_ids)

    # Carico il cliente selezionato
    with get_session() as session:
        client_obj = session.get(Client, client_id_sel)

    if not client_obj:
        st.warning("Cliente non trovato.")
        return

    with st.form("edit_client"):
        col1, col2 = st.columns(2)
        with col1:
            ragione_sociale_e = st.text_input("Ragione sociale", client_obj.ragione_sociale or "")
            piva_e = st.text_input("Partita IVA", client_obj.piva or "")
            settore_e = st.text_input("Settore", client_obj.settore or "")
            paese_e = st.text_input("Paese", client_obj.paese or "")
            segmento_cliente_e = st.text_input("Segmento cliente (es. A/B/C)", client_obj.segmento_cliente or "")
        with col2:
            canale_acquisizione_e = st.text_input("Canale acquisizione", client_obj.canale_acquisizione or "")
            stato_cliente_e = st.selectbox(
                "Stato cliente",
                ["attivo", "prospect", "perso"],
                index=["attivo", "prospect", "perso"].index(client_obj.stato_cliente or "attivo"),
            )
            data_creazione_e = st.date_input(
                "Data creazione",
                value=client_obj.data_creazione or date.today(),
            )

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            update_clicked = st.form_submit_button("💾 Aggiorna cliente")
        with col_btn2:
            delete_clicked = st.form_submit_button("🗑 Elimina cliente")

    if update_clicked:
        if not ragione_sociale_e.strip():
            st.warning("La ragione sociale è obbligatoria.")
        else:
            with get_session() as session:
                obj = session.get(Client, client_id_sel)
                if obj:
                    obj.ragione_sociale = ragione_sociale_e.strip()
                    obj.piva = piva_e.strip() or None
                    obj.settore = settore_e.strip() or None
                    obj.paese = paese_e.strip() or None
                    obj.segmento_cliente = segmento_cliente_e.strip() or None
                    obj.canale_acquisizione = canale_acquisizione_e.strip() or None
                    obj.data_creazione = data_creazione_e
                    obj.stato_cliente = stato_cliente_e
                    session.add(obj)
                    session.commit()
            st.success("Cliente aggiornato.")
            st.rerun()

    if delete_clicked:
        with get_session() as session:
            obj = session.get(Client, client_id_sel)
            if obj:
                session.delete(obj)
                session.commit()
        st.success("Cliente eliminato.")
        st.rerun()


def page_crm_sales():
    # Lettura querystring per deep-link da calendario
    params = st.query_params
    opp_id = params.get("opp_id", None)
    if opp_id:
        try:
            opp_id = int(opp_id)
        except ValueError:
            opp_id = None

    # Cattura eventuali parametri UTM dall'URL
    capture_utm_params()

    st.title("🤝 CRM & Vendite (SQLite)")
    role = st.session_state.get("role", "user")

    # =========================
    # FORM INSERIMENTO OPPORTUNITÀ
    # =========================
    st.subheader("➕ Inserisci nuova opportunità")

    # Carico lista clienti per selezione
    with get_session() as session:
        clients = session.exec(select(Client)).all()

    if not clients:
        st.info("Prima crea almeno un cliente nella pagina 'Clienti'.")
    else:
        df_clients = pd.DataFrame([c.__dict__ for c in clients])
        df_clients["label"] = (
            df_clients["client_id"].astype(str)
            + " - "
            + df_clients["ragione_sociale"]
        )

        with st.form("new_opportunity"):
            col1, col2 = st.columns(2)
            with col1:
                client_label = st.selectbox("Cliente", df_clients["label"].tolist())
                nome_opportunita = st.text_input("Nome opportunità", "")
                fase_pipeline = st.selectbox(
                    "Fase pipeline",
                    [
                        "Lead pre-qualificato (MQL)",
                        "Lead qualificato (SQL)",
                        "Lead",
                        "Offerta",
                        "Negoziazione",
                        "Vinta",
                        "Persa",
                    ],
                    index=0,
                )
                owner = st.text_input("Owner (commerciale)", "")
            with col2:
                valore_stimato = st.number_input(
                    "Valore stimato (€)", min_value=0.0, step=100.0
                )
                probabilita = st.slider(
                    "Probabilità (%)", min_value=0, max_value=100, value=50
                )
                data_apertura = st.date_input("Data apertura", value=date.today())
                data_chiusura_prevista = st.date_input(
                    "Data chiusura prevista", value=date.today()
                )

            # --- PROSSIMA AZIONE ---
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                data_prossima_azione = st.date_input(
                    "📅 Data prossima azione",
                    value=date.today(),
                )
            with col_a2:
                tipo_prossima_azione = st.selectbox(
                    "📌 Tipo prossima azione",
                    ["", "Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"],
                )

            note_prossima_azione = st.text_area(
                "📝 Note prossima azione",
                value="",
            )

            stato_opportunita = st.selectbox(
                "Stato opportunità",
                ["aperta", "vinta", "persa"],
                index=0,
            )

            submitted_opp = st.form_submit_button("Salva opportunità")

        if submitted_opp:
            if not nome_opportunita.strip():
                st.warning("Il nome opportunità è obbligatorio.")
            else:
                client_id_sel = int(client_label.split(" - ")[0])

                client_row = df_clients[
                    df_clients["client_id"] == client_id_sel
                ].iloc[0]
                client_name = client_row["ragione_sociale"]

                # UTM da session_state
                utm_source = st.session_state.get("utm_source") or None
                utm_medium = st.session_state.get("utm_medium") or None
                utm_campaign = st.session_state.get("utm_campaign") or None
                utm_content = st.session_state.get("utm_content") or None

                with get_session() as session:
                    new_opp = Opportunity(
                        client_id=client_id_sel,
                        nome_opportunita=nome_opportunita.strip(),
                        fase_pipeline=fase_pipeline,
                        owner=owner.strip() or None,
                        valore_stimato=valore_stimato,
                        probabilita=float(probabilita),
                        data_apertura=data_apertura,
                        data_chiusura_prevista=data_chiusura_prevista,
                        data_prossima_azione=data_prossima_azione,
                        tipo_prossima_azione=tipo_prossima_azione or None,
                        note_prossima_azione=note_prossima_azione or None,
                        stato_opportunita=stato_opportunita,
                        utm_source=utm_source,
                        utm_medium=utm_medium,
                        utm_campaign=utm_campaign,
                        utm_content=utm_content,
                    )
                    session.add(new_opp)
                    session.commit()
                    session.refresh(new_opp)

                track_ga4_event(
                    "lead_generato",
                    {
                        "client_name": client_name,
                        "opportunity_name": new_opp.nome_opportunita,
                        "opportunity_id": str(new_opp.opportunity_id),
                        "pipeline_stage": new_opp.fase_pipeline,
                        "owner": new_opp.owner or "",
                        "opportunity_value": float(new_opp.valore_stimato or 0),
                        "probability": float(new_opp.probabilita or 0),
                        "status": new_opp.stato_opportunita,
                    },
                    client_id=None,
                )

                track_facebook_event(
                    "Lead",
                    {
                        "value": float(new_opp.valore_stimato or 0),
                        "currency": "EUR",
                        "content_name": new_opp.nome_opportunita,
                        "content_category": "CRM-Opportunity",
                        "client_name": client_name,
                        "status": new_opp.stato_opportunita,
                    },
                )

                st.success(f"Opportunità creata con ID {new_opp.opportunity_id}")
                st.rerun()

    st.markdown("---")

    # =========================
    # VISTA / FILTRI OPPORTUNITÀ
    # =========================
    st.subheader("🎯 Funnel Opportunità")

    with get_session() as session:
        opps = session.exec(select(Opportunity)).all()
        clients_all = session.exec(select(Client)).all()

    if not opps:
        st.info("Nessuna opportunità presente.")
        return

    df_opps = pd.DataFrame([o.__dict__ for o in opps])
    df_clients_all = (
        pd.DataFrame([c.__dict__ for c in clients_all]) if clients_all else pd.DataFrame()
    )
    client_map = (
        {c["client_id"]: c["ragione_sociale"] for _, c in df_clients_all.iterrows()}
        if not df_clients_all.empty
        else {}
    )

    df_opps["Cliente"] = df_opps["client_id"].map(client_map).fillna(df_opps["client_id"])

    # Se ho opp_id da querystring, salvo la riga selezionata
    selected_opp = None
    if opp_id is not None and not df_opps.empty:
        df_match = df_opps[df_opps["opportunity_id"] == opp_id]
        if not df_match.empty:
            selected_opp = df_match.iloc[0]

    df_open = df_opps[df_opps["stato_opportunita"] == "aperta"].copy()
    if not df_open.empty:
        df_open["valore_ponderato"] = (
            df_open["valore_stimato"] * df_open["probabilita"] / 100.0
        )

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.metric(
                "Valore pipeline (aperte)",
                f"€ {df_open['valore_stimato'].sum():,.0f}".replace(",", "."),
            )
        with col_k2:
            st.metric(
                "Valore ponderato",
                f"€ {df_open['valore_ponderato'].sum():,.0f}".replace(",", "."),
            )
        with col_k3:
            st.metric(
                "N. opportunità aperte",
                int(df_open.shape[0]),
            )

    col_c, col1, col2 = st.columns(3)

    # Filtro cliente
    with col_c:
        clienti_opt = ["Tutti"] + sorted(
            df_opps["Cliente"].dropna().astype(str).unique().tolist()
        )
        f_cliente = st.selectbox("Filtro cliente", clienti_opt)

    # Filtro fase
    with col1:
        fase_opt = ["Tutte"] + sorted(
            df_opps["fase_pipeline"].dropna().unique().tolist()
        )
        f_fase = st.selectbox("Filtro fase pipeline", fase_opt)

    # Filtro owner
    with col2:
        owner_opt = (
            ["Tutti"]
            + sorted(df_opps["owner"].dropna().unique().tolist())
            if "owner" in df_opps.columns
            else ["Tutti"]
        )
        f_owner = st.selectbox("Filtro owner", owner_opt)

    # Applicazione filtri
    df_f = df_opps.copy()

    if f_cliente != "Tutti":
        df_f = df_f[df_f["Cliente"] == f_cliente]

    if f_fase != "Tutte":
        df_f = df_f[df_f["fase_pipeline"] == f_fase]

    if f_owner != "Tutti":
        df_f = df_f[df_f["owner"] == f_owner]

    st.subheader("📂 Opportunità filtrate")

    if df_f.empty:
        st.info("Nessuna opportunità trovata con i filtri selezionati.")
    else:
        for _, row in df_f.iterrows():
            expanded_default = bool(
                selected_opp is not None and row["opportunity_id"] == opp_id
            )

            header = (
                f"{row['opportunity_id']} – {row['Cliente']} – "
                f"{row['nome_opportunita']} ({row['stato_opportunita']})"
            )

with st.expander(header, expanded=expanded_default):
    st.write(f"Fase pipeline: {row['fase_pipeline']}")
    st.write(f"Owner: {row.get('owner', '')}")
    st.write(f"Valore stimato: {row['valore_stimato']} €")
    st.write(f"Probabilità: {row['probabilita']} %")
    st.write(f"Data apertura: {row['data_apertura']}")
    st.write(f"Data chiusura prevista: {row['data_chiusura_prevista']}")
    st.write(f"Data prossima azione: {row.get('data_prossima_azione', '')}")
    st.write(f"Tipo prossima azione: {row.get('tipo_prossima_azione', '')}")
    st.write(
        f"Note prossima azione: {row.get('note_prossima_azione', '')}"
    )

    # --- INFO UTM CAMPAGNA ---
    st.markdown("**Dati campagna (UTM)**")
    st.write(f"utm_source: {row.get('utm_source', '')}")
    st.write(f"utm_medium: {row.get('utm_medium', '')}")
    st.write(f"utm_campaign: {row.get('utm_campaign', '')}")
    st.write(f"utm_content: {row.get('utm_content', '')}")

    st.markdown("---")
    st.markdown("**Pianifica prossima azione**")
    ...


                col_na1, col_na2 = st.columns(2)
                with col_na1:
                    nuova_data = st.date_input(
                        "Nuova data",
                        value=row.get("data_prossima_azione") or date.today(),
                        key=f"nuova_data_{row['opportunity_id']}",
                    )
                with col_na2:
                    nuovo_tipo = st.selectbox(
                        "Nuovo tipo azione",
                        ["", "Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"],
                        index=(
                            ["", "Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"].index(
                                row.get("tipo_prossima_azione")
                            )
                            if row.get("tipo_prossima_azione")
                            in ["Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"]
                            else 0
                        ),
                        key=f"nuovo_tipo_{row['opportunity_id']}",
                    )

                nuove_note = st.text_area(
                    "Note prossima azione",
                    value=row.get("note_prossima_azione", "") or "",
                    key=f"nuove_note_{row['opportunity_id']}",
                )

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button(
                        "✅ Segna azione come fatta (svuota)",
                        key=f"done_{row['opportunity_id']}",
                    ):
                        with get_session() as session:
                            opp_db = session.get(
                                Opportunity, row["opportunity_id"]
                            )
                            if opp_db:
                                opp_db.data_prossima_azione = None
                                opp_db.tipo_prossima_azione = None
                                opp_db.note_prossima_azione = None
                                session.add(opp_db)
                                session.commit()
                        st.success(
                            "Azione segnata come completata e rimossa dall'agenda."
                        )
                        st.rerun()

                with col_b2:
                    if st.button(
                        "📅 Salva nuova prossima azione",
                        key=f"next_{row['opportunity_id']}",
                    ):
                        with get_session() as session:
                            opp_db = session.get(
                                Opportunity, row["opportunity_id"]
                            )
                            if opp_db:
                                opp_db.data_prossima_azione = nuova_data
                                opp_db.tipo_prossima_azione = nuovo_tipo or None
                                opp_db.note_prossima_azione = nuove_note or None
                                session.add(opp_db)
                                session.commit()
                        st.success("Nuova prossima azione salvata.")
                        st.rerun()

    if {"fase_pipeline", "valore_stimato"}.issubset(df_f.columns) and not df_f.empty:
        st.subheader("📈 Valore opportunità per fase")
        pivot = df_f.groupby("fase_pipeline")["valore_stimato"].sum().reset_index()
        fig_fase = px.bar(
            pivot,
            x="fase_pipeline",
            y="valore_stimato",
            title="Valore totale per fase pipeline",
            text="valore_stimato",
        )
        fig_fase.update_traces(texttemplate="€ %{y:,.0f}", textposition="outside")
        fig_fase.update_layout(yaxis_title="Valore (€)")
        st.plotly_chart(fig_fase, use_container_width=True)

    # =========================
    # AGENDA VENDITORE (tutti i ruoli)
    # =========================
    st.markdown("---")
    st.subheader("📞 Agenda venditore")

    if "data_prossima_azione" in df_opps.columns:
        oggi = date.today()
        df_agenda = df_opps.copy()
        df_agenda = df_agenda.dropna(subset=["data_prossima_azione"])
        df_agenda = df_agenda[df_agenda["data_prossima_azione"] >= oggi]
        df_agenda = df_agenda.sort_values("data_prossima_azione")

        # --- FILTRI AGENDA ---
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            owner_opt = ["Tutti"] + sorted(
                df_agenda["owner"].dropna().astype(str).unique().tolist()
            )
            f_owner_ag = st.selectbox("Filtro owner agenda", owner_opt)

        with col_f2:
            tipo_opt = ["Tutti"] + sorted(
                df_agenda["tipo_prossima_azione"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
            f_tipo_ag = st.selectbox("Filtro tipo azione", tipo_opt)

        df_agenda_f = df_agenda.copy()
        if f_owner_ag != "Tutti":
            df_agenda_f = df_agenda_f[df_agenda_f["owner"] == f_owner_ag]
        if f_tipo_ag != "Tutti":
            df_agenda_f = df_agenda_f[
                df_agenda_f["tipo_prossima_azione"] == f_tipo_ag
            ]

        cols_agenda = [
            "data_prossima_azione",
            "Cliente",
            "nome_opportunita",
            "tipo_prossima_azione",
            "note_prossima_azione",
            "fase_pipeline",
            "probabilita",
            "owner",
        ]
        df_agenda_f = df_agenda_f[cols_agenda]
        st.dataframe(df_agenda_f)

        # 🔔 bottone test notifica Telegram
        if st.button("🔔 Invia agenda di oggi su Telegram"):
            send_agenda_oggi_telegram()
            st.success("Agenda di oggi inviata su Telegram (se ci sono azioni).")

        # 📅 CALENDARIO PROSSIME AZIONI
        st.subheader("📅 Calendario prossime azioni")

        base_url = "https://forgialean.streamlit.app"

        events = []
        for _, row in df_agenda_f.iterrows():
            if pd.notnull(row["data_prossima_azione"]):
                opp_id_event = row["opportunity_id"]
                event_url = f"{base_url}?page=crm&opp_id={opp_id_event}"

                events.append(
                    {
                        "title": f"{row['Cliente']} – {row['nome_opportunita']} "
                                 f"({row.get('tipo_prossima_azione', '')})",
                        "start": row["data_prossima_azione"].strftime("%Y-%m-%d"),
                        "url": event_url,
                    }
                )

        options = {
            "initialView": "dayGridMonth",
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,listWeek",
            },
        }

        calendar(events=events, options=options, key="crm_calendar")

    else:
        st.info(
            "Per usare l’agenda venditore aggiungi i campi 'data_prossima_azione', "
            "'tipo_prossima_azione' e 'note_prossima_azione' al modello Opportunity."
        )

    # =========================
    # SEZIONE EDIT / DELETE (SOLO ADMIN)
    # =========================
    if role != "admin":
        return

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina opportunità (solo admin)")

    if not opps:
        st.info("Nessuna opportunità da modificare/eliminare.")
        return

    df_opp_all = pd.DataFrame([o.__dict__ for o in opps])
    opp_ids = df_opp_all["opportunity_id"].tolist()
    opp_id_sel = st.selectbox("ID opportunità", opp_ids, key="crm_opp_sel")

    with get_session() as session:
        opp_obj = session.get(Opportunity, opp_id_sel)

    if not opp_obj:
        st.warning("Opportunità non trovata.")
        return

    if not df_clients_all.empty:
        df_clients_all["label"] = (
            df_clients_all["client_id"].astype(str)
            + " - "
            + df_clients_all["ragione_sociale"]
        )
        try:
            current_client_label = df_clients_all[
                df_clients_all["client_id"] == opp_obj.client_id
            ]["label"].iloc[0]
        except IndexError:
            current_client_label = df_clients_all["label"].iloc[0]
    else:
        current_client_label = ""

    with st.form(f"edit_opp_{opp_id_sel}"):
        col1, col2 = st.columns(2)
        with col1:
            client_label_e = (
                st.selectbox(
                    "Cliente",
                    df_clients_all["label"].tolist()
                    if not df_clients_all.empty
                    else [],
                    index=df_clients_all["label"].tolist().index(
                        current_client_label
                    )
                    if current_client_label
                    else 0,
                )
                if not df_clients_all.empty
                else ("",)
            )
            nome_opportunita_e = st.text_input(
                "Nome opportunità", opp_obj.nome_opportunita or ""
            )
            fase_pipeline_e = st.selectbox(
                "Fase pipeline",
                [
                    "Lead pre-qualificato (MQL)",
                    "Lead qualificato (SQL)",
                    "Lead",
                    "Offerta",
                    "Negoziazione",
                    "Vinta",
                    "Persa",
                ],
                index=[
                    "Lead pre-qualificato (MQL)",
                    "Lead qualificato (SQL)",
                    "Lead",
                    "Offerta",
                    "Negoziazione",
                    "Vinta",
                    "Persa",
                ].index(opp_obj.fase_pipeline or "Lead"),
            )
            owner_e = st.text_input("Owner", opp_obj.owner or "")
        with col2:
            valore_stimato_e = st.number_input(
                "Valore stimato (€)",
                min_value=0.0,
                step=100.0,
                value=float(opp_obj.valore_stimato or 0.0),
            )
            probabilita_e = st.number_input(
                "Probabilità (%)",
                min_value=0.0,
                max_value=100.0,
                step=5.0,
                value=float(opp_obj.probabilita or 0.0),
            )
            data_apertura_e = st.date_input(
                "Data apertura",
                value=opp_obj.data_apertura or date.today(),
            )
            data_chiusura_prevista_e = st.date_input(
                "Data chiusura prevista",
                value=opp_obj.data_chiusura_prevista or date.today(),
            )

        # --- PROSSIMA AZIONE (EDIT) ---
        col_a1_e, col_a2_e = st.columns(2)
        with col_a1_e:
            data_prossima_azione_e = st.date_input(
                "📅 Data prossima azione",
                value=opp_obj.data_prossima_azione or date.today(),
            )
        with col_a2_e:
            tipo_prossima_azione_e = st.selectbox(
                "📌 Tipo prossima azione",
                ["", "Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"],
                index=(
                    ["", "Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"].index(
                        opp_obj.tipo_prossima_azione
                    )
                    if opp_obj.tipo_prossima_azione
                    in ["Telefonata", "Email", "Visita", "Preventivo", "Follow‑up"]
                    else 0
                ),
            )

        note_prossima_azione_e = st.text_area(
            "📝 Note prossima azione",
            value=opp_obj.note_prossima_azione or "",
        )

        colb1, colb2 = st.columns(2)
        with colb1:
            update_opp = st.form_submit_button("💾 Aggiorna opportunità")
        with colb2:
            delete_opp = st.form_submit_button("🗑 Elimina opportunità")

    if update_opp:
        with get_session() as session:
            obj = session.get(Opportunity, opp_id_sel)
            if obj:
                if not df_clients_all.empty:
                    client_id_e = int(client_label_e.split(" - ")[0])
                    obj.client_id = client_id_e
                obj.nome_opportunita = nome_opportunita_e.strip()
                obj.fase_pipeline = fase_pipeline_e
                obj.owner = owner_e.strip() or None
                obj.valore_stimato = valore_stimato_e
                obj.probabilita = probabilita_e
                obj.data_apertura = data_apertura_e
                obj.data_chiusura_prevista = data_chiusura_prevista_e
                obj.data_prossima_azione = data_prossima_azione_e
                obj.tipo_prossima_azione = tipo_prossima_azione_e or None
                obj.note_prossima_azione = note_prossima_azione_e or None
                session.add(obj)
                session.commit()
        st.success("Opportunità aggiornata.")
        st.rerun()

    if delete_opp:
        with get_session() as session:
            obj = session.get(Opportunity, opp_id_sel)
            if obj:
                session.delete(obj)
                session.commit()
        st.success("Opportunità eliminata.")
        st.rerun()

    # === QUI SOTTO AGGIUNGIAMO LA PARTE COMMESSE DA OPPORTUNITÀ VINTA ===

    st.markdown("---")
    st.subheader("📦 Crea commessa da opportunità vinta")

    with get_session() as session:
        # Opportunità vinte
        opp_vinte = session.exec(
            select(Opportunity).where(Opportunity.fase_pipeline == "Vinta")
        ).all()
        commesse = session.exec(select(ProjectCommessa)).all()

    # Mappa delle commesse già legate a un'opportunity (se hai il campo opportunity_id)
    commesse_by_opp = set()
    if commesse and hasattr(ProjectCommessa, "opportunity_id"):
        for c in commesse:
            if getattr(c, "opportunity_id", None) is not None:
                commesse_by_opp.add(c.opportunity_id)

    # Filtra solo le opportunity vinte che NON hanno ancora una commessa collegata
    opp_vinte_creabili = [
        o
        for o in opp_vinte
        if (
            not hasattr(ProjectCommessa, "opportunity_id")
            or o.opportunity_id not in commesse_by_opp
        )
    ]

    if not opp_vinte_creabili:
        st.info(
            "Nessuna opportunità 'Vinta' disponibile per creare una nuova commessa."
        )
        return

    # Selectbox per scegliere l'opportunity vinta
    opp_options = [
        f"{o.opportunity_id} - {o.nome_opportunita}" for o in opp_vinte_creabili
    ]
    sel_opp_label = st.selectbox(
        "Seleziona un'opportunità vinta per creare la commessa",
        opp_options,
        key="opp_vinta_sel",
    )
    sel_opp_id = int(sel_opp_label.split(" - ")[0])

    with get_session() as session:
        opp_sel = session.get(Opportunity, sel_opp_id)
        client_sel = session.get(Client, opp_sel.client_id) if opp_sel else None

    default_cod = f"COM-{sel_opp_id}"
    default_desc = opp_sel.nome_opportunita if opp_sel else ""

    with st.form("create_commessa_from_opp"):
        colc1, colc2 = st.columns(2)
        with colc1:
            cod_commessa = st.text_input("Codice commessa", default_cod)
            descr_commessa = st.text_input(
                "Descrizione commessa", default_desc
            )
        with colc2:
            data_ini_prev = st.date_input(
                "Data inizio prevista", value=date.today()
            )
            data_fine_prev = st.date_input(
                "Data fine prevista", value=date.today()
            )
        crea_commessa = st.form_submit_button("Crea commessa")

    if crea_commessa and opp_sel and client_sel:
        with get_session() as session:
            # ricarico opportunità e cliente
            opp_db = session.get(Opportunity, opp_sel.opportunity_id)
            client_db = session.get(Client, client_sel.client_id)

            new_comm = ProjectCommessa(
                client_id=client_db.client_id,
                cod_commessa=cod_commessa.strip() or default_cod,
                descrizione=descr_commessa.strip() or default_desc,
                data_inizio_prevista=data_ini_prev,
                data_fine_prevista=data_fine_prev,
            )

            if hasattr(ProjectCommessa, "opportunity_id"):
                new_comm.opportunity_id = opp_db.opportunity_id

            session.add(new_comm)
            session.commit()
            session.refresh(new_comm)

        opp_id = opp_db.opportunity_id
        comm_id = new_comm.commessa_id
        st.success(
            f"Commessa creata da opportunità {opp_id} con ID {comm_id}."
        )
        st.rerun()

class StepOutcome(str, Enum):
    OK = "ok"
    APPROFONDISCI = "approfondisci"
    RINVIA = "rinvia"

def page_lead_capture():
    """
    Pagina pubblica/semipubblica per catturare lead da campagne online.
    Crea Client (se mancante) + Opportunity collegata con UTM.
    """

    # Cattura UTM dall'URL e li mette in session_state
    capture_utm_params()

    st.title("📥 Richiedi una call con ForgiaLean")

    # Leggi eventuali UTM già in session_state
    utm_source = st.session_state.get("utm_source")
    utm_medium = st.session_state.get("utm_medium")
    utm_campaign = st.session_state.get("utm_campaign")
    utm_content = st.session_state.get("utm_content")

    st.caption(
        "Compila il form e ti ricontattiamo per una call di analisi su produzione, OEE e margini."
    )

    with st.form("lead_capture_form"):
        col1, col2 = st.columns(2)
        with col1:
            azienda = st.text_input("Azienda *")
            nome = st.text_input("Nome e cognome *")
            email = st.text_input("Email *")
        with col2:
            telefono = st.text_input("Telefono (facoltativo)")
            ruolo = st.text_input("Ruolo (facoltativo)")

        note = st.text_area(
            "Contesto / cosa vorresti migliorare?",
            height=120,
        )

        accetta_privacy = st.checkbox(
            "Ho letto e accetto l'informativa privacy", value=False
        )

        submitted = st.form_submit_button("📨 Invia richiesta")

    if submitted:
        # Validazioni base
        if not azienda.strip() or not nome.strip() or not email.strip():
            st.warning("Compila almeno Azienda, Nome e Email.")
            return
        if not accetta_privacy:
            st.warning("Devi accettare l'informativa privacy per procedere.")
            return

        # 1) Crea / trova Client
        with get_session() as session:
            # Cerca client per ragione_sociale (case-insensitive molto semplice)
            existing_client = session.exec(
                select(Client).where(Client.ragione_sociale == azienda.strip())
            ).first()

            if existing_client:
                client = existing_client
            else:
                client = Client(
                    ragione_sociale=azienda.strip(),
                    referente=nome.strip(),
                    email=email.strip(),
                    telefono=telefono.strip() or None,
                    note=note or None,
                )
                session.add(client)
                session.commit()
                session.refresh(client)

            # 2) Crea Opportunity collegata
            nuova_opp = Opportunity(
                client_id=client.client_id,
                nome_opportunita=f"Lead da campagna - {azienda.strip()}",
                fase_pipeline="Lead pre-qualificato (MQL)",
                owner=None,  # opzionale: puoi sostituire con owner di default
                valore_stimato=0.0,  # opzionale: stimare o lasciare 0
                probabilita=10.0,
                data_apertura=date.today(),
                data_chiusura_prevista=date.today(),
                data_prossima_azione=date.today(),
                tipo_prossima_azione="Telefonata",
                note_prossima_azione=(
                    f"Lead da form: {note}\n"
                    f"Nome: {nome}, Email: {email}, Tel: {telefono}, Ruolo: {ruolo}"
                ),
                stato_opportunita="aperta",
                utm_source=utm_source,
                utm_medium=utm_medium,
                utm_campaign=utm_campaign,
                utm_content=utm_content,
            )
            session.add(nuova_opp)
            session.commit()
            session.refresh(nuova_opp)

        # 3) Notifica Telegram al commerciale
        try:
            testo_msg = (
                f"📥 Nuovo LEAD da form\n"
                f"Azienda: {azienda}\n"
                f"Nome: {nome}\n"
                f"Email: {email}\n"
                f"Telefono: {telefono}\n"
                f"Ruolo: {ruolo}\n\n"
                f"Campagna: {utm_campaign} | Sorgente: {utm_source}/{utm_medium}\n"
                f"Opportunity ID: {nuova_opp.opportunity_id}"
            )
            send_telegram_message(testo_msg)  # usa il tuo wrapper esistente
        except Exception as e:
            st.warning(f"Lead creato, ma Telegram ha dato errore: {e}")

        st.success(
            f"Richiesta ricevuta. Ti contattiamo a breve. (ID opportunità: {nuova_opp.opportunity_id})"
        )

        # 4) Deep-link al CRM
        base_url = "https://forgialean.streamlit.app"
        crm_url = f"{base_url}?page=crm&opp_id={nuova_opp.opportunity_id}"
        st.markdown(
            f"[Apri subito la scheda nel CRM]({crm_url})"
        )

# --------------------------------------------------------------------
# PAGINA: TRENO VENDITE GUIDATO (7 VAGONI) + UPDATE CRM
# --------------------------------------------------------------------
def page_sales_train():
    st.title("Treno vendite – Call guidata")
    st.write(
        "Usa i 7 vagoni per seguire la call in modo guidato, "
        "restando entro 30–40 minuti complessivi."
    )

    # ------------------------------
    # 1) Selezione Opportunity CRM
    # ------------------------------
    with get_session() as session:
        opps = session.exec(select(Opportunity)).all()
        clients = session.exec(select(Client)).all()

    if not opps:
        st.info("Nessuna opportunità presente. Crea prima almeno una opportunità nel CRM.")
        return

    df_opps = pd.DataFrame([o.__dict__ for o in opps])
    df_clients = pd.DataFrame([c.__dict__ for c in clients]) if clients else pd.DataFrame()
    client_map = {c["client_id"]: c["ragione_sociale"] for _, c in df_clients.iterrows()} if not df_clients.empty else {}

    df_opps["Cliente"] = df_opps["client_id"].map(client_map).fillna(df_opps["client_id"])

    opp_labels = [
        f"{row['opportunity_id']} - {row['Cliente']} - {row['nome_opportunita']}"
        for _, row in df_opps.iterrows()
    ]
    sel_opp_label = st.selectbox(
        "Aggancia questa call a un'opportunity CRM",
        opp_labels,
        key="train_opp_sel_guidata",
    )
    sel_opp_id = int(sel_opp_label.split(" - ")[0])

    # ------------------------------
    # 2) Session state per gli step
    # ------------------------------
    for key in ["v1_step", "v2_step", "v3_step", "v4_step", "v5_step", "v6_step", "v7_step"]:
        if key not in st.session_state:
            st.session_state[key] = 1

    # Appunti globali per ogni vagone (per costruire il testo da salvare)
    note_keys = [
        "v1_note_1", "v1_note_2", "v1_note_3", "v1_note_4",
        "v2_note_1", "v2_note_2", "v2_note_3",
        "v3_note_1", "v3_note_2", "v3_note_3",
        "v4_note_1", "v4_note_2", "v4_note_3",
        "v5_note_1", "v5_note_2", "v5_note_3",
        "v6_note_1", "v6_note_2", "v6_note_3",
        "v7_note_1", "v7_note_2",
    ]
    for nk in note_keys:
        if nk not in st.session_state:
            st.session_state[nk] = ""

    # ------------------------------
    # Sidebar – info chiamata
    # ------------------------------
    with st.sidebar:
        st.markdown("### Dati chiamata")
        cliente = st.text_input("Cliente / Azienda", key="train_cliente")
        referente = st.text_input("Referente", key="train_referente")
        data_call = st.date_input("Data call", value=datetime.today())
        durata_prevista = st.selectbox(
            "Durata prevista",
            ["30 minuti", "40 minuti", "Altro"],
            index=0,
        )
        st.write("Suggerito: usa i vagoni in ordine da 1 a 7.")
        st.caption(f"Opportunity ID collegata: {sel_opp_id}")

    # ==================================================================
    # VAGONE 1 – PRIMO CONTATTO
    # ==================================================================
    with st.expander("Vagone 1 – Primo contatto", expanded=True):
        step = st.session_state.v1_step

        if step == 1:
            st.markdown("### Step 1 – Apertura")
            st.write("Obiettivo: rompere il ghiaccio e dare contesto (3–4 minuti).")
            st.markdown(
                "- Presentati per nome e ruolo.\n"
                "- Ricorda come vi siete conosciuti / chi vi ha messi in contatto.\n"
                "- Chiedi: **\"Hai circa 20–30 minuti per parlare ora?\"**"
            )

            col_a1, col_a2, col_a3 = st.columns(3)
            with col_a1:
                if st.button("Ha tempo (sì)", key="v1_s1_yes"):
                    st.success("Perfetto: puoi passare al motivo della call.")
                    st.session_state.v1_step = 2
            with col_a2:
                if st.button("Ha poco tempo", key="v1_s1_short"):
                    st.info(
                        "Concorda subito un momento preciso per una call completa "
                        "(data, ora, durata) e valuta se fare una mini scoperta ora."
                    )
            with col_a3:
                if st.button("Non è il momento", key="v1_s1_no"):
                    st.warning(
                        "Prima di chiudere la call, concorda un follow-up con data/orario."
                    )

            st.text_area("Appunti apertura", key="v1_note_1")
            if st.checkbox("Step 1 completato", key="v1_done_1"):
                st.session_state.v1_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Motivo della call")
            st.write("Obiettivo: capire perché sta parlando con te (5 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Cosa ti ha spinto a confrontarti su questo tema adesso?\"*\n"
                "- *\"Cosa non ti sta funzionando oggi su produzione / OEE / margini?\"*\n"
                "- *\"Come gestite attualmente questa situazione?\"*"
            )

            st.markdown("**Come percepisci la risposta?**")
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Dolore chiaro e concreto", key="v1_s2_pain"):
                    st.success(
                        "Bene: segnati esempi, numeri e reparti coinvolti. "
                        "Puoi passare all’impatto."
                    )
                    st.session_state.v1_step = 3
            with col_b2:
                if st.button("Vago / superficiale", key="v1_s2_vague"):
                    st.info(
                        "Approfondisci con: *\"Puoi farmi un esempio pratico degli ultimi 30 giorni?\"*"
                    )
            with col_b3:
                if st.button("Nessun vero problema", key="v1_s2_none"):
                    st.warning(
                        "Probabile curiosità: valuta se vale la pena proseguire "
                        "o chiudere con eleganza proponendo solo contenuti."
                    )

            st.text_area("Appunti motivo / contesto", key="v1_note_2")
            if st.checkbox("Step 2 completato", key="v1_done_2"):
                st.session_state.v1_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Impatto e priorità")
            st.write("Obiettivo: misurare impatto su numeri e priorità (8–10 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Che impatto ha questo problema su tempi, OEE o margini?\"*\n"
                "- *\"Se non fate nulla per 6–12 mesi, cosa succede?\"*\n"
                "- *\"Rispetto ad altri progetti in corso, dove lo metteresti come priorità?\"*"
            )

            st.markdown("**Come reagisce?**")
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                if st.button("Impatto alto e urgente", key="v1_s3_high"):
                    st.success(
                        "È un problema strategico: preparati a proporre un prossimo passo concreto."
                    )
                    st.session_state.v1_step = 4
            with col_c2:
                if st.button("Impatto medio", key="v1_s3_mid"):
                    st.info(
                        "Aiutalo a capire il costo di non fare nulla con esempi o benchmark."
                    )
            with col_c3:
                if st.button("Impatto basso", key="v1_s3_low"):
                    st.warning(
                        "Potrebbe non essere prioritario: valuta un follow-up leggero "
                        "(contenuti, newsletter, check periodico)."
                    )

            st.text_area("Appunti impatto / priorità", key="v1_note_3")
            if st.checkbox("Step 3 completato", key="v1_done_3"):
                st.session_state.v1_step = 4

        elif step == 4:
            st.markdown("### Step 4 – Prossimo passo")
            st.write("Obiettivo: chiudere con un next step chiaro (5–7 minuti).")
            st.markdown(
                "Opzioni tipiche di prossimo passo:\n"
                "- Analisi dati OEE / margini su un campione di commesse.\n"
                "- Sopralluogo in stabilimento.\n"
                "- Demo del cruscotto ForgiaLean su dati di test.\n"
                "- Call operativa con produzione + qualità + controllo di gestione."
            )

            st.markdown("**Cosa accetta il cliente?**")
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                if st.button("Accetta un passo concreto", key="v1_s4_yes"):
                    st.success(
                        "Concorda data/ora, definisci chi deve esserci e invia un riepilogo per email."
                    )
            with col_d2:
                if st.button("Deve parlarne internamente", key="v1_s4_internal"):
                    st.info(
                        "Fissa comunque un tentativo di follow-up con data/orario "
                        "prima di chiudere la call."
                    )
            with col_d3:
                if st.button("Non vuole impegnarsi", key="v1_s4_no"):
                    st.warning(
                        "Chiudi con eleganza, lascia la porta aperta e proponi solo contenuti "
                        "o un check tra qualche mese."
                    )

            st.text_area("Appunti next step / decisione", key="v1_note_4")
            if st.checkbox("Vagone 1 completato", key="v1_done_4"):
                st.success("Vagone 1 completato: puoi passare al vagone successivo.")

    # ==================================================================
    # VAGONE 2 – PROCESSO / FLUSSO
    # ==================================================================
    with st.expander("Vagone 2 – Processo / flusso", expanded=False):
        step = st.session_state.v2_step

        if step == 1:
            st.markdown("### Step 1 – Come lavorate oggi?")
            st.write("Obiettivo: capire il flusso produttivo e informativo attuale (5 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Mi racconti in breve il flusso tipico: dall’ordine alla consegna?\"*\n"
                "- *\"Dove vedi oggi più intoppi: pianificazione, produzione, logistica?\"*\n"
                "- *\"Che strumenti usate: ERP, Excel, fogli cartacei?\"*"
            )

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if st.button("Flusso chiaro", key="v2_s1_clear"):
                    st.success("Bene: prendi nota delle fasi chiave e passa ai colli di bottiglia.")
                    st.session_state.v2_step = 2
            with col_a2:
                if st.button("Flusso confuso", key="v2_s1_confused"):
                    st.info(
                        "Ridisegna a voce un flusso semplice e chiedi conferma: "
                        "*\"Quindi, se ho capito bene, l’ordine fa così…\"*"
                    )

            st.text_area("Appunti flusso attuale", key="v2_note_1")
            if st.checkbox("Step 1 completato (V2)", key="v2_done_1"):
                st.session_state.v2_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Colli di bottiglia")
            st.write("Obiettivo: identificare dove si perde tempo o qualità (5–7 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"In quale punto del flusso si accumulano più ritardi?\"*\n"
                "- *\"Ci sono reparti o macchine che aspettano spesso informazioni o materiale?\"*\n"
                "- *\"Dove nascono più rilavorazioni o scarti?\"*"
            )

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Bottleneck chiaro", key="v2_s2_bneck"):
                    st.success("Perfetto: collega questo bottleneck ai numeri (OEE, ritardi, margini).")
                    st.session_state.v2_step = 3
            with col_b2:
                if st.button("Più punti critici", key="v2_s2_multi"):
                    st.info("Chiedi di priorizzare: *\"Se dovessi scegliere uno solo da risolvere ora?\"*")
            with col_b3:
                if st.button("Nessun collo evidente", key="v2_s2_none"):
                    st.warning("Probabile percezione diffusa di caos: indaga su ritardi e straordinari.")

            st.text_area("Appunti colli di bottiglia", key="v2_note_2")
            if st.checkbox("Step 2 completato (V2)", key="v2_done_2"):
                st.session_state.v2_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Flussi informativi")
            st.write("Obiettivo: capire come girano le informazioni (5 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Chi vede cosa, e con che strumenti (monitor, report, Excel)?\"*\n"
                "- *\"Quando un problema succede in linea, chi lo vede e con che ritardo?\"*\n"
                "- *\"Ci sono doppi inserimenti o copia/incolla tra sistemi?\"*"
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Flussi chiari ma manuali", key="v2_s3_manual"):
                    st.success("Ottimo gancio per digitalizzare e centralizzare i dati in un cruscotto.")
            with col_c2:
                if st.button("Flussi confusi / silos", key="v2_s3_silos"):
                    st.info("Evidenzia il rischio di errori, ritardi e mancanza di visione d’insieme.")

            st.text_area("Appunti flussi informativi", key="v2_note_3")
            if st.checkbox("Vagone 2 completato", key="v2_done_3"):
                st.success("Vagone 2 completato: puoi passare al Vagone 3.")

    # ==================================================================
    # VAGONE 3 – DATI E MISURE
    # ==================================================================
    with st.expander("Vagone 3 – Dati e misure", expanded=False):
        step = st.session_state.v3_step

        if step == 1:
            st.markdown("### Step 1 – Cosa misurate oggi")
            st.write("Obiettivo: capire quali KPI esistono e quanto sono affidabili (5 minuti).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Che indicatori usate oggi (OEE, scarti, tempi setup, ritardi consegna)?\"*\n"
                "- *\"Con che frequenza li guardate e chi li vede?\"*\n"
                "- *\"Vi fidate dei numeri o avete dubbi sulla qualità del dato?\"*"
            )

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if st.button("Misure chiare", key="v3_s1_clear"):
                    st.success("Bene: chiedi qualche valore tipico e trend recente.")
                    st.session_state.v3_step = 2
            with col_a2:
                if st.button("Misure scarse/confuse", key="v3_s1_poor"):
                    st.info("Punto di forza per te: senza misure affidabili è difficile migliorare davvero.")

            st.text_area("Appunti KPI attuali", key="v3_note_1")
            if st.checkbox("Step 1 completato (V3)", key="v3_done_1"):
                st.session_state.v3_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Fonti dati")
            st.write("Obiettivo: capire da dove arrivano i dati (ERP, macchine, Excel).")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Da dove arrivano questi numeri: ERP, MES, fogli manuali?\"*\n"
                "- *\"Quanta parte è input manuale operatore?\"*\n"
                "- *\"Quanto tempo passa tra l’evento e la disponibilità del dato?\"*"
            )

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Dati quasi automatici", key="v3_s2_auto"):
                    st.success("Buona base: puoi concentrarti su analisi e azioni, non solo raccolta.")
                    st.session_state.v3_step = 3
            with col_b2:
                if st.button("Dati molto manuali", key="v3_s2_manual"):
                    st.info("Stressa il tema errori, ritardi e tempo perso in data entry.")
            with col_b3:
                if st.button("Dati sparsi in più sistemi", key="v3_s2_scattered"):
                    st.warning("Ottimo gancio per proporre un cruscotto unico e integrato.")

            st.text_area("Appunti fonti dati", key="v3_note_2")
            if st.checkbox("Step 2 completato (V3)", key="v3_done_2"):
                st.session_state.v3_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Uso dei dati")
            st.write("Obiettivo: capire se i dati guidano davvero decisioni e miglioramenti.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Che decisioni prendete oggi grazie a questi dati?\"*\n"
                "- *\"Vi capita di scoprire i problemi solo a fine mese?\"*\n"
                "- *\"Coinvolgete i capi turno / operatori nella lettura dei numeri?\"*"
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Dati usati per decisioni", key="v3_s3_used"):
                    st.success("Puoi proporre di rendere più veloce e visiva l’analisi (cruscotti real-time).")
            with col_c2:
                if st.button("Dati poco usati", key="v3_s3_unused"):
                    st.info("Sottolinea il gap tra sforzo di raccolta e valore ottenuto, proponendo casi pratici.")

            st.text_area("Appunti uso dei dati", key="v3_note_3")
            if st.checkbox("Vagone 3 completato", key="v3_done_3"):
                st.success("Vagone 3 completato: puoi passare al Vagone 4.")

    # ==================================================================
    # VAGONE 4 – IMPATTO ECONOMICO
    # ==================================================================
    with st.expander("Vagone 4 – Impatto economico", expanded=False):
        step = st.session_state.v4_step

        if step == 1:
            st.markdown("### Step 1 – Effetti sul cliente finale")
            st.write("Obiettivo: collegare i problemi interni a clienti e fatturato.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Questi problemi come impattano consegne, qualità percepita, reclami?\"*\n"
                "- *\"Vi capita di consegnare in ritardo o fuori specifica?\"*\n"
                "- *\"Avete perso ordini o clienti per questi motivi?\"*"
            )

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if st.button("Impatto forte sui clienti", key="v4_s1_high"):
                    st.success("Ottimo: stai collegando il tuo lavoro a fatturato e soddisfazione cliente.")
                    st.session_state.v4_step = 2
            with col_a2:
                if st.button("Impatto limitato", key="v4_s1_low"):
                    st.info("Concentrati su costi interni: scarti, straordinari, stock, stress organizzativo.")

            st.text_area("Appunti impatto cliente", key="v4_note_1")
            if st.checkbox("Step 1 completato (V4)", key="v4_done_1"):
                st.session_state.v4_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Costi e sprechi")
            st.write("Obiettivo: far emergere costi nascosti e potenziale di recupero.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Dove vedi più sprechi di tempo o denaro (scarti, rework, attese)?\"*\n"
                "- *\"Quanto incidono straordinari o turni aggiuntivi per inseguire i ritardi?\"*\n"
                "- *\"Avete un’idea di quanto varrebbe risolvere il problema (% o €)?\"*"
            )

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Costi ben noti", key="v4_s2_known"):
                    st.success("Puoi già abbozzare un business case di miglioramento.")
                    st.session_state.v4_step = 3
            with col_b2:
                if st.button("Costi percepiti ma non misurati", key="v4_s2_guess"):
                    st.info("Proponi una fase di quantificazione con dati reali (diagnostica).")
            with col_b3:
                if st.button("Nessuna idea dei costi", key="v4_s2_none"):
                    st.warning("Grande opportunità: far vedere al cliente quanto sta lasciando sul tavolo.")

            st.text_area("Appunti costi / sprechi", key="v4_note_2")
            if st.checkbox("Step 2 completato (V4)", key="v4_done_2"):
                st.session_state.v4_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Potenziale di miglioramento")
            st.write("Obiettivo: far intravedere il valore economico di una soluzione.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Se riduceste scarti / fermi / ritardi del 20–30%, cosa cambierebbe?\"*\n"
                "- *\"Ci sono obiettivi aziendali già fissati (OEE, margine, OTIF)?\"*\n"
                "- *\"C’è già un budget o un piano per migliorare questo ambito?\"*"
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Potenziale chiaro e importante", key="v4_s3_high"):
                    st.success("Collega direttamente questi obiettivi alla tua proposta nella parte soluzione.")
            with col_c2:
                if st.button("Potenziale poco chiaro", key="v4_s3_unclear"):
                    st.info("Suggerisci una fase di analisi numerica per quantificare in modo più preciso.")

            st.text_area("Appunti potenziale economico", key="v4_note_3")
            if st.checkbox("Vagone 4 completato", key="v4_done_3"):
                st.success("Vagone 4 completato: puoi passare al Vagone 5.")

    # ==================================================================
    # VAGONE 5 – PERSONE E RUOLI
    # ==================================================================
    with st.expander("Vagone 5 – Persone e ruoli", expanded=False):
        step = st.session_state.v5_step

        if step == 1:
            st.markdown("### Step 1 – Chi è coinvolto")
            st.write("Obiettivo: mappare la squadra interna coinvolta nel problema e nella soluzione.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Chi vive il problema tutti i giorni (reparti, ruoli)?\"*\n"
                "- *\"Chi dovrà usare la soluzione quotidianamente?\"*\n"
                "- *\"Chi potrebbe ostacolare il cambiamento?\"*"
            )

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if st.button("Mappa chiara", key="v5_s1_clear"):
                    st.success("Perfetto: puoi preparare una proposta che tenga conto di tutti gli attori.")
                    st.session_state.v5_step = 2
            with col_a2:
                if st.button("Mappa confusa", key="v5_s1_confused"):
                    st.info("Proponi una call successiva con produzione + qualità + controllo gestione insieme.")

            st.text_area("Appunti persone coinvolte", key="v5_note_1")
            if st.checkbox("Step 1 completato (V5)", key="v5_done_1"):
                st.session_state.v5_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Processo decisionale")
            st.write("Obiettivo: capire come si prende la decisione di acquisto.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Chi decide alla fine se partire o no con un progetto così?\"*\n"
                "- *\"Quali passi dovete fare internamente per approvare un investimento?\"*\n"
                "- *\"Avete già fatto progetti simili? Come avete deciso allora?\"*"
            )

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Decision maker chiaro", key="v5_s2_dm_clear"):
                    st.success("Ottimo: coinvolgilo presto nelle prossime call.")
                    st.session_state.v5_step = 3
            with col_b2:
                if st.button("Comitato / più persone", key="v5_s2_committee"):
                    st.info("Identifica un champion interno che ti aiuti a far circolare il valore del progetto.")
            with col_b3:
                if st.button("Processo poco chiaro", key="v5_s2_unknown"):
                    st.warning("Rischio di stallo: torna su questo punto prima di formulare un’offerta completa.")

            st.text_area("Appunti processo decisionale", key="v5_note_2")
            if st.checkbox("Step 2 completato (V5)", key="v5_done_2"):
                st.session_state.v5_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Cultura e cambiamento")
            st.write("Obiettivo: capire quanto l’azienda è pronta a cambiare modo di lavorare.")
            st.markdown(
                "Domande chiave:\n"
                "- *\"Avete già fatto progetti di miglioramento (Lean, digitalizzazione, ecc.)?\"*\n"
                "- *\"Come sono andati?\"*\n"
                "- *\"Cosa dovrebbe succedere perché questo progetto venga considerato un successo?\"*"
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Apertura al cambiamento alta", key="v5_s3_open"):
                    st.success("Puoi proporre un percorso più ambizioso (roadmap a step).")
            with col_c2:
                if st.button("Resistenza alta", key="v5_s3_resist"):
                    st.info("Meglio partire da un pilota piccolo, con risultati veloci e visibili.")

            st.text_area("Appunti cultura / cambiamento", key="v5_note_3")
            if st.checkbox("Vagone 5 completato", key="v5_done_3"):
                st.success("Vagone 5 completato: puoi passare al Vagone 6.")

    # ==================================================================
    # VAGONE 6 – SOLUZIONE PROPOSTA
    # ==================================================================
    with st.expander("Vagone 6 – Soluzione proposta", expanded=False):
        step = st.session_state.v6_step

        if step == 1:
            st.markdown("### Step 1 – Collegare problemi e moduli")
            st.write("Obiettivo: collegare quanto emerso con i pezzi della tua soluzione.")
            st.markdown(
                "Checklist:\n"
                "- Richiama in 1 minuto i problemi chiave emersi (OEE, flussi, dati, costi).\n"
                "- Mappa i problemi sui moduli / servizi che puoi offrire.\n"
                "- Verifica che il cliente si ritrovi in questo collegamento."
            )

            col_a1, col_a2 = st.columns(2)
            with col_a1:
                if st.button("Allineamento forte", key="v6_s1_fit"):
                    st.success("Puoi passare a descrivere la soluzione in 2–3 step chiari.")
                    st.session_state.v6_step = 2
            with col_a2:
                if st.button("Allineamento da rivedere", key="v6_s1_weak"):
                    st.info("Chiedi cosa manca o cosa è meno rilevante, e ritarare la proposta.")

            st.text_area("Appunti collegamento problemi-soluzione", key="v6_note_1")
            if st.checkbox("Step 1 completato (V6)", key="v6_done_1"):
                st.session_state.v6_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Descrizione ad alto livello")
            st.write("Obiettivo: spiegare la soluzione senza perdersi nei dettagli tecnici.")
            st.markdown(
                "Checklist:\n"
                "- Descrivi la soluzione in 2–3 blocchi (es. Raccolta dati → Cruscotto → Miglioramento).\n"
                "- Usa il linguaggio del cliente (turni, linee, commesse, ecc.).\n"
                "- Mostra 1–2 esempi concreti di cosa vedrà/otterrà."
            )

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Cliente segue e annuisce", key="v6_s2_yes"):
                    st.success("Perfetto: puoi accennare a tempi, effort e impatto.")
                    st.session_state.v6_step = 3
            with col_b2:
                if st.button("Cliente confuso / scettico", key="v6_s2_no"):
                    st.info("Fermati e chiedi: *\"Cosa non ti torna o non è chiaro?\"*")

            st.text_area("Appunti descrizione soluzione", key="v6_note_2")
            if st.checkbox("Step 2 completato (V6)", key="v6_done_2"):
                st.session_state.v6_step = 3

        elif step == 3:
            st.markdown("### Step 3 – Tempi, rischi, impegno")
            st.write("Obiettivo: dare un’idea realistica di tempi e impegno richiesti.")
            st.markdown(
                "Checklist:\n"
                "- Indica durata tipica del progetto o della fase pilota.\n"
                "- Sii chiaro sulle attività del cliente (chi deve fare cosa, e per quanto tempo).\n"
                "- Evidenzia come riduci i rischi (pilota, step incrementali, supporto)."
            )

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("Cliente vede fattibile", key="v6_s3_ok"):
                    st.success("Puoi portarlo verso il prossimo passo concreto nel Vagone 7.")
            with col_c2:
                if st.button("Cliente preoccupato per effort", key="v6_s3_effort"):
                    st.info("Ridimensiona il primo step (pilota più piccolo, focus su una linea/reparto).")

            st.text_area("Appunti tempi / rischi", key="v6_note_3")
            if st.checkbox("Vagone 6 completato", key="v6_done_3"):
                st.success("Vagone 6 completato: puoi passare al Vagone 7.")

    # ==================================================================
    # VAGONE 7 – CHIUSURA / RECAP
    # ==================================================================
    with st.expander("Vagone 7 – Chiusura / recap", expanded=False):
        step = st.session_state.v7_step

        if step == 1:
            st.markdown("### Step 1 – Riepilogo condiviso")
            st.write("Obiettivo: chiudere con una fotografia condivisa di problemi e soluzione.")
            st.markdown(
                "Checklist:\n"
                "- Riepiloga in 1–2 minuti cosa hai capito: problemi, impatti, priorità.\n"
                "- Chiedi conferma: *\"Mi confermi che è una sintesi corretta?\"*\n"
                "- Se serve, correggi la sintesi insieme a lui."
            )

            if st.button("Riepilogo confermato", key="v7_s1_ok"):
                st.success("Bene: ora definisci insieme il prossimo passo concreto.")
                st.session_state.v7_step = 2

            st.text_area("Appunti riepilogo", key="v7_note_1")
            if st.checkbox("Step 1 completato (V7)", key="v7_done_1"):
                st.session_state.v7_step = 2

        elif step == 2:
            st.markdown("### Step 2 – Next step e commit")
            st.write("Obiettivo: chiudere la call con un impegno chiaro, non solo 'ci sentiamo'.")
            st.markdown(
                "Opzioni tipiche:\n"
                "- Invio proposta con call già fissata per discuterla.\n"
                "- Analisi dati / diagnosi con accesso a storici.\n"
                "- Sopralluogo operativo.\n"
                "- Workshop con team interno."
            )

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if st.button("Accordo su step concreto", key="v7_s2_yes"):
                    st.success("Concorda data/ora e chi partecipa, e prometti un riepilogo scritto.")
            with col_b2:
                if st.button("Deve allinearsi internamente", key="v7_s2_internal"):
                    st.info("Fissa comunque una data indicativa per aggiornarsi.")
            with col_b3:
                if st.button("No decision ora", key="v7_s2_nodec"):
                    st.warning("Chiudi lasciando la porta aperta, con un check leggero a data futura.")

            st.text_area("Appunti prossimo passo", key="v7_note_2")
            if st.checkbox("Vagone 7 completato", key="v7_done_2"):
                st.success("Call completata. Ricorda di aggiornare CRM / dashboard dopo la call.")

    st.markdown("---")

    # =========================================================
    # SALVATAGGIO SU CRM: NOTE + FASE + PROBABILITÀ
    # =========================================================
    st.subheader("Aggiorna CRM da questa call")

    col_save1, col_save2 = st.columns(2)
    with col_save1:
        if st.button("💾 Salva questa call sull'opportunity"):
            testo = f"\n\n=== Call treno vendite del {data_call.strftime('%Y-%m-%d')} ===\n"
            testo += f"Cliente: {cliente} – Referente: {referente}\n"
            testo += "Vagone 1:\n"
            testo += f"- Apertura: {st.session_state['v1_note_1']}\n"
            testo += f"- Motivo: {st.session_state['v1_note_2']}\n"
            testo += f"- Impatto: {st.session_state['v1_note_3']}\n"
            testo += f"- Next step: {st.session_state['v1_note_4']}\n"
            testo += "Vagone 2:\n"
            testo += f"- Flusso: {st.session_state['v2_note_1']}\n"
            testo += f"- Colli di bottiglia: {st.session_state['v2_note_2']}\n"
            testo += f"- Flussi informativi: {st.session_state['v2_note_3']}\n"
            testo += "Vagone 3:\n"
            testo += f"- KPI: {st.session_state['v3_note_1']}\n"
            testo += f"- Fonti dati: {st.session_state['v3_note_2']}\n"
            testo += f"- Uso dei dati: {st.session_state['v3_note_3']}\n"
            testo += "Vagone 4:\n"
            testo += f"- Impatto cliente: {st.session_state['v4_note_1']}\n"
            testo += f"- Costi/sprechi: {st.session_state['v4_note_2']}\n"
            testo += f"- Potenziale: {st.session_state['v4_note_3']}\n"
            testo += "Vagone 5:\n"
            testo += f"- Persone coinvolte: {st.session_state['v5_note_1']}\n"
            testo += f"- Processo decisionale: {st.session_state['v5_note_2']}\n"
            testo += f"- Cultura/cambiamento: {st.session_state['v5_note_3']}\n"
            testo += "Vagone 6:\n"
            testo += f"- Collegamento problemi-soluzione: {st.session_state['v6_note_1']}\n"
            testo += f"- Descrizione soluzione: {st.session_state['v6_note_2']}\n"
            testo += f"- Tempi/rischi: {st.session_state['v6_note_3']}\n"
            testo += "Vagone 7:\n"
            testo += f"- Riepilogo: {st.session_state['v7_note_1']}\n"
            testo += f"- Prossimo passo: {st.session_state['v7_note_2']}\n"

            with get_session() as session:
                opp = session.get(Opportunity, sel_opp_id)
                if not opp:
                    st.error("Opportunity non trovata.")
                else:
                    opp.note = (opp.note or "") + testo

                    fase_attuale = (opp.fase_pipeline or "").strip()
                    v1_ok = st.session_state.get("v1_done_4", False)
                    v4_ok = st.session_state.get("v4_done_3", False)

                    if v1_ok and v4_ok:
                        if fase_attuale in ("Lead", "Lead pre-qualificato (MQL)", ""):
                            opp.fase_pipeline = "Lead qualificato (SQL)"
                        elif fase_attuale in ("Lead qualificato (SQL)", "Analisi"):
                            opp.fase_pipeline = "Proposta / Trattativa"

                    v7_ok = st.session_state.get("v7_done_2", False)
                    prob_attuale = float(opp.probabilita or 0.0)
                    if v7_ok:
                        nuova_prob = max(prob_attuale, 70.0)
                    elif v1_ok and v4_ok:
                        nuova_prob = max(prob_attuale, 50.0)
                    else:
                        nuova_prob = prob_attuale
                    opp.probabilita = nuova_prob

                    session.add(opp)
                    session.commit()
                    st.success("Call salvata sull'opportunity e campi CRM aggiornati.")

    with col_save2:
        st.caption("Dopo il salvataggio trovi subito note e stato aggiornato nella pagina CRM / Opportunità.")

    st.caption("Treno vendite guidato per call di 30–40 minuti, integrato con il CRM.")

def get_next_invoice_number(session, year=None, prefix="FL"):
    year = year or date.today().year
    res = session.exec(
        select(Invoice.num_fattura).where(
            Invoice.data_fattura.between(date(year, 1, 1), date(year, 12, 31))
        )
    ).all()
    nums = []
    for r in res:
        if not r:
            continue
        try:
            base = str(r).split("/")[0]  # "12/2025-FL" -> "12"
            nums.append(int(base))
        except ValueError:
            continue
    next_seq = (max(nums) + 1) if nums else 1
    return f"{next_seq}/{year}-" + prefix


def page_finance_invoices():
    st.title("💵 Finanza / Fatture (SQLite)")
    role = st.session_state.get("role", "user")

    # =========================
    # 1) INSERIMENTO MANUALE FATTURA
    # =========================
    st.subheader("➕ Inserisci nuova fattura (manuale)")

    with get_session() as session:
        clients = session.exec(select(Client)).all()
        suggested_num = get_next_invoice_number(session, year=date.today().year, prefix="FL")

    if not clients:
        st.info("Prima registra almeno un cliente nella sezione Clienti.")
    else:
        df_clients = pd.DataFrame([c.__dict__ for c in clients])
        df_clients["label"] = df_clients["client_id"].astype(str) + " - " + df_clients["ragione_sociale"]

        with st.form("new_invoice_manual"):
            col1, col2 = st.columns(2)
            with col1:
                client_label = st.selectbox("Cliente", df_clients["label"].tolist())
                num_fattura = st.text_input("Numero fattura", suggested_num)
                data_fattura = st.date_input("Data fattura", value=date.today())
                data_scadenza = st.date_input("Data scadenza", value=date.today())
            with col2:
                importo_imponibile = st.number_input("Imponibile (€)", min_value=0.0, step=100.0)
                iva_perc = st.number_input("Aliquota IVA (%)", min_value=0.0, step=1.0, value=22.0)
                stato_pagamento = st.selectbox(
                    "Stato pagamento",
                    ["emessa", "incassata", "scaduta"],
                    index=0,
                )
                data_incasso = st.date_input("Data incasso (se incassata)", value=date.today())

            submitted_manual = st.form_submit_button("Salva fattura manuale")

        if submitted_manual:
            if not num_fattura.strip():
                st.warning("Il numero fattura è obbligatorio.")
            else:
                client_id_sel = int(client_label.split(" - ")[0])
                iva_val = importo_imponibile * iva_perc / 100.0
                totale = importo_imponibile + iva_val

                with get_session() as session:
                    new_inv = Invoice(
                        client_id=client_id_sel,
                        num_fattura=num_fattura.strip(),
                        data_fattura=data_fattura,
                        data_scadenza=data_scadenza,
                        importo_imponibile=importo_imponibile,
                        iva=iva_val,
                        importo_totale=totale,
                        stato_pagamento=stato_pagamento,
                        data_incasso=data_incasso if stato_pagamento == "incassata" else None,
                    )
                    session.add(new_inv)
                    session.commit()
                    session.refresh(new_inv)
                st.success(f"Fattura {new_inv.num_fattura} registrata.")
                st.rerun()

    st.markdown("---")

    # =========================
    # 2) UPLOAD PDF FATTURA + PRECOMPILAZIONE
    # =========================
    st.subheader("📎 Carica fattura PDF e precompila")

    uploaded_file = st.file_uploader("Carica file PDF fattura", type=["pdf"])

    parsed_data = {
        "num_fattura": "",
        "data_fattura": date.today(),
        "data_scadenza": date.today(),
        "imponibile": 0.0,
        "iva_perc": 22.0,
    }

    if uploaded_file is not None:
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                text_pages = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(text_pages)

            import re

            # Numero fattura
            m_num = re.search(r"[Ff]attura\s*(n\.|nr\.|numero)?\s*([A-Za-z0-9\-\/]+)", full_text)
            if m_num:
                parsed_data["num_fattura"] = m_num.group(2).strip()

            # Data fattura
            m_date = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", full_text)
            if m_date:
                for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        parsed_data["data_fattura"] = datetime.strptime(m_date.group(1), fmt).date()
                        break
                    except ValueError:
                        continue

            # Imponibile e totale (euristica)
            numbers = re.findall(r"(\d{1,3}(?:[\.\,]\d{3})*(?:[\.\,]\d{2}))", full_text)
            if len(numbers) >= 2:
                def to_float(s):
                    s = s.replace(".", "").replace(",", ".")
                    return float(s)
                parsed_data["imponibile"] = to_float(numbers[-2])
                totale_pdf = to_float(numbers[-1])
                if parsed_data["imponibile"] > 0:
                    parsed_data["iva_perc"] = round((totale_pdf / parsed_data["imponibile"] - 1) * 100, 2)

            st.success("PDF letto, controlla e conferma i dati sotto.")

        except Exception as e:
            st.error(f"Errore lettura PDF: {e}")

    if uploaded_file is not None and clients:
        df_clients = pd.DataFrame([c.__dict__ for c in clients])
        df_clients["label"] = df_clients["client_id"].astype(str) + " - " + df_clients["ragione_sociale"]

        with get_session() as session:
            suggested_num_pdf = get_next_invoice_number(session, year=date.today().year, prefix="FL")

        with st.form("new_invoice_from_pdf"):
            st.markdown("#### Dati fattura precompilati")

            col1, col2 = st.columns(2)
            with col1:
                client_label_pdf = st.selectbox("Cliente", df_clients["label"].tolist())
                num_fattura_pdf = st.text_input(
                    "Numero fattura",
                    parsed_data["num_fattura"] or suggested_num_pdf,
                )
                data_fattura_pdf = st.date_input("Data fattura", value=parsed_data["data_fattura"])
                data_scadenza_pdf = st.date_input("Data scadenza", value=parsed_data["data_fattura"])
            with col2:
                imponibile_pdf = st.number_input(
                    "Imponibile (€)",
                    min_value=0.0,
                    step=100.0,
                    value=float(parsed_data["imponibile"]),
                )
                iva_perc_pdf = st.number_input(
                    "Aliquota IVA (%)",
                    min_value=0.0,
                    step=1.0,
                    value=float(parsed_data["iva_perc"]),
                )
                stato_pagamento_pdf = st.selectbox(
                    "Stato pagamento",
                    ["emessa", "incassata", "scaduta"],
                    index=0,
                )
                data_incasso_pdf = st.date_input("Data incasso (se incassata)", value=date.today())

            submitted_pdf = st.form_submit_button("Salva fattura da PDF")

        if submitted_pdf:
            if not num_fattura_pdf.strip():
                st.warning("Il numero fattura è obbligatorio.")
            else:
                client_id_sel_pdf = int(client_label_pdf.split(" - ")[0])
                iva_val_pdf = imponibile_pdf * iva_perc_pdf / 100.0
                totale_pdf = imponibile_pdf + iva_val_pdf

                with get_session() as session:
                    new_inv_pdf = Invoice(
                        client_id=client_id_sel_pdf,
                        num_fattura=num_fattura_pdf.strip(),
                        data_fattura=data_fattura_pdf,
                        data_scadenza=data_scadenza_pdf,
                        importo_imponibile=imponibile_pdf,
                        iva=iva_val_pdf,
                        importo_totale=totale_pdf,
                        stato_pagamento=stato_pagamento_pdf,
                        data_incasso=data_incasso_pdf if stato_pagamento_pdf == "incassata" else None,
                    )
                    session.add(new_inv_pdf)
                    session.commit()
                    session.refresh(new_inv_pdf)
                st.success(f"Fattura {new_inv_pdf.num_fattura} (da PDF) registrata.")
                st.rerun()

    st.markdown("---")

    # =========================
    # 3) ELENCO FATTURE + KPI
    # =========================
    st.subheader("📊 Elenco fatture")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        data_da = st.date_input("Da data (fattura)", value=None)
    with col_f2:
        data_a = st.date_input("A data (fattura)", value=None)

    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()

    if not invoices:
        st.info("Nessuna fattura registrata.")
        return

    df_inv = pd.DataFrame([i.__dict__ for i in invoices])
    df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")

    if data_da:
        df_inv = df_inv[df_inv["data_fattura"] >= pd.to_datetime(data_da)]
    if data_a:
        df_inv = df_inv[df_inv["data_fattura"] <= pd.to_datetime(data_a)]

    st.dataframe(df_inv)

    # KPI base: totale fatturato per anno
    if {"data_fattura", "importo_totale"}.issubset(df_inv.columns):
        df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")
        df_inv["anno"] = df_inv["data_fattura"].dt.year
        kpi_year = df_inv.groupby("anno")["importo_totale"].sum().reset_index()
        st.markdown("#### Totale fatturato per anno")
        st.bar_chart(kpi_year.set_index("anno")["importo_totale"])

    # =========================
    # 4) MODIFICA / ELIMINA FATTURA (SOLO ADMIN) + EXPORT XML
    # =========================
    if role != "admin":
        st.info("Modifica, eliminazione ed export XML disponibili solo per ruolo 'admin'.")
        return

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina / esporta fattura (solo admin)")

    inv_ids = df_inv["invoice_id"].tolist()
    inv_id_sel = st.selectbox("Seleziona ID fattura", inv_ids)

    with get_session() as session:
        inv_obj = session.get(Invoice, inv_id_sel)
        clients_all = session.exec(select(Client)).all()

    if not inv_obj:
        st.warning("Fattura non trovata.")
        return

    df_clients_all = pd.DataFrame([c.__dict__ for c in clients_all]) if clients_all else pd.DataFrame()
    if not df_clients_all.empty:
        df_clients_all["label"] = df_clients_all["client_id"].astype(str) + " - " + df_clients_all["ragione_sociale"]
        try:
            current_client_label = df_clients_all[
                df_clients_all["client_id"] == inv_obj.client_id
            ]["label"].iloc[0]
        except IndexError:
            current_client_label = df_clients_all["label"].iloc[0]
    else:
        current_client_label = ""

    with st.form("edit_invoice"):
        col1, col2 = st.columns(2)
        with col1:
            client_label_e = st.selectbox(
                "Cliente",
                df_clients_all["label"].tolist() if not df_clients_all.empty else [],
                index=df_clients_all["label"].tolist().index(current_client_label) if current_client_label else 0,
            ) if not df_clients_all.empty else ("",)
            num_fattura_e = st.text_input("Numero fattura", inv_obj.num_fattura or "")
            data_fattura_e = st.date_input(
                "Data fattura",
                value=inv_obj.data_fattura or date.today(),
            )
            data_scadenza_e = st.date_input(
                "Data scadenza",
                value=inv_obj.data_scadenza or date.today(),
            )
        with col2:
            importo_imponibile_e = st.number_input(
                "Imponibile (€)",
                min_value=0.0,
                step=100.0,
                value=float(inv_obj.importo_imponibile or 0.0),
            )
            iva_e = st.number_input(
                "IVA (€)",
                min_value=0.0,
                step=100.0,
                value=float(inv_obj.iva or 0.0),
            )
            stato_pagamento_e = st.selectbox(
                "Stato pagamento",
                ["emessa", "incassata", "scaduta"],
                index=["emessa", "incassata", "scaduta"].index(inv_obj.stato_pagamento or "emessa"),
            )
            data_incasso_e = st.date_input(
                "Data incasso",
                value=inv_obj.data_incasso or date.today(),
            )

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            update_clicked = st.form_submit_button("💾 Aggiorna fattura")
        with col_b2:
            delete_clicked = st.form_submit_button("🗑 Elimina fattura")
        with col_b3:
            export_xml_clicked = st.form_submit_button("📤 Esporta XML FatturaPA (bozza)")

    if update_clicked:
        if not num_fattura_e.strip():
            st.warning("Il numero fattura è obbligatorio.")
        else:
            with get_session() as session:
                obj = session.get(Invoice, inv_id_sel)
                if obj:
                    if not df_clients_all.empty:
                        client_id_e = int(client_label_e.split(" - ")[0])
                        obj.client_id = client_id_e
                    obj.num_fattura = num_fattura_e.strip()
                    obj.data_fattura = data_fattura_e
                    obj.data_scadenza = data_scadenza_e
                    obj.importo_imponibile = importo_imponibile_e
                    obj.iva = iva_e
                    obj.importo_totale = importo_imponibile_e + iva_e
                    obj.stato_pagamento = stato_pagamento_e
                    obj.data_incasso = data_incasso_e if stato_pagamento_e == "incassata" else None
                    session.add(obj)
                    session.commit()
            st.success("Fattura aggiornata.")
            st.rerun()

    if delete_clicked:
        with get_session() as session:
            obj = session.get(Invoice, inv_id_sel)
            if obj:
                pays_linked = session.exec(
                    select(Payment).where(Payment.invoice_id == inv_id_sel)
                ).all()
                if pays_linked:
                    st.warning("Impossibile eliminare: esistono incassi collegati a questa fattura.")
                else:
                    session.delete(obj)
                    session.commit()
                    st.success("Fattura eliminata.")
                    st.rerun()

    if export_xml_clicked:
        inv = inv_obj

        # Carica dati cliente dal DB
        with get_session() as session:
            client_xml = session.get(Client, inv.client_id)

        my = MY_COMPANY_DATA

        # Cedente/prestatore (tu)
        ced_den = my["denominazione"]
        ced_piva = my["piva"]
        ced_cf = my["codice_fiscale"]
        ced_addr = my["indirizzo"]
        ced_cap = my["cap"]
        ced_comune = my["comune"]
        ced_prov = my["provincia"]
        ced_paese = my["nazione"]
        ced_regime = my.get("regime_fiscale", "RF19")
        id_paese_trasm = my.get("id_paese_trasmittente", "IT")
        id_codice_trasm = my.get("id_codice_trasmittente", ced_cf)
        formato_trasm = my.get("formato_trasmissione", "FPR12")

        # Cessionario/committente (cliente)
        cli_den = client_xml.ragione_sociale or ""
        cli_piva = (client_xml.piva or "").strip() or ced_piva
        cli_cf = (client_xml.cod_fiscale or "").strip() or cli_piva

        raw_paese = (client_xml.paese or "IT").strip()
        if raw_paese.lower() in ("italia", "it"):
            cli_paese = "IT"
        else:
            cli_paese = raw_paese.upper()[:2]

        cli_addr = client_xml.indirizzo or ""
        cli_cap = client_xml.cap or ""
        cli_comune = client_xml.comune or ""
        cli_prov = client_xml.provincia or ""
        cli_cod_dest = client_xml.codice_destinatario or "0000000"
        cli_pec = client_xml.pec_fatturazione or my.get("pec_mittente", "")

        # Progressivo invio
        prefisso = my.get("progressivo_invio_prefisso", "FL")
        raw_prog = f"{prefisso}{inv.invoice_id:08d}"
        progressivo_invio = raw_prog[:10] 

        aliquota_iva = (inv.iva / inv.importo_imponibile * 100) if inv.importo_imponibile else 22.0

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica versione="{formato_trasm}">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>{id_paese_trasm}</IdPaese>
        <IdCodice>{id_codice_trasm}</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>{progressivo_invio}</ProgressivoInvio>
      <FormatoTrasmissione>{formato_trasm}</FormatoTrasmissione>
      <CodiceDestinatario>{cli_cod_dest}</CodiceDestinatario>
      {"<PECDestinatario>" + cli_pec + "</PECDestinatario>" if cli_cod_dest == "0000000" and cli_pec else ""}
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>{ced_paese}</IdPaese>
          <IdCodice>{ced_piva}</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>{ced_cf}</CodiceFiscale>
        <Anagrafica>
          <Denominazione>{ced_den}</Denominazione>
        </Anagrafica>
        <RegimeFiscale>{ced_regime}</RegimeFiscale>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>{ced_addr}</Indirizzo>
        <CAP>{ced_cap}</CAP>
        <Comune>{ced_comune}</Comune>
        <Provincia>{ced_prov}</Provincia>
        <Nazione>{ced_paese}</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>{cli_paese}</IdPaese>
          <IdCodice>{cli_piva}</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>{cli_cf}</CodiceFiscale>
        <Anagrafica>
          <Denominazione>{cli_den}</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>{cli_addr}</Indirizzo>
        <CAP>{cli_cap}</CAP>
        <Comune>{cli_comune}</Comune>
        <Provincia>{cli_prov}</Provincia>
        <Nazione>{cli_paese}</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{inv.data_fattura}</Data>
        <Numero>{inv.num_fattura}</Numero>
        <ImportoTotaleDocumento>{inv.importo_totale:.2f}</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>Servizi di consulenza ForgiaLean</Descrizione>
        <Quantita>1.00</Quantita>
        <PrezzoUnitario>{inv.importo_imponibile:.2f}</PrezzoUnitario>
        <PrezzoTotale>{inv.importo_imponibile:.2f}</PrezzoTotale>
        <AliquotaIVA>{aliquota_iva:.2f}</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>{aliquota_iva:.2f}</AliquotaIVA>
        <ImponibileImporto>{inv.importo_imponibile:.2f}</ImponibileImporto>
        <Imposta>{inv.iva:.2f}</Imposta>
        <EsigibilitaIVA>I</EsigibilitaIVA>
      </DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento>
      <CondizioniPagamento>TP02</CondizioniPagamento>
      <DettaglioPagamento>
        <ModalitaPagamento>MP01</ModalitaPagamento>
        <DataScadenzaPagamento>{inv.data_scadenza or inv.data_fattura}</DataScadenzaPagamento>
        <ImportoPagamento>{inv.importo_totale:.2f}</ImportoPagamento>
      </DettaglioPagamento>
    </DatiPagamento>
  </FatturaElettronicaBody>
</FatturaElettronica>
"""

        b = io.BytesIO(xml_content.encode("utf-8"))
        st.download_button(
            label="⬇️ Scarica XML FatturaPA (bozza)",
            data=b,
            file_name=f"fattura_{inv.num_fattura}.xml",
            mime="application/xml",
            key=f"download_xml_{inv.invoice_id}",
        )
        st.info("XML FatturaPA di bozza generato. Verifica con un validatore/gestionale prima dell'invio allo SdI.")
     
def page_payments():
    st.title("💶 Incassi / Scadenze")
    role = st.session_state.get("role", "user")

    # =========================
    # CARICO FATTURE E COSTRUISCO LABEL
    # =========================
    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()

    if not invoices:
        st.info("Nessuna fattura registrata. Prima inserisci almeno una fattura nella pagina Finanza / Fatture.")
        return

    df_inv = pd.DataFrame([i.__dict__ for i in invoices])

    # Etichetta: ID - Numero fattura - Cliente - Totale - Stato
    with get_session() as session:
        clients = session.exec(select(Client)).all()
    df_clients = pd.DataFrame([c.__dict__ for c in clients]) if clients else pd.DataFrame()

    df_inv["label"] = df_inv["invoice_id"].astype(str) + " - " + df_inv["num_fattura"].astype(str)

    if not df_clients.empty:
        df_clients = df_clients.rename(columns={"client_id": "client_id"})
        df_inv = df_inv.merge(
            df_clients[["client_id", "ragione_sociale"]],
            how="left",
            on="client_id",
        )
        df_inv["label"] = (
            df_inv["invoice_id"].astype(str)
            + " - "
            + df_inv["num_fattura"].astype(str)
            + " - "
            + df_inv["ragione_sociale"].fillna("")
        )

    df_inv["label"] = df_inv["label"] + " - " + df_inv["importo_totale"].fillna(0).astype(float).map(lambda x: f"€ {x:,.2f}")
    df_inv["label"] = df_inv["label"] + " - " + df_inv["stato_pagamento"].fillna("emessa")

    # =========================
    # Helper per aggiornare lo stato fattura
    # =========================
    def aggiorna_stato_fattura(session, invoice_id, payment_date):
        inv_obj = session.get(Invoice, invoice_id)
        if not inv_obj:
            return

        pays_all = session.exec(
            select(Payment).where(Payment.invoice_id == invoice_id)
        ).all()
        totale_incassato = sum(p.amount for p in pays_all) if pays_all else 0.0

        today = date.today()
        scadenza = inv_obj.data_scadenza or inv_obj.data_fattura or today

        if totale_incassato >= (inv_obj.importo_totale or 0):
            inv_obj.stato_pagamento = "incassata"
            # data incasso = data ultimo incasso registrato
            if pays_all:
                last_pay_date = max(p.payment_date for p in pays_all if p.payment_date)
                inv_obj.data_incasso = last_pay_date or payment_date
            else:
                inv_obj.data_incasso = payment_date
        else:
            if totale_incassato > 0:
                inv_obj.stato_pagamento = "parzialmente_incassata"
            else:
                # nessun incasso
                if scadenza < today:
                    inv_obj.stato_pagamento = "scaduta"
                else:
                    inv_obj.stato_pagamento = "emessa"
            inv_obj.data_incasso = None

        session.add(inv_obj)

    # =========================
    # NUOVO INCASSO (con precompilazione dalla fattura)
    # =========================
    st.subheader("➕ Registra nuovo incasso")

    with st.form("new_payment"):
        invoice_label = st.selectbox("Fattura", df_inv["label"].tolist())
        invoice_id_sel = int(invoice_label.split(" - ")[0])

        fattura_sel = df_inv[df_inv["invoice_id"] == invoice_id_sel].iloc[0]
        importo_totale_fattura = float(fattura_sel["importo_totale"] or 0.0)

        with get_session() as session:
            pays_existing = session.exec(
                select(Payment).where(Payment.invoice_id == invoice_id_sel)
            ).all()
        totale_gia_incassato = sum(p.amount for p in pays_existing) if pays_existing else 0.0
        residuo = importo_totale_fattura - totale_gia_incassato

        st.write(f"Totale fattura: € {importo_totale_fattura:,.2f}")
        st.write(f"Già incassato: € {totale_gia_incassato:,.2f}")
        st.write(f"Residuo: € {residuo:,.2f}")

        payment_date = st.date_input("Data pagamento", value=date.today())
        default_amount = max(residuo, 0.0) if residuo > 0 else 0.0
        amount = st.number_input("Importo incassato (€)", min_value=0.0, step=50.0, value=default_amount)
        method = st.text_input("Metodo (bonifico, carta, contanti...)", "bonifico")
        note = st.text_area("Note", "")

        submitted_pay = st.form_submit_button("Salva incasso")

    if submitted_pay:
        if amount <= 0:
            st.warning("L'importo deve essere maggiore di zero.")
        else:
            with get_session() as session:
                new_pay = Payment(
                    invoice_id=invoice_id_sel,
                    payment_date=payment_date,
                    amount=amount,
                    method=method.strip() or "bonifico",
                    note=note.strip() or None,
                )
                session.add(new_pay)

                # aggiorno stato fattura in base a tutti gli incassi
                aggiorna_stato_fattura(session, invoice_id_sel, payment_date)

                session.commit()
            st.success("Incasso registrato e stato fattura aggiornato.")
            st.rerun()
    # =========================
    # KPI INCASSI / SCADENZE
    # =========================
    st.markdown("---")
    st.subheader("📊 KPI incassi e scadenze")

    # Ricalcolo df_inv aggiornato dal DB per sicurezza
    with get_session() as session:
        invoices_kpi = session.exec(select(Invoice)).all()
    df_kpi = pd.DataFrame([i.__dict__ for i in invoices_kpi]) if invoices_kpi else pd.DataFrame()

    if not df_kpi.empty:
        df_kpi["data_fattura"] = pd.to_datetime(df_kpi["data_fattura"], errors="coerce")
        df_kpi["anno"] = df_kpi["data_fattura"].dt.year

        anno_corrente = date.today().year
        fatture_anno = df_kpi[df_kpi["anno"] == anno_corrente]

        totale_incassato_ytd = fatture_anno[
            fatture_anno["stato_pagamento"].isin(["parzialmente_incassata", "incassata"])
        ]["importo_totale"].sum() if not fatture_anno.empty else 0.0

        esposizione_aperta = df_kpi[
            ~df_kpi["stato_pagamento"].isin(["incassata"])
        ]["importo_totale"].sum()

        oggi = pd.to_datetime(date.today())
        df_kpi["data_scadenza"] = pd.to_datetime(df_kpi["data_scadenza"], errors="coerce")
        scadute_non_incassate = df_kpi[
            (df_kpi["data_scadenza"].notna())
            & (df_kpi["data_scadenza"] < oggi)
            & (~df_kpi["stato_pagamento"].isin(["incassata"]))
        ]

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.metric("Incassato anno corrente", f"€ {totale_incassato_ytd:,.2f}")
        with col_k2:
            st.metric("Esposizione aperta", f"€ {esposizione_aperta:,.2f}")
        with col_k3:
            st.metric("Fatture scadute non incassate", int(scadute_non_incassate.shape[0]))
    else:
        st.info("Nessuna fattura disponibile per i KPI.")

    # =========================
    # AGING FATTURE APERTE
    # =========================
    st.markdown("---")
    st.subheader("📌 Aging fatture aperte")

    with get_session() as session:
        invoices_aging = session.exec(select(Invoice)).all()
    df_aging = pd.DataFrame([i.__dict__ for i in invoices_aging]) if invoices_aging else pd.DataFrame()

    if not df_aging.empty:
        df_aging["data_scadenza"] = pd.to_datetime(df_aging["data_scadenza"], errors="coerce")
        df_aging["data_fattura"] = pd.to_datetime(df_aging["data_fattura"], errors="coerce")

        oggi = pd.to_datetime(date.today())

        # Considero solo fatture non completamente incassate
        df_aging_open = df_aging[~df_aging["stato_pagamento"].isin(["incassata"])].copy()

        # Calcolo giorni di ritardo (solo se scadute)
        df_aging_open["days_overdue"] = (oggi - df_aging_open["data_scadenza"]).dt.days
        df_aging_open["days_overdue"] = df_aging_open["days_overdue"].fillna(0)

        # Bucket aging
        def aging_bucket(row):
            d = row["days_overdue"]
            if d <= 0:
                return "Non ancora scaduta"
            elif 1 <= d <= 30:
                return "1-30 giorni"
            elif 31 <= d <= 60:
                return "31-60 giorni"
            elif 61 <= d <= 90:
                return "61-90 giorni"
            else:
                return ">90 giorni"

        df_aging_open["aging_bucket"] = df_aging_open.apply(aging_bucket, axis=1)

        # Totale per bucket
        aging_summary = (
            df_aging_open.groupby("aging_bucket")["importo_totale"]
            .sum()
            .reset_index()
            .sort_values(
                "aging_bucket",
                key=lambda s: s.map(
                    {
                        "Non ancora scaduta": 0,
                        "1-30 giorni": 1,
                        "31-60 giorni": 2,
                        "61-90 giorni": 3,
                        ">90 giorni": 4,
                    }
                ),
            )
        )

        st.markdown("**Riepilogo per bucket**")
        st.dataframe(aging_summary)

        st.markdown("**Dettaglio fatture aperte**")
        # Se hai il merge con clienti come sopra, puoi riutilizzare df_clients; altrimenti lascio così
        st.dataframe(
            df_aging_open[
                [
                    "invoice_id",
                    "num_fattura",
                    "data_fattura",
                    "data_scadenza",
                    "importo_totale",
                    "stato_pagamento",
                    "days_overdue",
                    "aging_bucket",
                ]
            ]
        )
    else:
        st.info("Nessuna fattura disponibile per l'aging.")

    st.markdown("---")
    st.subheader("📋 Pagamenti registrati")

    with get_session() as session:
        pays = session.exec(select(Payment)).all()

    if not pays:
        st.info("Nessun pagamento registrato.")
        return

    df_pay = pd.DataFrame([p.__dict__ for p in pays])

    df_pay = df_pay.merge(
        df_inv[["invoice_id", "num_fattura", "ragione_sociale"]] if "ragione_sociale" in df_inv.columns else df_inv[["invoice_id", "num_fattura"]],
        how="left",
        left_on="invoice_id",
        right_on="invoice_id",
    )

    st.dataframe(df_pay)

    # =========================
    # 1) INSERIMENTO MANUALE FATTURA
    # =========================
    st.subheader("➕ Inserisci nuova fattura (manuale)")

    with get_session() as session:
        clients = session.exec(select(Client)).all()

    if not clients:
        st.info("Prima registra almeno un cliente nella sezione Clienti.")
    else:
        df_clients = pd.DataFrame([c.__dict__ for c in clients])
        df_clients["label"] = df_clients["client_id"].astype(str) + " - " + df_clients["ragione_sociale"]

        with st.form("new_invoice_manual"):
            col1, col2 = st.columns(2)
            with col1:
                client_label = st.selectbox("Cliente", df_clients["label"].tolist())
                num_fattura = st.text_input("Numero fattura", "")
                data_fattura = st.date_input("Data fattura", value=date.today())
                data_scadenza = st.date_input("Data scadenza", value=date.today())
            with col2:
                importo_imponibile = st.number_input("Imponibile (€)", min_value=0.0, step=100.0)
                iva_perc = st.number_input("Aliquota IVA (%)", min_value=0.0, step=1.0, value=22.0)
                stato_pagamento = st.selectbox(
                    "Stato pagamento",
                    ["emessa", "incassata", "scaduta"],
                    index=0,
                )
                data_incasso = st.date_input("Data incasso (se incassata)", value=date.today())

            submitted_manual = st.form_submit_button("Salva fattura manuale")

        if submitted_manual:
            if not num_fattura.strip():
                st.warning("Il numero fattura è obbligatorio.")
            else:
                client_id_sel = int(client_label.split(" - ")[0])
                iva_val = importo_imponibile * iva_perc / 100.0
                totale = importo_imponibile + iva_val

                with get_session() as session:
                    new_inv = Invoice(
                        client_id=client_id_sel,
                        num_fattura=num_fattura.strip(),
                        data_fattura=data_fattura,
                        data_scadenza=data_scadenza,
                        importo_imponibile=importo_imponibile,
                        iva=iva_val,
                        importo_totale=totale,
                        stato_pagamento=stato_pagamento,
                        data_incasso=data_incasso if stato_pagamento == "incassata" else None,
                    )
                    session.add(new_inv)
                    session.commit()
                    session.refresh(new_inv)
                st.success(f"Fattura {new_inv.num_fattura} registrata.")
                st.rerun()

    st.markdown("---")

    # =========================
    # 2) UPLOAD PDF FATTURA + PRECOMPILAZIONE
    # =========================
    st.subheader("📎 Carica fattura PDF e precompila")

    uploaded_file = st.file_uploader("Carica file PDF fattura", type=["pdf"])

    parsed_data = {
        "num_fattura": "",
        "data_fattura": date.today(),
        "data_scadenza": date.today(),
        "imponibile": 0.0,
        "iva_perc": 22.0,
    }

    if uploaded_file is not None:
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                text_pages = [page.extract_text() or "" for page in pdf.pages]
            full_text = "\n".join(text_pages)

            import re

            # Numero fattura
            m_num = re.search(r"[Ff]attura\s*(n\.|nr\.|numero)?\s*([A-Za-z0-9\-\/]+)", full_text)
            if m_num:
                parsed_data["num_fattura"] = m_num.group(2).strip()

            # Data fattura
            m_date = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", full_text)
            if m_date:
                for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        parsed_data["data_fattura"] = datetime.strptime(m_date.group(1), fmt).date()
                        break
                    except ValueError:
                        continue

            # Imponibile e totale (euristica)
            numbers = re.findall(r"(\d{1,3}(?:[\.\,]\d{3})*(?:[\.\,]\d{2}))", full_text)
            if len(numbers) >= 2:
                def to_float(s):
                    s = s.replace(".", "").replace(",", ".")
                    return float(s)
                parsed_data["imponibile"] = to_float(numbers[-2])
                totale_pdf = to_float(numbers[-1])
                if parsed_data["imponibile"] > 0:
                    parsed_data["iva_perc"] = round((totale_pdf / parsed_data["imponibile"] - 1) * 100, 2)

            st.success("PDF letto, controlla e conferma i dati sotto.")

        except Exception as e:
            st.error(f"Errore lettura PDF: {e}")

    if uploaded_file is not None and clients:
        df_clients = pd.DataFrame([c.__dict__ for c in clients])
        df_clients["label"] = df_clients["client_id"].astype(str) + " - " + df_clients["ragione_sociale"]

        with st.form("new_invoice_from_pdf"):
            st.markdown("#### Dati fattura precompilati")

            col1, col2 = st.columns(2)
            with col1:
                client_label_pdf = st.selectbox("Cliente", df_clients["label"].tolist())
                num_fattura_pdf = st.text_input("Numero fattura", parsed_data["num_fattura"])
                data_fattura_pdf = st.date_input("Data fattura", value=parsed_data["data_fattura"])
                data_scadenza_pdf = st.date_input("Data scadenza", value=parsed_data["data_fattura"])
            with col2:
                imponibile_pdf = st.number_input(
                    "Imponibile (€)",
                    min_value=0.0,
                    step=100.0,
                    value=float(parsed_data["imponibile"]),
                )
                iva_perc_pdf = st.number_input(
                    "Aliquota IVA (%)",
                    min_value=0.0,
                    step=1.0,
                    value=float(parsed_data["iva_perc"]),
                )
                stato_pagamento_pdf = st.selectbox(
                    "Stato pagamento",
                    ["emessa", "incassata", "scaduta"],
                    index=0,
                )
                data_incasso_pdf = st.date_input("Data incasso (se incassata)", value=date.today())

            submitted_pdf = st.form_submit_button("Salva fattura da PDF")

        if submitted_pdf:
            if not num_fattura_pdf.strip():
                st.warning("Il numero fattura è obbligatorio.")
            else:
                client_id_sel_pdf = int(client_label_pdf.split(" - ")[0])
                iva_val_pdf = imponibile_pdf * iva_perc_pdf / 100.0
                totale_pdf = imponibile_pdf + iva_val_pdf

                with get_session() as session:
                    new_inv_pdf = Invoice(
                        client_id=client_id_sel_pdf,
                        num_fattura=num_fattura_pdf.strip(),
                        data_fattura=data_fattura_pdf,
                        data_scadenza=data_scadenza_pdf,
                        importo_imponibile=imponibile_pdf,
                        iva=iva_val_pdf,
                        importo_totale=totale_pdf,
                        stato_pagamento=stato_pagamento_pdf,
                        data_incasso=data_incasso_pdf if stato_pagamento_pdf == "incassata" else None,
                    )
                    session.add(new_inv_pdf)
                    session.commit()
                    session.refresh(new_inv_pdf)
                st.success(f"Fattura {new_inv_pdf.num_fattura} (da PDF) registrata.")
                st.rerun()

    st.markdown("---")

    # =========================
    # 3) ELENCO FATTURE + KPI
    # =========================
    st.subheader("📊 Elenco fatture")

    # -------------------------
    # FILTRI RICERCA FATTURE
    # -------------------------
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        data_da = st.date_input("Da data (fattura)", value=None)
    with col_f2:
        data_a = st.date_input("A data (fattura)", value=None)
    with col_f3:
        stato_filter = st.selectbox(
            "Stato pagamento",
            ["tutti", "emessa", "parzialmente_incassata", "incassata", "scaduta"],
            index=0,
        )

    # filtro per cliente e anno
    col_f4, col_f5 = st.columns(2)
    with col_f4:
        with get_session() as session:
            clients_all = session.exec(select(Client)).all()
        df_clients_all = pd.DataFrame([c.__dict__ for c in clients_all]) if clients_all else pd.DataFrame()
        cliente_filter = "tutti"
        if not df_clients_all.empty:
            clienti_labels = ["tutti"] + (
                df_clients_all["client_id"].astype(str) + " - " + df_clients_all["ragione_sociale"]
            ).tolist()
            cliente_filter = st.selectbox("Cliente", clienti_labels, index=0)
    with col_f5:
        anno_filter = st.selectbox("Anno fattura", ["tutti"] + [str(y) for y in range(2023, date.today().year + 1)], index=0)

    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()

    if not invoices:
        st.info("Nessuna fattura registrata.")
        return

    df_inv = pd.DataFrame([i.__dict__ for i in invoices])
    df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")

    # Applica filtri
    if data_da:
        df_inv = df_inv[df_inv["data_fattura"] >= pd.to_datetime(data_da)]
    if data_a:
        df_inv = df_inv[df_inv["data_fattura"] <= pd.to_datetime(data_a)]

    if stato_filter != "tutti" and "stato_pagamento" in df_inv.columns:
        df_inv = df_inv[df_inv["stato_pagamento"] == stato_filter]

    if cliente_filter != "tutti" and "client_id" in df_inv.columns:
        client_id_sel = int(cliente_filter.split(" - ")[0])
        df_inv = df_inv[df_inv["client_id"] == client_id_sel]

    if anno_filter != "tutti":
        df_inv["anno"] = df_inv["data_fattura"].dt.year
        df_inv = df_inv[df_inv["anno"] == int(anno_filter)]

    if df_inv.empty:
        st.info("Nessuna fattura trovata con i filtri selezionati.")
        return

    st.dataframe(df_inv)

    if not invoices:
        st.info("Nessuna fattura registrata.")
        return

    df_inv = pd.DataFrame([i.__dict__ for i in invoices])
    df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")

    if data_da:
        df_inv = df_inv[df_inv["data_fattura"] >= pd.to_datetime(data_da)]
    if data_a:
        df_inv = df_inv[df_inv["data_fattura"] <= pd.to_datetime(data_a)]

    st.dataframe(df_inv)

    # KPI base: totale fatturato per anno
    if {"data_fattura", "importo_totale"}.issubset(df_inv.columns):
        df_inv["data_fattura"] = pd.to_datetime(df_inv["data_fattura"], errors="coerce")
        df_inv["anno"] = df_inv["data_fattura"].dt.year
        kpi_year = df_inv.groupby("anno")["importo_totale"].sum().reset_index()
        st.markdown("#### Totale fatturato per anno")
        st.bar_chart(kpi_year.set_index("anno")["importo_totale"])

    # =========================
    # 4) MODIFICA / ELIMINA FATTURA (SOLO ADMIN) + EXPORT XML
    # =========================
    if role != "admin":
        st.info("Modifica, eliminazione ed export XML disponibili solo per ruolo 'admin'.")
        return

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina / esporta fattura (solo admin)")

    inv_ids = df_inv["invoice_id"].tolist()
    inv_id_sel = st.selectbox("Seleziona ID fattura", inv_ids)

    with get_session() as session:
        inv_obj = session.get(Invoice, inv_id_sel)
        clients_all = session.exec(select(Client)).all()

    if not inv_obj:
        st.warning("Fattura non trovata.")
        return

    df_clients_all = pd.DataFrame([c.__dict__ for c in clients_all]) if clients_all else pd.DataFrame()
    if not df_clients_all.empty:
        df_clients_all["label"] = df_clients_all["client_id"].astype(str) + " - " + df_clients_all["ragione_sociale"]
        try:
            current_client_label = df_clients_all[
                df_clients_all["client_id"] == inv_obj.client_id
            ]["label"].iloc[0]
        except IndexError:
            current_client_label = df_clients_all["label"].iloc[0]
    else:
        current_client_label = ""

    with st.form("edit_invoice"):
        col1, col2 = st.columns(2)
        with col1:
            client_label_e = st.selectbox(
                "Cliente",
                df_clients_all["label"].tolist() if not df_clients_all.empty else [],
                index=df_clients_all["label"].tolist().index(current_client_label) if current_client_label else 0,
            ) if not df_clients_all.empty else ("",)
            num_fattura_e = st.text_input("Numero fattura", inv_obj.num_fattura or "")
            data_fattura_e = st.date_input(
                "Data fattura",
                value=inv_obj.data_fattura or date.today(),
            )
            data_scadenza_e = st.date_input(
                "Data scadenza",
                value=inv_obj.data_scadenza or date.today(),
            )
        with col2:
            importo_imponibile_e = st.number_input(
                "Imponibile (€)",
                min_value=0.0,
                step=100.0,
                value=float(inv_obj.importo_imponibile or 0.0),
            )
            iva_e = st.number_input(
                "IVA (€)",
                min_value=0.0,
                step=100.0,
                value=float(inv_obj.iva or 0.0),
            )
            stato_pagamento_e = st.selectbox(
                "Stato pagamento",
                ["emessa", "incassata", "scaduta"],
                index=["emessa", "incassata", "scaduta"].index(inv_obj.stato_pagamento or "emessa"),
            )
            data_incasso_e = st.date_input(
                "Data incasso",
                value=inv_obj.data_incasso or date.today(),
            )

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            update_clicked = st.form_submit_button("💾 Aggiorna fattura")
        with col_b2:
            delete_clicked = st.form_submit_button("🗑 Elimina fattura")
        with col_b3:
            export_xml_clicked = st.form_submit_button("📤 Esporta XML FatturaPA (bozza)")

    if update_clicked:
        if not num_fattura_e.strip():
            st.warning("Il numero fattura è obbligatorio.")
        else:
            with get_session() as session:
                obj = session.get(Invoice, inv_id_sel)
                if obj:
                    if not df_clients_all.empty:
                        client_id_e = int(client_label_e.split(" - ")[0])
                        obj.client_id = client_id_e
                    obj.num_fattura = num_fattura_e.strip()
                    obj.data_fattura = data_fattura_e
                    obj.data_scadenza = data_scadenza_e
                    obj.importo_imponibile = importo_imponibile_e
                    obj.iva = iva_e
                    obj.importo_totale = importo_imponibile_e + iva_e
                    obj.stato_pagamento = stato_pagamento_e
                    obj.data_incasso = data_incasso_e if stato_pagamento_e == "incassata" else None
                    session.add(obj)
                    session.commit()
            st.success("Fattura aggiornata.")
            st.rerun()

    if delete_clicked:
        with get_session() as session:
            obj = session.get(Invoice, inv_id_sel)
            if obj:
                session.delete(obj)
                session.commit()
        st.success("Fattura eliminata.")
        st.rerun()

    if export_xml_clicked:
        inv = inv_obj

        # Carica dati cliente dal DB
        with get_session() as session:
            client_xml = session.get(Client, inv.client_id)

        my = MY_COMPANY_DATA

        # Cedente/prestatore (tu)
        ced_den = my["denominazione"]
        ced_piva = my["piva"]
        ced_cf = my["codice_fiscale"]
        ced_addr = my["indirizzo"]
        ced_cap = my["cap"]
        ced_comune = my["comune"]
        ced_prov = my["provincia"]
        ced_paese = my["nazione"]
        ced_regime = my.get("regime_fiscale", "RF19")
        id_paese_trasm = my.get("id_paese_trasmittente", "IT")
        id_codice_trasm = my.get("id_codice_trasmittente", ced_cf)
        formato_trasm = my.get("formato_trasmissione", "FPR12")

        # Cessionario/committente (cliente)
        cli_den = client_xml.ragione_sociale or ""
        cli_piva = (client_xml.piva or "").strip() or ced_piva
        cli_cf = (client_xml.cod_fiscale or "").strip() or cli_piva

        raw_paese = (client_xml.paese or "IT").strip()
        if raw_paese.lower() in ("italia", "it"):
            cli_paese = "IT"
        else:
            cli_paese = raw_paese.upper()[:2]

        cli_addr = client_xml.indirizzo or ""
        cli_cap = client_xml.cap or ""
        cli_comune = client_xml.comune or ""
        cli_prov = client_xml.provincia or ""
        cli_cod_dest = client_xml.codice_destinatario or "0000000"
        cli_pec = client_xml.pec_fatturazione or my.get("pec_mittente", "")

        # Progressivo invio
        prefisso = my.get("progressivo_invio_prefisso", "FL")
        progressivo_invio = f"{prefisso}_{(inv.num_fattura or '1').replace('/', '_')}"

        # Aliquota IVA: calcolata da imponibile e iva
        if inv.importo_imponibile:
            aliquota_iva = round((inv.iva / inv.importo_imponibile) * 100, 2)
        else:
            aliquota_iva = 22.0

        # Descrizione riga (per ora fissa, ma parametrizzabile)
        descrizione_riga = "Servizi di consulenza ForgiaLean"

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica versione="{formato_trasm}">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente>
        <IdPaese>{id_paese_trasm}</IdPaese>
        <IdCodice>{id_codice_trasm}</IdCodice>
      </IdTrasmittente>
      <ProgressivoInvio>{progressivo_invio}</ProgressivoInvio>
      <FormatoTrasmissione>{formato_trasm}</FormatoTrasmissione>
      <CodiceDestinatario>{cli_cod_dest}</CodiceDestinatario>{("<PECDestinatario>" + cli_pec + "</PECDestinatario>") if cli_cod_dest == "0000000" and cli_pec else ""}
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>{ced_paese}</IdPaese>
          <IdCodice>{ced_piva}</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>{ced_cf}</CodiceFiscale>
        <Anagrafica>
          <Denominazione>{ced_den}</Denominazione>
        </Anagrafica>
        <RegimeFiscale>{ced_regime}</RegimeFiscale>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>{ced_addr}</Indirizzo>
        <CAP>{ced_cap}</CAP>
        <Comune>{ced_comune}</Comune>
        <Provincia>{ced_prov}</Provincia>
        <Nazione>{ced_paese}</Nazione>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA>
          <IdPaese>{cli_paese}</IdPaese>
          <IdCodice>{cli_piva}</IdCodice>
        </IdFiscaleIVA>
        <CodiceFiscale>{cli_cf}</CodiceFiscale>
        <Anagrafica>
          <Denominazione>{cli_den}</Denominazione>
        </Anagrafica>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>{cli_addr}</Indirizzo>
        <CAP>{cli_cap}</CAP>
        <Comune>{cli_comune}</Comune>
        <Provincia>{cli_prov}</Provincia>
        <Nazione>{cli_paese}</Nazione>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Divisa>EUR</Divisa>
        <Data>{inv.data_fattura}</Data>
        <Numero>{inv.num_fattura}</Numero>
        <ImportoTotaleDocumento>{inv.importo_totale:.2f}</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea>
        <Descrizione>{descrizione_riga}</Descrizione>
        <Quantita>1.00</Quantita>
        <PrezzoUnitario>{inv.importo_imponibile:.2f}</PrezzoUnitario>
        <PrezzoTotale>{inv.importo_imponibile:.2f}</PrezzoTotale>
        <AliquotaIVA>{aliquota_iva:.2f}</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo>
        <AliquotaIVA>{aliquota_iva:.2f}</AliquotaIVA>
        <ImponibileImporto>{inv.importo_imponibile:.2f}</ImponibileImporto>
        <Imposta>{inv.iva:.2f}</Imposta>
        <EsigibilitaIVA>I</EsigibilitaIVA>
      </DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento>
      <CondizioniPagamento>TP02</CondizioniPagamento>
      <DettaglioPagamento>
        <ModalitaPagamento>MP01</ModalitaPagamento>
        <DataScadenzaPagamento>{inv.data_scadenza or inv.data_fattura}</DataScadenzaPagamento>
        <ImportoPagamento>{inv.importo_totale:.2f}</ImportoPagamento>
      </DettaglioPagamento>
    </DatiPagamento>
  </FatturaElettronicaBody>
</FatturaElettronica>
"""

        b = io.BytesIO(xml_content.encode("utf-8"))
        st.download_button(
            label="⬇️ Scarica XML FatturaPA (bozza)",
            data=b,
            file_name=f"fattura_{inv.num_fattura}.xml",
            mime="application/xml",
            key=f"download_xml_{inv.invoice_id}",
        )
        st.info("XML FatturaPA di bozza generato. Verifica con un validatore/gestionale prima dell'invio allo SdI.")

def page_operations():
    st.title("🏭 Operations / Commesse (SQLite)")
    role = st.session_state.get("role", "user")

    # =========================
    # FORM INSERIMENTO COMMESSA
    # =========================
    st.subheader("➕ Inserisci nuova commessa")

    with st.form("new_commessa"):
        col1, col2 = st.columns(2)
        with col1:
            cod_commessa = st.text_input("Codice commessa", "")
            descrizione_cliente = st.text_input("Descrizione / Cliente", "")
            stato_commessa = st.selectbox(
                "Stato commessa",
                ["aperta", "in corso", "chiusa"],
                index=0,
            )
            data_inizio = st.date_input("Data inizio", value=date.today())
        with col2:
            data_fine_prevista = st.date_input("Data fine prevista", value=date.today())
            ore_previste = st.number_input("Ore previste", min_value=0.0, step=1.0)
            costo_previsto = st.number_input("Costo previsto (€)", min_value=0.0, step=100.0)

        submitted_commessa = st.form_submit_button("Salva commessa")

    if submitted_commessa:
        if not cod_commessa.strip():
            st.warning("Il codice commessa è obbligatorio.")
        else:
            with get_session() as session:
                new_comm = ProjectCommessa(
                    cod_commessa=cod_commessa.strip(),
                    descrizione_cliente=descrizione_cliente.strip() or None,
                    stato_commessa=stato_commessa,
                    data_inizio=data_inizio,
                    data_fine_prevista=data_fine_prevista,
                    ore_previste=ore_previste,
                    ore_consumate=0.0,
                    costo_previsto=costo_previsto,
                    costo_consuntivo=0.0,
                )
                session.add(new_comm)
                session.commit()
                session.refresh(new_comm)
            st.success(f"Commessa creata con ID {new_comm.commessa_id}")
            st.rerun()

    st.markdown("---")

    # =========================
    # FORM INSERIMENTO FASE / TASK
    # =========================
    st.subheader("🧩 Inserisci nuova fase di commessa")

    with get_session() as session:
        commesse = session.exec(select(ProjectCommessa)).all()

    if not commesse:
        st.info("Prima crea almeno una commessa con il form sopra.")
    else:
        df_comm = pd.DataFrame([c.__dict__ for c in commesse])
        df_comm["label"] = df_comm["commessa_id"].astype(str) + " - " + df_comm["cod_commessa"]

        with st.form("new_fase"):
            col1, col2 = st.columns(2)
            with col1:
                commessa_label = st.selectbox("Commessa", df_comm["label"].tolist())
                nome_fase = st.text_input("Nome fase / task", "")
                stato_fase = st.selectbox(
                    "Stato fase",
                    ["aperta", "in corso", "chiusa"],
                    index=0,
                )
                data_inizio_fase = st.date_input("Data inizio fase", value=date.today())
            with col2:
                data_fine_prevista_fase = st.date_input("Data fine prevista fase", value=date.today())
                ore_previste_fase = st.number_input("Ore previste fase", min_value=0.0, step=1.0)
                risorsa_responsabile = st.text_input("Risorsa responsabile", "")

            submitted_fase = st.form_submit_button("Salva fase")

        if submitted_fase:
            if not nome_fase.strip():
                st.warning("Il nome fase è obbligatorio.")
            else:
                commessa_id_sel = int(commessa_label.split(" - ")[0])
                with get_session() as session:
                    new_fase = TaskFase(
                        commessa_id=commessa_id_sel,
                        nome_fase=nome_fase.strip(),
                        stato_fase=stato_fase,
                        data_inizio=data_inizio_fase,
                        data_fine_prevista=data_fine_prevista_fase,
                        data_fine_effettiva=None,
                        ore_previste=ore_previste_fase,
                        ore_consumate=0.0,
                        risorsa_responsabile=risorsa_responsabile.strip() or None,
                    )
                    session.add(new_fase)
                    session.commit()
                    session.refresh(new_fase)
                st.success(f"Fase creata con ID {new_fase.fase_id}")
                st.rerun()

    st.markdown("---")

    # =========================
    # FORM REGISTRAZIONE ORE (TIMESHEET)
    # =========================
    st.subheader("🕒 Registrazione ore (timesheet)")

    with get_session() as session:
        commesse_ts = session.exec(select(ProjectCommessa)).all()
        fasi_ts = session.exec(select(TaskFase)).all()

    if not commesse_ts or not fasi_ts:
        st.info("Servono almeno una commessa e una fase per registrare ore.")
    else:
        df_comm_ts = pd.DataFrame([c.__dict__ for c in commesse_ts])
        df_fasi_ts = pd.DataFrame([f.__dict__ for f in fasi_ts])

        df_comm_ts["label"] = df_comm_ts["commessa_id"].astype(str) + " - " + df_comm_ts["cod_commessa"]

        with st.form("new_timeentry"):
            col1, col2 = st.columns(2)
            with col1:
                commessa_label_ts = st.selectbox("Commessa (timesheet)", df_comm_ts["label"].tolist())
                # filtra le fasi per commessa selezionata
                commessa_id_ts = int(commessa_label_ts.split(" - ")[0])
                df_fasi_comm = df_fasi_ts[df_fasi_ts["commessa_id"] == commessa_id_ts]
                if df_fasi_comm.empty:
                    st.warning("Questa commessa non ha ancora fasi. Creane una sopra.")
                    fase_label = None
                else:
                    df_fasi_comm["label"] = df_fasi_comm["fase_id"].astype(str) + " - " + df_fasi_comm["nome_fase"]
                    fase_label = st.selectbox("Fase", df_fasi_comm["label"].tolist())
                data_lavoro = st.date_input("Data lavoro", value=date.today())
            with col2:
                ore_lavorate = st.number_input("Ore lavorate", min_value=0.0, step=0.5)
                operatore = st.text_input("Operatore", "")

            submitted_time = st.form_submit_button("Registra ore")

        if submitted_time:
            if fase_label is None:
                st.warning("Seleziona una fase valida.")
            elif ore_lavorate <= 0:
                st.warning("Le ore devono essere maggiori di zero.")
            else:
                fase_id_ts = int(fase_label.split(" - ")[0])
                with get_session() as session:
                    new_entry = TimeEntry(
                        commessa_id=commessa_id_ts,
                        fase_id=fase_id_ts,
                        data_lavoro=data_lavoro,
                        ore=float(ore_lavorate),
                        operatore=operatore.strip() or None,
                    )
                    session.add(new_entry)

                    # aggiorna ore_consumate fase
                    total_ore_fase = session.exec(
                        select(TimeEntry.ore).where(TimeEntry.fase_id == fase_id_ts)
                    ).all()
                    somma_fase = sum(total_ore_fase)

                    fase_obj = session.get(TaskFase, fase_id_ts)
                    if fase_obj:
                        fase_obj.ore_consumate = somma_fase

                    # aggiorna ore_consumate commessa
                    total_ore_comm = session.exec(
                        select(TimeEntry.ore).where(TimeEntry.commessa_id == commessa_id_ts)
                    ).all()
                    somma_comm = sum(total_ore_comm)

                    comm_obj = session.get(ProjectCommessa, commessa_id_ts)
                    if comm_obj:
                        comm_obj.ore_consumate = somma_comm

                    session.commit()

                st.success("Ore registrate e KPIs aggiornati.")
                st.rerun()

    st.markdown("---")

    # =========================
    # VISTA COMMESSE + KPI BASE
    # =========================
    st.subheader("📂 Elenco commesse")

    with get_session() as session:
        commesse_all = session.exec(select(ProjectCommessa)).all()
        fasi_all = session.exec(select(TaskFase)).all()
        times_all = session.exec(select(TimeEntry)).all()

    if not commesse_all:
        st.info("Nessuna commessa ancora registrata.")
        return

    df_all = pd.DataFrame([c.__dict__ for c in commesse_all])
    st.dataframe(df_all)

    st.subheader("📈 Ore previste vs consumate per commessa")
    cols = {"cod_commessa", "ore_previste", "ore_consumate"}
    if cols.issubset(df_all.columns):
        kpi = df_all[list(cols)]
        fig_kpi = px.bar(
            kpi,
            x="cod_commessa",
            y=["ore_previste", "ore_consumate"],
            barmode="group",
            title="Ore previste vs consumate per commessa",
        )
        st.plotly_chart(fig_kpi, use_container_width=True)
    else:
        st.info("Mancano colonne per il grafico ore previste/consumate.")


    st.markdown("---")
    st.subheader("📋 Fasi / Task commesse")

    if fasi_all:
        df_fasi_all = pd.DataFrame([f.__dict__ for f in fasi_all])
        st.dataframe(df_fasi_all)
    else:
        st.info("Nessuna fase registrata.")

    st.markdown("---")
    st.subheader("🧾 Timesheet registrati")

    if times_all:
        df_times = pd.DataFrame([t.__dict__ for t in times_all])
        st.dataframe(df_times)
    else:
        st.info("Nessuna riga di timesheet registrata.")

    st.markdown("---")
    st.subheader("📊 KPI commesse e ore lavorate")

    with get_session() as session:
        commesse_all_kpi = session.exec(select(ProjectCommessa)).all()
        time_all_kpi = session.exec(select(TimeEntry)).all()

    if not commesse_all_kpi or not time_all_kpi:
        st.info("Per i KPI servono almeno una commessa e qualche registrazione ore.")
    else:
        df_comm_all = pd.DataFrame([c.__dict__ for c in commesse_all_kpi])
        df_time_all = pd.DataFrame([t.__dict__ for t in time_all_kpi])

        # KPI sintetici
        ore_totali = df_time_all["ore"].sum()
        n_commesse_aperte = df_comm_all[
            df_comm_all["stato_commessa"].isin(["aperta", "in corso"])
        ].shape[0]
        ore_previste_tot = df_comm_all["ore_previste"].sum()
        utilizzo_ore = (ore_totali / ore_previste_tot * 100.0) if ore_previste_tot > 0 else 0.0

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.metric("Ore totali lavorate (tutte le commesse)", f"{ore_totali:.1f} h")
        with col_k2:
            st.metric("N. commesse aperte / in corso", int(n_commesse_aperte))
        with col_k3:
            st.metric("Utilizzo ore vs previste", f"{utilizzo_ore:.1f} %")

        st.markdown("---")
        st.subheader("📦 Avanzamento commesse")

        # Avanzamento per commessa: ore_consumate vs ore_previste
        df_comm_all["Avanzamento_ore_%"] = df_comm_all.apply(
            lambda r: (r["ore_consumate"] / r["ore_previste"] * 100.0) if r["ore_previste"] > 0 else 0.0,
            axis=1,
        )

        st.dataframe(
            df_comm_all[
                ["cod_commessa", "stato_commessa", "ore_previste", "ore_consumate", "Avanzamento_ore_%"]
            ].rename(
                columns={
                    "cod_commessa": "Commessa",
                    "stato_commessa": "Stato",
                    "ore_previste": "Ore previste",
                    "ore_consumate": "Ore consumate",
                    "Avanzamento_ore_%": "Avanzamento ore (%)",
                }
            )
        )

        fig_comm_av = px.bar(
            df_comm_all,
            x="cod_commessa",
            y="Avanzamento_ore_%",
            color="stato_commessa",
            title="Avanzamento ore per commessa",
            labels={
                "cod_commessa": "Commessa",
                "Avanzamento_ore_%": "Avanzamento ore (%)",
                "stato_commessa": "Stato",
            },
            range_y=[0, 150],
        )
        st.plotly_chart(fig_comm_av, use_container_width=True)

        st.caption("Valori >100% indicano commesse che hanno superato le ore previste.")

    # =========================
    # SEZIONE EDIT / DELETE (SOLO ADMIN)
    # =========================
    if role != "admin":
        return  # niente edit/delete per utenti normali

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina dati Operations (solo admin)")

    # ---- 1) Commessa ----
    st.markdown("#### Commessa")

    if not commesse_all:
        st.info("Nessuna commessa da modificare/eliminare.")
    else:
        comm_ids = [c.commessa_id for c in commesse_all]
        comm_id_sel = st.selectbox("ID commessa", comm_ids, key="op_comm_sel")

        with get_session() as session:
            comm_obj = session.get(ProjectCommessa, comm_id_sel)

        if comm_obj:
            with st.form(f"edit_commessa_{comm_id_sel}"):
                col1, col2 = st.columns(2)
                with col1:
                    cod_commessa_e = st.text_input("Codice commessa", comm_obj.cod_commessa or "")
                    descrizione_cliente_e = st.text_input("Descrizione / Cliente", comm_obj.descrizione_cliente or "")
                    stato_commessa_e = st.selectbox(
                        "Stato commessa",
                        ["aperta", "in corso", "chiusa"],
                        index=["aperta", "in corso", "chiusa"].index(comm_obj.stato_commessa or "aperta"),
                    )
                    data_inizio_e = st.date_input("Data inizio", value=comm_obj.data_inizio or date.today())
                with col2:
                    data_fine_prevista_e = st.date_input(
                        "Data fine prevista",
                        value=comm_obj.data_fine_prevista or date.today(),
                    )
                    ore_previste_e = st.number_input(
                        "Ore previste",
                        min_value=0.0,
                        step=1.0,
                        value=float(comm_obj.ore_previste or 0.0),
                    )
                    costo_previsto_e = st.number_input(
                        "Costo previsto (€)",
                        min_value=0.0,
                        step=100.0,
                        value=float(comm_obj.costo_previsto or 0.0),
                    )

                colb1, colb2 = st.columns(2)
                with colb1:
                    update_comm = st.form_submit_button("💾 Aggiorna commessa")
                with colb2:
                    delete_comm = st.form_submit_button("🗑 Elimina commessa")

            if update_comm:
                with get_session() as session:
                    obj = session.get(ProjectCommessa, comm_id_sel)
                    if obj:
                        obj.cod_commessa = cod_commessa_e.strip()
                        obj.descrizione_cliente = descrizione_cliente_e.strip() or None
                        obj.stato_commessa = stato_commessa_e
                        obj.data_inizio = data_inizio_e
                        obj.data_fine_prevista = data_fine_prevista_e
                        obj.ore_previste = ore_previste_e
                        obj.costo_previsto = costo_previsto_e
                        session.add(obj)
                        session.commit()
                st.success("Commessa aggiornata.")
                st.rerun()

            if delete_comm:
                with get_session() as session:
                    # opzionale: eliminare anche fasi e timeentry collegati
                    session.exec(delete(TimeEntry).where(TimeEntry.commessa_id == comm_id_sel))
                    session.exec(delete(TaskFase).where(TaskFase.commessa_id == comm_id_sel))
                    obj = session.get(ProjectCommessa, comm_id_sel)
                    if obj:
                        session.delete(obj)
                    session.commit()
                st.success("Commessa e relative fasi/timesheet eliminati.")
                st.rerun()

    st.markdown("---")

    # ---- 2) Fase ----
    st.markdown("#### Fase / Task")

    if not fasi_all:
        st.info("Nessuna fase da modificare/eliminare.")
    else:
        fase_ids = [f.fase_id for f in fasi_all]
        fase_id_sel = st.selectbox("ID fase", fase_ids, key="op_fase_sel")

        with get_session() as session:
            fase_obj = session.get(TaskFase, fase_id_sel)

        if fase_obj:
            with st.form(f"edit_fase_{fase_id_sel}"):
                col1, col2 = st.columns(2)
                with col1:
                    nome_fase_e = st.text_input("Nome fase / task", fase_obj.nome_fase or "")
                    stato_fase_e = st.selectbox(
                        "Stato fase",
                        ["aperta", "in corso", "chiusa"],
                        index=["aperta", "in corso", "chiusa"].index(fase_obj.stato_fase or "aperta"),
                    )
                    data_inizio_fase_e = st.date_input(
                        "Data inizio fase",
                        value=fase_obj.data_inizio or date.today(),
                    )
                with col2:
                    data_fine_prevista_fase_e = st.date_input(
                        "Data fine prevista fase",
                        value=fase_obj.data_fine_prevista or date.today(),
                    )
                    ore_previste_fase_e = st.number_input(
                        "Ore previste fase",
                        min_value=0.0,
                        step=1.0,
                        value=float(fase_obj.ore_previste or 0.0),
                    )
                    risorsa_responsabile_e = st.text_input(
                        "Risorsa responsabile",
                        fase_obj.risorsa_responsabile or "",
                    )

                colb1, colb2 = st.columns(2)
                with colb1:
                    update_fase = st.form_submit_button("💾 Aggiorna fase")
                with colb2:
                    delete_fase = st.form_submit_button("🗑 Elimina fase")

            if update_fase:
                with get_session() as session:
                    obj = session.get(TaskFase, fase_id_sel)
                    if obj:
                        obj.nome_fase = nome_fase_e.strip()
                        obj.stato_fase = stato_fase_e
                        obj.data_inizio = data_inizio_fase_e
                        obj.data_fine_prevista = data_fine_prevista_fase_e
                        obj.ore_previste = ore_previste_fase_e
                        obj.risorsa_responsabile = risorsa_responsabile_e.strip() or None
                        session.add(obj)
                        session.commit()
                st.success("Fase aggiornata.")
                st.rerun()

            if delete_fase:
                with get_session() as session:
                    # elimina anche timeentry relativi alla fase
                    session.exec(delete(TimeEntry).where(TimeEntry.fase_id == fase_id_sel))
                    obj = session.get(TaskFase, fase_id_sel)
                    if obj:
                        session.delete(obj)
                    session.commit()
                st.success("Fase e relative righe timesheet eliminate.")
                st.rerun()

    st.markdown("---")

    # ---- 3) Timesheet ----
    st.markdown("#### Righe timesheet")

    if not times_all:
        st.info("Nessuna riga timesheet da eliminare.")
    else:
        time_ids = [t.entry_id for t in times_all]
        time_id_sel = st.selectbox("ID riga timesheet", time_ids, key="op_time_sel")

        if st.button("🗑 Elimina riga timesheet selezionata"):
            with get_session() as session:
                te = session.get(TimeEntry, time_id_sel)
                if te:
                    comm_id = te.commessa_id
                    fase_id = te.fase_id
                    session.delete(te)
                    session.commit()

                    # ricalcola ore_consumate fase
                    total_ore_fase = session.exec(
                        select(TimeEntry.ore).where(TimeEntry.fase_id == fase_id)
                    ).all()
                    somma_fase = sum(total_ore_fase)
                    fase_obj2 = session.get(TaskFase, fase_id)
                    if fase_obj2:
                        fase_obj2.ore_consumate = somma_fase

                    # ricalcola ore_consumate commessa
                    total_ore_comm = session.exec(
                        select(TimeEntry.ore).where(TimeEntry.commessa_id == comm_id)
                    ).all()
                    somma_comm = sum(total_ore_comm)
                    comm_obj2 = session.get(ProjectCommessa, comm_id)
                    if comm_obj2:
                        comm_obj2.ore_consumate = somma_comm

                    session.commit()
            st.success("Riga timesheet eliminata e ore ricalcolate.")
            st.rerun()


def page_people_departments():
    st.title("👥 People & Reparti (SQLite)")

    # =========================
    # FORM INSERIMENTO REPARTO
    # =========================
    st.subheader("🏢 Inserisci nuovo reparto")

    with st.form("new_department"):
        col1, col2 = st.columns(2)
        with col1:
            nome_reparto = st.text_input("Nome reparto", "")
            descrizione_reparto = st.text_input("Descrizione", "")
        with col2:
            responsabile_reparto = st.text_input("Responsabile", "")

        submitted_dept = st.form_submit_button("Salva reparto")

    if submitted_dept:
        if not nome_reparto.strip():
            st.warning("Il nome reparto è obbligatorio.")
        else:
            with get_session() as session:
                new_dept = Department(
                    nome_reparto=nome_reparto.strip(),
                    descrizione=descrizione_reparto.strip() or None,
                    responsabile=responsabile_reparto.strip() or None,
                )
                session.add(new_dept)
                session.commit()
                session.refresh(new_dept)
            st.success(f"Reparto creato con ID {new_dept.department_id}")
            st.rerun()

    st.markdown("---")

    # =========================
    # FORM INSERIMENTO PERSONA
    # =========================
    st.subheader("👤 Inserisci nuova persona")

    with get_session() as session:
        departments = session.exec(select(Department)).all()

    if not departments:
        st.info("Prima crea almeno un reparto con il form sopra.")
    else:
        df_dept = pd.DataFrame([d.__dict__ for d in departments])
        df_dept["label"] = df_dept["department_id"].astype(str) + " - " + df_dept["nome_reparto"]

        with st.form("new_employee"):
            col1, col2 = st.columns(2)
            with col1:
                dept_label = st.selectbox("Reparto", df_dept["label"].tolist())
                nome = st.text_input("Nome", "")
                cognome = st.text_input("Cognome", "")
                ruolo = st.text_input("Ruolo", "")
            with col2:
                data_assunzione = st.date_input("Data assunzione", value=date.today())
                stato = st.selectbox(
                    "Stato",
                    ["attivo", "non attivo"],
                    index=0,
                )

            submitted_emp = st.form_submit_button("Salva persona")

        if submitted_emp:
            if not nome.strip() or not cognome.strip():
                st.warning("Nome e cognome sono obbligatori.")
            else:
                dept_id_sel = int(dept_label.split(" - ")[0])
                with get_session() as session:
                    new_emp = Employee(
                        nome=nome.strip(),
                        cognome=cognome.strip(),
                        ruolo=ruolo.strip() or None,
                        department_id=dept_id_sel,
                        data_assunzione=data_assunzione,
                        stato=stato,
                    )
                    session.add(new_emp)
                    session.commit()
                    session.refresh(new_emp)
                st.success(f"Persona creata con ID {new_emp.employee_id}")
                st.rerun()

    st.markdown("---")

    # =========================
    # VISTA REPARTI E PERSONE + KPI
    # =========================
    st.subheader("📂 Elenco reparti e persone")

    with get_session() as session:
        departments_all = session.exec(select(Department)).all()
        employees_all = session.exec(select(Employee)).all()
        kpi_dept = session.exec(select(KpiDepartmentTimeseries)).all()
        kpi_emp = session.exec(select(KpiEmployeeTimeseries)).all()

    df_dept_all = pd.DataFrame([d.__dict__ for d in departments_all]) if departments_all else pd.DataFrame()
    df_emp_all = pd.DataFrame([e.__dict__ for e in employees_all]) if employees_all else pd.DataFrame()
    df_kpi_dept = pd.DataFrame([k.__dict__ for k in kpi_dept]) if kpi_dept else pd.DataFrame()
    df_kpi_emp = pd.DataFrame([k.__dict__ for k in kpi_emp]) if kpi_emp else pd.DataFrame()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Reparti")
        if df_dept_all.empty:
            st.info("Nessun reparto registrato.")
        else:
            st.dataframe(df_dept_all)

    with col2:
        st.markdown("#### Persone")
        if df_emp_all.empty:
            st.info("Nessuna persona registrata.")
        else:
            st.dataframe(df_emp_all)

    # =========================
    # KPI PEOPLE & ORE (da timesheet)
    # =========================
    with get_session() as session:
        time_all = session.exec(select(TimeEntry)).all()

    st.markdown("---")
    st.subheader("📊 KPI People (tutte le persone)")
    ...
    # (tutto il blocco KPI + grafico ore per reparto)
    ...
    # =========================
    # FILTRO PERIODO KPI MANUALI (reparto/persona)
    # =========================
    st.markdown("---")
    st.subheader("📅 Filtro periodo KPI (manuali)")

    col_k1, col_k2 = st.columns(2)
    with col_k1:
        kpi_da = st.date_input("Da data KPI", value=None, key="kpi_da")
    with col_k2:
        kpi_a = st.date_input("A data KPI", value=None, key="kpi_a")
    # =========================
    # INSERIMENTO KPI REPARTO (DATI REALI)
    # =========================
    st.markdown("### ➕ Aggiungi KPI reparto (dati reali)")

    if not df_dept_all.empty:
        df_dept_all["label"] = df_dept_all["department_id"].astype(str) + " - " + df_dept_all["nome_reparto"]
        with st.form("new_kpi_dept"):
            col1, col2 = st.columns(2)
            with col1:
                dept_label_k = st.selectbox("Reparto", df_dept_all["label"].tolist())
                data_kpi_dept = st.date_input("Data KPI reparto", value=date.today())
                kpi_name_dept = st.text_input("Nome KPI reparto", "Produttività reparto (%)")
            with col2:
                valore_dept = st.number_input("Valore KPI reparto", step=0.1)
                target_dept = st.number_input("Target KPI reparto", step=0.1, value=100.0)
                unita_dept = st.text_input("Unità KPI reparto", "percentuale")

            submitted_kpi_dept = st.form_submit_button("Salva KPI reparto")

        if submitted_kpi_dept:
            dept_id_sel = int(dept_label_k.split(" - ")[0])
            with get_session() as session:
                new_kpi_d = KpiDepartmentTimeseries(
                    department_id=dept_id_sel,
                    data=data_kpi_dept,
                    kpi_name=kpi_name_dept.strip(),
                    valore=float(valore_dept),
                    target=float(target_dept),
                    unita=unita_dept.strip() or "",
                )
                session.add(new_kpi_d)
                session.commit()
            st.success("KPI reparto salvato.")
            st.rerun()
    else:
        st.info("Prima crea almeno un reparto per registrare KPI reparto.")

    st.markdown("---")
    st.markdown("### ➕ Aggiungi KPI persona (dati reali)")

    if not df_emp_all.empty:
        df_emp_all["nome_completo"] = df_emp_all["employee_id"].astype(str) + " - " + df_emp_all["nome"] + " " + df_emp_all["cognome"]
        with st.form("new_kpi_emp"):
            col1, col2 = st.columns(2)
            with col1:
                emp_label_k = st.selectbox("Persona", df_emp_all["nome_completo"].tolist())
                data_kpi_emp = st.date_input("Data KPI persona", value=date.today())
                kpi_name_emp = st.text_input("Nome KPI persona", "Ore produttive / giorno")
            with col2:
                valore_emp = st.number_input("Valore KPI persona", step=0.1)
                target_emp = st.number_input("Target KPI persona", step=0.1, value=7.0)
                unita_emp = st.text_input("Unità KPI persona", "ore")

            submitted_kpi_emp = st.form_submit_button("Salva KPI persona")

        if submitted_kpi_emp:
            emp_id_sel = int(emp_label_k.split(" - ")[0])
            with get_session() as session:
                new_kpi_e = KpiEmployeeTimeseries(
                    employee_id=emp_id_sel,
                    data=data_kpi_emp,
                    kpi_name=kpi_name_emp.strip(),
                    valore=float(valore_emp),
                    target=float(target_emp),
                    unita=unita_emp.strip() or "",
                )
                session.add(new_kpi_e)
                session.commit()
            st.success("KPI persona salvato.")
            st.rerun()
    else:
        st.info("Prima crea almeno una persona per registrare KPI persona.")

    # Filtro e grafici KPI reparto
    if not df_kpi_dept.empty:
        df_kpi_dept["data"] = pd.to_datetime(df_kpi_dept["data"], errors="coerce")

        if kpi_da:
            df_kpi_dept = df_kpi_dept[df_kpi_dept["data"] >= pd.to_datetime(kpi_da)]
        if kpi_a:
            df_kpi_dept = df_kpi_dept[df_kpi_dept["data"] <= pd.to_datetime(kpi_a)]

        dept_opt = ["Tutti"]
        if not df_dept_all.empty and "nome_reparto" in df_dept_all.columns:
            dept_opt += df_dept_all["nome_reparto"].dropna().unique().tolist()
        sel_dept = st.selectbox("Reparto KPI", dept_opt)

        df = df_kpi_dept.copy()
        if sel_dept != "Tutti" and not df_dept_all.empty:
            row = df_dept_all[df_dept_all["nome_reparto"] == sel_dept]
            if not row.empty:
                dept_id = row.iloc[0]["department_id"]
                df = df[df["department_id"] == dept_id]

        if {"data", "kpi_name", "valore", "target"}.issubset(df.columns):
            kpi_list = ["Tutti"] + sorted(df["kpi_name"].dropna().unique().tolist())
            sel_kpi = st.selectbox("Seleziona KPI reparto", kpi_list)
            if sel_kpi != "Tutti":
                df = df[df["kpi_name"] == sel_kpi]
            df = df.sort_values("data")
            st.line_chart(df.set_index("data")[["valore", "target"]])
            st.dataframe(df)
        else:
            st.info("Dati KPI reparto non completi.")
    else:
        st.info("Nessun KPI reparto registrato.")

    st.markdown("---")
    st.subheader("📈 KPI per persona (time series)")

    if not df_kpi_emp.empty:
        df_kpi_emp["data"] = pd.to_datetime(df_kpi_emp["data"], errors="coerce")

        if kpi_da:
            df_kpi_emp = df_kpi_emp[df_kpi_emp["data"] >= pd.to_datetime(kpi_da)]
        if kpi_a:
            df_kpi_emp = df_kpi_emp[df_kpi_emp["data"] <= pd.to_datetime(kpi_a)]

        if not df_emp_all.empty and {"nome", "cognome"}.issubset(df_emp_all.columns):
            df_emp_all["nome_completo"] = df_emp_all["nome"] + " " + df_emp_all["cognome"]
            emp_opt = ["Tutti"] + df_emp_all["nome_completo"].dropna().unique().tolist()
        else:
            emp_opt = ["Tutti"]

        sel_emp = st.selectbox("Persona KPI", emp_opt)

        df_e = df_kpi_emp.copy()
        if sel_emp != "Tutti" and not df_emp_all.empty and "nome_completo" in df_emp_all.columns:
            row = df_emp_all[df_emp_all["nome_completo"] == sel_emp]
            if not row.empty:
                emp_id = row.iloc[0]["employee_id"]
                df_e = df_e[df_e["employee_id"] == emp_id]

        if {"data", "kpi_name", "valore", "target"}.issubset(df_e.columns):
            kpi_list_e = ["Tutti"] + sorted(df_e["kpi_name"].dropna().unique().tolist())
            sel_kpi_e = st.selectbox("Seleziona KPI persona", kpi_list_e)
            if sel_kpi_e != "Tutti":
                df_e = df_e[df_e["kpi_name"] == sel_kpi_e]
            df_e = df_e.sort_values("data")
            st.line_chart(df_e.set_index("data")[["valore", "target"]])
            st.dataframe(df_e)
        else:
            st.info("Dati KPI persona non completi.")
    else:
        st.info("Nessun KPI persona registrato.")

    # =========================
    # SEZIONE EDIT / DELETE (SOLO ADMIN)
    # =========================
    role = st.session_state.get("role", "user")
    if role != "admin":
        return

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina dati People (solo admin)")

    # ---- Reparto ----
    st.markdown("#### Reparto")
    if df_dept_all.empty:
        st.info("Nessun reparto da modificare/eliminare.")
    else:
        dept_ids = df_dept_all["department_id"].tolist()
        dept_id_sel = st.selectbox("ID reparto", dept_ids, key="people_dept_sel")

        with get_session() as session:
            dept_obj = session.get(Department, dept_id_sel)

        if dept_obj:
            with st.form(f"edit_dept_{dept_id_sel}"):
                col1, col2 = st.columns(2)
                with col1:
                    nome_reparto_e = st.text_input("Nome reparto", dept_obj.nome_reparto or "")
                    descrizione_reparto_e = st.text_input("Descrizione", dept_obj.descrizione or "")
                with col2:
                    responsabile_reparto_e = st.text_input("Responsabile", dept_obj.responsabile or "")

                colb1, colb2 = st.columns(2)
                with colb1:
                    update_dept = st.form_submit_button("💾 Aggiorna reparto")
                with colb2:
                    delete_dept = st.form_submit_button("🗑 Elimina reparto")

            if update_dept:
                with get_session() as session:
                    obj = session.get(Department, dept_id_sel)
                    if obj:
                        obj.nome_reparto = nome_reparto_e.strip()
                        obj.descrizione = descrizione_reparto_e.strip() or None
                        obj.responsabile = responsabile_reparto_e.strip() or None
                        session.add(obj)
                        session.commit()
                st.success("Reparto aggiornato.")
                st.rerun()

            if delete_dept:
                with get_session() as session:
                    obj = session.get(Department, dept_id_sel)
                    if obj:
                        session.delete(obj)
                        session.commit()
                st.success("Reparto eliminato.")
                st.rerun()

    st.markdown("---")

    # ---- Persona ----
    st.markdown("#### Persona")
    if df_emp_all.empty:
        st.info("Nessuna persona da modificare/eliminare.")
    else:
        emp_ids = df_emp_all["employee_id"].tolist()
        emp_id_sel = st.selectbox("ID persona", emp_ids, key="people_emp_sel")

        with get_session() as session:
            emp_obj = session.get(Employee, emp_id_sel)

        if emp_obj:
            with st.form(f"edit_emp_{emp_id_sel}"):
                col1, col2 = st.columns(2)
                with col1:
                    nome_e = st.text_input("Nome", emp_obj.nome or "")
                    cognome_e = st.text_input("Cognome", emp_obj.cognome or "")
                    ruolo_e = st.text_input("Ruolo", emp_obj.ruolo or "")
                with col2:
                    data_assunzione_e = st.date_input(
                        "Data assunzione",
                        value=emp_obj.data_assunzione or date.today(),
                    )
                    stato_e = st.selectbox(
                        "Stato",
                        ["attivo", "non attivo"],
                        index=["attivo", "non attivo"].index(emp_obj.stato or "attivo"),
                    )

                colc1, colc2 = st.columns(2)
                with colc1:
                    update_emp = st.form_submit_button("💾 Aggiorna persona")
                with colc2:
                    delete_emp = st.form_submit_button("🗑 Elimina persona")

            if update_emp:
                with get_session() as session:
                    obj = session.get(Employee, emp_id_sel)
                    if obj:
                        obj.nome = nome_e.strip()
                        obj.cognome = cognome_e.strip()
                        obj.ruolo = ruolo_e.strip() or None
                        obj.data_assunzione = data_assunzione_e
                        obj.stato = stato_e
                        session.add(obj)
                        session.commit()
                st.success("Persona aggiornata.")
                st.rerun()

            if delete_emp:
                with get_session() as session:
                    obj = session.get(Employee, emp_id_sel)
                    if obj:
                        session.delete(obj)
                        session.commit()
                st.success("Persona eliminata.")
                st.rerun()

def page_capacity_people():
    st.title("👥 Capacità people vs carico (da timesheet)")

    # ---------- Filtro periodo ----------
    st.subheader("Filtro periodo")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        data_da = st.date_input("Da data", value=date(date.today().year, 1, 1), key="cap_da")
    with col_f2:
        data_a = st.date_input("A data", value=date.today(), key="cap_a")

    # ---------- Parametri capacità standard ----------
    st.subheader("Parametri capacità standard")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        ore_giorno = st.number_input(
            "Ore/giorno",
            min_value=1.0,
            max_value=12.0,
            value=8.0,
            step=0.5,
            key="cap_ore_giorno",
        )
    with col_c2:
        giorni_settimana = st.number_input(
            "Giorni/settimana",
            min_value=1,
            max_value=7,
            value=5,
            step=1,
            key="cap_giorni_sett",
        )

    # ---------- Carico timesheet ----------
    with get_session() as session:
        entries = session.exec(select(TimeEntry)).all()
        employees = session.exec(select(Employee)).all()

    if not entries:
        st.info("Nessuna riga timesheet registrata.")
        return

    df_te = pd.DataFrame([e.__dict__ for e in entries])
    df_te["data_lavoro"] = pd.to_datetime(df_te["data_lavoro"], errors="coerce")
    df_te = df_te.dropna(subset=["data_lavoro"])

    df_te = df_te[
        (df_te["data_lavoro"] >= pd.to_datetime(data_da)) &
        (df_te["data_lavoro"] <= pd.to_datetime(data_a))
    ]

    if df_te.empty:
        st.info("Nessuna riga timesheet nel periodo selezionato.")
        return

    # ---------- Mapping operatore -> employee / reparto ----------
    df_emp = pd.DataFrame([e.__dict__ for e in (employees or [])])
    if not df_emp.empty:
        df_emp["nome_completo"] = df_emp["nome"] + " " + df_emp["cognome"]
        df_te = df_te.merge(
            df_emp[["employee_id", "department_id", "nome_completo"]],
            how="left",
            left_on="operatore",
            right_on="nome_completo",
        )
    else:
        df_te["employee_id"] = None
        df_te["department_id"] = None

    # ---------- Capacità teorica periodo ----------
    giorni = pd.date_range(start=data_da, end=data_a, freq="D")
    # 0 = lunedì ... 6 = domenica; prendiamo solo i primi 'giorni_settimana' valori
    giorni_lav = [g for g in giorni if g.weekday() < giorni_settimana]
    giorni_lav_count = len(giorni_lav)
    capacita_teorica = giorni_lav_count * ore_giorno

    # ---------- Aggregazione per persona ----------
    agg = (
        df_te.groupby("operatore")["ore"]
        .sum()
        .reset_index()
        .rename(columns={"ore": "Ore_registrate"})
    )
    agg["Capacita_teorica"] = capacita_teorica
    agg["Utilization_%"] = agg["Ore_registrate"] / agg["Capacita_teorica"] * 100.0

    st.subheader("Saturazione per persona (periodo)")
    st.dataframe(
        agg.style.format(
            {
                "Ore_registrate": "{:,.2f}",
                "Capacita_teorica": "{:,.2f}",
                "Utilization_%": "{:,.1f}",
            }
        )
    )

    # ---------- Grafico utilizzo ----------
    fig = px.bar(
        agg,
        x="operatore",
        y="Utilization_%",
        title="Utilization % per persona",
        labels={"operatore": "Operatore", "Utilization_%": "Utilization (%)"},
    )
    st.plotly_chart(fig, use_container_width=True)

# =========================
# PAGINE FINANZA AVANZATE
# =========================

def page_finance_payments():
    st.title("Incassi / Scadenze clienti")

    # Carico fatture e calcolo pagato/da incassare mentre la sessione è aperta
    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()
        clients = {c.client_id: c.ragione_sociale for c in session.exec(select(Client)).all()}

        data_rows = []
        for inv in invoices:
            amount_paid = inv.amount_paid      # usa la property finché la sessione è attiva
            amount_open = inv.amount_open
            data_rows.append(
                {
                    "ID": inv.invoice_id,
                    "Numero": inv.num_fattura,
                    "Cliente": clients.get(inv.client_id, inv.client_id),
                    "Data": inv.data_fattura,
                    "Scadenza": inv.data_scadenza,
                    "Totale": inv.importo_totale,
                    "Pagato": amount_paid,
                    "Da incassare": amount_open,
                    "Stato pagamento": inv.stato_pagamento,
                }
            )

    if not data_rows:
        st.info("Nessuna fattura presente.")
        return

    df = pd.DataFrame(data_rows)

    st.subheader("Stato incassi")
    st.dataframe(df)

    st.subheader("Registra un pagamento")
    invoice_ids = [row["ID"] for row in data_rows]
    invoice_id_sel = st.selectbox("Fattura", invoice_ids)
    payment_date = st.date_input("Data pagamento", value=date.today())
    amount = st.number_input("Importo incassato", min_value=0.0, step=10.0)
    method = st.selectbox("Metodo", ["bonifico", "contanti", "carta", "altro"])
    note = st.text_input("Note", "")

    if st.button("💰 Registra pagamento"):
        with get_session() as session:
            pay = Payment(
                invoice_id=invoice_id_sel,
                payment_date=payment_date,
                amount=amount,
                method=method,
                note=note or None,
            )
            session.add(pay)

            inv = session.get(Invoice, invoice_id_sel)
            session.refresh(inv)
            if inv.amount_open <= 0:
                inv.stato_pagamento = "incassata"
                inv.data_incasso = payment_date
                session.add(inv)

            session.commit()
        st.success("Pagamento registrato. Ricarica la pagina per aggiornare i totali.")

def page_invoice_transmission():
    st.title("Fatture → Agenzia Entrate (tracciamento manuale)")

    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()
        clients = {c.client_id: c.ragione_sociale for c in session.exec(select(Client)).all()}
        transmissions = session.exec(select(InvoiceTransmission)).all()
        trans_by_inv = {t.invoice_id: t for t in transmissions}

    if not invoices:
        st.info("Nessuna fattura presente.")
        return

    data_rows = []
    for inv in invoices:
        t = trans_by_inv.get(inv.invoice_id)
        data_rows.append({
            "ID": inv.invoice_id,
            "Numero": inv.num_fattura,
            "Cliente": clients.get(inv.client_id, inv.client_id),
            "Data": inv.data_fattura,
            "Totale": inv.importo_totale,
            "Stato SdI": t.sdi_status if t else "non inviato",
            "Data upload": t.upload_date if t else None,
        })
    df = pd.DataFrame(data_rows)

    st.subheader("Stato trasmissione fatture")
    st.dataframe(df)

    st.subheader("Aggiorna stato trasmissione")
    invoice_ids = [inv.invoice_id for inv in invoices]
    invoice_id_sel = st.selectbox("Fattura", invoice_ids)
    xml_name = st.text_input("Nome file XML caricato sul portale", "")
    upload_date = st.date_input("Data upload su portale AE", value=date.today())
    sdi_status = st.selectbox("Stato SdI", ["uploaded", "sent", "delivered", "rejected"])
    sdi_message = st.text_area("Messaggio / errore SdI", "")
    sdi_protocol = st.text_input("Protocollo AE (se presente)", "")

    if st.button("💾 Salva/aggiorna stato"):
        with get_session() as session:
            t = session.exec(
                select(InvoiceTransmission).where(InvoiceTransmission.invoice_id == invoice_id_sel)
            ).first()
            if not t:
                t = InvoiceTransmission(invoice_id=invoice_id_sel)
            t.xml_file_name = xml_name
            t.upload_date = upload_date
            t.sdi_status = sdi_status
            t.sdi_message = sdi_message or None
            t.sdi_protocol = sdi_protocol or None
            session.add(t)
            session.commit()
        st.success("Stato trasmissione aggiornato.")


def page_tax_inps():
    st.title("Fisco & INPS")

    current_year = date.today().year

    # =========================
    # CONFIGURAZIONE FISCALE
    # =========================
    with get_session() as session:
        cfg = session.exec(select(TaxConfig).where(TaxConfig.year == current_year)).first()
        fatture = session.exec(
            select(Invoice).where(
                Invoice.data_fattura.between(date(current_year, 1, 1), date(current_year, 12, 31))
            )
        ).all()

    fatturato = sum(inv.importo_totale or 0 for inv in (fatture or []))

    st.subheader("Configurazione fiscale anno in corso")
    regime_options = ["forfettario", "ordinario"]
    default_regime_idx = 0 if not cfg else regime_options.index(cfg.regime)
    regime = st.selectbox("Regime", regime_options, index=default_regime_idx)
    aliquota_imposta = st.number_input(
        "Aliquota imposta (es. 0.15)",
        value=cfg.aliquota_imposta if cfg else 0.15,
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    )
    aliquota_inps = st.number_input(
        "Aliquota INPS Gestione Separata (es. 0.26)",
        value=cfg.aliquota_inps if cfg else 0.26,
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    )
    redditivita = st.number_input(
        "Redditività forfettario (es. 0.78)",
        value=(cfg.redditivita_forfettario if cfg and cfg.redditivita_forfettario is not None else 0.78),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    )

    if st.button("💾 Salva configurazione fiscale"):
        with get_session() as session:
            cfg_db = session.exec(select(TaxConfig).where(TaxConfig.year == current_year)).first()
            if cfg_db:
                cfg_db.regime = regime
                cfg_db.aliquota_imposta = aliquota_imposta
                cfg_db.aliquota_inps = aliquota_inps
                cfg_db.redditivita_forfettario = redditivita
            else:
                cfg_db = TaxConfig(
                    year=current_year,
                    regime=regime,
                    aliquota_imposta=aliquota_imposta,
                    aliquota_inps=aliquota_inps,
                    redditivita_forfettario=redditivita,
                )
            session.add(cfg_db)
            session.commit()
        st.success("Configurazione fiscale salvata.")

    # =========================
    # STIMA IMPOSTE & CONTRIBUTI
    # =========================
    st.subheader("Stima imposte e contributi anno in corso")
    st.write(f"Fatturato {current_year}: {fatturato:.2f} €")
    if fatture:
        if regime == "forfettario":
            base_imponibile = fatturato * redditivita
        else:
            base_imponibile = fatturato

        imposta = base_imponibile * aliquota_imposta
        inps = base_imponibile * aliquota_inps
        netto = fatturato - imposta - inps  # nuovo calcolo

        st.write(f"Base imponibile stimata: {base_imponibile:.2f} €")
        st.write(f"Imposta stimata (IRPEF/Imposta sostitutiva): {imposta:.2f} €")
        st.write(f"Contributi INPS Gestione Separata stimati: {inps:.2f} €")
        st.write(f"**Netto stimato dopo imposte e contributi:** {netto:.2f} €")
    else:
        st.info("Nessuna fattura emessa nell'anno corrente.")

    st.markdown("---")

    # =========================
    # SCADENZE FISCALI & INPS (TaxDeadline)
    # =========================
    st.subheader(f"Scadenze fiscali & INPS {current_year}")

    with get_session() as session:
        deadlines = session.exec(
            select(TaxDeadline).where(TaxDeadline.year == current_year)
        ).all()

    df_dead = pd.DataFrame(
        [
            {
                "ID": d.deadline_id,
                "Data scadenza": d.due_date,
                "Tipo": d.type,
                "Importo stimato": d.estimated_amount,
                "Importo pagato": d.amount_paid,
                "Data pagamento": d.payment_date,
                "Stato": d.status,
                "Note": d.note,
            }
            for d in (deadlines or [])
        ]
    )

    if df_dead.empty:
        st.info("Nessuna scadenza registrata per l'anno corrente.")
    else:
        st.dataframe(df_dead)

    st.markdown("### ➕ Aggiungi / modifica scadenza")

    # Tipologie suggerite: puoi aggiungerne altre a piacere
    tipo_opzioni = [
        "Saldo imposta",
        "Acconto 1 imposta",
        "Acconto 2 imposta",
        "Saldo INPS Gestione Separata",
        "Acconto 1 INPS Gestione Separata",
        "Acconto 2 INPS Gestione Separata",
        "Altro",
    ]

    with st.form("tax_deadline_form"):
        col1, col2 = st.columns(2)
        with col1:
            # Se vuoi modificare una scadenza esistente, seleziona ID; 0 = nuova
            existing_ids = [0] + [d.deadline_id for d in (deadlines or [])]
            selected_id = st.selectbox("ID scadenza (0 = nuova)", existing_ids)
            type_sel = st.selectbox("Tipo scadenza", tipo_opzioni)
            due_date = st.date_input("Data scadenza", value=date(current_year, 6, 30))
        with col2:
            estimated_amount = st.number_input("Importo stimato", min_value=0.0, step=50.0)
            amount_paid = st.number_input("Importo pagato", min_value=0.0, step=50.0)
            payment_date = st.date_input("Data pagamento", value=date.today())
            status = st.selectbox("Stato", ["planned", "paid", "partial"])
        note = st.text_input("Note (opzionali)", "")

        submit_deadline = st.form_submit_button("💾 Salva scadenza")

    if submit_deadline:
        with get_session() as session:
            if selected_id == 0:
                # nuova scadenza
                d = TaxDeadline(
                    year=current_year,
                    due_date=due_date,
                    type=type_sel,
                    estimated_amount=estimated_amount,
                    amount_paid=amount_paid,
                    payment_date=payment_date if amount_paid > 0 else None,
                    status=status,
                    note=note or None,
                )
                session.add(d)
            else:
                # aggiorna esistente
                d = session.get(TaxDeadline, selected_id)
                if d:
                    d.year = current_year
                    d.due_date = due_date
                    d.type = type_sel
                    d.estimated_amount = estimated_amount
                    d.amount_paid = amount_paid
                    d.payment_date = payment_date if amount_paid > 0 else None
                    d.status = status
                    d.note = note or None
                    session.add(d)
            session.commit()
        st.success("Scadenza salvata.")
        st.rerun()


def page_expenses():
    st.title("💸 Costi & Fornitori")

    # ---------- CARICAMENTI BASE ----------
    with get_session() as session:
        vendors = session.exec(select(Vendor)).all()
        categories = session.exec(select(ExpenseCategory)).all()
        accounts = session.exec(select(Account)).all()
        commesse = session.exec(select(ProjectCommessa)).all()
        expenses = session.exec(select(Expense)).all()

    # ---------- 1) FORNITORI ----------
    st.subheader("🏢 Fornitori")

    with st.form("new_vendor"):
        col1, col2 = st.columns(2)
        with col1:
            ragione_sociale_v = st.text_input("Ragione sociale fornitore", "")
            email_v = st.text_input("Email", "")
            piva_v = st.text_input("Partita IVA", "")
            cod_fiscale_v = st.text_input("Codice fiscale", "")
        with col2:
            settore_v = st.text_input("Settore (software, viaggi, ecc.)", "")
            paese_v = st.text_input("Paese", "IT")
            indirizzo_v = st.text_input("Indirizzo", "")
            comune_v = st.text_input("Comune", "")
        col3, col4 = st.columns(2)
        with col3:
            cap_v = st.text_input("CAP", "")
            provincia_v = st.text_input("Provincia", "")
        with col4:
            note_v = st.text_input("Note", "")

        submitted_vendor = st.form_submit_button("Salva fornitore")

    if submitted_vendor:
        if not ragione_sociale_v.strip():
            st.warning("La ragione sociale è obbligatoria.")
        else:
            with get_session() as session:
                new_v = Vendor(
                    ragione_sociale=ragione_sociale_v.strip(),
                    email=email_v.strip() or None,
                    piva=piva_v.strip() or None,
                    cod_fiscale=cod_fiscale_v.strip() or None,
                    settore=settore_v.strip() or None,
                    paese=paese_v.strip() or None,
                    indirizzo=indirizzo_v.strip() or None,
                    comune=comune_v.strip() or None,
                    cap=cap_v.strip() or None,
                    provincia=provincia_v.strip() or None,
                    note=note_v.strip() or None,
                )
                session.add(new_v)
                session.commit()
            st.success("Fornitore salvato.")
            st.rerun()

    if vendors:
        df_v = pd.DataFrame([v.__dict__ for v in vendors])
        st.dataframe(df_v)
    else:
        st.info("Nessun fornitore registrato.")

    st.markdown("---")

def page_finance_dashboard():
    st.title("📊 Cruscotto Finanza")

    # Filtro periodo esistente
    st.subheader("Filtro periodo")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        data_da = st.date_input("Da data", value=date(date.today().year, 1, 1))
    with col_f2:
        data_a = st.date_input("A data", value=date.today())

    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()
        expenses = session.exec(select(Expense)).all()

    df_inv = pd.DataFrame([i.__dict__ for i in (invoices or [])])
    df_exp = pd.DataFrame([e.__dict__ for e in (expenses or [])])

    if df_inv.empty and df_exp.empty:
        st.info("Nessun dato di entrate o uscite nel sistema.")
        return

    # =========================
    # Conto Economico gestionale (annuale)
    # =========================
    st.markdown("---")
    anno_ce = st.number_input(
        "Anno Conto Economico gestionale",
        min_value=2020,
        max_value=2100,
        value=date.today().year,
        step=1,
    )

    df_ce = build_income_statement(anno_ce)

    st.subheader(f"Conto Economico gestionale {anno_ce}")
    st.dataframe(df_ce.style.format({"Importo": "{:,.2f}"}))

    # =========================
    # Conto Economico mensile (anno selezionato)
    # =========================
    st.subheader(f"Conto Economico mensile {anno_ce}")
    df_ce_mese = build_income_statement_monthly(anno_ce)

    st.dataframe(
        df_ce_mese.style.format(
            {
                "Proventi": "{:,.2f}",
                "Costi_spese": "{:,.2f}",
                "Costi_inps": "{:,.2f}",
                "Costi_tasse": "{:,.2f}",
                "Costi_totali": "{:,.2f}",
                "Risultato_netto": "{:,.2f}",
            }
        )
    )

    st.subheader("Risultato netto per mese")
    fig_ce_m = px.line(
        df_ce_mese,
        x="Mese",
        y="Risultato_netto",
        markers=True,
        title=f"Risultato netto mensile {anno_ce}",
    )
    st.plotly_chart(fig_ce_m, use_container_width=True)

    # =========================
    # Cashflow operativo mensile (anno selezionato)
    # =========================
    st.subheader(f"Cashflow operativo mensile {anno_ce}")

    df_cf_mese = build_cashflow_monthly(anno_ce)

    if df_cf_mese.empty:
        st.info("Nessun dato di cashflow disponibile per l'anno selezionato.")
    else:
        st.dataframe(
            df_cf_mese.style.format(
                {
                    "Incassi_clienti": "{:,.2f}",
                    "Uscite_spese": "{:,.2f}",
                    "Uscite_fisco_inps": "{:,.2f}",
                    "Net_cash_flow": "{:,.2f}",
                }
            )
        )

        st.subheader("Net cash flow per mese")
        fig_cf_m = px.bar(
            df_cf_mese,
            x="Mese",
            y="Net_cash_flow",
            title=f"Net cash flow mensile {anno_ce}",
        )
        st.plotly_chart(fig_cf_m, use_container_width=True)

    # =========================
    # Stato Patrimoniale minimale
    # =========================
    st.markdown("---")
    st.subheader("Stato Patrimoniale minimale")

    col_sp1, col_sp2 = st.columns(2)
    with col_sp1:
        data_sp = st.date_input(
            "Data di riferimento SP",
            value=date.today(),
            help="Data alla quale vuoi vedere la situazione crediti/debiti.",
        )

    with col_sp2:
        # saldo calcolato automaticamente da conti, incassi, spese, fisco/INPS
        saldo_cassa_auto = calcola_saldo_cassa(data_sp)
        saldo_cassa = st.number_input(
            "Saldo cassa/conti alla data",
            value=float(saldo_cassa_auto),
            step=100.0,
            help="Valore proposto calcolato dal gestionale; puoi modificarlo se necessario.",
        )

    df_sp = build_balance_sheet(data_sp, saldo_cassa)

    st.dataframe(df_sp.style.format({"Importo": "{:,.2f}"}))

    # ---------- ENTRATE (Fatture incassate) ----------
    if not df_inv.empty:
        df_inv["data_riferimento"] = df_inv["data_incasso"].fillna(df_inv["data_fattura"])
        df_inv["data_riferimento"] = pd.to_datetime(df_inv["data_riferimento"], errors="coerce")
        df_inv = df_inv.dropna(subset=["data_riferimento"])
        df_inv = df_inv[
            (df_inv["data_riferimento"] >= pd.to_datetime(data_da))
            & (df_inv["data_riferimento"] <= pd.to_datetime(data_a))
        ]
        df_inv["mese"] = df_inv["data_riferimento"].dt.to_period("M").dt.to_timestamp()
        entrate_mensili = (
            df_inv.groupby("mese")["importo_totale"].sum().rename("Entrate").reset_index()
        )
        totale_entrate = df_inv["importo_totale"].sum()
    else:
        entrate_mensili = pd.DataFrame(columns=["mese", "Entrate"])
        totale_entrate = 0.0

    # ---------- USCITE (Spese) ----------
    if not df_exp.empty:
        df_exp["data"] = pd.to_datetime(df_exp["data"], errors="coerce")
        df_exp = df_exp.dropna(subset=["data"])
        df_exp = df_exp[
            (df_exp["data"] >= pd.to_datetime(data_da))
            & (df_exp["data"] <= pd.to_datetime(data_a))
        ]
        df_exp["mese"] = df_exp["data"].dt.to_period("M").dt.to_timestamp()
        uscite_mensili = (
            df_exp.groupby("mese")["importo_totale"].sum().rename("Uscite").reset_index()
        )
        totale_uscite = df_exp["importo_totale"].sum()
    else:
        uscite_mensili = pd.DataFrame(columns=["mese", "Uscite"])
        totale_uscite = 0.0

    # Merge Entrate/Uscite
    df_kpi = pd.merge(
        entrate_mensili,
        uscite_mensili,
        on="mese",
        how="outer",
    ).fillna(0.0)
    df_kpi["Margine"] = df_kpi["Entrate"] - df_kpi["Uscite"]

    # ---------- KPI sintetici ----------
    st.subheader("KPI periodo selezionato")

    margine_val = totale_entrate - totale_uscite
    margine_perc = (margine_val / totale_entrate * 100.0) if totale_entrate > 0 else 0.0

    col_k1, col_k2, col_k3 = st.columns(3)
    with col_k1:
        st.metric("Entrate totali", f"€ {totale_entrate:,.0f}".replace(",", "."))
    with col_k2:
        st.metric("Uscite totali", f"€ {totale_uscite:,.0f}".replace(",", "."))
    with col_k3:
        st.metric(
            "Margine",
            f"€ {margine_val:,.0f} ({margine_perc:.1f}%)".replace(",", "."),
            delta=None,
        )

    # ---------- Grafici ----------
    if not df_kpi.empty:
        st.subheader("Entrate vs Uscite per mese")
        fig_eu = px.bar(
            df_kpi,
            x="mese",
            y=["Entrate", "Uscite"],
            barmode="group",
            title="Entrate vs Uscite per mese",
            labels={"value": "Importo (€)", "mese": "Mese", "variable": "Voce"},
        )
        fig_eu.update_layout(legend_title_text="")
        st.plotly_chart(fig_eu, use_container_width=True)

        st.subheader("Margine per mese")
        fig_m = px.line(
            df_kpi,
            x="mese",
            y="Margine",
            markers=True,
            title="Margine mensile",
        )
        st.plotly_chart(fig_m, use_container_width=True)

        st.dataframe(df_kpi)
    else:
        st.info("Nessun dato nel periodo selezionato.")

    # ---------- Breakdown entrate per cliente ----------
    st.markdown("---")
    st.subheader("🏆 Top clienti per entrate (periodo)")

    if not df_inv.empty:
        with get_session() as session:
            clients = {c.client_id: c.ragione_sociale for c in session.exec(select(Client)).all()}

        df_cli = df_inv.copy()
        df_cli["Cliente"] = df_cli["client_id"].map(clients).fillna(df_cli["client_id"])
        entrate_cliente = (
            df_cli.groupby("Cliente")["importo_totale"]
            .sum()
            .reset_index()
            .sort_values("importo_totale", ascending=False)
        )

        top_n = st.slider("Numero di clienti da mostrare", min_value=3, max_value=20, value=10, step=1)
        entrate_cliente_top = entrate_cliente.head(top_n)

        col_ec1, col_ec2 = st.columns(2)
        with col_ec1:
            st.dataframe(entrate_cliente_top.rename(columns={"importo_totale": "Entrate €"}))
        with col_ec2:
            fig_cli = px.pie(
                entrate_cliente_top,
                names="Cliente",
                values="importo_totale",
                title="Distribuzione entrate per cliente",
            )
            st.plotly_chart(fig_cli, use_container_width=True)
    else:
        st.info("Nessuna entrata nel periodo selezionato per analisi per cliente.")

    # ---------- Breakdown uscite per categoria ----------
    st.markdown("---")
    st.subheader("📂 Uscite per categoria costo (periodo)")

    if not df_exp.empty:
        with get_session() as session:
            categories_map = {
                c.category_id: c.nome for c in session.exec(select(ExpenseCategory)).all()
            }

        df_cat_exp = df_exp.copy()
        df_cat_exp["Categoria"] = df_cat_exp["category_id"].map(categories_map).fillna("Senza categoria")
        uscite_categoria = (
            df_cat_exp.groupby("Categoria")["importo_totale"]
            .sum()
            .reset_index()
            .sort_values("importo_totale", ascending=False)
        )

        top_n_cat = st.slider(
            "Numero categorie da mostrare",
            min_value=3,
            max_value=20,
            value=10,
            step=1,
            key="top_cat",
        )
        uscite_categoria_top = uscite_categoria.head(top_n_cat)

        col_uc1, col_uc2 = st.columns(2)
        with col_uc1:
            st.dataframe(uscite_categoria_top.rename(columns={"importo_totale": "Uscite €"}))
        with col_uc2:
            fig_cat = px.pie(
                uscite_categoria_top,
                names="Categoria",
                values="importo_totale",
                title="Distribuzione uscite per categoria",
            )
            st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("Nessuna uscita nel periodo selezionato per analisi per categoria.")

    # ---------- Margine per commessa ----------
    st.markdown("---")
    st.subheader("📦 Margine per commessa (periodo)")

    if not df_inv.empty or not df_exp.empty:
        with get_session() as session:
            commesse_map = {
                c.commessa_id: c.cod_commessa
                for c in session.exec(select(ProjectCommessa)).all()
            }

        # Entrate per commessa (dalle fatture)
        if not df_inv.empty and "commessa_id" in df_inv.columns:
            df_inv_comm = df_inv.copy()
            df_inv_comm["Commessa"] = df_inv_comm["commessa_id"].map(commesse_map).fillna("Senza commessa")
            entrate_commessa = (
                df_inv_comm.groupby(["commessa_id", "Commessa"])["importo_totale"]
                .sum()
                .reset_index()
                .rename(columns={"importo_totale": "Entrate_commessa"})
            )
        else:
            entrate_commessa = pd.DataFrame(columns=["commessa_id", "Commessa", "Entrate_commessa"])

        # Uscite per commessa (dalle spese)
        if not df_exp.empty and "commessa_id" in df_exp.columns:
            df_exp_comm = df_exp.copy()
            df_exp_comm["Commessa"] = df_exp_comm["commessa_id"].map(commesse_map).fillna("Senza commessa")
            uscite_commessa = (
                df_exp_comm.groupby(["commessa_id", "Commessa"])["importo_totale"]
                .sum()
                .reset_index()
                .rename(columns={"importo_totale": "Uscite_commessa"})
            )
        else:
            uscite_commessa = pd.DataFrame(columns=["commessa_id", "Commessa", "Uscite_commessa"])

        if not entrate_commessa.empty or not uscite_commessa.empty:
            df_comm = pd.merge(
                entrate_commessa,
                uscite_commessa,
                on=["commessa_id", "Commessa"],
                how="outer",
            ).fillna(0.0)

            df_comm["Margine_commessa"] = df_comm["Entrate_commessa"] - df_comm["Uscite_commessa"]
            df_comm = df_comm.sort_values("Margine_commessa", ascending=False)

            st.dataframe(
                df_comm[
                    ["Commessa", "Entrate_commessa", "Uscite_commessa", "Margine_commessa"]
                ].rename(
                    columns={
                        "Entrate_commessa": "Entrate €",
                        "Uscite_commessa": "Uscite €",
                        "Margine_commessa": "Margine €",
                    }
                )
            )

            fig_comm = px.bar(
                df_comm,
                x="Commessa",
                y="Margine_commessa",
                title="Margine per commessa",
            )
            st.plotly_chart(fig_comm, use_container_width=True)
        else:
            st.info("Nessuna entrata o uscita collegata a commesse nel periodo selezionato.")
    else:
        st.info("Nessuna entrata o uscita disponibile per calcolare il margine per commessa.")

    # ---------- Uscite per conto finanziario ----------
    st.markdown("---")
    st.subheader("🏦 Uscite per conto finanziario (periodo)")

    if not df_exp.empty:
        with get_session() as session:
            accounts_map = {
                a.account_id: a.nome for a in session.exec(select(Account)).all()
            }

        df_acc_exp = df_exp.copy()
        df_acc_exp["Conto"] = df_acc_exp["account_id"].map(accounts_map).fillna("Senza conto")
        uscite_conto = (
            df_acc_exp.groupby("Conto")["importo_totale"]
            .sum()
            .reset_index()
            .sort_values("importo_totale", ascending=False)
        )

        top_n_acc = st.slider(
            "Numero conti da mostrare",
            min_value=3,
            max_value=20,
            value=10,
            step=1,
            key="top_acc",
        )
        uscite_conto_top = uscite_conto.head(top_n_acc)

        col_ua1, col_ua2 = st.columns(2)
        with col_ua1:
            st.dataframe(uscite_conto_top.rename(columns={"importo_totale": "Uscite €"}))
        with col_ua2:
            fig_acc = px.pie(
                uscite_conto_top,
                names="Conto",
                values="importo_totale",
                title="Distribuzione uscite per conto",
            )
            st.plotly_chart(fig_acc, use_container_width=True)
    else:
        st.info("Nessuna uscita nel periodo selezionato per analisi per conto.")

    # ---------- Sintesi per anno ----------
    st.markdown("---")
    st.subheader("📅 Sintesi Entrate / Uscite / Margine per anno")

    with get_session() as session:
        invoices_all = session.exec(select(Invoice)).all()
        expenses_all = session.exec(select(Expense)).all()

    df_inv_all = pd.DataFrame([i.__dict__ for i in (invoices_all or [])])
    df_exp_all = pd.DataFrame([e.__dict__ for e in (expenses_all or [])])

    if df_inv_all.empty and df_exp_all.empty:
        st.info("Nessun dato storico disponibile per la sintesi per anno.")
    else:
        if not df_inv_all.empty:
            df_inv_all["data_riferimento"] = df_inv_all["data_incasso"].fillna(df_inv_all["data_fattura"])
            df_inv_all["data_riferimento"] = pd.to_datetime(df_inv_all["data_riferimento"], errors="coerce")
            df_inv_all = df_inv_all.dropna(subset=["data_riferimento"])
            df_inv_all["anno"] = df_inv_all["data_riferimento"].dt.year
            entrate_anno = (
                df_inv_all.groupby("anno")["importo_totale"]
                .sum()
                .reset_index()
                .rename(columns={"importo_totale": "Entrate"})
            )
        else:
            entrate_anno = pd.DataFrame(columns=["anno", "Entrate"])

        if not df_exp_all.empty:
            df_exp_all["data"] = pd.to_datetime(df_exp_all["data"], errors="coerce")
            df_exp_all = df_exp_all.dropna(subset=["data"])
            df_exp_all["anno"] = df_exp_all["data"].dt.year
            uscite_anno = (
                df_exp_all.groupby("anno")["importo_totale"]
                .sum()
                .reset_index()
                .rename(columns={"importo_totale": "Uscite"})
            )
        else:
            uscite_anno = pd.DataFrame(columns=["anno", "Uscite"])

        df_year = pd.merge(entrate_anno, uscite_anno, on="anno", how="outer").fillna(0.0)
        if df_year.empty:
            st.info("Nessun dato aggregato per anno disponibile.")
        else:
            df_year["Margine"] = df_year["Entrate"] - df_year["Uscite"]
            df_year = df_year.sort_values("anno")

            st.dataframe(df_year)

            fig_year = px.bar(
                df_year,
                x="anno",
                y=["Entrate", "Uscite", "Margine"],
                barmode="group",
                title="Entrate, Uscite e Margine per anno",
            )
            st.plotly_chart(fig_year, use_container_width=True)

    # ---------- 2) CATEGORIE & CONTI ----------
    st.subheader("📂 Categorie costi & Conti")

    colc1, colc2 = st.columns(2)

    with colc1:
        st.markdown("#### Categoria costo")
        with st.form("new_expense_category"):
            nome_cat = st.text_input("Nome categoria", "Software")
            descr_cat = st.text_input("Descrizione", "")
            ded_perc = st.number_input("Deducibilità (%)", min_value=0.0, max_value=100.0, value=100.0, step=5.0)
            submitted_cat = st.form_submit_button("Salva categoria")
        if submitted_cat:
            with get_session() as session:
                new_c = ExpenseCategory(
                    nome=nome_cat.strip(),
                    descrizione=descr_cat.strip() or None,
                    deducibilita_perc=ded_perc / 100.0,
                )
                session.add(new_c)
                session.commit()
            st.success("Categoria salvata.")
            st.rerun()

        if categories:
            df_cat = pd.DataFrame([c.__dict__ for c in categories])
            st.dataframe(df_cat)
        else:
            st.info("Nessuna categoria registrata.")

    with colc2:
        st.markdown("#### Conto finanziario")
        with st.form("new_account"):
            nome_acc = st.text_input("Nome conto", "Conto corrente principale")
            tipo_acc = st.selectbox("Tipo", ["bank", "card", "cash", "paypal"])
            saldo_init = st.number_input("Saldo iniziale", value=0.0, step=100.0)
            valuta_acc = st.text_input("Valuta", "EUR")
            note_acc = st.text_input("Note", "")
            submitted_acc = st.form_submit_button("Salva conto")
        if submitted_acc:
            with get_session() as session:
                new_a = Account(
                    nome=nome_acc.strip(),
                    tipo=tipo_acc,
                    saldo_iniziale=saldo_init,
                    valuta=valuta_acc.strip() or "EUR",
                    note=note_acc.strip() or None,
                )
                session.add(new_a)
                session.commit()
            st.success("Conto salvato.")
            st.rerun()

        if accounts:
            df_acc = pd.DataFrame([a.__dict__ for a in accounts])
            st.dataframe(df_acc)
        else:
            st.info("Nessun conto registrato.")

    st.markdown("---")

    # ---------- 3) NUOVA SPESA ----------
    st.subheader("🧾 Registra nuova spesa")

    if not categories or not accounts:
        st.info("Per registrare una spesa serve almeno una categoria e un conto.")
        return

    df_cat = pd.DataFrame([c.__dict__ for c in categories])
    df_cat["label"] = df_cat["category_id"].astype(str) + " - " + df_cat["nome"]

    df_acc = pd.DataFrame([a.__dict__ for a in accounts])
    df_acc["label"] = df_acc["account_id"].astype(str) + " - " + df_acc["nome"]

    df_vend = pd.DataFrame([v.__dict__ for v in (vendors or [])]) if vendors else pd.DataFrame()
    if not df_vend.empty:
        df_vend["label"] = df_vend["vendor_id"].astype(str) + " - " + df_vend["ragione_sociale"]

    df_comm = pd.DataFrame([c.__dict__ for c in (commesse or [])]) if commesse else pd.DataFrame()
    if not df_comm.empty:
        df_comm["label"] = df_comm["commessa_id"].astype(str) + " - " + df_comm["cod_commessa"]

    with st.form("new_expense"):
        col1, col2 = st.columns(2)
        with col1:
            data_e = st.date_input("Data spesa", value=date.today())
            descr_e = st.text_input("Descrizione", "")
            cat_label = st.selectbox("Categoria costo", df_cat["label"].tolist())
            acc_label = st.selectbox("Conto", df_acc["label"].tolist())
        with col2:
            vendor_label = st.selectbox(
                "Fornitore (opzionale)",
                df_vend["label"].tolist() if not df_vend.empty else ["Nessun fornitore"],
            )
            comm_label = st.selectbox(
                "Commessa (opzionale)",
                df_comm["label"].tolist() if not df_comm.empty else ["Nessuna commessa"],
            )
            importo_imp = st.number_input("Imponibile (€)", min_value=0.0, step=50.0)
            iva_perc = st.number_input("Aliquota IVA (%)", min_value=0.0, max_value=50.0, value=22.0, step=1.0)

        col3, col4 = st.columns(2)
        with col3:
            document_ref = st.text_input("Rif. documento (fattura fornitore, ricevuta...)", "")
        with col4:
            pagata = st.checkbox("Pagata", value=True)
            data_pag = st.date_input("Data pagamento", value=date.today())

        submit_exp = st.form_submit_button("Salva spesa")

    if submit_exp:
        if importo_imp <= 0:
            st.warning("L'imponibile deve essere maggiore di zero.")
        else:
            cat_id = int(cat_label.split(" - ")[0])
            acc_id = int(acc_label.split(" - ")[0])

            vendor_id = None
            if not df_vend.empty and vendor_label in df_vend["label"].tolist():
                vendor_id = int(vendor_label.split(" - ")[0])

            commessa_id = None
            if not df_comm.empty and comm_label in df_comm["label"].tolist():
                commessa_id = int(comm_label.split(" - ")[0])

            iva_val = importo_imp * iva_perc / 100.0
            totale_val = importo_imp + iva_val

            with get_session() as session:
                new_exp = Expense(
                    data=data_e,
                    vendor_id=vendor_id,
                    category_id=cat_id,
                    account_id=acc_id,
                    descrizione=descr_e.strip() or None,
                    importo_imponibile=importo_imp,
                    iva=iva_val,
                    importo_totale=totale_val,
                    commessa_id=commessa_id,
                    document_ref=document_ref.strip() or None,
                    pagata=pagata,
                    data_pagamento=data_pag if pagata else None,
                    note=None,
                )
                session.add(new_exp)
                session.commit()
            st.success("Spesa salvata.")
            st.rerun()

    st.markdown("---")

    # ---------- 4) ELENCO SPESE ----------
    st.subheader("📋 Elenco spese")

    if not expenses:
        st.info("Nessuna spesa registrata.")
        return

    df_exp = pd.DataFrame([e.__dict__ for e in expenses])
    st.dataframe(df_exp)

def page_bilancio_gestionale():
    st.title("📘 Bilancio gestionale")

    col1, col2 = st.columns(2)
    with col1:
        anno_sel = st.number_input(
            "Anno di riferimento",
            min_value=2020,
            max_value=2100,
            value=date.today().year,
            step=1,
        )
    with col2:
        data_sp = st.date_input(
            "Data Stato Patrimoniale",
            value=date.today(),
        )

    saldo_cassa_auto = calcola_saldo_cassa(data_sp)
    saldo_cassa = st.number_input(
        "Saldo cassa/conti alla data",
        value=float(saldo_cassa_auto),
        step=100.0,
        help="Valore proposto calcolato dal gestionale; puoi modificarlo se necessario.",
    )

    bil = build_full_management_balance(anno_sel, data_sp, saldo_cassa)

    st.subheader("Stato Patrimoniale gestionale")
    if not bil["stato_patrimoniale"].empty:
        st.dataframe(bil["stato_patrimoniale"].style.format({"Importo": "{:,.2f}"}))
    else:
        st.info("Nessun dato di Stato Patrimoniale disponibile.")

    st.subheader("Conto Economico gestionale")
    if not bil["conto_economico"].empty:
        st.dataframe(bil["conto_economico"].style.format({"Importo": "{:,.2f}"}))
    else:
        st.info("Nessun dato di Conto Economico disponibile.")

    st.subheader("Indicatori di bilancio")
    if not bil["indicatori"].empty:
        st.dataframe(bil["indicatori"].style.format({"Valore": "{:,.2f}"}))
    else:
        st.info("Nessun indicatore calcolabile per l’anno selezionato.")

def page_cashflow_forecast():
    st.title("📈 Cashflow proiettato (budget vs consuntivo)")

    oggi = date.today()
    anni = list(range(oggi.year - 1, oggi.year + 3))
    anni.sort()
    anno_sel = st.selectbox("Anno", anni, index=anni.index(oggi.year))

    # Saldo iniziale al 1° gennaio anno selezionato (lo puoi impostare a mano)
    saldo_iniziale = st.number_input(
        f"Saldo iniziale al 01/01/{anno_sel} (€)",
        value=0.0,
        step=500.0,
        help="Inserisci il saldo di cassa/banca all'inizio dell'anno selezionato.",
    )

    # Carico dati da DB
    with get_session() as session:
        # Budget cashflow per anno
        budgets = session.exec(
            select(CashflowBudget).where(CashflowBudget.anno == anno_sel)
        ).all()

        # Eventi futuri (entrano nel forecast, non nel consuntivo)
        events = session.exec(
            select(CashflowEvent).where(
                CashflowEvent.data >= date(anno_sel, 1, 1),
                CashflowEvent.data <= date(anno_sel, 12, 31),
            )
        ).all()

        # Fatture e spese per consuntivo
        invoices = session.exec(select(Invoice)).all()
        expenses = session.exec(select(Expense)).all()

    # =========================
    # 1) BUDGET & EVENTI INPUT
    # =========================
    st.subheader("🧭 Budget mensile per categoria")

    df_budget_raw = pd.DataFrame(
        [
            {"mese": b.mese, "categoria": b.categoria, "importo_previsto": b.importo_previsto}
            for b in (budgets or [])
        ]
    )

    with st.form("budget_form_cf"):
        col1, col2, col3 = st.columns(3)
        with col1:
            mese_b = st.selectbox("Mese", list(range(1, 13)), index=oggi.month - 1)
        with col2:
            categoria_b = st.text_input(
                "Categoria",
                "Entrate clienti",
                help="Es. Entrate clienti, Costi fissi, Costi variabili, Fisco/INPS",
            )
        with col3:
            importo_b = st.number_input(
                "Importo previsto (positivo=entrata, negativo=uscita)",
                value=0.0,
                step=100.0,
            )
        submit_budget = st.form_submit_button("💾 Aggiungi riga budget")

    if submit_budget:
        with get_session() as session:
            new_b = CashflowBudget(
                anno=anno_sel,
                mese=mese_b,
                categoria=categoria_b.strip(),
                importo_previsto=float(importo_b),
            )
            session.add(new_b)
            session.commit()
        st.success("Riga budget salvata.")
        st.rerun()

    if not df_budget_raw.empty:
        st.dataframe(df_budget_raw.sort_values(["mese", "categoria"]))
    else:
        st.info("Nessun budget definito per questo anno.")

    st.markdown("---")
    st.subheader("📌 Eventi futuri (entrate/uscite specifiche)")

    df_events_raw = pd.DataFrame(
        [
            {
                "data": e.data,
                "tipo": e.tipo,
                "categoria": e.categoria,
                "importo": e.importo,
                "client_id": e.client_id,
                "commessa_id": e.commessa_id,
            }
            for e in (events or [])
        ]
    )

    with st.form("event_form_cf"):
        col1, col2 = st.columns(2)
        with col1:
            data_e = st.date_input("Data evento", value=oggi)
            tipo_e = st.selectbox("Tipo", ["entrata", "uscita"])
            categoria_e = st.text_input("Categoria evento", "Entrate clienti")
        with col2:
            importo_e = st.number_input(
                "Importo",
                value=0.0,
                step=100.0,
            )
        descr_e = st.text_input("Descrizione", "")
        submit_event = st.form_submit_button("💾 Aggiungi evento")

    if submit_event:
        with get_session() as session:
            new_e = CashflowEvent(
                data=data_e,
                tipo=tipo_e,
                categoria=categoria_e.strip(),
                descrizione=descr_e.strip() or None,
                importo=float(importo_e),
                client_id=None,
                commessa_id=None,
            )
            session.add(new_e)
            session.commit()
        st.success("Evento salvato.")
        st.rerun()

    if not df_events_raw.empty:
        st.dataframe(df_events_raw.sort_values("data"))
    else:
        st.info("Nessun evento futuro registrato per questo anno.")

    st.markdown("---")

    # ---------------------------
    # Consuntivo per mese (Actual)
    # ---------------------------
    df_inv = pd.DataFrame([i.__dict__ for i in (invoices or [])])
    df_exp = pd.DataFrame([e.__dict__ for e in (expenses or [])])

    # Entrate: uso data_incasso se presente, altrimenti data_fattura
    if not df_inv.empty:
        df_inv["data_rif"] = pd.to_datetime(
            df_inv["data_incasso"].fillna(df_inv["data_fattura"]),
            errors="coerce",
        )
        df_inv = df_inv.dropna(subset=["data_rif"])
        df_inv["anno"] = df_inv["data_rif"].dt.year
        df_inv["mese"] = df_inv["data_rif"].dt.month
        df_inv = df_inv[df_inv["anno"] == anno_sel]
        entrate_actual = (
            df_inv.groupby("mese")["importo_totale"]
            .sum()
            .rename("Entrate_actual")
            .reset_index()
        )
    else:
        entrate_actual = pd.DataFrame(columns=["mese", "Entrate_actual"])

    # Uscite: uso data pagamento se presente, altrimenti data
    if not df_exp.empty:
        df_exp["data_rif"] = pd.to_datetime(
            df_exp["data_pagamento"].fillna(df_exp["data"]),
            errors="coerce",
        )
        df_exp = df_exp.dropna(subset=["data_rif"])
        df_exp["anno"] = df_exp["data_rif"].dt.year
        df_exp["mese"] = df_exp["data_rif"].dt.month
        df_exp = df_exp[df_exp["anno"] == anno_sel]
        uscite_actual = (
            df_exp.groupby("mese")["importo_totale"]
            .sum()
            .rename("Uscite_actual")
            .reset_index()
        )
    else:
        uscite_actual = pd.DataFrame(columns=["mese", "Uscite_actual"])

    # ---------------------------
    # Budget per mese (con categorie di cashflow)
    # ---------------------------
    df_budget = pd.DataFrame(
        [
            {
                "mese": b.mese,
                "categoria": (b.categoria or "").strip(),
                "importo_previsto": b.importo_previsto,
            }
            for b in (budgets or [])
        ]
    )

    def _classifica_cashflow_cat(nome_cat: str) -> str:
        """Restituisce: operativo / fisco_inps / investimenti_altro."""
        nome = (nome_cat or "").lower()
        if any(k in nome for k in ["fisco", "imposte", "tasse", "inps", "previd"]):
            return "fisco_inps"
        if any(k in nome for k in ["invest", "macchin", "impiant", "attrezz", "capex"]):
            return "investimenti_altro"
        # default: tutto ciò che non è fisco/INPS o investimenti lo consideriamo operativo
        return "operativo"

    if not df_budget.empty:
        df_budget["macro_cat"] = df_budget["categoria"].apply(_classifica_cashflow_cat)
        # netto totale budget (come prima)
        budget_mese = (
            df_budget.groupby("mese")["importo_previsto"]
            .sum()
            .rename("Netto_budget")
            .reset_index()
        )
        # budget per macro-categoria
        budget_mese_macro = (
            df_budget.groupby(["mese", "macro_cat"])["importo_previsto"]
            .sum()
            .reset_index()
            .pivot(index="mese", columns="macro_cat", values="importo_previsto")
            .fillna(0.0)
            .reset_index()
        )
        budget_mese_macro = budget_mese_macro.rename(
            columns={
                "operativo": "Budget_operativo",
                "fisco_inps": "Budget_fisco_inps",
                "investimenti_altro": "Budget_investimenti_altro",
            }
        )
    else:
        budget_mese = pd.DataFrame(columns=["mese", "Netto_budget"])
        budget_mese_macro = pd.DataFrame(
            columns=[
                "mese",
                "Budget_operativo",
                "Budget_fisco_inps",
                "Budget_investimenti_altro",
            ]
        )

    # ---------------------------
    # Eventi puntuali (forecast)
    # ---------------------------
    df_events = pd.DataFrame(
        [
            {
                "data": e.data,
                "mese": e.data.month,
                "tipo": e.tipo,
                "importo": e.importo if e.tipo == "entrata" else -e.importo,
            }
            for e in (events or [])
        ]
    )
    if not df_events.empty:
        events_mese = (
            df_events.groupby("mese")["importo"]
            .sum()
            .rename("Events_netto")
            .reset_index()
        )
    else:
        events_mese = pd.DataFrame(columns=["mese", "Events_netto"])

    # ---------------------------
    # Merge mensile e calcolo saldo
    # ---------------------------
    mesi_df = pd.DataFrame({"mese": list(range(1, 13))})

    df_cf = mesi_df.merge(entrate_actual, on="mese", how="left")
    df_cf = df_cf.merge(uscite_actual, on="mese", how="left")
    df_cf = df_cf.merge(budget_mese, on="mese", how="left")
    df_cf = df_cf.merge(events_mese, on="mese", how="left")
    df_cf = df_cf.merge(budget_mese_macro, on="mese", how="left")


    df_cf = df_cf.fillna(0.0)

    df_cf["Entrate_forecast"] = df_cf["Entrate_actual"]
    df_cf["Uscite_forecast"] = df_cf["Uscite_actual"]

    # Dove non hai ancora consuntivo (mesi futuri), il netto budget + eventi aiuta il forecast
    df_cf["Netto_actual"] = df_cf["Entrate_actual"] - df_cf["Uscite_actual"]
    df_cf["Netto_budget_events"] = df_cf["Netto_budget"] + df_cf["Events_netto"]
    df_cf["Netto_forecast"] = df_cf["Netto_actual"] + df_cf["Netto_budget_events"]
    # Scomposizione del forecast per macro-categoria
    df_cf["Netto_operativo"] = df_cf["Netto_actual"] + df_cf["Budget_operativo"]
    df_cf["Netto_fisco_inps"] = df_cf["Budget_fisco_inps"]
    df_cf["Netto_investimenti_altro"] = df_cf["Budget_investimenti_altro"]

    # Controllo: somma delle tre componenti
    df_cf["Netto_somma_componenti"] = (
        df_cf["Netto_operativo"]
        + df_cf["Netto_fisco_inps"]
        + df_cf["Netto_investimenti_altro"]
    )

    # Calcolo saldo mese per mese
    saldi = []
    saldo = saldo_iniziale
    for _, row in df_cf.sort_values("mese").iterrows():
        saldo_finale = saldo + row["Netto_forecast"]
        saldi.append(
            {
                "mese": row["mese"],
                "Saldo_iniziale": saldo,
                "Netto_forecast": row["Netto_forecast"],
                "Saldo_finale": saldo_finale,
            }
        )
        saldo = saldo_finale

    df_saldi = pd.DataFrame(saldi)

    # Join per tabella finale leggibile
    df_view = df_cf.merge(df_saldi, on="mese")
    df_view["Mese"] = df_view["mese"].apply(lambda m: f"{m:02d}/{anno_sel}")

    # Colonna forecast (qui in realtà è già in df_cf, questa riga può anche non servire)
    # df_view["Netto_forecast"] = (
    #     df_view["Netto_operativo"]
    #     + df_view["Netto_fisco_inps"]
    #     + df_view["Netto_investimenti_altro"]
    # )

    cols_show = [
        "Mese",
        "Entrate_actual",
        "Uscite_actual",
        "Netto_actual",
        "Netto_budget",
        "Events_netto",
        "Netto_operativo",
        "Netto_fisco_inps",
        "Netto_investimenti_altro",
        "Netto_forecast",
        "Saldo_iniziale",
        "Saldo_finale",
    ]

    df_view = df_view[cols_show]

    st.subheader("Tabella mensile Actual vs Budget + saldo proiettato")
    st.dataframe(df_view.style.format("{:,.2f}", subset=df_view.columns[1:]))

    # ---------------------------
    # Grafico saldo proiettato
    # ---------------------------
    st.subheader("Andamento saldo proiettato per mese")
    fig = px.line(
        df_saldi,
        x="mese",
        y="Saldo_finale",
        markers=True,
        labels={"mese": "Mese", "Saldo_finale": "Saldo finale previsto (€)"},
    )
    st.plotly_chart(fig, use_container_width=True)


PAGES = {
    "Presentazione": page_presentation,
    "Overview": page_overview,
    "Clienti": page_clients,
    "CRM & Vendite": page_crm_sales,
    "Treno vendite": page_sales_train,
    "Lead da campagne": page_lead_capture,
    "Finanza / Fatture": page_finance_invoices,    # pagina fatture
    "Finanza / Pagamenti": page_finance_payments,  # se è una pagina distinta
    "Incassi / Scadenze": page_payments,
    "Cashflow proiettato": page_cashflow_forecast,
    "Fatture → AE": page_invoice_transmission,
    "Fisco & INPS": page_tax_inps,
    "Spese": page_expenses,
    "Finanza / Dashboard": page_finance_dashboard,
    "Bilancio gestionale": page_bilancio_gestionale,
    "Nota integrativa gestionale": page_nota_integrativa,
    "Operations / Commesse": page_operations,
    "People & Reparti": page_people_departments,
    "Capacità People": page_capacity_people,
}

# =========================
# LOGIN & MAIN
# =========================

def check_login_sidebar():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = "user"

    with st.sidebar:
        if not st.session_state.logged_in:
            st.markdown("### 🔐 Login")

            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")

            if submit:
                if username == "Marian Dutu" and password == "mariand":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = "admin"
                    st.rerun()
                elif username == "Demo User" and password == "demodemo":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = "user"
                    st.rerun()
                else:
                    st.error("Credenziali non valide.")
        else:
            if st.button("Logout", key="logout_button"):
                st.session_state.logged_in = False
                st.session_state.username = ""
                st.session_state.role = "user"
                st.rerun()

    if not st.session_state.logged_in:
        st.stop()


def main():
    # 👉 chiamata subito all'inizio
    capture_utm_params()

    # ---------- Inizializzazione stato ----------
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["role"] = "anon"  # visitatore non loggato
        st.session_state["username"] = ""

    # ---------- SIDEBAR ----------
    st.sidebar.title(APP_NAME)
    st.sidebar.caption("Versione SQLite")

    # Blocco login admin (semplice)
    if not st.session_state["authenticated"]:
        st.sidebar.subheader("Area riservata")
        username_input = st.sidebar.text_input("Username")
        password_input = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if username_input == "Marian Dutu" and password_input == "mariand":
                st.session_state["authenticated"] = True
                st.session_state["role"] = "admin"
                st.session_state["username"] = username_input
            else:
                st.sidebar.error("Credenziali non valide")
    else:
        st.sidebar.write("✅ Accesso admin")
        if st.sidebar.button("Logout"):
            st.session_state["authenticated"] = False
            st.session_state["role"] = "anon"
            st.session_state["username"] = ""

    # Menu pagine in base al ruolo
    role = st.session_state["role"]
    if role == "anon":
        pages = ["Presentazione"]
    else:
        pages = list(PAGES.keys())

    page = st.sidebar.radio("Pagina", pages)

    if LOGO_PATH.exists():
        st.sidebar.markdown("---")
        st.sidebar.image(str(LOGO_PATH), use_container_width=True)

    PAGES[page]()


if __name__ == "__main__":
    main()