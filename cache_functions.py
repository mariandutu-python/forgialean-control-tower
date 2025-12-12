# cache_functions.py
"""
Modulo di caching per ForgiaLean Control Tower.
Implementa @st.cache_data per tutte le query SQL.

Strategia di caching:
- Volatile (60s): KPI, TimeEntry (dati real-time)
- Transactional (300s): Fatture, Opportunità, Commesse, Fasi
- Static (3600s): Clienti, Reparti, Persone (master data)

Uso:
    from cache_functions import get_all_clients, invalidate_all_cache
    
    clients = get_all_clients()  # Cache automatico
    invalidate_all_cache()  # Dopo INSERT/UPDATE/DELETE
"""

import streamlit as st
from config import CACHE_TTL, CACHE_ENABLED
from db import (
    get_session,
    Client,
    Opportunity,
    Invoice,
    ProjectCommessa,
    TaskFase,
    Department,
    Employee,
    KpiDepartmentTimeseries,
    KpiEmployeeTimeseries,
    TimeEntry,
)
from sqlmodel import select


# ========================
# HELPER: Decorator wrapper per disabilitare cache in dev
# ========================

def cache_data(ttl):
    """Wrapper che rispetta la configurazione CACHE_ENABLED"""
    def decorator(func):
        if CACHE_ENABLED:
            return st.cache_data(ttl=ttl)(func)
        else:
            return func
    return decorator


# ========================
# CACHE VOLATILE (60 sec) - Dati real-time
# ========================

@cache_data(CACHE_TTL["volatile"])
def get_all_timeentries():
    """Carica tutti i TimeEntry (cambiano frequentemente)"""
    with get_session() as session:
        times = session.exec(select(TimeEntry)).all()
        # Converti in dict per evitare problemi con la sessione chiusa
        return [t.__dict__.copy() for t in times]


@cache_data(CACHE_TTL["volatile"])
def get_all_kpi_department_timeseries():
    """Carica tutti i KPI reparto (real-time)"""
    with get_session() as session:
        kpi = session.exec(select(KpiDepartmentTimeseries)).all()
        return [k.__dict__.copy() for k in kpi]


@cache_data(CACHE_TTL["volatile"])
def get_all_kpi_employee_timeseries():
    """Carica tutti i KPI persona (real-time)"""
    with get_session() as session:
        kpi = session.exec(select(KpiEmployeeTimeseries)).all()
        return [k.__dict__.copy() for k in kpi]


# ========================
# CACHE TRANSAZIONALE (300 sec)
# ========================

@cache_data(CACHE_TTL["transactional"])
def get_all_opportunities():
    """Carica tutte le opportunità"""
    with get_session() as session:
        opps = session.exec(select(Opportunity)).all()
        return [o.__dict__.copy() for o in opps]


@cache_data(CACHE_TTL["transactional"])
def get_all_invoices():
    """Carica tutte le fatture"""
    with get_session() as session:
        invoices = session.exec(select(Invoice)).all()
        return [i.__dict__.copy() for i in invoices]


@cache_data(CACHE_TTL["transactional"])
def get_all_task_fasi():
    """Carica tutte le fasi"""
    with get_session() as session:
        fasi = session.exec(select(TaskFase)).all()
        return [f.__dict__.copy() for f in fasi]


@cache_data(CACHE_TTL["transactional"])
def get_all_commesse():
    """Carica tutte le commesse"""
    with get_session() as session:
        commesse = session.exec(select(ProjectCommessa)).all()
        return [c.__dict__.copy() for c in commesse]


# ========================
# CACHE STATICO (3600 sec) - Master data
# ========================

@cache_data(CACHE_TTL["static"])
def get_all_clients():
    """Carica tutti i clienti (master data)"""
    with get_session() as session:
        clients = session.exec(select(Client)).all()
        return [c.__dict__.copy() for c in clients]


@cache_data(CACHE_TTL["static"])
def get_all_departments():
    """Carica tutti i reparti (master data)"""
    with get_session() as session:
        depts = session.exec(select(Department)).all()
        return [d.__dict__.copy() for d in depts]


@cache_data(CACHE_TTL["static"])
def get_all_employees():
    """Carica tutti gli impiegati (master data)"""
    with get_session() as session:
        emps = session.exec(select(Employee)).all()
        return [e.__dict__.copy() for e in emps]


# ========================
# INVALIDAZIONE CACHE (Selettiva)
# ========================

def invalidate_volatile_cache():
    """Invalida solo i dati real-time (KPI, TimeEntry)"""
    if CACHE_ENABLED:
        get_all_timeentries.clear()
        get_all_kpi_department_timeseries.clear()
        get_all_kpi_employee_timeseries.clear()


def invalidate_transactional_cache():
    """Invalida i dati transazionali (Fatture, Opportunità, Commesse, Fasi)"""
    if CACHE_ENABLED:
        get_all_opportunities.clear()
        get_all_invoices.clear()
        get_all_task_fasi.clear()
        get_all_commesse.clear()


def invalidate_static_cache():
    """Invalida master data (Clienti, Reparti, Persone)"""
    if CACHE_ENABLED:
        get_all_clients.clear()
        get_all_departments.clear()
        get_all_employees.clear()


def invalidate_all_cache():
    """Invalida TUTTO il cache"""
    if CACHE_ENABLED:
        st.cache_data.clear()