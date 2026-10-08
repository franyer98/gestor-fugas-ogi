"""Lógica de negocio del ciclo de vida de una fuga (sin dependencias de FastAPI)."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .config import Settings
from .models import Estado, Evento, Fuga, Rol, Severidad, utcnow


class ErrorNegocio(Exception):
    """Transición o dato inválido; la API lo traduce a 409/422."""


# Acción -> (estados origen permitidos, estado destino, roles autorizados)
TRANSICIONES: dict[str, tuple[set[Estado], Estado, set[Rol]]] = {
    "asignar": (
        {Estado.DETECTADA, Estado.EN_REPARACION},
        Estado.EN_REPARACION,
        {Rol.SUPERVISOR},
    ),
    "reparar": (
        {Estado.EN_REPARACION},
        Estado.REPARADA,
        {Rol.CUADRILLA, Rol.SUPERVISOR},
    ),
    "verificar": (
        {Estado.REPARADA},
        Estado.VERIFICADA,
        {Rol.INSPECTOR, Rol.SUPERVISOR},
    ),
    # Re-inspección con la fuga todavía presente: vuelve a reparación.
    "rechazar": (
        {Estado.REPARADA},
        Estado.EN_REPARACION,
        {Rol.INSPECTOR, Rol.SUPERVISOR},
    ),
}

PESO_SEVERIDAD = {Severidad.ALTA: 3, Severidad.MEDIA: 2, Severidad.BAJA: 1}


@dataclass(frozen=True)
class Plazo:
    nombre: str  # "primer_intento" | "definitivo" | "cerrada"
    vence_en: datetime | None
    dias_restantes: int | None
    semaforo: str  # VERDE | AMARILLO | ROJO | CERRADA


def _dias_enteros(delta: timedelta) -> int:
    # floor: 0.4 días restantes cuenta como 0; -0.4 como -1 (ya vencido).
    return delta.days


def calcular_plazo(fuga: Fuga, settings: Settings, ahora: datetime | None = None) -> Plazo:
    ahora = ahora or utcnow()
    if fuga.estado == Estado.VERIFICADA:
        return Plazo("cerrada", None, None, "CERRADA")

    if fuga.primer_intento_en is None:
        nombre = "primer_intento"
        vence = fuga.detectada_en + timedelta(days=settings.plazo_primer_intento_dias)
    else:
        nombre = "definitivo"
        vence = fuga.detectada_en + timedelta(days=settings.plazo_definitivo_dias)

    faltante = vence - ahora
    # El semáforo compara el tiempo exacto; los días enteros son solo para mostrar.
    if faltante < timedelta(0):
        semaforo = "ROJO"
    elif faltante <= timedelta(days=settings.umbral_amarillo_dias):
        semaforo = "AMARILLO"
    else:
        semaforo = "VERDE"
    return Plazo(nombre, vence, _dias_enteros(faltante), semaforo)


def antiguedad_dias(fuga: Fuga, ahora: datetime | None = None) -> int:
    fin = fuga.verificada_en or (ahora or utcnow())
    return max((fin - fuga.detectada_en).days, 0)


def prioridad(fuga: Fuga, settings: Settings, ahora: datetime | None = None) -> int:
    """Mayor número = más urgente. Cerradas valen 0.

    severidad (x10) + antigüedad en días + bono por plazo vencido.
    """
    if fuga.estado == Estado.VERIFICADA:
        return 0
    plazo = calcular_plazo(fuga, settings, ahora)
    bono_vencida = 25 if plazo.semaforo == "ROJO" else 0
    return PESO_SEVERIDAD[fuga.severidad] * 10 + antiguedad_dias(fuga, ahora) + bono_vencida


def aplicar_accion(
    db: Session,
    fuga: Fuga,
    accion: str,
    usuario: str,
    rol: Rol,
    nota: str = "",
    cuadrilla_id: int | None = None,
    ahora: datetime | None = None,
) -> Fuga:
    if accion not in TRANSICIONES:
        raise ErrorNegocio(f"Acción desconocida: {accion}")
    origenes, destino, roles = TRANSICIONES[accion]

    if rol not in roles:
        raise ErrorNegocio(f"El rol {rol.value} no puede ejecutar '{accion}'")
    if fuga.estado not in origenes:
        raise ErrorNegocio(
            f"No se puede '{accion}' una fuga en estado {fuga.estado.value}"
        )
    if accion == "asignar" and cuadrilla_id is None:
        raise ErrorNegocio("Falta cuadrilla_id para asignar")

    ahora = ahora or utcnow()
    anterior = fuga.estado

    if accion == "asignar":
        fuga.cuadrilla_id = cuadrilla_id
    elif accion == "reparar":
        if fuga.primer_intento_en is None:
            fuga.primer_intento_en = ahora
    elif accion == "verificar":
        fuga.verificada_en = ahora
    elif accion == "rechazar":
        fuga.reinspecciones_fallidas += 1

    fuga.estado = destino
    db.add(
        Evento(
            fuga=fuga,
            fecha=ahora,
            usuario=usuario,
            accion=accion,
            de_estado=anterior.value,
            a_estado=destino.value,
            nota=nota,
        )
    )
    db.flush()
    return fuga


def registrar_fuga(db: Session, datos: dict, usuario: str, ahora: datetime | None = None) -> Fuga:
    ahora = ahora or utcnow()
    siguiente = (db.query(Fuga).count()) + 1
    fuga = Fuga(
        codigo=f"FG-{ahora.year}-{siguiente:04d}",
        estado=Estado.DETECTADA,
        detectada_en=ahora,
        inspector=usuario,
        **datos,
    )
    fuga.eventos.append(
        Evento(
            fecha=ahora,
            usuario=usuario,
            accion="registrar",
            de_estado=None,
            a_estado=Estado.DETECTADA.value,
            nota="Fuga registrada",
        )
    )
    db.add(fuga)
    db.flush()
    return fuga


def calcular_kpis(db: Session, settings: Settings, ahora: datetime | None = None) -> dict:
    ahora = ahora or utcnow()
    fugas = db.query(Fuga).all()

    abiertas = [f for f in fugas if f.estado != Estado.VERIFICADA]
    cerradas = [f for f in fugas if f.estado == Estado.VERIFICADA]

    por_estado = {e.value: 0 for e in Estado}
    por_semaforo = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0}
    for f in fugas:
        por_estado[f.estado.value] += 1
    for f in abiertas:
        por_semaforo[calcular_plazo(f, settings, ahora).semaforo] += 1

    tiempos = [(f.verificada_en - f.detectada_en).total_seconds() / 86400 for f in cerradas]
    a_tiempo = [
        f
        for f in cerradas
        if f.verificada_en <= f.detectada_en + timedelta(days=settings.plazo_definitivo_dias)
    ]

    # Emisión acumulada estimada = factor ilustrativo x días que estuvo abierta.
    emisiones = sum(
        settings.emision_kg_ch4_dia[f.severidad.value] * antiguedad_dias(f, ahora)
        for f in fugas
    )

    return {
        "total": len(fugas),
        "abiertas": len(abiertas),
        "cerradas": len(cerradas),
        "por_estado": por_estado,
        "abiertas_por_semaforo": por_semaforo,
        "tiempo_medio_cierre_dias": round(sum(tiempos) / len(tiempos), 1) if tiempos else None,
        "pct_cerradas_a_tiempo": (
            round(100 * len(a_tiempo) / len(cerradas), 1) if cerradas else None
        ),
        "reinspecciones_fallidas": sum(f.reinspecciones_fallidas for f in fugas),
        "emisiones_estimadas_kg_ch4": round(emisiones, 1),
        "nota_emisiones": (
            "Estimación ilustrativa con factores configurables por severidad; "
            "no corresponde a factores oficiales ni a datos reales."
        ),
    }
