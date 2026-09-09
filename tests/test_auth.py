from pathlib import Path

import pytest

from swimops import auth


def test_default_token_store_uses_xdg_data_home() -> None:
    assert auth.token_store_path({"XDG_DATA_HOME": "/tmp/user-data"}) == Path(
        "/tmp/user-data/swimops/garmin"
    )


def test_configured_token_store_is_used() -> None:
    assert auth.token_store_path({"GARMIN_TOKEN_DIR": "/private/tokens"}) == Path(
        "/private/tokens"
    )


def test_login_persists_tokens_in_private_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    class FakeGarmin:
        def __init__(self, **kwargs: object) -> None:
            calls["init"] = kwargs

        def login(self, path: str) -> None:
            calls["login"] = path

    token_store = tmp_path / "tokens"
    monkeypatch.setattr(auth, "Garmin", FakeGarmin)

    auth.login(token_store, lambda _: "user@example.com", lambda _: "secret")

    assert calls["login"] == str(token_store)
    assert token_store.stat().st_mode & 0o777 == 0o700


def test_load_session_uses_saved_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_store = tmp_path / "tokens"
    token_store.mkdir()
    (token_store / auth.TOKEN_FILENAME).touch()
    calls: list[str] = []

    class FakeGarmin:
        def login(self, path: str) -> None:
            calls.append(path)

    monkeypatch.setattr(auth, "Garmin", FakeGarmin)

    client = auth.load_session(token_store)

    assert isinstance(client, FakeGarmin)
    assert calls == [str(token_store)]
