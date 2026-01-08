from sqlmodel import select
from db import TaxConfig, get_session

def seed_taxconfig_for_year(year: int):
    with get_session() as session:
        existing = session.exec(
            select(TaxConfig).where(TaxConfig.year == year)
        ).first()
        if existing:
            print(f"TaxConfig per l'anno {year} già presente.")
            return

        cfg = TaxConfig(
            year=year,
            regime="forfettario",        # o "ordinario"
            aliquota_imposta=0.15,       # esempio
            aliquota_inps=0.26,          # esempio
            redditivita_forfettario=0.78 # esempio
        )
        session.add(cfg)
        session.commit()
        print(f"Creata TaxConfig per l'anno {year}.")

if __name__ == "__main__":
    seed_taxconfig_for_year(2026)   # metti qui l'anno che usi in "Anno di analisi"