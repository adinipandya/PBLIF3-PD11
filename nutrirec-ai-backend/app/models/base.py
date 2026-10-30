"""
app/models/base.py
Base deklaratif SQLAlchemy yang dipakai bersama oleh semua model ORM.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Kelas dasar untuk seluruh model ORM NutriRec AI."""
    pass

