from datetime import datetime, timedelta

import pytest

from app.config import Settings
from app.models import Estado, Fuga, Rol, Severidad
from app.servicios import (
    ErrorNegocio, aplicar_accion, calcular_plazo, prioridad,
)

S = Settings()
T0 = datetime(2026, 1, 1, 8, 0)


def fuga(severidad=Severidad.MEDIA, estado=Estado.DETECTADA, **kw) -> Fuga:
    return Fuga(
        codigo="FG-T", cluster="C1", pozo="P1", componente="Brida",
        severidad=severidad, estado=estado, detectada_en=T0, inspector="inspector",
        reinspecciones_fallidas=0, **kw,
    )


# ---- semáforo ----
@pytest.mark.parametrize(
    "dias, esperado",
    [(0, "VERDE"), (9, "VERDE"), (10, "AMARILLO"), (14, "AMARILLO"), (16, "ROJO")],
)
def test_semaforo_primer_intento(dias, esperado):
    p = calcular_plazo(fuga(), S, ahora=T0 + timedelta(days=dias, hours=1))
    assert p.nombre == "primer_intento"
    assert p.semaforo == esperado


def test_plazo_pasa_a_definitivo_tras_primer_intento():
    f = fuga(estado=Estado.REPARADA, primer_intento_en=T0 + timedelta(days=5))
    p = calcular_plazo(f, S, ahora=T0 + timedelta(days=20))
    assert p.nombre == "definitivo"
    assert p.semaforo == "VERDE"  # quedan 10 días de 30
    assert calcular_plazo(f, S, ahora=T0 + timedelta(days=31)).semaforo == "ROJO"


def test_fuga_verificada_no_tiene_plazo():
    f = fuga(estado=Estado.VERIFICADA)
    assert calcular_plazo(f, S, ahora=T0 + timedelta(days=100)).semaforo == "CERRADA"
    assert prioridad(f, S, ahora=T0 + timedelta(days=100)) == 0


# ---- prioridad ----
def test_prioridad_severidad_y_antiguedad():
    ahora = T0 + timedelta(days=3)
    alta = prioridad(fuga(Severidad.ALTA), S, ahora)
    baja = prioridad(fuga(Severidad.BAJA), S, ahora)
    assert alta > baja
    # una baja muy vencida supera a una alta recién detectada
    baja_vieja = prioridad(fuga(Severidad.BAJA), S, T0 + timedelta(days=40))
    alta_nueva = prioridad(fuga(Severidad.ALTA), S, T0 + timedelta(days=1))
    assert baja_vieja > alta_nueva


# ---- transiciones ----
class DBFalsa:
    """Doble mínimo de Session: aplicar_accion solo usa add y flush."""
    def __init__(self):
        self.agregados = []
    def add(self, obj):
        self.agregados.append(obj)
    def flush(self):
        pass


def test_ciclo_completo_registra_eventos():
    db, f = DBFalsa(), fuga()
    aplicar_accion(db, f, "asignar", "sup", Rol.SUPERVISOR, cuadrilla_id=1, ahora=T0)
    aplicar_accion(db, f, "reparar", "cua", Rol.CUADRILLA, ahora=T0 + timedelta(days=2))
    aplicar_accion(db, f, "verificar", "ins", Rol.INSPECTOR, ahora=T0 + timedelta(days=4))
    assert f.estado == Estado.VERIFICADA
    assert f.primer_intento_en == T0 + timedelta(days=2)
    assert f.verificada_en == T0 + timedelta(days=4)
    assert [e.accion for e in db.agregados] == ["asignar", "reparar", "verificar"]


def test_rechazo_vuelve_a_reparacion_y_cuenta():
    db, f = DBFalsa(), fuga(estado=Estado.REPARADA, primer_intento_en=T0)
    aplicar_accion(db, f, "rechazar", "ins", Rol.INSPECTOR, ahora=T0 + timedelta(days=3))
    assert f.estado == Estado.EN_REPARACION
    assert f.reinspecciones_fallidas == 1
    # el primer intento ya ocurrió: no se reinicia
    aplicar_accion(db, f, "reparar", "cua", Rol.CUADRILLA, ahora=T0 + timedelta(days=5))
    assert f.primer_intento_en == T0


@pytest.mark.parametrize(
    "accion, estado, rol",
    [
        ("reparar", Estado.DETECTADA, Rol.CUADRILLA),   # estado incorrecto
        ("verificar", Estado.EN_REPARACION, Rol.INSPECTOR),
        ("asignar", Estado.VERIFICADA, Rol.SUPERVISOR),  # cerrada no se reabre
        ("asignar", Estado.DETECTADA, Rol.CUADRILLA),    # rol incorrecto
        ("verificar", Estado.REPARADA, Rol.CUADRILLA),   # la cuadrilla no se autoverifica
    ],
)
def test_transiciones_invalidas(accion, estado, rol):
    with pytest.raises(ErrorNegocio):
        aplicar_accion(DBFalsa(), fuga(estado=estado), accion, "x", rol, cuadrilla_id=1)


def test_asignar_exige_cuadrilla():
    with pytest.raises(ErrorNegocio):
        aplicar_accion(DBFalsa(), fuga(), "asignar", "sup", Rol.SUPERVISOR)
