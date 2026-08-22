from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import stat
from wsgiref.util import setup_testing_defaults

import pytest

from runtime.local_uat import create_local_uat_application
from runtime.local_uat import cli
from runtime.local_uat.cli import _execution_configuration, _parser


def _request(application, path: str, method: str = "GET"):
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
        }
    )
    observed: dict[str, object] = {}

    def start_response(status, headers):
        observed["status"] = status
        observed["headers"] = dict(headers)

    observed["body"] = b"".join(application(environ, start_response))
    return observed


def test_launcher_exposes_welcome_health_and_authenticated_status(tmp_path):
    application = create_local_uat_application(
        tmp_path / "uat-data",
        "http://127.0.0.1:8765",
        preauth_secret=b"u" * 32,
    )

    welcome = _request(application, "/")
    assert welcome["status"] == "200 OK"
    assert b"Unified local UAT launcher" in welcome["body"]
    assert b"Local UAT only" in welcome["body"]
    assert welcome["headers"]["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in welcome["headers"]["Content-Security-Policy"]

    health = _request(application, "/healthz")
    assert health["status"] == "200 OK"
    assert json.loads(health["body"]) == {
        "application": "ascos-local-uat",
        "mode": "LOCAL_UAT_ONLY",
        "status": "ok",
    }

    status = _request(application, "/uat")
    assert status["status"] == "303 See Other"
    assert status["headers"]["Location"] == "/login"


def test_launcher_head_and_method_boundaries_are_explicit(tmp_path):
    application = create_local_uat_application(
        tmp_path,
        "http://127.0.0.1:8765",
        preauth_secret=b"u" * 32,
    )

    head = _request(application, "/healthz", "HEAD")
    assert head["status"] == "200 OK"
    assert head["body"] == b""
    assert int(head["headers"]["Content-Length"]) > 0

    rejected = _request(application, "/healthz", "POST")
    assert rejected["status"] == "405 Method Not Allowed"
    assert rejected["headers"]["Allow"] == "GET, HEAD"


def test_launcher_creates_and_reuses_one_private_local_secret(tmp_path):
    root = tmp_path / "persistent-uat"
    first = create_local_uat_application(root, "http://127.0.0.1:8765")
    secret_path = root / ".preauth-secret"
    secret = secret_path.read_bytes()

    second = create_local_uat_application(root, "http://127.0.0.1:8765")

    assert first is not second
    assert len(secret) == 32
    assert secret_path.read_bytes() == secret
    if os.name != "nt":
        assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(root.stat().st_mode) == 0o700


def test_launcher_rejects_noncanonical_origin_and_unsafe_secret(tmp_path):
    with pytest.raises(ValueError, match="canonical"):
        create_local_uat_application(
            tmp_path / "trailing",
            "http://127.0.0.1:8765/",
            preauth_secret=b"u" * 32,
        )

    root = tmp_path / "invalid-secret"
    root.mkdir()
    (root / ".preauth-secret").write_bytes(b"short")
    with pytest.raises(ValueError, match="secret file is invalid"):
        create_local_uat_application(root, "http://127.0.0.1:8765")


def test_cli_contract_uses_safe_defaults_and_rejects_invalid_ports():
    defaults = _parser().parse_args([])
    assert defaults.port == 8765
    assert defaults.data_dir == Path(".ascos-uat-data")
    assert defaults.no_browser is False

    with pytest.raises(SystemExit):
        _parser().parse_args(["--port", "0"])


def test_cli_builds_operator_only_execution_configuration_and_fails_closed(tmp_path):
    parser = _parser()
    arguments = parser.parse_args(
        [
            "--execution-workspace",
            str(tmp_path / "product"),
            "--execution-auth-mode",
            "chatgpt-subscription",
            "--execution-allowed-path",
            "src",
            "--execution-candidate-file",
            "src/app.py",
            "--enable-live-execution",
            "--confirm-live-operation",
        ]
    )
    configuration = _execution_configuration(parser, arguments)
    assert configuration is not None
    assert configuration.enabled is True
    assert configuration.live_operation_confirmed is True
    assert configuration.allowed_paths == ("src",)
    assert configuration.candidate_files == ("src/app.py",)
    assert configuration.billing_source == "chatgpt-plan"

    missing = _parser().parse_args(["--enable-live-execution"])
    with pytest.raises(SystemExit):
        _execution_configuration(_parser(), missing)


def test_launcher_truthfully_reports_optional_governed_execution(tmp_path):
    parser = _parser()
    arguments = parser.parse_args(
        [
            "--execution-workspace",
            str(tmp_path / "product"),
            "--execution-allowed-path",
            "src",
            "--execution-candidate-file",
            "src/app.py",
            "--enable-live-execution",
            "--confirm-live-operation",
        ]
    )
    configuration = _execution_configuration(parser, arguments)
    application = create_local_uat_application(
        tmp_path / "uat-data",
        "http://127.0.0.1:8765",
        preauth_secret=b"u" * 32,
        execution_configuration=configuration,
        execution_adapter=object(),
    )
    welcome = _request(application, "/")
    assert welcome["status"] == "200 OK"
    assert b"run one chargeable governed Codex coding turn" in welcome["body"]
    assert b"cannot commit, push, open a PR, merge, deploy, release" in welcome["body"]


def test_cli_binds_only_loopback_reports_boundary_and_closes(tmp_path, monkeypatch, capsys):
    observed: dict[str, object] = {}

    class Server:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            observed["closed"] = True

    def make_server(host, port, application):
        observed.update(host=host, port=port, application=application)
        return Server()

    monkeypatch.setattr(cli, "make_server", make_server)

    assert cli.main(["--no-browser", "--port", "8877", "--data-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 8877
    assert observed["closed"] is True
    assert "http://127.0.0.1:8877" in output
    assert "LOCAL UAT ONLY" in output
