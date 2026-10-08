"""Configuración por variables de entorno, con valores por defecto para la demo."""
import os
from dataclasses import dataclass, field


def _normalizar_db_url(url: str) -> str:
    # Render/Heroku entregan "postgres://", SQLAlchemy espera "postgresql://".
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./gestor_fugas.db"
    secret_key: str = "cambia-esto-en-produccion"
    token_ttl_horas: int = 12

    # Plazos en días desde la detección (configurables).
    plazo_primer_intento_dias: int = 15
    plazo_definitivo_dias: int = 30
    # Semáforo: amarillo cuando faltan <= N días para el plazo vigente.
    umbral_amarillo_dias: int = 5

    # Datos sintéticos de demostración.
    demo_seed: bool = True
    demo_password: str = "demo1234"
    demo_cantidad_fugas: int = 60

    # Valores ilustrativos de emisión (kg CH4/día) por severidad.
    # NO son factores oficiales: sirven para mostrar el cálculo del KPI.
    emision_kg_ch4_dia: dict = field(
        default_factory=lambda: {"ALTA": 6.0, "MEDIA": 2.0, "BAJA": 0.5}
    )

    @classmethod
    def desde_entorno(cls) -> "Settings":
        e = os.environ
        return cls(
            database_url=_normalizar_db_url(e.get("DATABASE_URL", cls.database_url)),
            secret_key=e.get("SECRET_KEY", cls.secret_key),
            token_ttl_horas=int(e.get("TOKEN_TTL_HORAS", cls.token_ttl_horas)),
            plazo_primer_intento_dias=int(e.get("PLAZO_PRIMER_INTENTO_DIAS", 15)),
            plazo_definitivo_dias=int(e.get("PLAZO_DEFINITIVO_DIAS", 30)),
            umbral_amarillo_dias=int(e.get("UMBRAL_AMARILLO_DIAS", 5)),
            demo_seed=e.get("DEMO_SEED", "true").lower() == "true",
            demo_password=e.get("DEMO_PASSWORD", cls.demo_password),
            demo_cantidad_fugas=int(e.get("DEMO_CANTIDAD_FUGAS", 60)),
        )
