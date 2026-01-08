# finance_utils.py
from datetime import date
import pandas as pd

from db import get_session, Invoice, Expense, TaxDeadline, TaxConfig, InpsContribution
from sqlmodel import select
def build_full_management_balance(year: int, ref_date: date, saldo_cassa: float) -> dict:
    """
    Restituisce:
      - 'stato_patrimoniale': DataFrame con Attivo/Passivo gestionale alla data ref_date
      - 'conto_economico': DataFrame con Ricavi/Costi/INPS/Imposte/Utile dell'anno 'year'
      - 'indicatori': DataFrame con alcuni KPI di bilancio
    """
    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()
        expenses = session.exec(select(Expense)).all()
        deadlines = session.exec(
            select(TaxDeadline).where(TaxDeadline.year == year)
        ).all()

    # =========================
    # 1) CONTO ECONOMICO GESTIONALE (anno)
    # =========================
    df_inv = pd.DataFrame([i.__dict__ for i in (invoices or [])])
    df_exp = pd.DataFrame([e.__dict__ for e in (expenses or [])])

    # --- Ricavi (fatture incassate o almeno emesse nell'anno) ---
    ricavi = 0.0
    if not df_inv.empty:
        df_inv["data_rif"] = pd.to_datetime(
            df_inv["data_incasso"].fillna(df_inv["data_fattura"]),
            errors="coerce",
        )
        df_inv = df_inv.dropna(subset=["data_rif"])
        df_inv["anno"] = df_inv["data_rif"].dt.year
        ricavi = float(
            df_inv.loc[df_inv["anno"] == year, "importo_totale"].sum()
        )

    # --- Costi di esercizio (spese pagate o almeno datate nell'anno) ---
    costi = 0.0
    if not df_exp.empty:
        df_exp["data_rif"] = pd.to_datetime(
            df_exp["data_pagamento"].fillna(df_exp["data"]),
            errors="coerce",
        )
        df_exp = df_exp.dropna(subset=["data_rif"])
        df_exp["anno"] = df_exp["data_rif"].dt.year
        costi = float(
            df_exp.loc[df_exp["anno"] == year, "importo_totale"].sum()
        )

    # --- Imposte & INPS (da TaxDeadline per l'anno selezionato) ---
    imposte = 0.0
    inps = 0.0
    for d in (deadlines or []):
        tipo = (d.type or "").lower()
        if "imposta" in tipo or "tasse" in tipo or "irpef" in tipo:
            imposte += d.amount_paid or 0.0 if d.amount_paid else d.estimated_amount or 0.0
        if "inps" in tipo or "gestione separata" in tipo:
            inps += d.amount_paid or 0.0 if d.amount_paid else d.estimated_amount or 0.0

    # --- Utile netto gestionale ---
    utile_lordo = ricavi - costi
    utile_netto = utile_lordo - imposte - inps

    df_ce = pd.DataFrame(
        [
            {"Voce": "Ricavi", "Importo": ricavi},
            {"Voce": "Costi di esercizio", "Importo": -costi},
            {"Voce": "Imposte", "Importo": -imposte},
            {"Voce": "Contributi INPS", "Importo": -inps},
            {"Voce": "Utile netto gestionale", "Importo": utile_netto},
        ]
    )

    # =========================
    # 2) STATO PATRIMONIALE GESTIONALE (alla data ref_date)
    # =========================

    # --- Cassa/banche: usiamo il saldo passato dalla UI ---
    att_cassa = float(saldo_cassa)

    # --- Crediti verso clienti (fatture emesse non ancora incassate alla data) ---
    crediti_clienti = 0.0
    if not df_inv.empty:
        # rifacciamo df_inv pulito per la parte "aperto"
        df_inv_sp = pd.DataFrame([i.__dict__ for i in (invoices or [])])
        df_inv_sp["data_fattura"] = pd.to_datetime(df_inv_sp["data_fattura"], errors="coerce")
        df_inv_sp["data_incasso"] = pd.to_datetime(df_inv_sp["data_incasso"], errors="coerce")

        # fatture emesse fino alla ref_date
        df_emesse = df_inv_sp[
            df_inv_sp["data_fattura"].notna()
            & (df_inv_sp["data_fattura"] <= pd.to_datetime(ref_date))
        ].copy()

        # Incassate prima della ref_date → non più credito
        df_emesse["incassata_prima"] = (
            df_emesse["data_incasso"].notna()
            & (df_emesse["data_incasso"] <= pd.to_datetime(ref_date))
        )

        crediti_clienti = float(
            df_emesse.loc[~df_emesse["incassata_prima"], "importo_totale"].sum()
        )

    # --- Debiti verso fornitori (spese non ancora pagate alla data) ---
    debiti_fornitori = 0.0
    if not df_exp.empty:
        df_exp_sp = pd.DataFrame([e.__dict__ for e in (expenses or [])])
        df_exp_sp["data"] = pd.to_datetime(df_exp_sp["data"], errors="coerce")
        df_exp_sp["data_pagamento"] = pd.to_datetime(df_exp_sp["data_pagamento"], errors="coerce")

        df_spese = df_exp_sp[
            df_exp_sp["data"].notna()
            & (df_exp_sp["data"] <= pd.to_datetime(ref_date))
        ].copy()
        df_spese["pagata_prima"] = (
            df_spese["pagata"]
            & df_spese["data_pagamento"].notna()
            & (df_spese["data_pagamento"] <= pd.to_datetime(ref_date))
        )

        debiti_fornitori = float(
            df_spese.loc[~df_spese["pagata_prima"], "importo_totale"].sum()
        )

    # --- Debiti fiscali & INPS residui (scadenze planned/partial dopo ref_date) ---
    debiti_fisco_inps = 0.0
    for d in (deadlines or []):
        # se la scadenza è successiva alla ref_date, la consideriamo debito residuo
        if d.due_date and d.due_date > ref_date:
            residuo = (d.estimated_amount or 0.0) - (d.amount_paid or 0.0)
            if residuo > 0:
                debiti_fisco_inps += residuo

    # --- Patrimonio netto gestionale (Attivo - Passivo) ---
    attivo_tot = att_cassa + crediti_clienti
    passivo_tot = debiti_fornitori + debiti_fisco_inps
    patrimonio_netto = attivo_tot - passivo_tot

    df_sp = pd.DataFrame(
        [
            {"Sezione": "Attivo", "Voce": "Cassa e conti", "Importo": att_cassa},
            {"Sezione": "Attivo", "Voce": "Crediti verso clienti", "Importo": crediti_clienti},
            {"Sezione": "Passivo", "Voce": "Debiti verso fornitori", "Importo": debiti_fornitori},
            {"Sezione": "Passivo", "Voce": "Debiti fiscali e INPS", "Importo": debiti_fisco_inps},
            {"Sezione": "Patrimonio netto", "Voce": "Patrimonio netto gestionale", "Importo": patrimonio_netto},
        ]
    )

    # =========================
    # 3) INDICATORI DI BILANCIO
    # =========================
    margine_lordo = ricavi - costi
    margine_perc = (margine_lordo / ricavi * 100.0) if ricavi > 0 else 0.0
    peso_inps_imposte_su_ricavi = (
        (imposte + inps) / ricavi * 100.0 if ricavi > 0 else 0.0
    )
    # Capitale circolante netto = (Cassa + Crediti) - (Debiti fornitori + Debiti fisco/INPS)
    ccn = attivo_tot - passivo_tot
    # Posizione finanziaria netta "artigianale" = Debiti totali - Cassa
    pfn = passivo_tot - att_cassa

    df_ind = pd.DataFrame(
        [
            {"Indicatore": "Ricavi", "Valore": ricavi},
            {"Indicatore": "Costi di esercizio", "Valore": costi},
            {"Indicatore": "Margine lordo", "Valore": margine_lordo},
            {"Indicatore": "Margine lordo % su ricavi", "Valore": margine_perc},
            {"Indicatore": "Imposte + INPS", "Valore": imposte + inps},
            {"Indicatore": "Peso imposte+INPS su ricavi %", "Valore": peso_inps_imposte_su_ricavi},
            {"Indicatore": "Utile netto gestionale", "Valore": utile_netto},
            {"Indicatore": "Capitale circolante netto", "Valore": ccn},
            {"Indicatore": "Posizione finanziaria netta (semplificata)", "Valore": pfn},
        ]
    )

    return {
        "stato_patrimoniale": df_sp,
        "conto_economico": df_ce,
        "indicatori": df_ind,
    }

def calcola_imposte_e_inps_normative(year: int) -> dict:
    """
    Calcolo 'normativo' semplificato di reddito, imposta e INPS per l'anno.
    """
    with get_session() as session:
        cfg = session.exec(
            select(TaxConfig).where(TaxConfig.year == year)
        ).first()

        # se manca la TaxConfig, la creo di default invece di restituire errore
        if cfg is None:
            cfg = TaxConfig(
                year=year,
                regime="forfettario",        # oppure "ordinario"
                aliquota_imposta=0.15,       # metti i tuoi valori reali
                aliquota_inps=0.26,
                redditivita_forfettario=0.78,
            )
            session.add(cfg)
            session.commit()

        invoices = session.exec(select(Invoice)).all()
        expenses = session.exec(select(Expense)).all()
        deadlines = session.exec(
            select(TaxDeadline).where(TaxDeadline.year == year)
        ).all()
        inps_rows = session.exec(
            select(InpsContribution).where(InpsContribution.year == year)
        ).all()


    regime = (cfg.regime or "").lower()

    df_inv = pd.DataFrame([i.__dict__ for i in (invoices or [])])
    ricavi_fiscali = 0.0
    if not df_inv.empty:
        df_inv["data_rif"] = pd.to_datetime(
            df_inv["data_incasso"].fillna(df_inv["data_fattura"]),
            errors="coerce",
        )
        df_inv = df_inv.dropna(subset=["data_rif"])
        df_inv["anno"] = df_inv["data_rif"].dt.year
        ricavi_fiscali = float(
            df_inv.loc[df_inv["anno"] == year, "importo_totale"].sum()
        )

    df_exp = pd.DataFrame([e.__dict__ for e in (expenses or [])])
    costi_fiscali = 0.0
    if regime == "ordinario" and not df_exp.empty:
        df_exp["data_rif"] = pd.to_datetime(
            df_exp["data_pagamento"].fillna(df_exp["data"]),
            errors="coerce",
        )
        df_exp = df_exp.dropna(subset=["data_rif"])
        df_exp["anno"] = df_exp["data_rif"].dt.year
        costi_fiscali = float(
            df_exp.loc[df_exp["anno"] == year, "importo_totale"].sum()
        )

    redditivita = cfg.redditivita_forfettario or 1.0

    if regime == "forfettario":
        reddito_imponibile = ricavi_fiscali * redditivita
    else:
        reddito_imponibile = ricavi_fiscali - costi_fiscali

    aliquota_imposta = cfg.aliquota_imposta or 0.0
    imposta_dovuta = max(reddito_imponibile, 0.0) * aliquota_imposta

    aliquota_inps = cfg.aliquota_inps or 0.0
    base_inps = max(reddito_imponibile, 0.0)
    inps_dovuti = base_inps * aliquota_inps

    imposte_registrate = 0.0
    for d in (deadlines or []):
        tipo = (d.type or "").lower()
        if "imposta" in tipo or "tasse" in tipo or "irpef" in tipo:
            if d.amount_paid:
                imposte_registrate += d.amount_paid
            else:
                imposte_registrate += d.estimated_amount or 0.0

    inps_registrati = 0.0
    for r in (inps_rows or []):
        if r.amount_paid:
            inps_registrati += r.amount_paid
        else:
            inps_registrati += r.amount_due or 0.0

    return {
        "year": year,
        "regime": regime,
        "ricavi_fiscali": ricavi_fiscali,
        "costi_fiscali": costi_fiscali,
        "redditivita_forfettario": redditivita if regime == "forfettario" else None,
        "reddito_imponibile": reddito_imponibile,
        "aliquota_imposta": aliquota_imposta,
        "imposta_dovuta": imposta_dovuta,
        "base_inps": base_inps,
        "aliquota_inps": aliquota_inps,
        "inps_dovuti": inps_dovuti,
        "imposte_registrate": imposte_registrate,
        "inps_registrati": inps_registrati,
    }