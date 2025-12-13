from typing import Optional
from datetime import date, datetime
from sqlalchemy import Column, DateTime

from sqlmodel import SQLModel, Field, create_engine, Session

# File SQLite locale
SQLITE_FILE_NAME = "forgialean.db"
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
    email: Optional[str] = None   # <--- NUOVO CAMPO
    piva: Optional[str] = None
    cod_fiscale: Optional[str] = None
    settore: Optional[str] = None
    paese: Optional[str] = None
    canale_acquisizione: Optional[str] = None
    segmento_cliente: Optional[str] = None
    data_creazione: Optional[date] = None
    stato_cliente: Optional[str] = None  # attivo, prospect, perso


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
    stato_opportunita: Optional[str] = "aperta"


class Invoice(SQLModel, table=True):
    invoice_id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.client_id")
    num_fattura: str
    data_fattura: Optional[date] = None
    data_scadenza: Optional[date] = None
    importo_imponibile: Optional[float] = 0.0
    iva: Optional[float] = 0.0
    importo_totale: Optional[float] = 0.0
    stato_pagamento: Optional[str] = None  # emessa, incassata, scaduta
    data_incasso: Optional[date] = None


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

# =========================
# INIT & SESSION
# =========================

def init_db():
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)