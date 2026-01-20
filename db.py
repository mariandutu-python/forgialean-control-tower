from typing import Optional, List
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Column, DateTime
from sqlmodel import SQLModel, Field, Relationship, create_engine, Session, select

# =========================
# PATH DB IN CARTELLA SCRIVIBILE
# =========================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SQLITE_FILE_NAME = DATA_DIR / "forgialean.db"
SQLITE_URL = f"sqlite:///{SQLITE_FILE_NAME}"

engine = create_engine(SQLITE_URL, echo=False)

# PULIZIA METADATA per evitare "Table ... is already defined"
SQLModel.metadata.clear()

# =========================
# MODELLI
# =========================

class Client(SQLModel, table=True):
    client_id: Optional[int] = Field(default=None, primary_key=True)
    ragione_sociale: str
    email: Optional[str] = None
    piva: Optional[str] = None
    cod_fiscale: Optional[str] = None
    settore: Optional[str] = None
    paese: Optional[str] = None
    canale_acquisizione: Optional[str] = None
    segmento_cliente: Optional[str] = None
    data_creazione: Optional[date] = None
    stato_cliente: Optional[str] = None  # attivo, prospect, perso

    # ▼ FATTURAZIONE ELETTRONICA ▼
    indirizzo: Optional[str] = None       # Via e numero civico
    cap: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None       # es. "BO"
    codice_destinatario: Optional[str] = None
    pec_fatturazione: Optional[str] = None

class MarketingCampaign(SQLModel, table=True):
    """Campagne marketing collegate a opportunità e spese (per CAC/ROI)."""
    campaign_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    tipo: Optional[str] = Field(
        default=None,
        description="es. ads, email, referral, evento"
    )
    canale: Optional[str] = Field(
        default=None,
        description="es. google_ads, meta_ads, linkedin, email, organico"
    )
    data_inizio: Optional[date] = None
    data_fine: Optional[date] = None
    budget_previsto: Optional[float] = Field(default=0.0)
    note: Optional[str] = None

    # relazioni logiche (non obbligatorie ma utili)
    opportunities: List["Opportunity"] = Relationship(back_populates="campaign")
    expenses: List["Expense"] = Relationship(back_populates="campaign")

class Opportunity(SQLModel, table=True):
    opportunity_id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.client_id")

    nome_opportunita: str
    fase_pipeline: Optional[str] = None  # Lead, Offerta, Negoziazione, Vinta, Persa
    owner: Optional[str] = None

    valore_stimato: Optional[float] = 0.0
    probabilita: Optional[float] = 0.0
    data_apertura: Optional[date] = None
    data_chiusura_prevista: Optional[date] = None

    data_prossima_azione: Optional[date] = None
    tipo_prossima_azione: Optional[str] = None
    note_prossima_azione: Optional[str] = None

    stato_opportunita: Optional[str] = "aperta"
    note: Optional[str] = None

    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None

    # collegamento (opzionale) a campagna marketing
    campaign_id: Optional[int] = Field(default=None, foreign_key="marketingcampaign.campaign_id")
    campaign: Optional[MarketingCampaign] = Relationship(back_populates="opportunities")

    # gamification
    flame_points: int = Field(default=0)

    # gamification
    flame_points: int = Field(default=0)
    form_oee_completed: bool = Field(default=False)
    form_call_completed: bool = Field(default=False)
    demo_scheduled: bool = Field(default=False)
    contract_sent: bool = Field(default=False)
    contract_signed: bool = Field(default=False)
    date_form_oee: Optional[date] = Field(default=None)
    date_form_call: Optional[date] = Field(default=None)
    date_demo: Optional[date] = Field(default=None)
    date_contract_sent: Optional[date] = Field(default=None)
    date_contract_signed: Optional[date] = Field(default=None)

    # telefono specifico dell’opportunità (es. form OEE / call)
    telefono_contatto: Optional[str] = Field(default=None)

    # relationship con task CRM
    tasks: list["CrmTask"] = Relationship(back_populates="opportunity")

    # relationship con attività CRM (log chiamate/email/meeting)
    activities: list["CrmActivity"] = Relationship(back_populates="opportunity")


class CrmTask(SQLModel, table=True):
    """Task operativi collegati alle opportunità CRM."""
    task_id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.opportunity_id")

    titolo: str
    tipo: Optional[str] = None  # es. "chiamata", "email", "demo"
    data_scadenza: date
    ora_scadenza: Optional[str] = None  # opzionale, formato "HH:MM"

    stato: str = "da_fare"  # "da_fare", "fatto", "posticipato"
    note: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    opportunity: Optional[Opportunity] = Relationship(back_populates="tasks")


class CrmActivity(SQLModel, table=True):
    """Log attività (chiamate, email, meeting, note) collegati a un'opportunità."""
    activity_id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.opportunity_id")

    tipo: str  # es. "chiamata", "email", "meeting", "whatsapp", "nota"
    canale: Optional[str] = None  # es. "telefono", "gmail", "whatsapp", "linkedin"
    oggetto: Optional[str] = None
    descrizione: Optional[str] = None

    esito: Optional[str] = None  # es. "risposta", "non_risponde", "rimandare", "interessato"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # opzionale: data/ora specifica attività se diversa da created_at
    data_attivita: Optional[date] = None

    opportunity: Optional[Opportunity] = Relationship(back_populates="activities")


def sync_next_action_from_tasks(opportunity_id: int) -> None:
    """Aggiorna i campi 'prossima azione' dell'opportunità in base ai task aperti."""
    with Session(engine) as session:
        opp = session.get(Opportunity, opportunity_id)
        if not opp:
            return

        tasks_open = session.exec(
            select(CrmTask)
            .where(CrmTask.opportunity_id == opportunity_id)
            .where(CrmTask.stato == "da_fare")
            .order_by(CrmTask.data_scadenza, CrmTask.created_at)
        ).all()

        if not tasks_open:
            opp.data_prossima_azione = None
            opp.tipo_prossima_azione = None
            opp.note_prossima_azione = None
        else:
            next_task = tasks_open[0]
            opp.data_prossima_azione = next_task.data_scadenza
            opp.tipo_prossima_azione = next_task.tipo or "Attività"
            opp.note_prossima_azione = next_task.titolo

        session.add(opp)
        session.commit()


class Invoice(SQLModel, table=True):
    invoice_id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.client_id")
    num_fattura: str
    data_fattura: Optional[date] = None
    data_scadenza: Optional[date] = None
    importo_imponibile: Optional[float] = 0.0
    iva: Optional[float] = 0.0
    importo_totale: Optional[float] = 0.0
    stato_pagamento: Optional[str] = None  # emessa, incassata, scaduta, parzialmente_incassata
    data_incasso: Optional[date] = None

    # collegamento a commessa/fase (opzionale)
    commessa_id: Optional[int] = Field(default=None, foreign_key="projectcommessa.commessa_id")
    fase_id: Optional[int] = Field(default=None, foreign_key="taskfase.fase_id")

    # relazione con i pagamenti
    payments: list["Payment"] = Relationship(back_populates="invoice")

    @property
    def amount_paid(self) -> float:
        return sum(p.amount for p in (self.payments or []))

    @property
    def amount_open(self) -> float:
        return (self.importo_totale or 0.0) - self.amount_paid


class Payment(SQLModel, table=True):
    payment_id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.invoice_id")
    payment_date: date
    amount: float
    method: str  # es. bonifico, contanti, carta
    note: Optional[str] = None

    invoice: Optional[Invoice] = Relationship(back_populates="payments")


class ProjectCommessa(SQLModel, table=True):
    commessa_id: Optional[int] = Field(default=None, primary_key=True)
    cod_commessa: str
    descrizione_cliente: Optional[str] = None
    stato_commessa: Optional[str] = None
    data_inizio: Optional[date] = None
    data_fine_prevista: Optional[date] = None
    data_fine_effettiva: Optional[date] = None
    ore_previste: Optional[float] = 0.0
    ore_consumate: Optional[float] = 0.0
    costo_previsto: Optional[float] = 0.0
    costo_consuntivo: Optional[float] = 0.0


class TaskFase(SQLModel, table=True):
    fase_id: Optional[int] = Field(default=None, primary_key=True)
    commessa_id: int = Field(foreign_key="projectcommessa.commessa_id")
    nome_fase: str
    stato_fase: Optional[str] = None
    data_inizio: Optional[date] = None
    data_fine_prevista: Optional[date] = None
    data_fine_effettiva: Optional[date] = None
    ore_previste: Optional[float] = 0.0
    ore_consumate: Optional[float] = 0.0
    risorsa_responsabile: Optional[str] = None


class TimeEntry(SQLModel, table=True):
    entry_id: Optional[int] = Field(default=None, primary_key=True)
    commessa_id: int = Field(foreign_key="projectcommessa.commessa_id")
    fase_id: int = Field(foreign_key="taskfase.fase_id")
    data_lavoro: date
    ore: float
    operatore: Optional[str] = None


class Department(SQLModel, table=True):
    department_id: Optional[int] = Field(default=None, primary_key=True)
    nome_reparto: str
    descrizione: Optional[str] = None
    responsabile: Optional[str] = None


class Employee(SQLModel, table=True):
    employee_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    cognome: str
    ruolo: Optional[str] = None
    department_id: int = Field(foreign_key="department.department_id")
    data_assunzione: Optional[date] = None
    stato: Optional[str] = None  # attivo, non attivo


class KpiDepartmentTimeseries(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    department_id: int = Field(foreign_key="department.department_id")
    data: date
    kpi_name: str
    valore: float
    target: float
    unita: str


class KpiEmployeeTimeseries(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.employee_id")
    data: date
    kpi_name: str
    valore: float
    target: float
    unita: str


class LoginEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    channel: Optional[str] = None  # es: "Demo LinkedIn"
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True))
    )


class TaxConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    regime: str  # "forfettario", "ordinario"
    aliquota_imposta: float  # es. 0.15
    aliquota_inps: float     # es. 0.26
    redditivita_forfettario: Optional[float] = None  # es. 0.78


class InpsContribution(SQLModel, table=True):
    contribution_id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    due_date: date
    amount_due: float
    amount_paid: float = 0.0
    payment_date: Optional[date] = None
    description: str
    status: str = "planned"  # planned / paid / partial


class TaxDeadline(SQLModel, table=True):
    deadline_id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    due_date: date
    type: str  # "saldo imposta", "acconto 1 imposta", "CU", ecc.
    estimated_amount: float = 0.0
    amount_paid: float = 0.0
    payment_date: Optional[date] = None
    status: str = "planned"  # planned / paid / partial
    note: Optional[str] = None


class InvoiceTransmission(SQLModel, table=True):
    transmission_id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.invoice_id")
    xml_file_name: str
    upload_date: date
    sdi_status: str      # uploaded / sent / delivered / rejected
    sdi_message: Optional[str] = None
    sdi_protocol: Optional[str] = None


class Vendor(SQLModel, table=True):
    """Fornitori (contabilità passiva)"""
    vendor_id: Optional[int] = Field(default=None, primary_key=True)
    ragione_sociale: str
    email: Optional[str] = None
    piva: Optional[str] = None
    cod_fiscale: Optional[str] = None
    settore: Optional[str] = None
    paese: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None
    note: Optional[str] = None


class ExpenseCategory(SQLModel, table=True):
    """Categorie di costo (es. software, viaggi, formazione, affitti, ecc.)"""
    category_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str                # es. "Software", "Viaggi", "Formazione"
    descrizione: Optional[str] = None
    deducibilita_perc: Optional[float] = 1.0  # 1.0 = 100% deducibile


class Account(SQLModel, table=True):
    """Conti finanziari (conto corrente, carta, cassa, ecc.)"""
    account_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str                    # es. "Conto corrente Intesa", "Carta credito"
    tipo: str                    # "bank", "card", "cash", "paypal", ...
    saldo_iniziale: float = 0.0
    valuta: str = "EUR"
    note: Optional[str] = None


class Expense(SQLModel, table=True):
    """Spese / contabilità passiva light"""
    expense_id: Optional[int] = Field(default=None, primary_key=True)
    data: date
    vendor_id: Optional[int] = Field(default=None, foreign_key="vendor.vendor_id")
    category_id: Optional[int] = Field(default=None, foreign_key="expensecategory.category_id")
    account_id: Optional[int] = Field(default=None, foreign_key="account.account_id")

    descrizione: Optional[str] = None
    importo_imponibile: float = 0.0
    iva: float = 0.0
    importo_totale: float = 0.0

    # collegamento facoltativo a commessa per analisi costi per progetto
    commessa_id: Optional[int] = Field(default=None, foreign_key="projectcommessa.commessa_id")

    document_ref: Optional[str] = None   # n° fattura fornitore / ricevuta
    pagata: bool = True                  # per default la considero già pagata
    data_pagamento: Optional[date] = None
    note: Optional[str] = None
    # collegamento opzionale a campagna marketing (per costi marketing/CAC)
    campaign_id: Optional[int] = Field(default=None, foreign_key="marketingcampaign.campaign_id")
    campaign: Optional[MarketingCampaign] = Relationship(back_populates="expenses")


class CashflowBudget(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    anno: int = Field(index=True)
    mese: int = Field(index=True)  # 1-12
    categoria: str = Field(index=True)  # es. "Entrate clienti", "Costi fissi", "Fisco/INPS"
    importo_previsto: float  # + entrata, - uscita


class CashflowEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    data: date = Field(index=True)
    tipo: str = Field(index=True)  # "entrata" / "uscita"
    categoria: str = Field(index=True)
    descrizione: Optional[str] = None
    importo: float  # + entrata, - uscita
    client_id: Optional[int] = Field(default=None, foreign_key="client.client_id")
    commessa_id: Optional[int] = Field(default=None, foreign_key="projectcommessa.commessa_id")


# =========================
# ESTENSIONI CRM TIPO KEAP (NO ABBONAMENTI)
# =========================

class Company(SQLModel, table=True):
    """Aziende (account) a cui possono essere collegati i Client (contatti)."""
    company_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    piva: Optional[str] = None
    cod_fiscale: Optional[str] = None
    settore: Optional[str] = None
    paese: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None
    telefono: Optional[str] = None
    sito_web: Optional[str] = None
    note: Optional[str] = None


class Tag(SQLModel, table=True):
    """Tag per segmentare contatti e guidare automazioni (stile Keap)."""
    tag_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    categoria: Optional[str] = None  # es. "Lead Source", "Interesse", "Stato Funnel"
    descrizione: Optional[str] = None
    colore: Optional[str] = None


class ContactTag(SQLModel, table=True):
    """Associazione Many-to-Many contatto <-> tag."""
    id: Optional[int] = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="client.client_id")
    tag_id: int = Field(foreign_key="tag.tag_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Campaign(SQLModel, table=True):
    """Campagne di marketing/automazione collegate ai contatti tramite tag."""
    campaign_id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    tipo: Optional[str] = None  # nurture, promo, webinar, onboarding, ecc.
    stato: Optional[str] = None  # attiva, bozza, sospesa, archiviata
    data_inizio: Optional[date] = None
    data_fine: Optional[date] = None
    note: Optional[str] = None

    # metriche base
    iscritti: int = 0
    email_inviate: int = 0
    aperture: int = 0
    click: int = 0
    conversioni: int = 0


class CampaignEvent(SQLModel, table=True):
    """Eventi logici di una campagna (semplificato, utile per future automazioni)."""
    event_id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.campaign_id")

    tipo: str  # es. "email_send", "tag_applied", "wait", "webhook"
    nome: Optional[str] = None
    ordine: int = 0
    configurazione_json: Optional[str] = None  # parametri/condizioni dell'evento


# =========================
# INIT & SESSION
# =========================

def init_db():
    """Crea le tabelle e ripristina backup se disponibile"""
    from pathlib import Path
    import shutil

    BACKUP_LATEST = Path("db_backups/forgialean_latest.db")
    DB_PATH = Path(SQLITE_FILE_NAME)

    # Se esiste backup e DB è vuoto/mancante, ripristina
    if BACKUP_LATEST.exists() and (not DB_PATH.exists() or DB_PATH.stat().st_size < 1000):
        print("🔄 Ripristino backup database...")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKUP_LATEST, DB_PATH)
        print(f"✅ Database ripristinato da {BACKUP_LATEST}")

    # Crea tabelle se non esistono
    SQLModel.metadata.create_all(engine)


def migrate_db():
    """Esegue migrazioni DB se necessario (compatibile con Streamlit Cloud)"""
    with engine.connect() as conn:
        # Controlla colonne esistenti su opportunity
        result = conn.exec_driver_sql(
            "PRAGMA table_info(opportunity);"
        ).fetchall()

        column_names = [row[1] for row in result]  # row[1] è il nome colonna

        # Colonne da aggiungere se mancano
        migrations = [
            ("telefono_contatto", "TEXT"),
            ("flame_points", "INTEGER DEFAULT 0"),
            ("form_oee_completed", "BOOLEAN DEFAULT 0"),
            ("form_call_completed", "BOOLEAN DEFAULT 0"),
            ("demo_scheduled", "BOOLEAN DEFAULT 0"),
            ("contract_sent", "BOOLEAN DEFAULT 0"),
            ("contract_signed", "BOOLEAN DEFAULT 0"),
            ("date_form_oee", "DATE"),
            ("date_form_call", "DATE"),
            ("date_demo", "DATE"),
            ("date_contract_sent", "DATE"),
            ("date_contract_signed", "DATE"),
            ("campaign_id", "INTEGER"),

        ]

        for col_name, col_type in migrations:
            if col_name not in column_names:
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE opportunity ADD COLUMN {col_name} {col_type};"
                    )
                    conn.commit()
                    print(f"✅ Colonna {col_name} aggiunta con successo")
                except Exception as e:
                    print(f"⚠️ Errore aggiunta colonna {col_name}: {e}")
            else:
                print(f"ℹ️ Colonna {col_name} già presente")

        # Crea tabella crm_task se non esiste
        result_tasks = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='crmtask';"
        ).fetchone()

        if not result_tasks:
            try:
                SQLModel.metadata.create_all(engine)
                print("✅ Tabella CrmTask creata (se non esisteva)")
            except Exception as e:
                print(f"⚠️ Errore creazione tabella CrmTask: {e}")

        # Crea tabella crmactivity se non esiste
        result_act = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='crmactivity';"
        ).fetchone()

        if not result_act:
            try:
                SQLModel.metadata.create_all(engine)
                print("✅ Tabella CrmActivity creata (se non esisteva)")
            except Exception as e:
                print(f"⚠️ Errore creazione tabella CrmActivity: {e}")


def get_session() -> Session:
    """Restituisce una nuova sessione SQLModel"""
    return Session(engine)