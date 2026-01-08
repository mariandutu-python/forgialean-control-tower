from sqlmodel import select
from db import TaxConfig, get_session, init_db

def seed_taxconfig_for_year(year: int):
    # assicura che tutte le tabelle (inclusa TaxConfig) esistano
    init_db()

    with get_session() as session:
        existing = session.exec(
            select(TaxConfig).where(TaxConfig.year == year)
        ).first()
        if existing:
            print(f"TaxConfig per l'anno {year} già presente.")
            print(f"  Regime: {existing.regime}")
            print(f"  Aliquota imposta: {existing.aliquota_imposta * 100}%")
            print(f"  Aliquota INPS: {existing.aliquota_inps * 100}%")
            print(f"  Reddività forfettario: {existing.redditivita_forfettario * 100}%")
            return

        cfg = TaxConfig(
            year=year,
            regime="forfettario",
            aliquota_imposta=0.15,       # 15% imposta sostitutiva ordinaria
            aliquota_inps=0.2607,        # 26,07% Gestione Separata INPS 2026
            redditivita_forfettario=0.78 # 78% coefficiente ATECO 74.90.99 (consulenza tecnica)
        )
        session.add(cfg)
        session.commit()
        print(f"Creata TaxConfig per l'anno {year}:")
        print(f"  Regime: forfettario")
        print(f"  Aliquota imposta: 15% (ordinaria)")
        print(f"  Aliquota INPS Gestione Separata: 26,07%")
        print(f"  Coefficiente redditività ATECO 74.90.99: 78%")

if __name__ == "__main__":
    seed_taxconfig_for_year(2026)