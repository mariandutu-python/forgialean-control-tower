# file: clear_clienti.py
import sqlite3
import os

db_path = os.path.join("data", "forgialean.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("DELETE FROM client")  # nome tabella corretto
conn.commit()
conn.close()
print("Tabella client svuotata.")
