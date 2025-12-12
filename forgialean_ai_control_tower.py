from datetime import date, timedelta
from pathlib import Path
import io

import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
from sqlmodel import SQLModel, Field, Session, select, delete

from config import CACHE_TTL, PAGES_BY_ROLE, APP_NAME, LOGO_PATH
from pathlib import Path

LOGO_PATH = Path("forgialean_logo.png")

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

from db import (
    get_session,
    Client,
    Opportunity,
    Invoice,
    ProjectCommessa,
    TaskFase,
    Department,
    Employee,
    KpiDepartmentTimeseries,
    KpiEmployeeTimeseries,
    TimeEntry,
)


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


st.set_page_config(page_title=APP_NAME, layout="wide")


def page_presentation():
    st.title("ForgiaLean - quando l'OEE fa male")

    st.subheader("Domanda iniziale")
    st.markdown("""
- OEE medio della tua linea principale è:
  - superiore all'85%?
  - tra 80% e 85%?
  - tra 70% e 80%?
  - sotto il 70%?

Se non conosci il valore, questo è già un primo campanello d'allarme.
""")

    st.subheader("Segnali che l'OEE sta facendo male")
    st.markdown("""
- Fermi impianto ricorrenti, ma senza una visione chiara delle cause principali.
- Scarti di qualità che aumentano, gestiti solo a consuntivo.
- Performance macchina lontana dai valori di targa, senza un monitoraggio continuo.
- Report e file Excel che richiedono molto tempo, ma danno poche risposte operative.
""")

    st.subheader("Perché l'OEE è il KPI centrale")
    st.markdown("""
- Combina disponibilità, performance e qualità in un unico indicatore.
- Un OEE inferiore all'80% indica un importante potenziale di recupero capacità.
- Lavorare sull'OEE significa agire contemporaneamente su fermi, velocità e scarti.
""")

    st.subheader("Cosa offre ForgiaLean")
    st.markdown("""
- Supporto a PMI manifatturiere con OEE inferiore all'80%.
- Analisi dei dati esistenti (Excel, sistemi di produzione, report interni).
- Costruzione di dashboard chiare per rendere visibili le perdite principali.
- Definizione di azioni concrete di miglioramento su disponibilità, performance e qualità.
""")

    st.subheader("Come procedere")
    st.markdown("""
1. Raccogli il valore di OEE medio degli ultimi mesi (in %).
2. Descrivi brevemente la tipologia di linea/impianto.
3. Contatta ForgiaLean per un primo check senza impegno.

_ForgiaLean - Crevalcore (BO) - by Marian Dutu_
""")

    # =====================
    # ESEMPIO INTERATTIVO OEE
    # =====================
    st.markdown("---")
    st.subheader("Esempio interattivo: OEE prima e dopo")

    periodi = ["Periodo 1", "Periodo 2", "Periodo 3", "Periodo 4", "Periodo 5"]
    oee_values = [72, 74, 76, 81, 84]

    df_oee_demo = pd.DataFrame({
        "Periodo": periodi,
        "OEE (%)": oee_values,
    })

    periodo_sel = st.slider(
        "Seleziona il periodo da analizzare",
        min_value=1,
        max_value=len(periodi),
        value=3,
        step=1,
        format="Periodo %d",
    )

    fig_oee = px.line(
        df_oee_demo,
        x="Periodo",
        y="OEE (%)",
        markers=True,
        title="OEE simulato prima e dopo un intervento mirato",
    )
    fig_oee.add_hline(y=80, line_dash="dash", line_color="red")  # soglia 80%

    st.plotly_chart(fig_oee, use_container_width=True)

    st.caption(
        "Esempio: dal 72-76% iniziale a oltre l'80% dopo un intervento, "
        "con linea rossa a 80% come soglia minima."
    )


    # =====================
    # ESEMPIO PARETO PERDITE
    # =====================
    st.markdown("---")
    st.subheader("Esempio: dove si perdono i punti di OEE?")

    cause = [
        "Fermi non pianificati",
        "Setup e cambi formato",
        "Scarti qualità",
        "Microfermi",
        "Velocità ridotta",
    ]
    perdita_punti = [8, 5, 4, 3, 2]  # punti OEE persi (fittizi)

    df_pareto = pd.DataFrame({
        "Causa": cause,
        "Punti OEE persi": perdita_punti,
    })

    fig_pareto = px.bar(
        df_pareto,
        x="Causa",
        y="Punti OEE persi",
        title="Pareto simulato delle perdite di OEE",
    )

    st.plotly_chart(fig_pareto, use_container_width=True)

    st.caption(
        "Esempio: i fermi non pianificati e i setup assorbono la quota principale di perdita; "
        "focalizzarsi su questi due ambiti porta il maggior beneficio."
    )

    
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
            settore = st.text_input("Settore", "")
            paese = st.text_input("Paese", "Italia")
            segmento_cliente = st.text_input("Segmento cliente (es. A/B/C)", "")
        with col2:
            canale_acquisizione = st.text_input("Canale acquisizione", "")
            stato_cliente = st.selectbox(
                "Stato cliente",
                ["attivo", "prospect", "perso"],
                index=0,
            )
            data_creazione = st.date_input("Data creazione", value=date.today())

        submitted = st.form_submit_button("Salva cliente")

    if submitted:
        if not ragione_sociale.strip():
            st.warning("La ragione sociale è obbligatoria.")
        else:
            with get_session() as session:
                new_client = Client(
                    ragione_sociale=ragione_sociale.strip(),
                    piva=piva.strip() or None,
                    settore=settore.strip() or None,
                    paese=paese.strip() or None,
                    canale_acquisizione=canale_acquisizione.strip() or None,
                    segmento_cliente=segmento_cliente.strip() or None,
                    data_creazione=data_creazione,
                    stato_cliente=stato_cliente,
                )
                session.add(new_client)
                session.commit()
                session.refresh(new_client)
            st.success(f"Cliente creato con ID {new_client.client_id}")
            st.rerun()

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

            # QUI: parsing minimale demo (regex / euristiche da migliorare)
            import re

            # Numero fattura: cerca stringhe tipo "Fattura n. 123" o "Fattura 123"
            m_num = re.search(r"[Ff]attura\s*(n\.|nr\.|numero)?\s*([A-Za-z0-9\-\/]+)", full_text)
            if m_num:
                parsed_data["num_fattura"] = m_num.group(2).strip()

            # Data fattura (pattern gg/mm/aaaa o gg-mm-aaaa)
            m_date = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", full_text)
            if m_date:
                try:
                    parsed_data["data_fattura"] = datetime.strptime(m_date.group(1), "%d/%m/%Y").date()
                except ValueError:
                    try:
                        parsed_data["data_fattura"] = datetime.strptime(m_date.group(1), "%d-%m-%Y").date()
                    except ValueError:
                        pass

            # Imponibile e totale (prende numeri con virgola o punto, ultima occorrenza)
            numbers = re.findall(r"(\d{1,3}(?:[\.\,]\d{3})*(?:[\.\,]\d{2}))", full_text)
            # euristica: penultima = imponibile, ultima = totale
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

    st.markdown("---")

    # =========================
    # 4) MODIFICA / ELIMINA FATTURA (SOLO ADMIN)
    # =========================
    if role != "admin":
        st.info("Modifica ed eliminazione fatture disponibili solo per ruolo 'admin'.")
        return

    st.subheader("✏️ Modifica / elimina fattura (solo admin)")

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

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            update_clicked = st.form_submit_button("💾 Aggiorna fattura")
        with col_b2:
            delete_clicked = st.form_submit_button("🗑 Elimina fattura")

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
    # VISTA REPARTI E PERSONE
    # =========================
    st.subheader("📂 Elenco reparti e persone")

        # =========================
    # INSERIMENTO KPI REPARTO (DATI REALI)
    # =========================
    st.markdown("### ➕ Aggiungi KPI reparto (dati reali)")

    with get_session() as session:
        departments_all = session.exec(select(Department)).all()

    if not departments_all:
        st.info("Prima crea almeno un reparto per registrare KPI reparto.")
    else:
        df_dept_all = pd.DataFrame([d.__dict__ for d in departments_all])
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

        st.markdown("---")
    st.markdown("### ➕ Aggiungi KPI persona (dati reali)")

    with get_session() as session:
        employees_all = session.exec(select(Employee)).all()

    if not employees_all:
        st.info("Prima crea almeno una persona per registrare KPI persona.")
    else:
        df_emp_all = pd.DataFrame([e.__dict__ for e in employees_all])
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
# ROUTER
# =========================

PAGES = {
    "Presentazione": page_presentation,  # 👈 nuova voce
    "Overview": page_overview,
    "Clienti": page_clients,
    "CRM & Vendite": page_crm_sales,
    "Finanza / Fatture": page_finance_invoices,
    "Operations / Commesse": page_operations,
    "People & Reparti": page_people_departments,
}

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
                # Admin
                if username == "Marian Dutu" and password == "mariand":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = "admin"
                    st.rerun()

                # Demo user: accesso diretto come "user"
                elif username == "Demo User" and password == "demodemo":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = "user"
                    st.rerun()

                # Credenziali sbagliate
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
    check_login_sidebar()
    role = st.session_state.get("role", "user")

    st.sidebar.title(APP_NAME)
    st.sidebar.caption("Versione SQLite – dati centralizzati in forgialean.db")

    if role == "admin":
        pages = list(PAGES.keys())
    else:
        # esempio: niente Finanza / Operations per user
        pages = ["Presentazione","Overview", "Clienti", "CRM & Vendite", "People & Reparti"]

    page = st.sidebar.radio("Pagina", pages)
    PAGES[page]()


        # Spazio vuoto per spingere il logo in basso
    for _ in range(18):
        st.sidebar.write("")

    # Mostra il logo se il path è valido e il file esiste
    if LOGO_PATH and isinstance(LOGO_PATH, Path) and LOGO_PATH.exists():
        st.sidebar.markdown("---")
        st.sidebar.image(str(LOGO_PATH), use_container_width=True)

if __name__ == "__main__":
    main()