from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import Estado, Rol, Severidad


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: Rol
    username: str


class FugaIn(BaseModel):
    cluster: str = Field(min_length=1, max_length=40)
    pozo: str = Field(min_length=1, max_length=40)
    componente: str = Field(min_length=1, max_length=60)
    severidad: Severidad
    descripcion: str = ""
    foto_url: str | None = Field(default=None, max_length=300)


class AsignarIn(BaseModel):
    cuadrilla_id: int
    nota: str = ""


class NotaIn(BaseModel):
    nota: str = ""


class CuadrillaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fecha: datetime
    usuario: str
    accion: str
    de_estado: str | None
    a_estado: str
    nota: str


class PlazoOut(BaseModel):
    vigente: str
    vence_en: datetime | None
    dias_restantes: int | None
    semaforo: str


class FugaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    cluster: str
    pozo: str
    componente: str
    severidad: Severidad
    descripcion: str
    foto_url: str | None
    estado: Estado
    detectada_en: datetime
    primer_intento_en: datetime | None
    verificada_en: datetime | None
    reinspecciones_fallidas: int
    inspector: str
    cuadrilla: CuadrillaOut | None
    prioridad: int = 0
    antiguedad_dias: int = 0
    plazo: PlazoOut | None = None


class FugaDetalleOut(FugaOut):
    eventos: list[EventoOut] = []
