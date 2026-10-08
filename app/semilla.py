"""Datos 100% sintéticos para la demo (sin información real de ninguna operación)."""
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .config import Settings
from .models import Cuadrilla, Estado, Rol, Severidad, Usuario, utcnow
from .seguridad import hash_password
from .servicios import aplicar_accion, registrar_fuga

COMPONENTES = [
    "Válvula de bloqueo", "Brida", "Conector roscado", "Sello de bomba",
    "Venteo de tanque", "Regulador de presión", "Línea de gas de baja presión",
    "Medidor", "Válvula de alivio",
]
DESCRIPCIONES = {
    Severidad.ALTA: "Pluma visible y persistente en la cámara OGI.",
    Severidad.MEDIA: "Pluma intermitente en el componente.",
    Severidad.BAJA: "Pluma leve, detectable solo a corta distancia.",
}


def sembrar_usuarios(db: Session, settings: Settings) -> list[Cuadrilla]:
    cuadrillas = [Cuadrilla(nombre=f"Cuadrilla {c}") for c in ("Alfa", "Bravo", "Charlie")]
    db.add_all(cuadrillas)
    db.flush()
    h = hash_password(settings.demo_password)
    db.add_all(
        [
            Usuario(username="inspector", password_hash=h, rol=Rol.INSPECTOR),
            Usuario(username="supervisor", password_hash=h, rol=Rol.SUPERVISOR),
            Usuario(
                username="cuadrilla", password_hash=h, rol=Rol.CUADRILLA,
                cuadrilla_id=cuadrillas[0].id,
            ),
        ]
    )
    db.flush()
    return cuadrillas


def sembrar_fugas(
    db: Session, settings: Settings, cuadrillas: list[Cuadrilla],
    cantidad: int | None = None, ahora: datetime | None = None, semilla: int = 42,
) -> None:
    """Genera fugas en distintos puntos del ciclo de vida, con fechas escalonadas."""
    rnd = random.Random(semilla)
    ahora = ahora or utcnow()
    cantidad = cantidad or settings.demo_cantidad_fugas

    for _ in range(cantidad):
        severidad = rnd.choices(list(Severidad), weights=[2, 4, 4])[0]
        edad = rnd.randint(1, 55)  # días desde la detección
        detectada = ahora - timedelta(days=edad, hours=rnd.randint(0, 20))
        fuga = registrar_fuga(
            db,
            {
                "cluster": f"CLUSTER-{rnd.randint(1, 12):02d}",
                "pozo": f"POZO-{rnd.randint(1, 40):03d}",
                "componente": rnd.choice(COMPONENTES),
                "severidad": severidad,
                "descripcion": DESCRIPCIONES[severidad],
                "foto_url": None,
            },
            usuario="inspector",
            ahora=detectada,
        )

        # Cuánto avanzó en el ciclo: más probable que las viejas estén cerradas.
        avance = rnd.random() + edad / 45
        t = detectada
        if avance < 0.35:
            continue  # sigue DETECTADA
        t += timedelta(days=rnd.uniform(0.5, 4))
        t = min(t, ahora)
        aplicar_accion(db, fuga, "asignar", "supervisor", Rol.SUPERVISOR,
                       cuadrilla_id=rnd.choice(cuadrillas).id, ahora=t)
        if avance < 0.65:
            continue  # EN_REPARACION
        # Cola larga: ~20% de las reparaciones se demoran bastante más de lo normal.
        dur_reparacion = rnd.uniform(14, 30) if rnd.random() < 0.2 else rnd.uniform(1, 10)
        t = min(t + timedelta(days=dur_reparacion), ahora)
        aplicar_accion(db, fuga, "reparar", "cuadrilla", Rol.CUADRILLA,
                       nota="Ajuste/reemplazo ejecutado", ahora=t)
        if avance < 0.85:
            continue  # REPARADA, a la espera de re-inspección
        t = min(t + timedelta(days=rnd.uniform(1, 6)), ahora)
        if rnd.random() < 0.15:  # re-inspección falla: vuelve a reparación
            aplicar_accion(db, fuga, "rechazar", "inspector", Rol.INSPECTOR,
                           nota="Fuga persiste en la re-inspección", ahora=t)
            continue
        aplicar_accion(db, fuga, "verificar", "inspector", Rol.INSPECTOR,
                       nota="Re-inspección OGI sin pluma", ahora=t)


def sembrar_demo(db: Session, settings: Settings) -> None:
    if db.query(Usuario).count() > 0:
        return  # ya sembrado
    cuadrillas = sembrar_usuarios(db, settings)
    sembrar_fugas(db, settings, cuadrillas)
    db.commit()
