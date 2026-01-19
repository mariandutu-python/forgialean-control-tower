import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from pathlib import Path

# ----------------- CONFIGURAZIONE PAGINA -----------------
st.set_page_config(
    page_title="Dashboard OEE - ForgiaLean",
    layout="wide",
    page_icon="📊",
)

PRIMARY_COLOR = "#0F4C81"   # blu (Dopo)
AFTER_COLOR = "#0F4C81"
BEFORE_COLOR = "#DC2626"    # rosso (Prima)
BG_COLOR = "#F5F7FA"
TEXT_MUTED = "#6B7280"

# ----------------- HEADER CON LOGO E TITOLO -----------------
col_logo, col_title = st.columns([1, 4])

with col_logo:
    logo_path = Path("forgialean_logo.png")
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
    else:
        st.markdown(
            f"<h2 style='color:{PRIMARY_COLOR}; margin-bottom:0;'>ForgiaLean</h2>",
            unsafe_allow_html=True,
        )

with col_title:
    st.markdown(
        f"""
        <div style="padding-left: 12px;">
            <h1 style="margin-bottom: 4px; color:{PRIMARY_COLOR};">
                Dashboard OEE
            </h1>
            <p style="margin-top: 0; color:{TEXT_MUTED}; font-size:15px;">
                Dalla capacità persa ai risultati economici: OEE, perdite e guadagni resi visibili per ogni linea.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    f"<div style='height:6px; background:{PRIMARY_COLOR}; margin-bottom:16px;'></div>",
    unsafe_allow_html=True,
)

# ----------------- SIDEBAR FILTRI -----------------
st.sidebar.title("Filtri")

linea = st.sidebar.selectbox("Linea", ["Linea 1", "Linea 2", "Linea 3"])
prodotto = st.sidebar.selectbox("Prodotto", ["Articolo A", "Articolo B", "Articolo C"])
periodo = st.sidebar.selectbox("Periodo", ["Ultima settimana", "Ultimo mese", "Ultimi 3 mesi"])

miglioramento = st.sidebar.slider(
    "Miglioramento OEE (%)",
    min_value=10,
    max_value=30,
    value=20,
    step=5,
)

st.sidebar.markdown("---")
costo_ora_linea = st.sidebar.number_input(
    "Margine medio per ora di linea (€)",
    min_value=100.0,
    max_value=2000.0,
    value=600.0,
    step=50.0,
)
st.sidebar.caption("Adatta a margine/linea della tua realtà.")

# ----------------- PARAMETRI DI BASE -----------------
ore_turno = 8
turni_per_giorno = 3
giorni_per_settimana = 5

ore_periodo = {
    "Ultima settimana": giorni_per_settimana * turni_per_giorno * ore_turno,
    "Ultimo mese": 4 * giorni_per_settimana * turni_per_giorno * ore_turno,
    "Ultimi 3 mesi": 12 * giorni_per_settimana * turni_per_giorno * ore_turno,
}[periodo]

np.random.seed(42)
base_oee = 0.60 + np.random.rand() * 0.05
target_oee = min(base_oee * (1 + miglioramento / 100), 0.85)

base_A = 0.78
base_P = 0.82
base_Q = 0.97

factor_A = 1 + (miglioramento * 0.5) / 100
factor_P = 1 + (miglioramento * 0.4) / 100
factor_Q = 1 + (miglioramento * 0.1) / 100

after_A = min(base_A * factor_A, 0.95)
after_P = min(base_P * factor_P, 0.97)
after_Q = min(base_Q * factor_Q, 0.995)

oee_after_raw = after_A * after_P * after_Q
after_oee = min(max(oee_after_raw, target_oee - 0.02), 0.85)

df_apq = pd.DataFrame({
    "Scenario": ["Prima", "Dopo"],
    "Availability": [base_A, after_A],
    "Performance": [base_P, after_P],
    "Quality": [base_Q, after_Q],
    "OEE": [base_oee, after_oee],
})

# ----------------- MODELLO ECONOMICO -----------------
ore_buone_prima = ore_periodo * base_oee
ore_buone_dopo = ore_periodo * after_oee
delta_ore_buone = ore_buone_dopo - ore_buone_prima

capacita_persa_prima = ore_periodo * (1 - base_oee)

impatto_euro = delta_ore_buone * costo_ora_linea

if periodo == "Ultima settimana":
    impatto_annuo = impatto_euro * 52
elif periodo == "Ultimo mese":
    impatto_annuo = impatto_euro * 12
else:
    impatto_annuo = impatto_euro * 4

categories = ["Setup", "Guasti", "Microfermi", "Attese materiali"]
downtime_before = np.array([120, 180, 90, 60])
downtime_after = (downtime_before * (1 - miglioramento / 100)).astype(int)

df_downtime = pd.DataFrame({
    "Categoria": categories,
    "Prima": downtime_before,
    "Dopo": downtime_after,
})

# ----------------- BLOCCO PAIN vs GAIN -----------------
st.markdown(
    f"""
    <div style='background:{BG_COLOR}; padding:14px 18px; border-radius:10px; margin-bottom:10px;'>
      <div style='display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap;'>
        <div style='flex:1; min-width:220px; border-right:1px solid #E5E7EB; padding-right:12px;'>
          <div style='font-size:13px; text-transform:uppercase; color:{BEFORE_COLOR}; letter-spacing:0.06em; font-weight:600; margin-bottom:4px;'>
            Capacità persa (prima)
          </div>
          <div style='font-size:24px; font-weight:600; color:{BEFORE_COLOR}; margin-bottom:2px;'>
            {(1-base_oee)*100:.1f}% del tempo
          </div>
          <div style='font-size:13px; color:{TEXT_MUTED};'>
            ≈ {capacita_persa_prima:,.1f} h sul periodo selezionato
          </div>
        </div>
        <div style='flex:1; min-width:220px; border-right:1px solid #E5E7EB; padding:0 12px;'>
          <div style='font-size:13px; text-transform:uppercase; color:{AFTER_COLOR}; letter-spacing:0.06em; font-weight:600; margin-bottom:4px;'>
            Capacità recuperata (dopo)
          </div>
          <div style='font-size:24px; font-weight:600; color:{AFTER_COLOR}; margin-bottom:2px;'>
            {delta_ore_buone:,.1f} h in più
          </div>
          <div style='font-size:13px; color:{TEXT_MUTED};'>
            da {base_oee*100:.1f}% a {after_oee*100:.1f}% di OEE
          </div>
        </div>
        <div style='flex:1; min-width:240px; padding-left:12px;'>
          <div style='font-size:13px; text-transform:uppercase; color:{AFTER_COLOR}; letter-spacing:0.06em; font-weight:600; margin-bottom:4px;'>
            Valore economico recuperato
          </div>
          <div style='font-size:24px; font-weight:600; color:{AFTER_COLOR}; margin-bottom:2px;'>
            {impatto_euro:,.0f} € sul periodo
          </div>
          <div style='font-size:13px; color:{TEXT_MUTED};'>
            ≈ {impatto_annuo:,.0f} € su base annua
          </div>
        </div>
      </div>
    </div>
    """.replace(",", "."),
    unsafe_allow_html=True,
)

# ----------------- RIGA KPI STANDARD -----------------
st.markdown(
    f"<div style='background:white; padding:10px 14px; border-radius:10px; border:1px solid #E5E7EB;'>",
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("OEE prima", f"{base_oee*100:.1f} %")
col2.metric(
    "OEE attuale",
    f"{after_oee*100:.1f} %",
    f"{(after_oee-base_oee)*100:.1f} pp",
)

col3.metric(
    "Ore produttive aggiuntive",
    f"{delta_ore_buone:,.1f} h".replace(",", "."),
)

col4.metric(
    "Impatto economico sul periodo",
    f"{impatto_euro:,.0f} €".replace(",", "."),
    f"+{impatto_euro:,.0f} €".replace(",", "."),
)

st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f"<p style='color:{TEXT_MUTED}; font-size:13px; margin-top:4px;'>"
    f"Linea: {linea} · Prodotto: {prodotto} · Periodo: {periodo}"
    f"</p>",
    unsafe_allow_html=True,
)

st.markdown("---")

# ----------------- RIGA 1: OEE/APQ + FERMATE -----------------
left_col, right_col = st.columns([2, 1])

with left_col:
    st.subheader("OEE complessivo")

    df_oee_plot = pd.DataFrame(
        {"Scenario": ["Prima", "Dopo"], "OEE": [base_oee * 100, after_oee * 100]}
    )

    oee_chart = (
        alt.Chart(df_oee_plot)
        .mark_bar()
        .encode(
            x=alt.X("Scenario", title=""),
            y=alt.Y("OEE:Q", title="OEE (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["Prima", "Dopo"],
                    range=[BEFORE_COLOR, AFTER_COLOR],
                ),
                legend=None,
            ),
            tooltip=["Scenario", alt.Tooltip("OEE:Q", format=".1f")],
        )
        .properties(height=260)
    )
    st.altair_chart(oee_chart, use_container_width=True)

    st.subheader("Availability / Performance / Quality")

    df_apq_long = df_apq.melt(
        id_vars="Scenario",
        value_vars=["Availability", "Performance", "Quality"],
        var_name="KPI",
        value_name="Valore",
    )
    df_apq_long["Valore"] = df_apq_long["Valore"] * 100

    apq_chart = (
        alt.Chart(df_apq_long)
        .mark_bar()
        .encode(
            x=alt.X("KPI:N", title="", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Valore:Q", title="Valore (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["Prima", "Dopo"],
                    range=[BEFORE_COLOR, AFTER_COLOR],
                ),
                title="",
            ),
            column=alt.Column(
                "Scenario:N",
                title="",
                header=alt.Header(labelOrient="bottom", labelAngle=0),
            ),
            tooltip=["Scenario", "KPI", alt.Tooltip("Valore:Q", format=".1f")],
        )
        .properties(height=260)
    )
    st.altair_chart(apq_chart, use_container_width=True)

with right_col:
    st.subheader("Fermate per categoria (base)")

    df_dt_long = df_downtime.melt(
        id_vars="Categoria",
        value_vars=["Prima", "Dopo"],
        var_name="Scenario",
        value_name="Minuti",
    )

    dt_chart = (
        alt.Chart(df_dt_long)
        .mark_bar()
        .encode(
            x=alt.X("Categoria:N", title="", axis=alt.Axis(labelAngle=20)),
            y=alt.Y("Minuti:Q", title="Minuti di fermo"),
            color=alt.Color(
                "Scenario:N",
                scale=alt.Scale(
                    domain=["Prima", "Dopo"],
                    range=[BEFORE_COLOR, AFTER_COLOR],
                ),
                title="",
            ),
            tooltip=["Categoria", "Scenario", "Minuti"],
        )
        .properties(height=260)
    )
    st.altair_chart(dt_chart, use_container_width=True)

# ----------------- RIGA 2: PARETO + WATERFALL + FUNNEL -----------------
st.markdown("---")
st.subheader("Dove intervenire e quanto vale")

pareto_col, waterfall_col, funnel_col = st.columns(3)

# ---- Pareto downtime ----
with pareto_col:
    st.caption("Pareto fermate (prima)")

    df_pareto = df_downtime[["Categoria", "Dopo"]].rename(columns={"Dopo": "Minuti"})
    df_pareto = df_pareto.sort_values("Minuti", ascending=False)
    df_pareto["Cumulata"] = df_pareto["Minuti"].cumsum()
    df_pareto["Perc"] = df_pareto["Minuti"] / df_pareto["Minuti"].sum() * 100
    df_pareto["PercCum"] = df_pareto["Perc"].cumsum()

    bars = (
        alt.Chart(df_pareto)
        .mark_bar()
        .encode(
            x=alt.X("Categoria:N", sort=list(df_pareto["Categoria"]), title=""),
            y=alt.Y("Minuti:Q", title="Minuti di fermo"),
            tooltip=[
                "Categoria",
                alt.Tooltip("Minuti:Q", format=".0f"),
                alt.Tooltip("Perc:Q", format=".1f"),
            ],
            color=alt.value(BEFORE_COLOR),
        )
    )

    line = (
        alt.Chart(df_pareto)
        .mark_line(point=True, color=AFTER_COLOR)
        .encode(
            x=alt.X("Categoria:N", sort=list(df_pareto["Categoria"])),
            y=alt.Y("PercCum:Q", title="Cumulata (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                "Categoria",
                alt.Tooltip("PercCum:Q", format=".1f"),
            ],
        )
    )

    pareto_chart = alt.layer(bars, line).resolve_scale(y="independent").properties(height=260)
    st.altair_chart(pareto_chart, use_container_width=True)

# ---- Waterfall perdita → margine ----
with waterfall_col:
    st.caption("Waterfall perdita di margine (periodo)")

    # breakdown molto semplice tra A / P / Q
    perdita_A = ore_periodo * (1 - base_A) * costo_ora_linea
    perdita_P = ore_periodo * base_A * (1 - base_P) * costo_ora_linea
    perdita_Q = ore_periodo * base_A * base_P * (1 - base_Q) * costo_ora_linea
    margine_potenziale = ore_periodo * costo_ora_linea
    margine_effettivo = margine_potenziale - (perdita_A + perdita_P + perdita_Q)

    wf_data = [
        {"label": "Potenziale", "amount": margine_potenziale},
        {"label": "Perdita A", "amount": -perdita_A},
        {"label": "Perdita P", "amount": -perdita_P},
        {"label": "Perdita Q", "amount": -perdita_Q},
        {"label": "Effettivo", "amount": margine_effettivo},
    ]
    wf_df = pd.DataFrame(wf_data)

    wf_df["pos"] = wf_df["amount"].cumsum() - wf_df["amount"]
    wf_df["pos_end"] = wf_df["pos"] + wf_df["amount"]

    color_cond = alt.condition(
        alt.datum.amount < 0,
        alt.value(BEFORE_COLOR),
        alt.value(AFTER_COLOR),
    )

    wf_chart = (
        alt.Chart(wf_df)
        .mark_bar()
        .encode(
            x=alt.X("label:O", title=""),
            y=alt.Y("pos:Q", title="€", axis=alt.Axis(format=",.0f")),
            y2="pos_end:Q",
            color=color_cond,
            tooltip=[
                "label",
                alt.Tooltip("amount:Q", format=",.0f"),
            ],
        )
        .properties(height=260)
    )

    st.altair_chart(wf_chart, use_container_width=True)

# ---- Funnel capacità → cash ----
with funnel_col:
    st.caption("Funnel capacità → valore")

    tempo_calendario = ore_periodo
    tempo_disponibile = ore_periodo * base_A
    tempo_buono = ore_periodo * base_oee
    margine_effettivo_funnel = tempo_buono * costo_ora_linea

    funnel_df = pd.DataFrame(
        {
            "Fase": ["Tempo calendario", "Tempo disponibile", "Tempo buono", "Margine effettivo"],
            "Valore": [tempo_calendario, tempo_disponibile, tempo_buono, margine_effettivo_funnel],
            "Tipo": ["Tempo", "Tempo", "Tempo", "€"],
        }
    )

    funnel_chart = (
        alt.Chart(funnel_df)
        .mark_bar()
        .encode(
            x=alt.X("Fase:N", sort=["Tempo calendario", "Tempo disponibile", "Tempo buono", "Margine effettivo"], title=""),
            y=alt.Y("Valore:Q", title="Valore"),
            color=alt.Color(
                "Tipo:N",
                scale=alt.Scale(
                    domain=["Tempo", "€"],
                    range=[BEFORE_COLOR, AFTER_COLOR],
                ),
                title="",
            ),
            tooltip=[
                "Fase",
                alt.Tooltip("Valore:Q", format=",.1f"),
            ],
        )
        .properties(height=260)
    )

    st.altair_chart(funnel_chart, use_container_width=True)

# --- Tabella riepilogo a tutta larghezza ---
st.markdown("---")
st.subheader("Riepilogo KPI OEE")

styled_df = (
    df_apq.set_index("Scenario")[["Availability", "Performance", "Quality", "OEE"]]
    .style.format("{:.1%}")
)
st.dataframe(styled_df, use_container_width=True)