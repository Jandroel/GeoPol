"""First-run account setup against isolated, temporary SQLite databases."""

import sys
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from geopol import cli
from geopol.models import User
from geopol.security import verify_password


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    User.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.delenv("GEOPOL_BOOTSTRAP_PASSWORD", raising=False)
    yield factory
    engine.dispose()


def invoke(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["geopol", *arguments])
    cli.main()


def snapshot(sessions):
    with sessions() as db:
        return [
            (user.id, user.username, user.password_hash, user.role, user.active)
            for user in db.scalars(select(User).order_by(User.username))
        ]


def test_empty_installation_prompts_once_and_creates_initial_admin(sessions, monkeypatch, capsys):
    password = "Synthetic-bootstrap-2026"
    prompt = Mock(return_value=password)
    monkeypatch.setattr(cli.getpass, "getpass", prompt)

    invoke(monkeypatch, "bootstrap-user")

    prompt.assert_called_once()
    users = snapshot(sessions)
    assert len(users) == 1
    _, username, encoded, role, active = users[0]
    assert (username, role, active) == ("administrador", "admin", True)
    assert encoded != password
    assert verify_password(password, encoded)
    output = capsys.readouterr()
    assert "Administrador inicial creado: administrador" in output.out
    assert password not in output.out + output.err


def test_empty_installation_supports_custom_name_and_password_environment(sessions, monkeypatch):
    monkeypatch.setenv("QA_INITIAL_PASSWORD", "Synthetic-environment-2026")
    prompt = Mock(side_effect=AssertionError("No debe pedir contraseña con la variable definida"))
    monkeypatch.setattr(cli.getpass, "getpass", prompt)

    invoke(
        monkeypatch, "bootstrap-user", "--username", "  responsable  ",
        "--password-env", "QA_INITIAL_PASSWORD",
    )

    users = snapshot(sessions)
    assert len(users) == 1
    assert users[0][1] == "responsable"
    assert users[0][3] == "admin"
    assert verify_password("Synthetic-environment-2026", users[0][2])
    prompt.assert_not_called()


def test_repeated_bootstrap_neither_prompts_nor_changes_accounts(sessions, monkeypatch, capsys):
    monkeypatch.setenv("GEOPOL_BOOTSTRAP_PASSWORD", "Synthetic-initial-2026")
    invoke(monkeypatch, "bootstrap-user")
    before = snapshot(sessions)
    capsys.readouterr()
    monkeypatch.setenv("GEOPOL_BOOTSTRAP_PASSWORD", "too-short")
    prompt = Mock(side_effect=AssertionError("Una instalación existente no pide contraseña"))
    hashing = Mock(side_effect=AssertionError("Una instalación existente no prepara credenciales"))
    monkeypatch.setattr(cli.getpass, "getpass", prompt)
    monkeypatch.setattr(cli, "password_hash", hashing)

    invoke(monkeypatch, "bootstrap-user", "--username", "otro-administrador")

    assert snapshot(sessions) == before
    prompt.assert_not_called()
    hashing.assert_not_called()
    assert "Ya existen usuarios" in capsys.readouterr().out


@pytest.mark.parametrize("role,active", [("operator", True), ("reviewer", True), ("analyst", False)])
def test_existing_non_admin_user_prevents_bootstrap_even_when_inactive(
    sessions, monkeypatch, role, active,
):
    with sessions() as db:
        db.add(User(username="cuenta-existente", password_hash="unchanged-hash", role=role, active=active))
        db.commit()
    before = snapshot(sessions)
    prompt = Mock(side_effect=AssertionError("No debe crear ni elevar una cuenta existente"))
    monkeypatch.setattr(cli.getpass, "getpass", prompt)

    invoke(monkeypatch, "bootstrap-user")

    assert snapshot(sessions) == before
    assert not any(user[3] == "admin" for user in snapshot(sessions))
    prompt.assert_not_called()


def test_user_created_during_password_prompt_is_not_overwritten_or_promoted(sessions, monkeypatch):
    def password_prompt(_):
        with sessions() as db:
            db.add(User(username="otro-operador", password_hash="preserved", role="operator"))
            db.commit()
        return "Synthetic-concurrent-2026"

    monkeypatch.setattr(cli.getpass, "getpass", password_prompt)

    invoke(monkeypatch, "bootstrap-user")

    users = snapshot(sessions)
    assert len(users) == 1
    assert users[0][1:] == ("otro-operador", "preserved", "operator", True)


@pytest.mark.parametrize("password", ["short", "eleven-chrs"])
def test_invalid_password_exits_cleanly_without_creating_user(sessions, monkeypatch, capsys, password):
    monkeypatch.setenv("GEOPOL_BOOTSTRAP_PASSWORD", password)

    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "bootstrap-user")

    assert error.value.code == 2
    assert snapshot(sessions) == []
    output = capsys.readouterr()
    assert "al menos 12 caracteres" in output.err
    assert "Traceback" not in output.err
    assert password not in output.out + output.err


def test_missing_interactive_input_reports_how_to_supply_password(sessions, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", Mock(side_effect=EOFError))

    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "bootstrap-user")

    assert error.value.code == 2
    assert snapshot(sessions) == []
    assert "GEOPOL_BOOTSTRAP_PASSWORD" in capsys.readouterr().err


def test_create_user_command_retains_explicit_role_and_duplicate_protection(sessions, monkeypatch, capsys):
    monkeypatch.setenv("GEOPOL_BOOTSTRAP_PASSWORD", "Synthetic-create-user-2026")
    invoke(monkeypatch, "create-user", "--username", "revisor", "--role", "reviewer")
    before = snapshot(sessions)
    assert before[0][3] == "reviewer"

    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, "create-user", "--username", "revisor", "--role", "admin")

    assert error.value.code == 2
    assert snapshot(sessions) == before
    assert "no se modificó su contraseña" in capsys.readouterr().err
