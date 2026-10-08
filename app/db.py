from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def crear_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        opciones: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            opciones["poolclass"] = StaticPool  # una sola conexión compartida en tests
        return create_engine(url, **opciones)
    # Evita conexiones obsoletas en Postgres gestionado (Render, etc.).
    return create_engine(url, pool_pre_ping=True, pool_recycle=280)


def crear_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def crear_tablas(engine: Engine) -> None:
    Base.metadata.create_all(engine)
