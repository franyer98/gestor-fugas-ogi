from tests.conftest import NUEVA_FUGA, login


def test_health_get_y_head(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.head("/health").status_code == 200


def test_login_incorrecto(client):
    r = client.post("/auth/login", json={"username": "inspector", "password": "mala"})
    assert r.status_code == 401


def test_requiere_token(client):
    assert client.get("/fugas").status_code == 401
    r = client.get("/fugas", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401


def test_ciclo_completo_por_api(client, h_inspector, h_supervisor, h_cuadrilla):
    r = client.post("/fugas", json=NUEVA_FUGA, headers=h_inspector)
    assert r.status_code == 201
    fuga = r.json()
    fid = fuga["id"]
    assert fuga["estado"] == "DETECTADA"
    assert fuga["plazo"]["vigente"] == "primer_intento"
    assert fuga["plazo"]["semaforo"] == "VERDE"

    cuadrilla_id = client.get("/cuadrillas", headers=h_supervisor).json()[0]["id"]
    r = client.post(f"/fugas/{fid}/asignar", json={"cuadrilla_id": cuadrilla_id}, headers=h_supervisor)
    assert r.status_code == 200 and r.json()["estado"] == "EN_REPARACION"

    r = client.post(f"/fugas/{fid}/reparar", json={"nota": "Cambio de empaque"}, headers=h_cuadrilla)
    assert r.json()["estado"] == "REPARADA"

    r = client.post(f"/fugas/{fid}/verificar", json={"nota": "Sin pluma"}, headers=h_inspector)
    cuerpo = r.json()
    assert cuerpo["estado"] == "VERIFICADA"
    assert cuerpo["plazo"]["semaforo"] == "CERRADA"
    assert [e["accion"] for e in cuerpo["eventos"]] == [
        "registrar", "asignar", "reparar", "verificar",
    ]

    k = client.get("/kpis", headers=h_supervisor).json()
    assert k["cerradas"] == 1 and k["abiertas"] == 0
    assert k["pct_cerradas_a_tiempo"] == 100.0


def test_permisos_por_rol(client, h_inspector, h_supervisor, h_cuadrilla):
    fid = client.post("/fugas", json=NUEVA_FUGA, headers=h_inspector).json()["id"]
    cid = client.get("/cuadrillas", headers=h_supervisor).json()[0]["id"]

    # la cuadrilla no crea ni asigna; el inspector no asigna
    assert client.post("/fugas", json=NUEVA_FUGA, headers=h_cuadrilla).status_code == 403
    assert client.post(f"/fugas/{fid}/asignar", json={"cuadrilla_id": cid},
                       headers=h_inspector).status_code == 403
    assert client.post(f"/fugas/{fid}/asignar", json={"cuadrilla_id": cid},
                       headers=h_cuadrilla).status_code == 403


def test_transicion_invalida_devuelve_409(client, h_inspector, h_cuadrilla):
    fid = client.post("/fugas", json=NUEVA_FUGA, headers=h_inspector).json()["id"]
    # reparar sin haber asignado
    r = client.post(f"/fugas/{fid}/reparar", json={}, headers=h_cuadrilla)
    assert r.status_code == 409


def test_rechazo_reabre_reparacion(client, h_inspector, h_supervisor, h_cuadrilla):
    fid = client.post("/fugas", json=NUEVA_FUGA, headers=h_inspector).json()["id"]
    cid = client.get("/cuadrillas", headers=h_supervisor).json()[0]["id"]
    client.post(f"/fugas/{fid}/asignar", json={"cuadrilla_id": cid}, headers=h_supervisor)
    client.post(f"/fugas/{fid}/reparar", json={}, headers=h_cuadrilla)
    r = client.post(f"/fugas/{fid}/rechazar", json={"nota": "Persiste"}, headers=h_inspector)
    assert r.json()["estado"] == "EN_REPARACION"
    assert r.json()["reinspecciones_fallidas"] == 1
    assert r.json()["plazo"]["vigente"] == "definitivo"


def test_listado_ordenado_por_prioridad_y_filtros(client, h_inspector):
    for sev in ("BAJA", "ALTA", "MEDIA"):
        client.post("/fugas", json={**NUEVA_FUGA, "severidad": sev}, headers=h_inspector)
    lista = client.get("/fugas", headers=h_inspector).json()
    assert [f["severidad"] for f in lista] == ["ALTA", "MEDIA", "BAJA"]
    solo_altas = client.get("/fugas?severidad=ALTA", headers=h_inspector).json()
    assert len(solo_altas) == 1
    assert client.get("/fugas?estado=VERIFICADA", headers=h_inspector).json() == []


def test_validacion_y_404(client, h_inspector):
    r = client.post("/fugas", json={**NUEVA_FUGA, "severidad": "GRAVISIMA"}, headers=h_inspector)
    assert r.status_code == 422
    assert client.get("/fugas/9999", headers=h_inspector).status_code == 404


def test_kpis_sin_datos(client, h_inspector):
    k = client.get("/kpis", headers=h_inspector).json()
    assert k["total"] == 0
    assert k["tiempo_medio_cierre_dias"] is None
    assert k["pct_cerradas_a_tiempo"] is None


def test_semilla_demo_genera_datos_consistentes():
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    s = Settings(database_url="sqlite:///:memory:", secret_key="x", demo_seed=True,
                 demo_password="clave-test", demo_cantidad_fugas=40)
    with TestClient(create_app(s)) as c:
        h = login(c, "supervisor")
        k = c.get("/kpis", headers=h).json()
        assert k["total"] == 40
        assert sum(k["por_estado"].values()) == 40
        assert k["abiertas"] + k["cerradas"] == 40
        lista = c.get("/fugas?limite=500", headers=h).json()
        prioridades = [f["prioridad"] for f in lista]
        assert prioridades == sorted(prioridades, reverse=True)


def test_interfaz_estatica(client):
    r = client.get("/")
    assert r.status_code == 200 and "Gestor de fugas OGI" in r.text
    assert client.head("/").status_code == 200  # sondeos de Render/UptimeRobot
    assert client.get("/sw.js").headers["content-type"].startswith("application/javascript")
    assert client.get("/static/manifest.webmanifest").status_code == 200
    assert client.get("/static/icon.svg").status_code == 200
