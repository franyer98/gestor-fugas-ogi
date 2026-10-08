# Gestor de fugas OGI

Gestiona lo que ocurre **después** de una inspección con cámara OGI: quién repara cada fuga, en cuánto tiempo y si la re-inspección confirmó el cierre.

> Proyecto de portafolio. Todos los datos de la demo son **sintéticos**; no incluye información de ninguna operación real.

## Ciclo de vida

```
DETECTADA ──asignar──▶ EN_REPARACION ──reparar──▶ REPARADA ──verificar──▶ VERIFICADA
                            ▲                         │
                            └──────── rechazar ───────┘   (la re-inspección encuentra pluma)
```

Cada cambio queda en una bitácora (`eventos`) con usuario, fecha y nota.

## Reglas de negocio

| Regla | Detalle |
|---|---|
| Plazos (configurables) | 15 días para el primer intento de reparación y 30 para el cierre definitivo, contados desde la detección |
| Semáforo | VERDE; AMARILLO cuando faltan ≤ 5 días para el plazo vigente; ROJO si venció; CERRADA al verificarse |
| Prioridad | severidad × 10 + antigüedad en días + 25 si el plazo está vencido |
| Roles | **Inspector** registra y re-inspecciona · **Supervisor** asigna y puede todo · **Cuadrilla** marca reparada |

## KPIs (`GET /kpis`)

Abiertas/cerradas, distribución por estado y semáforo, tiempo medio de cierre, % cerradas a tiempo, re-inspecciones fallidas y emisión acumulada estimada.

> La emisión estimada usa valores **ilustrativos** por severidad (kg CH₄/día), configurables en `app/config.py`. No son factores oficiales; sustitúyelos por los de tu metodología antes de usarlos en serio.

## Interfaz web (PWA)

Pensada para usarse desde el celular, en español y con modo claro/oscuro automático. Se sirve desde la raíz (`/`) y se puede instalar en la pantalla de inicio.

- **Tablero:** fugas abiertas, vencidas, tiempo medio de cierre, % a tiempo, semáforo y estado del ciclo.
- **Fugas:** lista ordenada por urgencia con filtros por estado y vencidas.
- **Detalle:** historial completo y solo las acciones que corresponden al rol y al estado.
- **Nueva fuga:** formulario para inspector y supervisor.

El acceso rápido «Probar la demo como…» entra con cualquiera de los tres roles.

## Ejecutar en local

```bash
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --reload
```

Documentación interactiva en `http://localhost:8000/docs`.

Usuarios de la demo (contraseña `demo1234`): `inspector`, `supervisor`, `cuadrilla`.

```bash
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"supervisor","password":"demo1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/kpis -H "Authorization: Bearer $TOKEN"
```

## Configuración

| Variable | Por defecto | Uso |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./gestor_fugas.db` | SQLite o PostgreSQL |
| `SECRET_KEY` | — | Firma de tokens (obligatoria en producción) |
| `PLAZO_PRIMER_INTENTO_DIAS` / `PLAZO_DEFINITIVO_DIAS` | 15 / 30 | Plazos |
| `UMBRAL_AMARILLO_DIAS` | 5 | Umbral del semáforo |
| `DEMO_SEED` | `true` | Genera datos sintéticos al arrancar si la base está vacía |

## Despliegue

`render.yaml` define un servicio web Docker en el plan gratuito con `/health` como health check. Con SQLite la base se regenera con datos de demostración en cada arranque, lo que es adecuado para un portafolio.

## Estructura

```
app/
  static/       interfaz web (index.html, service worker, manifiesto)
  models.py     entidades y enums
  servicios.py  ciclo de vida, plazos, prioridad y KPIs (sin FastAPI)
  main.py       API, autenticación y permisos por rol
  seguridad.py  scrypt + tokens HMAC (solo librería estándar)
  semilla.py    datos sintéticos
tests/          pytest: reglas de negocio, API y seguridad
```

## Pendiente

- Alertas por WhatsApp (la lógica de vencimientos ya está lista).
- Carga de fotos (hoy `foto_url` es solo un enlace).
- Migraciones con Alembic.
