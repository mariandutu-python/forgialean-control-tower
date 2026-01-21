# flux_shuttle_dual_mode.py
# SPC Dual Mode: TURNO + VALIDAZIONE PROGRAMMI CERTIFICATI EN9100+
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta
import sqlite3

st.set_page_config(
    page_title="Flux Shuttle SPC - Dual Mode",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# DATABASE SPC DUAL MODE
# =============================================================================
@st.cache_resource
def init_db():
    conn = sqlite3.connect('flux_spc_dual.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS flux_tests (
            id INTEGER PRIMARY KEY,
            test_type TEXT,  -- 'TURNO' o 'PROGRAMMA'
            timestamp TEXT,
            program_id TEXT,
            conveyor_speed REAL,
            flux_rate_ml_min REAL,
            pcb_width_cm REAL DEFAULT 40.0,
            target_ml_cm2 REAL,
            measured_ml_cm2 REAL,
            deviation_pct REAL,
            thickness_um1 REAL, thickness_um2 REAL, thickness_um3 REAL, thickness_um4 REAL,
            uniformity_pct REAL,
            cpk REAL,
            status TEXT,
            certification_level TEXT DEFAULT 'ISO9001'
        )
    ''')
    return conn

# =============================================================================
# TABS DUAL MODE
# =============================================================================
tab1, tab2, tab3 = st.tabs(["🎛️ **VERIFICA TURNO**", "⚙️ **VALIDAZIONE PROGRAMMA**", "📊 **SPC DASHBOARD**"])

# =============================================================================
# TAB 1: VERIFICA TURNO STANDARD (Inizio ogni turno)
# =============================================================================
with tab1:
    st.markdown("## **VERIFICA STABILITÀ MACCHINA - INIZIO TURNO**")
    st.info("**Esegui ogni inizio turno per verificare stabilità flussatura**")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        turno = st.selectbox("Turno", ["Mattina", "Pomeriggio", "Notte"], key="turno")
    with col2:
        std_program = f"STD_TURNO_{turno[:3].upper()}"
        st.info(f"**Programma Standard**: {std_program}")
    with col3:
        st.metric("**Target Fisso**", "0.015 ml/cm²")
    
    if st.button("🚀 **TEST TURNO STANDARD**", type="primary", use_container_width=True):
        with st.spinner("Test stabilità macchina in corso..."):
            # PARAMETRI TURNO STANDARD
            target_ml_cm2 = 0.015  # 30ml/min @ 100cm/min
            measured_ml_cm2 = target_ml_cm2 + np.random.normal(0, 0.0012)
            thickness_um = np.random.normal(1.2, 0.18, 4)
            uniformity_pct = min(thickness_um)/max(thickness_um)*100
            deviation_pct = (measured_ml_cm2 - target_ml_cm2)/target_ml_cm2 * 100
            
            # SALVA TURNO
            conn = init_db()
            conn.execute('''
                INSERT INTO flux_tests (test_type, timestamp, program_id, conveyor_speed, 
                flux_rate_ml_min, target_ml_cm2, measured_ml_cm2, deviation_pct,
                thickness_um1, thickness_um2, thickness_um3, thickness_um4, 
                uniformity_pct, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('TURNO', datetime.now().isoformat(), std_program, 100.0, 30.0,
                  target_ml_cm2, measured_ml_cm2, deviation_pct, *thickness_um, uniformity_pct,
                  "✅ PASS" if abs(deviation_pct)<8 and uniformity_pct>88 else "❌ FAIL"))
            conn.commit()
            conn.close()
            
            # RISULTATI TURNO
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Misurato", f"{measured_ml_cm2:.4f} ml/cm²", f"{deviation_pct:+.2f}%")
            col2.metric("Uniformità", f"{uniformity_pct:.1f}%")
            col3.metric("Stato", "✅ PASS" if abs(deviation_pct)<8 else "❌ FAIL")
            col4.success(f"Programma: {std_program}")

# =============================================================================
# TAB 2: VALIDAZIONE PROGRAMMI CERTIFICATI
# =============================================================================
with tab2:
    st.markdown("## **VALIDAZIONE PROGRAMMA CERTIFICATO**")
    st.warning("**EN9100 / IRIS / IATF - Validazione prima di produzione serie**")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        program_id = st.text_input("**ID Programma**", value="AERO_TIER1_001")
        cert_level = st.selectbox("**Livello Certificazione**", 
                                ["EN9100", "IRIS Ferroviario", "IATF Automotive", "ISO9001"])
    with col2:
        conveyor_speed = st.number_input("**Velocità Conveyor**", value=100.0, 
                                       min_value=50.0, max_value=150.0, suffix=" cm/min")
    with col3:
        flux_rate_ml_min = st.number_input("**Flux Rate**", value=30.0, 
                                         min_value=15.0, max_value=80.0, suffix=" ml/min")
    with col4:
        pcb_width = st.number_input("**Larghezza PCB**", value=40.0, 
                                  min_value=20.0, max_value=60.0, suffix=" cm")
    
    # TARGET DINAMICO
    target_ml_cm2 = flux_rate_ml_min / conveyor_speed
    st.metric("**Target Programma**", f"{target_ml_cm2:.4f} ml/cm²", 
              help="Flux Rate ÷ Conveyor Speed")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 **VALIDA PROGRAMMA**", type="primary", use_container_width=True):
            with st.spinner("Validazione certificato in corso..."):
                # MISURAZIONE SIMULATA
                measured_ml_cm2 = target_ml_cm2 + np.random.normal(0, target_ml_cm2*0.06)
                thickness_um = np.random.normal(1.2, 0.15, 4)
                uniformity_pct = min(thickness_um)/max(thickness_um)*100
                deviation_pct = (measured_ml_cm2 - target_ml_cm2)/target_ml_cm2 * 100
                
                # SALVA VALIDAZIONE
                conn = init_db()
                conn.execute('''
                    INSERT INTO flux_tests (test_type, timestamp, program_id, conveyor_speed,
                    flux_rate_ml_min, pcb_width_cm, target_ml_cm2, measured_ml_cm2,
                    deviation_pct, thickness_um1, thickness_um2, thickness_um3, thickness_um4,
                    uniformity_pct, certification_level, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('PROGRAMMA', datetime.now().isoformat(), program_id, conveyor_speed,
                      flux_rate_ml_min, pcb_width, target_ml_cm2, measured_ml_cm2,
                      deviation_pct, *thickness_um, uniformity_pct, cert_level,
                      "✅ CERTIFICATO" if abs(deviation_pct)<5 and uniformity_pct>90 else "❌ NON CONFORME"))
                conn.commit()
                conn.close()
                
                # RISULTATI CERTIFICAZIONE
                st.success("**VALIDAZIONE COMPLETATA**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Misurato", f"{measured_ml_cm2:.4f}", f"{deviation_pct:+.2f}%")
                col2.metric("Uniformità", f"{uniformity_pct:.1f}%")
                col3.metric("Stato Cert.", "✅ CERTIFICATO" if abs(deviation_pct)<5 else "❌ NON CONFORME")
                col4.metric("Livello", cert_level)

# =============================================================================
# TAB 3: DASHBOARD SPC COMPLETA
# =============================================================================
with tab3:
    st.markdown("# **📊 STATISTICAL PROCESS CONTROL - 7 GIORNI**")
    
    conn = init_db()
    df = pd.read_sql_query("SELECT * FROM flux_tests ORDER BY id DESC LIMIT 168", conn)  # 7gg
    conn.close()
    
    if not df.empty:
        # KPI AGGREGATI
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Test Totali", len(df))
        col2.metric("Pass Rate", f"{(df['status'].str.contains('✅').mean()*100):.1f}%")
        col3.metric("CpK Medio", f"{df['cpk'].mean():.2f}")
        col4.metric("Dev. Media", f"{df['deviation_pct'].abs().mean():.2f}%")
        
        # GRAFICI SPC PER TIPO TEST
        col1, col2 = st.columns(2)
        with col1:
            # XBAR-R PER TURNI
            turni = df[df['test_type']=='TURNO'].tail(24)
            if not turni.empty:
                fig = px.line(turni, x='timestamp', y='deviation_pct', 
                            title="**XBAR-R Chart - Verifiche Turno** (±8% spec limit)",
                            color='program_id')
                fig.add_hline(y=8, line_color="red", line_dash="dash")
                fig.add_hline(y=-8, line_color="red", line_dash="dash")
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # BOXPLOT CERTIFICAZIONI
            certs = df[df['test_type']=='PROGRAMMA']
            if not certs.empty:
                fig2 = px.box(certs, x='certification_level', y='deviation_pct',
                            title="**Deviazione per Livello Certificazione**")
                st.plotly_chart(fig2, use_container_width=True)
        
        # TABELLA COMPLETA
        st.markdown("### **📋 Traceability Completa - Ultimi 20 Test**")
        display_cols = ['timestamp', 'test_type', 'program_id', 'target_ml_cm2', 
                       'measured_ml_cm2', 'deviation_pct', 'uniformity_pct', 'status']
        df_display = df[display_cols].tail(20).round(4)
        df_display.columns = ['Data', 'Tipo', 'Programma', 'Target', 'Misurato', 
                            'Dev.%', 'Unif.%', 'Stato']
        st.dataframe(df_display, use_container_width=True)

# =============================================================================
# SIDEBAR OPERATIVA
# =============================================================================
with st.sidebar:
    st.markdown("## **OPERAZIONI SPC**")
    
    st.markdown("### **Tolleranze**")
    st.info("**TURNO**: ±8% | >88% uniformità")
    st.warning("**CERTIFICAZIONI**: ±5% | >90% uniformità")
    
    st.markdown("### **Frequenza**")
    st.success("✅ **TURNO**: Inizio ogni turno")
    st.info("🔍 **PROGRAMMA**: Cambio setup/certificazione")
    
    if st.button("**🗑️ RESET DB**", type="secondary"):
        init_db().execute("DELETE FROM flux_tests").fetchall()
        st.rerun()

# FOOTER
st.markdown("---")
st.markdown("<p style='text-align: center; color: #6b7280;'>Flux Shuttle SPC Dual Mode | EN9100 / IRIS Process Control</p>", 
            unsafe_allow_html=True)