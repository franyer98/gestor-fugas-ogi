import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings():
    return Settings(
        database_url="sqlite:///:memory:",
        secret_key="test-secret",
        demo_seed=False,
        demo_password="clave-test",
    )


@pytest.fixture()
def client(settings):
    # Con demo_seed=False creamos usuarios/cuadrillas a mano para controlar el escenario.
    app = create_app(settings)
    with TestClient(app) as c:
        from app.semilla import sembrar_usuarios

        with app.state.session_factory() as db:
            sembrar_usuarios(db, settings)
            db.commit()
        c.app_state = app.state
        yield c


def login(client: TestClient, username: str, password: str = "clave-test") -> dict:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def h_inspector(client):
    return login(client, "inspector")


@pytest.fixture()
def h_supervisor(client):
    return login(client, "supervisor")


@pytest.fixture()
def h_cuadrilla(client):
    return login(client, "cuadrilla")


NUEVA_FUGA = {
    "cluster": "CLUSTER-01",
    "pozo": "POZO-007",
    "componente": "Brida",
    "severidad": "ALTA",
    "descripcion": "Pluma visible",
}
