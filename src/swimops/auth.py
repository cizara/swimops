from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from getpass import getpass
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_FILENAME = "garmin_tokens.json"


class SessionNotFoundError(RuntimeError):
    pass


def token_store_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    if configured := env.get("GARMIN_TOKEN_DIR"):
        return Path(configured).expanduser()
    data_home = Path(env.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "swimops" / "garmin"


def _prepare_token_store(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def load_session(token_store: Path | None = None) -> Garmin:
    path = token_store or token_store_path()
    if not (path / TOKEN_FILENAME).is_file():
        raise SessionNotFoundError("No hay una sesión guardada. Ejecuta `garmin login`.")
    client = Garmin()
    client.login(str(path))
    return client


def login(
    token_store: Path | None = None,
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass,
) -> Garmin:
    path = token_store or token_store_path()
    _prepare_token_store(path)

    if (path / TOKEN_FILENAME).is_file():
        try:
            return load_session(path)
        except GarminConnectAuthenticationError:
            pass

    email = input_fn("Email de Garmin: ").strip()
    if not email:
        raise ValueError("El email no puede estar vacío.")
    password = password_fn("Contraseña de Garmin: ")
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")

    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: password_fn("Código MFA: ").strip(),
    )
    password = ""
    client.login(str(path))
    return client
