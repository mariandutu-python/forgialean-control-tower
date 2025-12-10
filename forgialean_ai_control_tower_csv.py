import streamlit as st
import pandas as pd
from pathlib import Path

# ============================================================
# CONFIGURAZIONE BASE APP
# ============================================================

APP_NAME = "ForgiaLean AI Control Tower"
DATA_DIR = Path("data")

st.set_page_config(page_title=APP_NAME, layout="wide")

# ============================================================
# FUNZIONI DI CARICAMENTO DATI
# ============================================================

@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df

# ============================================================
# PAGINA: OVERVIEW
# ============================================================

def page_overview():
    st.title(f"🏢 {APP_NAME} – Overview")

    clients = load_csv("clients.csv")
    opportunities = load_csv("opportunities.csv")
    quotes = load_csv("quotes.csv")
    orders = load_csv("orders.csv")
    invoices = load_csv("invoices.csv")
    commesse = load_csv("projects_commesse.csv")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if not clients.empty and "stato_cliente" in clients.columns:
            attivi = clients[clients["stato_cliente"] == "attivo"]
            st.metric("Clienti attivi", len(attivi))
        else:
            st.metric("Clienti attivi", 0)

    with col2:
        if not opportunities.empty and "stato_opportunita" in opportunities.columns:
            aperte = opportunities[opportunities["stato_opportunita"] == "aperta"]
            st.metric("Opportunità aperte", len(aperte))
        else:
            st.metric("Opportunità aperte", 0)

    with col3:
        if not quotes.empty and "stato_offerta" in quotes.columns:
            inviate = quotes[quotes["stato_offerta"] == "inviata"]
            st.metric("Offerte inviate", len(inviate))
        else:
            st.metric("Offerte inviate", 0)

    with col4:
        if (
            not invoices.empty
            and "stato_pagamento" in invoices.columns
            and "importo_totale" in invoices.columns
        ):
            incassato = invoices[invoices["stato_pagamento"] == "incassata"]["importo_totale"].sum()
            st.metric("Incassato totale", f"{incassato:,.2f} €")
        else:
            st.metric("Incassato totale", "0.00 €")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("📊 Ultime fatture")
        if not invoices.empty and "data_fattura" in invoices.columns:
            tmp = invoices.copy()
            tmp["data_fattura"] = pd.to_datetime(tmp["data_fattura"], errors="coerce")
            st.dataframe(tmp.sort_values("data_fattura", ascending=False).head(10))
        else:
            st.info("Nessuna fattura caricata o colonna 'data_fattura' mancante.")

    with col_b:
        st.subheader("📂 Commesse recenti")
        if not commesse.empty and "data_inizio" in commesse.columns:
            tmp = commesse.copy()
            tmp["data_inizio"] = pd.to_datetime(tmp["data_inizio"], errors="coerce")
            st.dataframe(tmp.sort_values("data_inizio", ascending=False).head(10))
        else:
            st.info("Nessuna commessa caricata o colonna 'data_inizio' mancante.")

# ============================================================
# PAGINA: CRM & VENDITE (LEAD, OPPORTUNITÀ, OFFERTE, ORDINI)
# ============================================================

def page_crm_sales():
    st.title("🤝 CRM & Vendite")

    clients = load_csv("clients.csv")
    opportunities = load_csv("opportunities.csv")
    quotes = load_csv("quotes.csv")
    orders = load_csv("orders.csv")

    st.subheader("🎯 Funnel Opportunità")

    col1, col2 = st.columns(2)

    with col1:
        f_fase = "Tutte"
        f_owner = "Tutti"
        if not opportunities.empty:
            f_fase = st.selectbox(
                "Filtro fase pipeline",
                options=["Tutte"] + sorted(
                    opportunities["fase_pipeline"].dropna().unique().tolist()
                )
                if "fase_pipeline" in opportunities.columns
                else ["Tutte"],
            )

    with col2:
        if not opportunities.empty:
            f_owner = st.selectbox(
                "Filtro owner",
                options=["Tutti"] + sorted(
                    opportunities["owner"].dropna().unique().tolist()
                )
                if "owner" in opportunities.columns
                else ["Tutti"],
            )

    df = opportunities.copy()
    if not df.empty:
        if f_fase != "Tutte" and "fase_pipeline" in df.columns:
            df = df[df["fase_pipeline"] == f_fase]
        if f_owner != "Tutti" and "owner" in df.columns:
            df = df[df["owner"] == f_owner]

        st.subheader("📂 Opportunità filtrate")
        st.dataframe(df)

        if "fase_pipeline" in df.columns and "valore_stimato" in df.columns:
            st.subheader("📈 Valore opportunità per fase")
            pivot = df.groupby("fase_pipeline")["valore_stimato"].sum().reset_index()
            if not pivot.empty:
                st.bar_chart(pivot.set_index("fase_pipeline"))
        else:
            st.info("Mancano colonne 'fase_pipeline' o 'valore_stimato' per il grafico.")

    st.markdown("---")
    st.subheader("📄 Offerte (quotes)")

    if not quotes.empty:
        if "data_offerta" in quotes.columns:
            tmp_q = quotes.copy()
            tmp_q["data_offerta"] = pd.to_datetime(tmp_q["data_offerta"], errors="coerce")
            st.dataframe(tmp_q.sort_values("data_offerta", ascending=False).head(50))
        else:
            st.dataframe(quotes.head(50))
    else:
        st.info("Nessuna offerta caricata (quotes.csv).")

    st.markdown("---")
    st.subheader("📦 Ordini")

    if not orders.empty:
        if "data_ordine" in orders.columns:
            tmp_o = orders.copy()
            tmp_o["data_ordine"] = pd.to_datetime(tmp_o["data_ordine"], errors="coerce")
            st.dataframe(tmp_o.sort_values("data_ordine", ascending=False).head(50))
        else:
            st.dataframe(orders.head(50))
    else:
        st.info("Nessun ordine caricato (orders.csv).")

# ============================================================
# PAGINA: FINANZA (FATTURE, INCASSI)
# ============================================================

def page_finance():
    st.title("💶 Finanza")

    invoices = load_csv("invoices.csv")

    if invoices.empty:
        st.info("Carica invoices.csv nella cartella 'data/' per vedere i dati finanziari.")
        return

    if "data_fattura" in invoices.columns:
        invoices["data_fattura"] = pd.to_datetime(invoices["data_fattura"], errors="coerce")
        invoices["mese"] = invoices["data_fattura"].dt.to_period("M").astype(str)
    else:
        invoices["mese"] = "N/D"

    col1, col2, col3 = st.columns(3)
    if "importo_totale" in invoices.columns:
        totale = invoices["importo_totale"].sum()
    else:
        totale = 0.0

    if "stato_pagamento" in invoices.columns and "importo_totale" in invoices.columns:
        incassato = invoices[invoices["stato_pagamento"] == "incassata"]["importo_totale"].sum()
    else:
        incassato = 0.0

    aperto = totale - incassato

    with col1:
        st.metric("Fatturato totale", f"{totale:,.2f} €")
    with col2:
        st.metric("Incassato", f"{incassato:,.2f} €")
    with col3:
        st.metric("Da incassare", f"{aperto:,.2f} €")

    st.markdown("---")
    st.subheader("📈 Fatturato per mese")

    if "importo_totale" in invoices.columns and "mese" in invoices.columns:
        fatt_mese = invoices.groupby("mese")["importo_totale"].sum().reset_index()
        if not fatt_mese.empty:
            fatt_mese = fatt_mese.sort_values("mese")
            st.line_chart(fatt_mese.set_index("mese"))
        else:
            st.info("Nessun dato valido per il grafico per mese.")
    else:
        st.info("Mancano colonne 'mese' o 'importo_totale' per il grafico.")

    st.markdown("---")
    st.subheader("📊 Dettaglio fatture")
    st.dataframe(invoices.sort_values("data_fattura", ascending=False, na_position="last"))

# ============================================================
# PAGINA: OPERATIONS / COMMESSE
# ============================================================

def page_operations():
    st.title("🏭 Operations / Commesse")

    commesse = load_csv("projects_commesse.csv")
    fasi = load_csv("tasks_fasi.csv")

    if commesse.empty:
        st.info("Carica projects_commesse.csv e tasks_fasi.csv nella cartella 'data/'.")
        return

    stato = "Tutte"
    if "stato_commessa" in commesse.columns:
        stato = st.selectbox(
            "Filtro stato commessa",
            options=["Tutte"] + sorted(commesse["stato_commessa"].dropna().unique().tolist()),
        )

    df = commesse.copy()
    if stato != "Tutte" and "stato_commessa" in df.columns:
        df = df[df["stato_commessa"] == stato]

    st.subheader("📂 Elenco commesse")
    st.dataframe(df)

    st.subheader("📈 Ore previste vs consumate per commessa")
    if not df.empty and {"cod_commessa", "ore_previste", "ore_consumate"}.issubset(df.columns):
        kpi = df[["cod_commessa", "ore_previste", "ore_consumate"]].set_index("cod_commessa")
        st.bar_chart(kpi)
    else:
        st.info("Mancano colonne 'cod_commessa', 'ore_previste' o 'ore_consumate' per il grafico.")

    st.markdown("---")
    st.subheader("🧩 Fasi / Task commesse")

    if not fasi.empty:
        st.dataframe(fasi)
    else:
        st.info("Nessuna fase caricata (tasks_fasi.csv).")

# ============================================================
# PAGINA: MARKETING
# ============================================================

def page_marketing():
    st.title("📣 Marketing")

    campaigns = load_csv("campaigns_marketing.csv")

    if campaigns.empty:
        st.info("Carica campaigns_marketing.csv nella cartella 'data/'.")
        return

    st.subheader("📂 Campagne marketing")
    st.dataframe(campaigns)

    st.subheader("📈 Lead e ricavi per campagna")
    cols_needed = {"nome_campagna", "lead_generati", "ricavi_attribuiti"}
    if cols_needed.issubset(campaigns.columns):
        agg = campaigns.groupby("nome_campagna")[["lead_generati", "ricavi_attribuiti"]].sum()
        st.bar_chart(agg)
    else:
        st.info("Mancano colonne 'nome_campagna', 'lead_generati' o 'ricavi_attribuiti' per il grafico.")

# ============================================================
# PAGINA: PEOPLE & REPARTI (KPI TEMPORALI)
# ============================================================

def page_people_departments():
    st.title("👥 People & Reparti")

    departments = load_csv("departments.csv")
    employees = load_csv("employees.csv")
    kpi_dept = load_csv("kpi_department_timeseries.csv")
    kpi_emp = load_csv("kpi_employee_timeseries.csv")

    if not kpi_dept.empty and "data" in kpi_dept.columns:
        kpi_dept["data"] = pd.to_datetime(kpi_dept["data"], errors="coerce")

    if not kpi_emp.empty and "data" in kpi_emp.columns:
        kpi_emp["data"] = pd.to_datetime(kpi_emp["data"], errors="coerce")

    col1, col2 = st.columns(2)

    with col1:
        dept_opt = ["Tutti"]
        if not departments.empty and "nome_reparto" in departments.columns:
            dept_opt += departments["nome_reparto"].dropna().unique().tolist()
        sel_dept = st.selectbox("Reparto", dept_opt)

    with col2:
        emp_opt = ["Tutti"]
        if not employees.empty and "nome" in employees.columns and "cognome" in employees.columns:
            employees["nome_completo"] = employees["nome"] + " " + employees["cognome"]
            emp_opt += employees["nome_completo"].dropna().unique().tolist()
        sel_emp = st.selectbox("Persona", emp_opt)

    st.markdown("---")
    st.subheader("📈 KPI per reparto (time series)")

    if not kpi_dept.empty:
        df = kpi_dept.copy()

        if sel_dept != "Tutti" and not departments.empty and "nome_reparto" in departments.columns:
            dept_row = departments[departments["nome_reparto"] == sel_dept]
            if not dept_row.empty and "department_id" in dept_row.columns:
                dept_id = dept_row.iloc[0]["department_id"]
                df = df[df["department_id"] == dept_id]

        if not df.empty and {"data", "kpi_name", "valore", "target"}.issubset(df.columns):
            kpi_list = ["Tutti"] + sorted(df["kpi_name"].dropna().unique().tolist())
            sel_kpi = st.selectbox("Seleziona KPI reparto", kpi_list)

            if sel_kpi != "Tutti":
                df = df[df["kpi_name"] == sel_kpi]

            df = df.sort_values("data")
            st.line_chart(df.set_index("data")[["valore", "target"]])
            st.dataframe(df)
        else:
            st.info("Dati KPI reparto non completi per il grafico.")
    else:
        st.info("Nessun dato in kpi_department_timeseries.csv.")

    st.markdown("---")
    st.subheader("📈 KPI per persona (time series)")

    if not kpi_emp.empty:
        df_e = kpi_emp.copy()

        if sel_emp != "Tutti" and not employees.empty:
            if "nome_completo" not in employees.columns and \
               "nome" in employees.columns and "cognome" in employees.columns:
                employees["nome_completo"] = employees["nome"] + " " + employees["cognome"]
            if "nome_completo" in employees.columns:
                emp_row = employees[employees["nome_completo"] == sel_emp]
                if not emp_row.empty and "employee_id" in emp_row.columns:
                    emp_id = emp_row.iloc[0]["employee_id"]
                    df_e = df_e[df_e["employee_id"] == emp_id]

        if not df_e.empty and {"data", "kpi_name", "valore", "target"}.issubset(df_e.columns):
            kpi_list_e = ["Tutti"] + sorted(df_e["kpi_name"].dropna().unique().tolist())
            sel_kpi_e = st.selectbox("Seleziona KPI persona", kpi_list_e)

            if sel_kpi_e != "Tutti":
                df_e = df_e[df_e["kpi_name"] == sel_kpi_e]

            df_e = df_e.sort_values("data")
            st.line_chart(df_e.set_index("data")[["valore", "target"]])
            st.dataframe(df_e)
        else:
            st.info("Dati KPI persona non completi per il grafico.")
    else:
        st.info("Nessun dato in kpi_employee_timeseries.csv.")

# ============================================================
# ROUTER PAGINE
# ============================================================

PAGES = {
    "Overview": page_overview,
    "CRM & Vendite": page_crm_sales,
    "Finanza": page_finance,
    "Operations": page_operations,
    "Marketing": page_marketing,
    "People & Reparti": page_people_departments,
}

def main():
    st.sidebar.title(APP_NAME)
    st.sidebar.caption("Dashboard aziendale interattiva con AI-ready data model.")
    page_name = st.sidebar.radio("Seleziona pagina", list(PAGES.keys()))
    PAGES[page_name]()

if __name__ == "__main__":
    main()