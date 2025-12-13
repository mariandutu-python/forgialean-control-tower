from db import engine
import sqlalchemy as sa

with engine.begin() as conn:
    conn.execute(sa.text("ALTER TABLE client ADD COLUMN email TEXT"))
    print("Colonna email aggiunta alla tabella client.")
