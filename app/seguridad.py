"""Hash de contraseñas y tokens firmados, solo con la librería estándar."""
import base64
import hashlib
import hmac
import json
import os
import time


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${dk.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        salt_hex, dk_hex = almacenado.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def crear_token(username: str, secret: str, ttl_horas: int, ahora: float | None = None) -> str:
    exp = int((ahora or time.time()) + ttl_horas * 3600)
    cuerpo = _b64(json.dumps({"u": username, "exp": exp}).encode())
    firma = _b64(hmac.new(secret.encode(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_token(token: str, secret: str, ahora: float | None = None) -> str | None:
    """Devuelve el username si el token es válido y no expiró; si no, None."""
    try:
        cuerpo, firma = token.split(".")
        esperada = _b64(hmac.new(secret.encode(), cuerpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_unb64(cuerpo))
    except (ValueError, json.JSONDecodeError):
        return None
    if datos.get("exp", 0) < (ahora or time.time()):
        return None
    return datos.get("u")
