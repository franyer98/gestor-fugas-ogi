import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """UTC 'naive' (SQLite no conserva zona horaria)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Estado(str, enum.Enum):
    DETECTADA = "DETECTADA"
    EN_REPARACION = "EN_REPARACION"
    REPARADA = "REPARADA"
    VERIFICADA = "VERIFICADA"  # re-inspección OGI confirmó cierre


class Severidad(str, enum.Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


class Rol(str, enum.Enum):
    INSPECTOR = "INSPECTOR"
    SUPERVISOR = "SUPERVISOR"
    CUADRILLA = "CUADRILLA"


class Cuadrilla(Base):
    __tablename__ = "cuadrillas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    rol: Mapped[Rol] = mapped_column(SAEnum(Rol, native_enum=False, length=20))
    cuadrilla_id: Mapped[int | None] = mapped_column(ForeignKey("cuadrillas.id"))


class Fuga(Base):
    __tablename__ = "fugas"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    cluster: Mapped[str] = mapped_column(String(40), index=True)
    pozo: Mapped[str] = mapped_column(String(40))
    componente: Mapped[str] = mapped_column(String(60))
    severidad: Mapped[Severidad] = mapped_column(
        SAEnum(Severidad, native_enum=False, length=10)
    )
    descripcion: Mapped[str] = mapped_column(Text, default="")
    foto_url: Mapped[str | None] = mapped_column(String(300))
    estado: Mapped[Estado] = mapped_column(
        SAEnum(Estado, native_enum=False, length=20), default=Estado.DETECTADA, index=True
    )

    detectada_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    primer_intento_en: Mapped[datetime | None] = mapped_column(DateTime)
    verificada_en: Mapped[datetime | None] = mapped_column(DateTime)
    reinspecciones_fallidas: Mapped[int] = mapped_column(Integer, default=0)

    inspector: Mapped[str] = mapped_column(String(40))
    cuadrilla_id: Mapped[int | None] = mapped_column(ForeignKey("cuadrillas.id"))
    cuadrilla: Mapped[Cuadrilla | None] = relationship()

    eventos: Mapped[list["Evento"]] = relationship(
        back_populates="fuga", order_by="Evento.fecha", cascade="all, delete-orphan"
    )


class Evento(Base):
    """Bitácora inmutable: cada cambio de estado queda registrado."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fuga_id: Mapped[int] = mapped_column(ForeignKey("fugas.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    usuario: Mapped[str] = mapped_column(String(40))
    accion: Mapped[str] = mapped_column(String(30))
    de_estado: Mapped[str | None] = mapped_column(String(20))
    a_estado: Mapped[str] = mapped_column(String(20))
    nota: Mapped[str] = mapped_column(Text, default="")

    fuga: Mapped[Fuga] = relationship(back_populates="eventos")
