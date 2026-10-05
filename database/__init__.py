"""
HospitalRobotNav — Hospital Database Package
==============================================
SQLite-backed hospital knowledge base with synthetic demo data.

Provides:
    - HospitalDatabase: Core CRUD + schema + seeding
    - DBQueryEngine: High-level query facade for voice/NLU commands
"""

from database.hospital_db import HospitalDatabase
from database.db_query_engine import DBQueryEngine

__all__ = ["HospitalDatabase", "DBQueryEngine"]
