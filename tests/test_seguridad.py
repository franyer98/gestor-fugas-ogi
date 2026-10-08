from app.seguridad import crear_token, hash_password, leer_token, verificar_password


def test_password_hash():
    h = hash_password("secreto")
    assert verificar_password("secreto", h)
    assert not verificar_password("otro", h)
    assert not verificar_password("secreto", "formato-invalido")
    assert hash_password("secreto") != h  # sal aleatoria


def test_token_valido_expirado_y_manipulado():
    t = crear_token("ana", "k", ttl_horas=1, ahora=1000.0)
    assert leer_token(t, "k", ahora=1000.0 + 3599) == "ana"
    assert leer_token(t, "k", ahora=1000.0 + 3601) is None      # expirado
    assert leer_token(t, "otra-clave", ahora=1000.0) is None     # firma distinta
    cuerpo, firma = t.split(".")
    assert leer_token(f"{cuerpo}x.{firma}", "k", ahora=1000.0) is None  # alterado
    assert leer_token("no-es-token", "k") is None
