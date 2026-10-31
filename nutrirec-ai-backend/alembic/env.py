"""
alembic/env.py
Konfigurasi lingkungan Alembic.

DATABASE_URL dibaca dari .env melalui Settings sehingga tidak perlu
menulis kredensial di alembic.ini.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Tambahkan root proyek ke sys.path agar import app.* berjalan
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import semua model agar Alembic mengenali metadata
from app.models import Base  # noqa: F401 — semua model diimpor via __init__
from app.core.config import get_settings

settings = get_settings()

# Objek config Alembic
config = context.config

# Timpa sqlalchemy.url dengan nilai dari .env
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Konfigurasi logging dari alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Jalankan migrasi dalam mode offline (tanpa koneksi aktif)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Jalankan migrasi dalam mode online (koneksi aktif)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

