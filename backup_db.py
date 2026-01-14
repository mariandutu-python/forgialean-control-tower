# backup_db.py
"""
Script per backup automatico del database SQLite.
Usato da GitHub Actions ogni notte.
"""
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/forgialean.db")
BACKUP_DIR = Path("db_backups")
BACKUP_DIR.mkdir(exist_ok=True)

if DB_PATH.exists():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"forgialean_backup_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name
    
    shutil.copy2(DB_PATH, backup_path)
    
    # Mantieni anche copia "latest" per restore facile
    latest_path = BACKUP_DIR / "forgialean_latest.db"
    shutil.copy2(DB_PATH, latest_path)
    
    print(f"✅ Backup creato: {backup_path}")
    print(f"✅ Latest aggiornato: {latest_path}")
else:
    print("⚠️ Database non trovato, nessun backup creato")