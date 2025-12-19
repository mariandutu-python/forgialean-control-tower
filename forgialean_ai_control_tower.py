from datetime import date, timedelta, datetime
from pathlib import Path
import io

import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
from sqlmodel import SQLModel, Field, Session, select, delete

from config import CACHE_TTL, PAGES_BY_ROLE, APP_NAME, LOGO_PATH, MY_COMPANY_DATA

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

init_db()

LOGO_PATH = Path("forgialean_logo.png")


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

def page_presentation():
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
ForgiaLean unisce **Black Belt Lean Six Sigma**, **Operations Management** e **dashboard real‑time Industry 4.0** per:

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

    # Dati fittizi per esempio
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
        )
        fig_oee.update_traces(texttemplate="%{y}%", textposition="outside")
        st.plotly_chart(fig_oee, use_container_width=True)

    with col_g2:
        fig_fermi = px.bar(
            df_fermi,
            x="Fase",
            y="Fermi orari/turno",
            title="Ore di fermo per turno",
            text="Fermi orari/turno",
        )
        fig_fermi.update_traces(texttemplate="%{y:.1f} h", textposition="outside")
        st.plotly_chart(fig_fermi, use_container_width=True)

    st.caption(
        "Esempio reale: progetto su una linea automatica. I valori sono indicativi e variano per settore e impianto."
    )

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

Questo è il primo passo: se i numeri confermano il pain, potrai prenotare un **Audit 30 minuti + piano personalizzato**.
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
            try:
                with get_session() as session:
                    # 1) Crea il Client
                    new_client = Client(
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
                    session.add(new_client)
                    session.commit()
                    session.refresh(new_client)

                    # 2) Crea l'Opportunity collegata al client
                    new_opp = Opportunity(
                        client_id=new_client.client_id,
                        nome_opportunita=f"Lead OEE - {nome}",
                        fase_pipeline="Lead",
                        owner="Marian Dutu",
                        valore_stimato=0.0,
                        probabilita=10.0,
                        data_apertura=date.today(),
                        stato_opportunita="aperta",
                        data_chiusura_prevista=None,
                    )
                    session.add(new_opp)
                    session.commit()

                st.success(
                    "Richiesta ricevuta. Riceverai via email il mini‑report OEE con la stima degli sprechi €/giorno per una macchina/linea, "
                    "una proiezione per più asset simili e 3 leve di azione prioritarie."
                )
            except Exception as e:
                st.error("Si è verificato un errore nel salvataggio del lead OEE.")
                st.text(str(e))

    # =====================
    # CALCOLATORE OEE & PERDITA € - SOLO ADMIN (uso interno)
    # =====================
    role = st.session_state.get("role", "user")
    if role != "admin":
        # Il cliente vede solo landing + form
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
                value=ore_fermi,
                step=0.5,
                key="oee_ore_fermi",
            )
        with col2:
            scarti_calc = st.number_input(
                "Scarti / rilavorazioni (%)",
                min_value=0.0,
                max_value=100.0,
                value=scarti,
                step=0.5,
                key="oee_scarti",
            )
            velocita_calc = st.number_input(
                "Velocità reale vs nominale (%)",
                min_value=0.0,
                max_value=200.0,
                value=velocita,
                step=1.0,
                key="oee_velocita",
            )

        valore_orario_calc = st.number_input(
            "Valore economico 1 ora produzione (€ / ora)",
            min_value=0.0,
            value=valore_orario if "valore_orario" in locals() else 0.0,
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
        df_clients["label"] = df_clients["client_id"].astype(str) + " - " + df_clients["ragione_sociale"]

        with st.form("new_opportunity"):
            col1, col2 = st.columns(2)
            with col1:
                client_label = st.selectbox("Cliente", df_clients["label"].tolist())
                nome_opportunita = st.text_input("Nome opportunità", "")
                fase_pipeline = st.selectbox(
                    "Fase pipeline",
                    ["Lead", "Offerta", "Negoziazione", "Vinta", "Persa"],
                    index=0,
                )
                owner = st.text_input("Owner (commerciale)", "")
            with col2:
                valore_stimato = st.number_input("Valore stimato (€)", min_value=0.0, step=100.0)
                probabilita = st.slider("Probabilità (%)", min_value=0, max_value=100, value=50)
                data_apertura = st.date_input("Data apertura", value=date.today())
                data_chiusura_prevista = st.date_input("Data chiusura prevista", value=date.today())

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

                # Recupero info cliente per avere il nome nel tracking
                client_row = df_clients[df_clients["client_id"] == client_id_sel].iloc[0]
                client_name = client_row["ragione_sociale"]

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
                        stato_opportunita=stato_opportunita,
                    )
                    session.add(new_opp)
                    session.commit()
                    session.refresh(new_opp)

                # === TRACKING GA4 ===
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
                    client_id=None,  # per ora usiamo un fallback server
                )

                # === TRACKING FACEBOOK (Conversions API) ===
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

    if not opps:
        st.info("Nessuna opportunità presente.")
        return

    df_opps = pd.DataFrame([o.__dict__ for o in opps])

    col1, col2 = st.columns(2)
    with col1:
        fase_opt = ["Tutte"] + sorted(df_opps["fase_pipeline"].dropna().unique().tolist())
        f_fase = st.selectbox("Filtro fase pipeline", fase_opt)
    with col2:
        owner_opt = ["Tutti"] + sorted(df_opps["owner"].dropna().unique().tolist()) if "owner" in df_opps.columns else ["Tutti"]
        f_owner = st.selectbox("Filtro owner", owner_opt)

    df_f = df_opps.copy()
    if f_fase != "Tutte":
        df_f = df_f[df_f["fase_pipeline"] == f_fase]
    if f_owner != "Tutti":
        df_f = df_f[df_f["owner"] == f_owner]

    st.subheader("📂 Opportunità filtrate")
    st.dataframe(df_f)

    if "fase_pipeline" in df_f.columns and "valore_stimato" in df_f.columns and not df_f.empty:
        st.subheader("📈 Valore opportunità per fase")
        pivot = df_f.groupby("fase_pipeline")["valore_stimato"].sum().reset_index()
        st.bar_chart(pivot.set_index("fase_pipeline"))

        # =========================
    # SEZIONE EDIT / DELETE (SOLO ADMIN)
    # =========================
    if role != "admin":
        return  # niente edit/delete per utenti normali

    st.markdown("---")
    st.subheader("✏️ Modifica / elimina opportunità (solo admin)")

    with get_session() as session:
        opp_all = session.exec(select(Opportunity)).all()
        clients_all = session.exec(select(Client)).all()

    if not opp_all:
        st.info("Nessuna opportunità da modificare/eliminare.")
        return

    df_opp_all = pd.DataFrame([o.__dict__ for o in opp_all])
    opp_ids = df_opp_all["opportunity_id"].tolist()
    opp_id_sel = st.selectbox("ID opportunità", opp_ids, key="crm_opp_sel")

    with get_session() as session:
        opp_obj = session.get(Opportunity, opp_id_sel)

    if not opp_obj:
        st.warning("Opportunità non trovata.")
        return

    # client label per select
    df_clients_all = pd.DataFrame([c.__dict__ for c in clients_all]) if clients_all else pd.DataFrame()
    if not df_clients_all.empty:
        df_clients_all["label"] = df_clients_all["client_id"].astype(str) + " - " + df_clients_all["ragione_sociale"]
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
            client_label_e = st.selectbox(
                "Cliente",
                df_clients_all["label"].tolist() if not df_clients_all.empty else [],
                index=df_clients_all["label"].tolist().index(current_client_label) if current_client_label else 0,
            ) if not df_clients_all.empty else ("",)
            nome_opportunita_e = st.text_input("Nome opportunità", opp_obj.nome_opportunita or "")
            fase_pipeline_e = st.selectbox(
                "Fase pipeline",
                ["Lead", "Offerta", "Negoziazione", "Vinta", "Persa"],
                index=["Lead", "Offerta", "Negoziazione", "Vinta", "Persa"].index(opp_obj.fase_pipeline or "Lead"),
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



def page_finance_invoices():
    st.title("💵 Finanza / Fatture (SQLite)")
    role = st.session_state.get("role", "user")

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

        with get_session() as session:
            client_xml = session.get(Client, inv.client_id)

     
def page_payments():
    st.title("💶 Incassi / Scadenze")
    role = st.session_state.get("role", "user")

    # Carico fatture
    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()

    if not invoices:
        st.info("Nessuna fattura registrata.")
        return

    df_inv = pd.DataFrame([i.__dict__ for i in invoices])
    df_inv["label"] = df_inv["invoice_id"].astype(str) + " - " + df_inv["num_fattura"]

    st.subheader("➕ Registra nuovo incasso")

    with st.form("new_payment"):
        invoice_label = st.selectbox("Fattura", df_inv["label"].tolist())
        payment_date = st.date_input("Data pagamento", value=date.today())
        amount = st.number_input("Importo incassato (€)", min_value=0.0, step=50.0)
        method = st.text_input("Metodo (bonifico, carta, contanti...)", "bonifico")
        note = st.text_area("Note", "")

        submitted_pay = st.form_submit_button("Salva incasso")

    if submitted_pay:
        if amount <= 0:
            st.warning("L'importo deve essere maggiore di zero.")
        else:
            invoice_id_sel = int(invoice_label.split(" - ")[0])
            with get_session() as session:
                new_pay = Payment(
                    invoice_id=invoice_id_sel,
                    payment_date=payment_date,
                    amount=amount,
                    method=method.strip() or "bonifico",
                    note=note.strip() or None,
                )
                session.add(new_pay)
                session.commit()
            st.success("Incasso registrato.")
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Pagamenti registrati")

    with get_session() as session:
        pays = session.exec(select(Payment)).all()

    if not pays:
        st.info("Nessun pagamento registrato.")
        return

    df_pay = pd.DataFrame([p.__dict__ for p in pays])
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

    st.markdown("---")
    st.subheader("📅 Filtro periodo KPI")

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

    # Filtro periodo
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

    # ---------- ENTRATE (Fatture incassate) ----------
    if not df_inv.empty:
        df_inv["data_riferimento"] = df_inv["data_incasso"].fillna(df_inv["data_fattura"])
        df_inv["data_riferimento"] = pd.to_datetime(df_inv["data_riferimento"], errors="coerce")
        df_inv = df_inv.dropna(subset=["data_riferimento"])
        df_inv = df_inv[
            (df_inv["data_riferimento"] >= pd.to_datetime(data_da)) &
            (df_inv["data_riferimento"] <= pd.to_datetime(data_a))
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
            (df_exp["data"] >= pd.to_datetime(data_da)) &
            (df_exp["data"] <= pd.to_datetime(data_a))
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
    col_k1, col_k2, col_k3 = st.columns(3)
    with col_k1:
        st.metric("Entrate totali", f"{totale_entrate:,.2f} €".replace(",", " "))
    with col_k2:
        st.metric("Uscite totali", f"{totale_uscite:,.2f} €".replace(",", " "))
    with col_k3:
        st.metric("Margine", f"{(totale_entrate - totale_uscite):,.2f} €".replace(",", " "))

    # ---------- Grafici ----------
    if not df_kpi.empty:
        st.subheader("Entrate vs Uscite per mese")
        fig_eu = px.bar(
            df_kpi,
            x="mese",
            y=["Entrate", "Uscite"],
            barmode="group",
            title="Entrate vs Uscite per mese",
        )
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

    # Servono commesse e almeno qualche fattura/spesa collegata
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

        # Merge entrate/uscite per commessa
        if not entrate_commessa.empty or not uscite_commessa.empty:
            df_comm = pd.merge(
                entrate_commessa,
                uscite_commessa,
                on=["commessa_id", "Commessa"],
                how="outer",
            ).fillna(0.0)

            df_comm["Margine_commessa"] = df_comm["Entrate_commessa"] - df_comm["Uscite_commessa"]

            # Ordina per margine decrescente
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

            # Grafico barre margine per commessa
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

    # Ricalcolo versioni non filtrate per anno (su tutto il DB)
    with get_session() as session:
        invoices_all = session.exec(select(Invoice)).all()
        expenses_all = session.exec(select(Expense)).all()

    df_inv_all = pd.DataFrame([i.__dict__ for i in (invoices_all or [])])
    df_exp_all = pd.DataFrame([e.__dict__ for e in (expenses_all or [])])

    if df_inv_all.empty and df_exp_all.empty:
        st.info("Nessun dato storico disponibile per la sintesi per anno.")
    else:
        # Entrate per anno
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

        # Uscite per anno
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

        # Merge e calcolo margine per anno
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

# =========================
# ROUTER
# =========================

PAGES = {
    "Presentazione": page_presentation,
    "Overview": page_overview,
    "Clienti": page_clients,
    "CRM & Vendite": page_crm_sales,
    "Finanza / Fatture": page_finance_invoices,
    "Incassi / Scadenze": page_finance_payments,      # nuova pagina
    "Costi & Fornitori": page_expenses,      # <--- aggiungi questa
    "Cruscotto Finanza": page_finance_dashboard,  # <-- nuova voce
    "Fatture → AE": page_invoice_transmission,         # nuova pagina
    "Fisco & INPS": page_tax_inps,                     # nuova pagina
    "Operations / Commesse": page_operations,
    "People & Reparti": page_people_departments,
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