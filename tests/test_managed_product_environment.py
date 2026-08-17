from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
from pathlib import Path
import os
import shutil
import subprocess
import threading

import pytest

from runtime.managed_product_environment import (
    EnvironmentAuthorityError,
    EnvironmentExecutionPolicy,
    EnvironmentExecutionRequest,
    EnvironmentObservationKind,
    EnvironmentObservationOutcome,
    EnvironmentStage,
    EnvironmentWorkspaceError,
    LocalManagedProductEnvironmentProvider,
    ManagedProductEnvironmentService,
)
from runtime.managed_product_runtime import (
    CommandSpec,
    InMemoryRuntimeConfigurationStore,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
    RuntimeEnvironmentVariable,
    SecretEnvironmentReference,
)


NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)
PROFILE_DIGEST = "a" * 64
SECRET_VALUE = "runtime-secret-value-that-must-never-persist"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


class MappingResolver:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def resolve(self, reference):
        self.calls.append(reference)
        return self.values[reference]


@pytest.fixture
def runtime_repository(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "migrate.py").write_text(
        """\
import os
from pathlib import Path
Path('migration.marker').write_text(os.environ['PUBLIC_VALUE'])
print(os.environ['SECRET_TOKEN'])
""",
        encoding="utf-8",
    )
    (source / "fail.py").write_text(
        "raise SystemExit(7)\n", encoding="utf-8"
    )
    (source / "service.py").write_text(
        """\
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, _format, *_args):
        return

server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = 0.1
while not Path('stop.flag').exists():
    server.handle_request()
server.server_close()
""",
        encoding="utf-8",
    )
    (source / "stop.py").write_text(
        "from pathlib import Path\nPath('stop.flag').write_text('stop')\n",
        encoding="utf-8",
    )
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "ASCOS Test")
    _git(source, "config", "user.email", "ascos@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "fixture")
    commit = _git(source, "rev-parse", "HEAD").strip()

    served = tmp_path / "served"
    served.mkdir()
    bare = served / "product.git"
    _git(tmp_path, "clone", "--bare", str(source), str(bare))
    _git(bare, "update-server-info")
    handler = partial(_QuietHandler, directory=str(served))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/product.git", commit
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _git(cwd, *arguments):
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def configuration(repository_url, commit_sha, port, **changes):
    origin = f"http://127.0.0.1:{port}"
    values = {
        "configuration_id": "product-runtime",
        "project_id": "product",
        "revision": 1,
        "repository_url": repository_url,
        "branch": "main",
        "commit_sha": commit_sha,
        "frontend_url": f"{origin}/",
        "backend_url": f"{origin}/api",
        "allowed_origins": (origin,),
        "migration_commands": (
            OneShotCommand("migrate", CommandSpec("python", ("migrate.py",)), 10),
        ),
        "services": (
            ManagedRuntimeService(
                "app",
                CommandSpec("python", ("service.py", "127.0.0.1", str(port))),
                ReadinessProbe("app-ready", f"{origin}/health", (204,), 5, 1),
                OneShotCommand("stop-app", CommandSpec("python", ("stop.py",)), 10),
                5,
                5,
            ),
        ),
        "environment_allow_list": ("PUBLIC_VALUE", "SECRET_TOKEN"),
        "environment": (RuntimeEnvironmentVariable("PUBLIC_VALUE", "acceptance"),),
        "secret_references": (
            SecretEnvironmentReference("SECRET_TOKEN", "fixture.runtime-token"),
        ),
        "acceptance_profile_id": "fixture-profile",
        "acceptance_profile_version": "1.0",
        "acceptance_profile_digest": PROFILE_DIGEST,
        "created_by": "test",
        "created_at": NOW,
    }
    values.update(changes)
    return ManagedProductRuntimeConfiguration(**values)


def service(tmp_path, config, *, resolver=None, policy=None):
    store = InMemoryRuntimeConfigurationStore()
    store.save(config)
    origin = config.allowed_origins[0]
    return ManagedProductEnvironmentService(
        store,
        LocalManagedProductEnvironmentProvider(tmp_path / "environments"),
        resolver or MappingResolver({"fixture.runtime-token": SECRET_VALUE}),
        policy
        or EnvironmentExecutionPolicy(
            frozenset({"127.0.0.1"}),
            frozenset({"python"}),
            frozenset({origin}),
            frozenset(config.environment_allow_list),
            frozenset({"fixture.runtime-token"}),
        ),
    )


def request(config):
    return EnvironmentExecutionRequest(
        "environment-run-1",
        config.project_id,
        config.configuration_id,
        config.revision,
        config.digest,
    )


def test_real_exact_sha_migration_service_readiness_shutdown_and_cleanup(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    port = _free_port()
    config = configuration(repository_url, commit, port)

    result = service(tmp_path, config).verify(request(config))

    assert result.stage is EnvironmentStage.STOPPED
    assert result.commit_sha == commit
    assert result.failure_code is None
    assert not result.workspace_retained
    assert [item.kind for item in result.observations] == [
        EnvironmentObservationKind.SOURCE,
        EnvironmentObservationKind.MIGRATION,
        EnvironmentObservationKind.SERVICE_STARTUP,
        EnvironmentObservationKind.READINESS,
        EnvironmentObservationKind.SERVICE_STOP,
        EnvironmentObservationKind.CLEANUP,
    ]
    assert all(
        item.outcome is EnvironmentObservationOutcome.PASS
        for item in result.observations
    )
    expected_redacted = hashlib.sha256(b"[REDACTED]\n\0").hexdigest()
    assert result.observations[1].output_digest == expected_redacted
    assert len(result.digest) == 64
    rendered = repr(result)
    assert SECRET_VALUE not in rendered
    assert "fixture.runtime-token" not in rendered
    assert not any((tmp_path / "environments").rglob("environment-run-1"))


def test_prepare_checks_out_exact_commit_and_removes_all_remotes(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    config = configuration(repository_url, commit, _free_port())
    provider = LocalManagedProductEnvironmentProvider(tmp_path / "environments")
    workspace, observation = provider.prepare(config, "prepare-run")
    try:
        assert observation.outcome is EnvironmentObservationOutcome.PASS
        assert _git(workspace.path, "rev-parse", "HEAD").strip() == commit
        assert _git(workspace.path, "remote").strip() == ""
        assert _git(workspace.path, "status", "--porcelain").strip() == ""
    finally:
        provider.cleanup(workspace)


def test_wrong_exact_commit_fails_and_removes_partial_clone(tmp_path, runtime_repository):
    repository_url, _commit = runtime_repository
    config = configuration(repository_url, "b" * 40, _free_port())

    result = service(tmp_path, config).verify(request(config))

    assert result.stage is EnvironmentStage.FAILED
    assert result.failure_code == "SOURCE_COMMIT_MISMATCH"
    assert result.observations == ()
    assert not result.workspace_retained
    assert not any((tmp_path / "environments").rglob("environment-run-1"))


def test_nonzero_migration_is_recorded_and_service_never_starts(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    port = _free_port()
    config = configuration(
        repository_url,
        commit,
        port,
        migration_commands=(
            OneShotCommand("fail-migration", CommandSpec("python", ("fail.py",)), 10),
        ),
    )

    result = service(tmp_path, config).verify(request(config))

    assert result.stage is EnvironmentStage.FAILED
    assert result.failure_code == "COMMAND_EXITED_NONZERO"
    assert [item.kind for item in result.observations] == [
        EnvironmentObservationKind.SOURCE,
        EnvironmentObservationKind.MIGRATION,
        EnvironmentObservationKind.CLEANUP,
    ]
    assert result.observations[1].outcome is EnvironmentObservationOutcome.FAIL


def test_current_execution_policy_is_rechecked_before_secret_or_provider_effects(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    config = configuration(repository_url, commit, _free_port())
    resolver = MappingResolver({"fixture.runtime-token": SECRET_VALUE})
    denied = EnvironmentExecutionPolicy(
        frozenset({"example.com"}),
        frozenset({"python"}),
        frozenset(config.allowed_origins),
        frozenset(config.environment_allow_list),
        frozenset({"fixture.runtime-token"}),
    )
    manager = service(tmp_path, config, resolver=resolver, policy=denied)

    with pytest.raises(EnvironmentAuthorityError, match="host"):
        manager.verify(request(config))

    assert resolver.calls == []
    assert not (tmp_path / "environments").exists()


def test_request_must_bind_the_exact_persisted_digest(tmp_path, runtime_repository):
    repository_url, commit = runtime_repository
    config = configuration(repository_url, commit, _free_port())
    invalid = replace(request(config), configuration_digest="f" * 64)

    with pytest.raises(EnvironmentAuthorityError, match="exact persisted"):
        service(tmp_path, config).verify(invalid)

    assert not (tmp_path / "environments").exists()


def test_secret_resolution_failure_is_bounded_and_has_no_runtime_effect(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    config = configuration(repository_url, commit, _free_port())

    class FailingResolver:
        def resolve(self, _reference):
            raise RuntimeError(f"provider exposed {SECRET_VALUE}")

    result = service(tmp_path, config, resolver=FailingResolver()).verify(request(config))

    assert result.stage is EnvironmentStage.FAILED
    assert result.failure_code == "SECRET_RESOLUTION_FAILED"
    assert result.observations == ()
    assert SECRET_VALUE not in repr(result)
    assert not (tmp_path / "environments").exists()


def test_readiness_failure_stops_service_and_cleans_workspace(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    service_port = _free_port()
    unreachable_port = _free_port()
    config = configuration(repository_url, commit, service_port)
    declared = config.services[0]
    config = replace(
        config,
        services=(
            replace(
                declared,
                readiness_probe=ReadinessProbe(
                    "app-ready",
                    f"http://127.0.0.1:{unreachable_port}/health",
                    (204,),
                    1,
                    1,
                ),
                startup_timeout_seconds=1,
            ),
        ),
        allowed_origins=tuple(
            sorted(
                {
                    config.allowed_origins[0],
                    f"http://127.0.0.1:{unreachable_port}",
                }
            )
        ),
    )
    policy = EnvironmentExecutionPolicy(
        frozenset({"127.0.0.1"}),
        frozenset({"python"}),
        frozenset(config.allowed_origins),
        frozenset(config.environment_allow_list),
        frozenset({"fixture.runtime-token"}),
    )

    result = service(tmp_path, config, policy=policy).verify(request(config))

    assert result.stage is EnvironmentStage.FAILED
    assert result.failure_code == "READINESS_TIMEOUT"
    assert EnvironmentObservationKind.SERVICE_STOP in {
        item.kind for item in result.observations
    }
    assert result.observations[-1].kind is EnvironmentObservationKind.CLEANUP
    assert not result.workspace_retained


def test_failed_declared_stop_is_reported_after_forced_termination_and_cleanup(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    port = _free_port()
    config = configuration(repository_url, commit, port)
    declared = config.services[0]
    config = replace(
        config,
        services=(
            replace(
                declared,
                stop_command=OneShotCommand(
                    "stop-app", CommandSpec("python", ("fail.py",)), 1
                ),
                shutdown_timeout_seconds=1,
            ),
        ),
    )

    result = service(tmp_path, config).verify(request(config))

    assert result.stage is EnvironmentStage.FAILED
    assert result.failure_code == "SERVICE_SHUTDOWN_FAILED"
    assert result.observations[-2].kind is EnvironmentObservationKind.SERVICE_STOP
    assert result.observations[-2].outcome is EnvironmentObservationOutcome.FAIL
    assert result.observations[-1].kind is EnvironmentObservationKind.CLEANUP


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is privilege-dependent")
def test_escaping_workspace_symlink_is_rejected_before_command_execution(
    tmp_path, runtime_repository
):
    repository_url, commit = runtime_repository
    config = configuration(repository_url, commit, _free_port())
    provider = LocalManagedProductEnvironmentProvider(tmp_path / "environments")
    workspace, _observation = provider.prepare(config, "symlink-run")
    outside = tmp_path / "outside.py"
    outside.write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
    (workspace.path / "escape.py").symlink_to(outside)
    command = OneShotCommand(
        "escape", CommandSpec("python", ("escape.py",)), 5
    )
    try:
        with pytest.raises(EnvironmentWorkspaceError, match="escaping symlink"):
            provider.run_migration(workspace, command, {}, ())
    finally:
        provider.cleanup(workspace)


def test_cleanup_failure_retains_workspace_and_requires_reconciliation(
    tmp_path, runtime_repository, monkeypatch
):
    repository_url, commit = runtime_repository
    port = _free_port()
    config = configuration(repository_url, commit, port)
    store = InMemoryRuntimeConfigurationStore()
    store.save(config)
    provider = LocalManagedProductEnvironmentProvider(tmp_path / "environments")

    def fail_cleanup(_path):
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(provider, "_remove", fail_cleanup)
    manager = ManagedProductEnvironmentService(
        store,
        provider,
        MappingResolver({"fixture.runtime-token": SECRET_VALUE}),
        EnvironmentExecutionPolicy(
            frozenset({"127.0.0.1"}),
            frozenset({"python"}),
            frozenset(config.allowed_origins),
            frozenset(config.environment_allow_list),
            frozenset({"fixture.runtime-token"}),
        ),
    )

    result = manager.verify(request(config))

    assert result.stage is EnvironmentStage.RECONCILIATION_REQUIRED
    assert result.workspace_retained
    assert result.failure_code == "WORKSPACE_CLEANUP_FAILED"
    retained = tmp_path / "environments" / "product" / "product-runtime" / "environment-run-1"
    assert retained.is_dir()
    shutil.rmtree(retained)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is privilege-dependent")
def test_workspace_root_symlink_is_rejected_before_clone(tmp_path, runtime_repository):
    repository_url, commit = runtime_repository
    actual = tmp_path / "actual-root"
    actual.mkdir()
    linked = tmp_path / "linked-root"
    linked.symlink_to(actual, target_is_directory=True)
    provider = LocalManagedProductEnvironmentProvider(linked)
    config = configuration(repository_url, commit, _free_port())

    with pytest.raises(EnvironmentWorkspaceError, match="root cannot be a symlink"):
        provider.prepare(config, "root-symlink-run")

    assert list(actual.iterdir()) == []


def test_execution_policy_rejects_unbounded_secret_reference_prefix():
    with pytest.raises(ValueError, match="prefixes"):
        EnvironmentExecutionPolicy(
            frozenset({"127.0.0.1"}),
            frozenset({"python"}),
            frozenset({"http://127.0.0.1:8000"}),
            frozenset({"APP_ENV"}),
            allowed_secret_reference_prefixes=("x" * 128 + ".",),
        )


def test_no_browser_network_or_repository_mutation_api_is_exposed():
    public = set(__import__("runtime.managed_product_environment", fromlist=["__all__"]).__all__)
    assert not public & {"Browser", "Playwright", "merge", "deploy", "release"}


def _free_port():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
