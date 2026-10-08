from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import servicios as svc
from .config import Settings
from .db import crear_engine, crear_session_factory, crear_tablas
from .models import Cuadrilla, Estado, Fuga, Rol, Severidad, Usuario
from .schemas import (
    AsignarIn, CuadrillaOut, FugaDetalleOut, FugaIn, FugaOut, LoginIn, NotaIn, TokenOut,
)
from .seguridad import crear_token, leer_token, verificar_password
from .semilla import sembrar_demo


ESTATICOS = Path(__file__).parent / "static"


# ---------- dependencias ----------
def get_db(request: Request):
    db: Session = request.app.state.session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def usuario_actual(
    request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Usuario:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Falta el token (Authorization: Bearer ...)")
    username = leer_token(auth[7:], settings.secret_key)
    usuario = db.query(Usuario).filter_by(username=username).first() if username else None
    if usuario is None:
        raise HTTPException(401, "Token inválido o expirado")
    return usuario


def requiere(*roles: Rol):
    def _dep(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(403, f"Rol {usuario.rol.value} sin permiso para esta acción")
        return usuario
    return _dep


# ---------- serialización ----------
def _a_out(fuga: Fuga, settings: Settings, detalle: bool = False):
    plazo = svc.calcular_plazo(fuga, settings)
    base = {
        **FugaOut.model_validate(fuga).model_dump(),
        "prioridad": svc.prioridad(fuga, settings),
        "antiguedad_dias": svc.antiguedad_dias(fuga),
        "plazo": {
            "vigente": plazo.nombre,
            "vence_en": plazo.vence_en,
            "dias_restantes": plazo.dias_restantes,
            "semaforo": plazo.semaforo,
        },
    }
    if detalle:
        return FugaDetalleOut(**base, eventos=fuga.eventos)
    return FugaOut(**base)


def _obtener_fuga(db: Session, fuga_id: int) -> Fuga:
    fuga = db.get(Fuga, fuga_id)
    if fuga is None:
        raise HTTPException(404, "Fuga no encontrada")
    return fuga


def _ejecutar(db, fuga, accion, usuario: Usuario, settings, **kw):
    try:
        svc.aplicar_accion(db, fuga, accion, usuario.username, usuario.rol, **kw)
    except svc.ErrorNegocio as e:
        raise HTTPException(409, str(e))
    return _a_out(fuga, settings, detalle=True)


# ---------- rutas ----------
router = APIRouter()


@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def interfaz():
    return FileResponse(ESTATICOS / "index.html", headers={"Cache-Control": "no-cache"})


@router.get("/sw.js", include_in_schema=False)
def service_worker():
    # Debe servirse desde la raíz para controlar todo el sitio.
    return FileResponse(
        ESTATICOS / "sw.js", media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


@router.post("/auth/login", response_model=TokenOut)
def login(datos: LoginIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    usuario = db.query(Usuario).filter_by(username=datos.username).first()
    if usuario is None or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = crear_token(usuario.username, settings.secret_key, settings.token_ttl_horas)
    return TokenOut(access_token=token, rol=usuario.rol, username=usuario.username)


@router.get("/cuadrillas", response_model=list[CuadrillaOut])
def listar_cuadrillas(db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    return db.query(Cuadrilla).order_by(Cuadrilla.nombre).all()


@router.get("/fugas", response_model=list[FugaOut])
def listar_fugas(
    estado: Estado | None = None,
    severidad: Severidad | None = None,
    cluster: str | None = None,
    solo_vencidas: bool = False,
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: Usuario = Depends(usuario_actual),
):
    q = db.query(Fuga)
    if estado:
        q = q.filter(Fuga.estado == estado)
    if severidad:
        q = q.filter(Fuga.severidad == severidad)
    if cluster:
        q = q.filter(Fuga.cluster == cluster)
    salida = [_a_out(f, settings) for f in q.all()]
    if solo_vencidas:
        salida = [f for f in salida if f.plazo and f.plazo.semaforo == "ROJO"]
    salida.sort(key=lambda f: f.prioridad, reverse=True)  # más urgentes primero
    return salida[:limite]


@router.post("/fugas", response_model=FugaDetalleOut, status_code=201)
def crear_fuga(
    datos: FugaIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    usuario: Usuario = Depends(requiere(Rol.INSPECTOR, Rol.SUPERVISOR)),
):
    fuga = svc.registrar_fuga(db, datos.model_dump(), usuario.username)
    return _a_out(fuga, settings, detalle=True)


@router.get("/fugas/{fuga_id}", response_model=FugaDetalleOut)
def detalle_fuga(
    fuga_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: Usuario = Depends(usuario_actual),
):
    return _a_out(_obtener_fuga(db, fuga_id), settings, detalle=True)


@router.post("/fugas/{fuga_id}/asignar", response_model=FugaDetalleOut)
def asignar(
    fuga_id: int, datos: AsignarIn,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    usuario: Usuario = Depends(requiere(Rol.SUPERVISOR)),
):
    if db.get(Cuadrilla, datos.cuadrilla_id) is None:
        raise HTTPException(404, "Cuadrilla no encontrada")
    return _ejecutar(db, _obtener_fuga(db, fuga_id), "asignar", usuario, settings,
                     cuadrilla_id=datos.cuadrilla_id, nota=datos.nota)


@router.post("/fugas/{fuga_id}/reparar", response_model=FugaDetalleOut)
def reparar(
    fuga_id: int, datos: NotaIn,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    usuario: Usuario = Depends(requiere(Rol.CUADRILLA, Rol.SUPERVISOR)),
):
    return _ejecutar(db, _obtener_fuga(db, fuga_id), "reparar", usuario, settings, nota=datos.nota)


@router.post("/fugas/{fuga_id}/verificar", response_model=FugaDetalleOut)
def verificar(
    fuga_id: int, datos: NotaIn,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    usuario: Usuario = Depends(requiere(Rol.INSPECTOR, Rol.SUPERVISOR)),
):
    return _ejecutar(db, _obtener_fuga(db, fuga_id), "verificar", usuario, settings, nota=datos.nota)


@router.post("/fugas/{fuga_id}/rechazar", response_model=FugaDetalleOut)
def rechazar(
    fuga_id: int, datos: NotaIn,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    usuario: Usuario = Depends(requiere(Rol.INSPECTOR, Rol.SUPERVISOR)),
):
    return _ejecutar(db, _obtener_fuga(db, fuga_id), "rechazar", usuario, settings, nota=datos.nota)


@router.get("/kpis")
def kpis(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    _: Usuario = Depends(usuario_actual),
):
    return svc.calcular_kpis(db, settings)


# ---------- fábrica de la app ----------
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.desde_entorno()
    engine = crear_engine(settings.database_url)
    session_factory = crear_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        crear_tablas(engine)
        if settings.demo_seed:
            with session_factory() as db:
                sembrar_demo(db, settings)
        yield

    app = FastAPI(
        title="Gestor de fugas OGI",
        description="Ciclo de vida de fugas: detección, reparación y re-inspección. Datos sintéticos.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
    return app


app = create_app()
