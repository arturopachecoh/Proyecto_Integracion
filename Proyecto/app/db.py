from sqlalchemy import create_engine, text

from app.config import DATABASE_URL

# Pool chico: el servidor tiene poca RAM y Postgres acepta max 30 conexiones
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=2, pool_pre_ping=True)


def db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
