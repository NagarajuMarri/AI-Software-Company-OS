from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import threading

import pytest

from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserArtifactError,
    BrowserAuthorityError,
    BrowserExecutionPolicy,
    BrowserExecutionRequest,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserInputBinding,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserPlanError,
    BrowserStep,
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
    FileBrowserJourneyPlanStore,
    InMemoryBrowserExecutionStore,
    InMemoryBrowserJourneyPlanStore,
    ManagedProductBrowserService,
    PlaywrightChromiumProvider,
)
from runtime.managed_product_browser.playwright_provider import _redact
from runtime.managed_product_environment import (
    EnvironmentExecutionPolicy,
    EnvironmentObservation,
    EnvironmentObservationKind,
    EnvironmentObservationOutcome,
    EnvironmentStage,
    LocalManagedProductEnvironmentProvider,
    ManagedProductEnvironmentResult,
    ManagedProductEnvironmentService,
    ReadyEnvironmentExecution,
)
from runtime.managed_product_runtime import (
    CommandSpec,
    InMemoryRuntimeConfigurationStore,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
    SecretEnvironmentReference,
)
from runtime.runtime_acceptance import (
    AcceptanceJourney,
    AcceptanceStage,
    CapabilityAcceptanceContract,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    RuntimeAcceptanceProfile,
    RuntimeAcceptanceRun,
    RuntimeAcceptanceService,
    RuntimeAcceptanceStore,
)


NOW = datetime(2026, 8, 17, 6, tzinfo=timezone.utc)
PASSWORD = "correct-horse-battery-staple"
JOURNEY_TITLE = "Learner logs in and restores the authenticated session"


class MappingResolver:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def resolve(self, reference):
        self.calls.append(reference)
        return self.values[reference]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


def profile():
    journey = AcceptanceJourney(
        "authentication.login",
        "AUTHENTICATION",
        JOURNEY_TITLE,
        (
            EvidenceKind.BROWSER,
            EvidenceKind.BROWSER_CONSOLE,
            EvidenceKind.BROWSER_NETWORK,
            EvidenceKind.SCREENSHOT,
        ),
    )
    contract = CapabilityAcceptanceContract(
        "AUTHENTICATION",
        "1.0",
        "Managed login",
        (journey.journey_id,),
    )
    return RuntimeAcceptanceProfile("login-profile", "1.0", (contract,), (journey,))


def configuration(repository_url="https://github.com/example/product.git", commit="a" * 40, port=8123):
    value = profile()
    origin = f"http://127.0.0.1:{port}"
    return ManagedProductRuntimeConfiguration(
        "product-runtime",
        "product",
        1,
        repository_url,
        "main",
        commit,
        f"{origin}/",
        f"{origin}/api",
        (origin,),
        (OneShotCommand("migrate", CommandSpec("python", ("migrate.py",)), 10),),
        (
            ManagedRuntimeService(
                "app",
                CommandSpec("python", ("service.py", "127.0.0.1", str(port))),
                ReadinessProbe("app-ready", f"{origin}/health", (204,), 10, 1),
                OneShotCommand("stop-app", CommandSpec("python", ("stop.py",)), 10),
                10,
                5,
            ),
        ),
        ("APP_PASSWORD",),
        (),
        (SecretEnvironmentReference("APP_PASSWORD", "fixture.product-password"),),
        value.profile_id,
        value.version,
        value.digest,
        "test",
        NOW,
    )


def plan(config=None, **changes):
    config = config or configuration()
    value = profile()
    fields = dict(
        plan_id="login-plan",
        run_id="acceptance-run",
        product_id=config.project_id,
        configuration_id=config.configuration_id,
        configuration_revision=config.revision,
        configuration_digest=config.digest,
        commit_sha=config.commit_sha,
        acceptance_profile_id=value.profile_id,
        acceptance_profile_version=value.version,
        acceptance_profile_digest=value.digest,
        journeys=(
            BrowserJourneySpecification(
                "authentication.login",
                "AUTHENTICATION",
                JOURNEY_TITLE,
                "/login",
                (
                    BrowserStep(
                        "fill-email",
                        BrowserActionKind.FILL,
                        BrowserLocator(BrowserLocatorKind.LABEL, "Email"),
                        "learner-email",
                    ),
                    BrowserStep(
                        "fill-password",
                        BrowserActionKind.FILL,
                        BrowserLocator(BrowserLocatorKind.LABEL, "Password"),
                        "learner-password",
                    ),
                    BrowserStep(
                        "submit-login",
                        BrowserActionKind.CLICK,
                        BrowserLocator(
                            BrowserLocatorKind.ROLE, "button", "Log in"
                        ),
                    ),
                    BrowserStep(
                        "welcome",
                        BrowserActionKind.ASSERT_TEXT,
                        BrowserLocator(BrowserLocatorKind.TEXT, "Welcome learner"),
                        expected_text="Welcome learner",
                    ),
                    BrowserStep(
                        "dashboard-url",
                        BrowserActionKind.ASSERT_URL_PATH,
                        expected_path="/dashboard",
                    ),
                    BrowserStep("reload", BrowserActionKind.RELOAD),
                    BrowserStep(
                        "restored",
                        BrowserActionKind.ASSERT_TEXT,
                        BrowserLocator(BrowserLocatorKind.TEXT, "Welcome learner"),
                        expected_text="Welcome learner",
                    ),
                ),
                30,
            ),
        ),
        inputs=(
            BrowserInputBinding("learner-email", "learner@example.invalid"),
            BrowserInputBinding(
                "learner-password", secret_reference="fixture.browser-password"
            ),
        ),
        created_by="test",
        created_at=NOW,
    )
    fields.update(changes)
    return BrowserJourneyPlan(**fields)


def acceptance_store(tmp_path, config):
    store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    value = profile()
    run = RuntimeAcceptanceRun(
        "acceptance-run",
        config.project_id,
        "1.0",
        config.commit_sha,
        AcceptanceStage.PLANNED,
        value.capabilities,
        value.journeys,
        NOW,
        NOW,
        runtime_configuration_id=config.configuration_id,
        runtime_configuration_revision=config.revision,
        runtime_configuration_digest=config.digest,
        acceptance_profile_id=value.profile_id,
        acceptance_profile_version=value.version,
        acceptance_profile_digest=value.digest,
    )
    service = RuntimeAcceptanceService(store)
    run = service.plan(run)
    run = service.mark_implemented(run.product_id, run.run_id, NOW)
    automated = tuple(
        EvidenceArtifact(
            f"acceptance-run.authentication.login.{kind.value}",
            run.run_id,
            "AUTHENTICATION",
            "authentication.login",
            kind,
            EvidenceOutcome.PASS,
            config.commit_sha,
            f"artifact://automated/{kind.value}",
            hashlib.sha256(kind.value.encode()).hexdigest(),
            NOW,
            f"Verified {kind.value}",
        )
        for kind in (EvidenceKind.CODE, EvidenceKind.AUTOMATED_TEST)
    )
    service.record_automated_verification(run.product_id, run.run_id, automated, NOW)
    return store


def test_browser_plan_is_canonical_and_sensitive_inputs_use_references():
    value = plan()
    assert len(value.digest) == 64
    assert value.digest != replace(
        value,
        inputs=(
            replace(value.inputs[0], public_value="other@example.invalid"),
            value.inputs[1],
        ),
    ).digest
    with pytest.raises(ValueError, match="Secret-bearing"):
        BrowserInputBinding("learner-password", "plaintext-password")
    with pytest.raises(ValueError, match="exactly one"):
        BrowserInputBinding("value")


@pytest.mark.parametrize("unsafe", ["/../admin", "/a/./b", "/a//b", "/%2e%2e/admin", "/x?q=1"])
def test_browser_paths_reject_ambiguous_or_traversing_targets(unsafe):
    with pytest.raises(ValueError, match="canonical|traversal"):
        replace(plan().journeys[0], start_path=unsafe)


def test_browser_steps_are_declarative_and_deeply_immutable():
    with pytest.raises(ValueError, match="tuple"):
        replace(plan().journeys[0], steps=list(plan().journeys[0].steps))
    with pytest.raises(ValueError, match="locator"):
        BrowserStep("unsafe", BrowserActionKind.CLICK)
    with pytest.raises(ValueError, match="Only fill"):
        BrowserStep("unsafe", BrowserActionKind.RELOAD, input_id="value")


def test_file_plan_store_is_restart_safe_immutable_and_tamper_evident(tmp_path):
    value = plan()
    store = FileBrowserJourneyPlanStore(tmp_path / "plans")
    store.save(value)
    restarted = FileBrowserJourneyPlanStore(tmp_path / "plans")
    assert restarted.load(value.product_id, value.run_id, value.plan_id) == value
    with pytest.raises(BrowserPlanError, match="immutable"):
        restarted.save(replace(value, created_by="other"))
    path = tmp_path / "plans" / value.product_id / value.run_id / f"{value.plan_id}.json"
    envelope = json.loads(path.read_text())
    envelope["digest"] = "f" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(BrowserPlanError, match="corrupt"):
        restarted.load(value.product_id, value.run_id, value.plan_id)


def test_artifacts_are_content_addressed_restart_safe_and_tamper_evident(tmp_path):
    store = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    uri, digest = store.write_json("product", "acceptance-run", {"status": "PASS"})
    assert digest in uri
    path = store.resolve(uri)
    assert json.loads(path.read_text()) == {"status": "PASS"}
    path.write_bytes(b"tampered")
    with pytest.raises(BrowserArtifactError, match="integrity"):
        store.resolve(uri)


def test_console_redaction_covers_resolved_and_standard_credential_forms():
    rendered = _redact(
        "password=hunter2 authorization:Basic QWxhZGRpbjpvcGVuU2VzYW1l raw-value",
        ("raw-value",),
    )
    assert "hunter2" not in rendered
    assert "QWxhZGRpbjpvcGVuU2VzYW1l" not in rendered
    assert "raw-value" not in rendered


def test_execution_store_restarts_and_rejects_mutation(tmp_path):
    value = BrowserExecutionResult(
        "acceptance-run",
        "product",
        "login-plan",
        plan().digest,
        "a" * 40,
        BrowserExecutionStage.FAILED,
        (),
        (),
        NOW,
        NOW,
        "BROWSER_PROVIDER_FAILED",
    )
    store = FileBrowserExecutionStore(tmp_path / "results")
    store.save(value)
    assert FileBrowserExecutionStore(tmp_path / "results").load(
        "product", "acceptance-run", "login-plan"
    ) == value
    with pytest.raises(BrowserArtifactError, match="immutable"):
        store.save(replace(value, failure_code="OTHER_FAILURE"))


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is privilege-dependent")
def test_browser_persistence_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "plans"
    store = FileBrowserJourneyPlanStore(root)
    (root / "product").symlink_to(outside, target_is_directory=True)
    with pytest.raises(BrowserPlanError, match="symlink"):
        store.save(plan())
    assert list(outside.iterdir()) == []


class FakeEnvironmentService:
    def __init__(self, config_store):
        self.configuration_store = config_store
        self.calls = 0

    def verify_with_ready_probe(self, request, probe):
        self.calls += 1
        config = self.configuration_store.get_revision(
            request.project_id, request.configuration_id, request.configuration_revision
        )
        browser = probe(config)
        observation = EnvironmentObservation(
            EnvironmentObservationKind.READINESS,
            "app-ready",
            EnvironmentObservationOutcome.PASS,
            NOW,
            NOW,
            "Ready",
            hashlib.sha256(b"").hexdigest(),
            204,
        )
        result = ManagedProductEnvironmentResult(
            request.run_id,
            request.project_id,
            request.configuration_id,
            request.configuration_revision,
            request.configuration_digest,
            config.commit_sha,
            EnvironmentStage.STOPPED,
            (observation,),
            NOW,
            NOW,
        )
        return ReadyEnvironmentExecution(result, browser)


class FakeBrowserProvider:
    provider_id = "playwright-chromium"

    def __init__(self):
        self.calls = 0

    def execute(self, value, config, inputs, redactions, artifact_store):
        self.calls += 1
        assert config.commit_sha == value.commit_sha
        assert inputs["learner-password"] == PASSWORD
        assert redactions == (PASSWORD,)
        journey = value.journeys[0]
        evidence = []
        for kind in (
            EvidenceKind.BROWSER,
            EvidenceKind.BROWSER_CONSOLE,
            EvidenceKind.BROWSER_NETWORK,
            EvidenceKind.SCREENSHOT,
        ):
            if kind is EvidenceKind.SCREENSHOT:
                uri, digest = artifact_store.write_bytes(
                    value.product_id, value.run_id, b"\x89PNG\r\n\x1a\nfake", "png"
                )
            else:
                uri, digest = artifact_store.write_json(
                    value.product_id,
                    value.run_id,
                    {"kind": kind.value, "outcome": "PASS"},
                )
            evidence.append(
                EvidenceArtifact(
                    f"{value.run_id}.{journey.journey_id}.{kind.value}",
                    value.run_id,
                    journey.capability_id,
                    journey.journey_id,
                    kind,
                    EvidenceOutcome.PASS,
                    value.commit_sha,
                    uri,
                    digest,
                    NOW,
                    f"Verified {kind.value}",
                )
            )
        result = JourneyResult(
            journey.journey_id,
            EvidenceOutcome.PASS,
            tuple(item.evidence_id for item in evidence),
            NOW,
        )
        return BrowserExecutionResult(
            value.run_id,
            value.product_id,
            value.plan_id,
            value.digest,
            value.commit_sha,
            BrowserExecutionStage.COMPLETED,
            tuple(evidence),
            (result,),
            NOW,
            NOW,
        )


def test_authority_and_current_policy_are_checked_before_browser_secrets_or_effects(tmp_path):
    config = configuration()
    configs = InMemoryRuntimeConfigurationStore()
    configs.save(config)
    plans = InMemoryBrowserJourneyPlanStore()
    value = plan(config)
    plans.save(value)
    resolver = MappingResolver({"fixture.browser-password": PASSWORD})
    provider = FakeBrowserProvider()
    environment = FakeEnvironmentService(configs)
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    service = ManagedProductBrowserService(
        acceptance_store(tmp_path, config),
        plans,
        InMemoryBrowserExecutionStore(),
        environment,
        resolver,
        BrowserExecutionPolicy(
            frozenset({provider.provider_id}),
            frozenset(config.allowed_origins),
            frozenset(),
        ),
        provider,
        artifacts,
    )
    with pytest.raises(BrowserAuthorityError, match="secret reference"):
        service.execute(
            BrowserExecutionRequest(value.run_id, value.product_id, value.plan_id, value.digest)
        )
    assert resolver.calls == []
    assert provider.calls == 0
    assert environment.calls == 0


def test_exact_retry_reuses_immutable_result_without_second_browser_effect(tmp_path):
    config = configuration()
    configs = InMemoryRuntimeConfigurationStore()
    configs.save(config)
    plans = InMemoryBrowserJourneyPlanStore()
    value = plans.save(plan(config))
    resolver = MappingResolver({"fixture.browser-password": PASSWORD})
    provider = FakeBrowserProvider()
    environment = FakeEnvironmentService(configs)
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    service = ManagedProductBrowserService(
        acceptance_store(tmp_path, config),
        plans,
        InMemoryBrowserExecutionStore(),
        environment,
        resolver,
        BrowserExecutionPolicy(
            frozenset({provider.provider_id}),
            frozenset(config.allowed_origins),
            frozenset({"fixture.browser-password"}),
        ),
        provider,
        artifacts,
    )
    request = BrowserExecutionRequest(
        value.run_id, value.product_id, value.plan_id, value.digest
    )
    first = service.execute(request)
    second = service.execute(request)
    assert second == first
    assert provider.calls == 1
    assert environment.calls == 1
    assert resolver.calls == ["fixture.browser-password"]
    artifacts.resolve(first.evidence[0].artifact_uri).write_bytes(b"tampered")
    with pytest.raises(BrowserArtifactError, match="integrity"):
        service.execute(request)
    assert provider.calls == 1
    assert environment.calls == 1


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_login_session_restore_and_secret_safe_evidence(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "migrate.py").write_text(
        "from pathlib import Path\nPath('migration.marker').write_text('ok')\n",
        encoding="utf-8",
    )
    (source / "stop.py").write_text(
        "from pathlib import Path\nPath('stop.flag').write_text('stop')\n",
        encoding="utf-8",
    )
    (source / "service.py").write_text(_SERVICE_FIXTURE, encoding="utf-8")
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "ASCOS Test")
    _git(source, "config", "user.email", "ascos@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "browser fixture")
    commit = _git(source, "rev-parse", "HEAD").strip()

    served = tmp_path / "served"
    served.mkdir()
    bare = served / "product.git"
    _git(tmp_path, "clone", "--bare", str(source), str(bare))
    _git(bare, "update-server-info")
    git_server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_QuietHandler, directory=str(served))
    )
    thread = threading.Thread(target=git_server.serve_forever, daemon=True)
    thread.start()
    try:
        product_port = _free_port()
        repository_url = (
            f"http://127.0.0.1:{git_server.server_address[1]}/product.git"
        )
        config = configuration(repository_url, commit, product_port)
        configs = InMemoryRuntimeConfigurationStore()
        configs.save(config)
        runtime_resolver = MappingResolver({"fixture.product-password": PASSWORD})
        environment = ManagedProductEnvironmentService(
            configs,
            LocalManagedProductEnvironmentProvider(tmp_path / "environments"),
            runtime_resolver,
            EnvironmentExecutionPolicy(
                frozenset({"127.0.0.1"}),
                frozenset({"python"}),
                frozenset(config.allowed_origins),
                frozenset(config.environment_allow_list),
                frozenset({"fixture.product-password"}),
            ),
        )
        plans = FileBrowserJourneyPlanStore(tmp_path / "plans")
        value = plans.save(plan(config))
        artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
        results = FileBrowserExecutionStore(tmp_path / "results")
        browser_resolver = MappingResolver({"fixture.browser-password": PASSWORD})
        service = ManagedProductBrowserService(
            acceptance_store(tmp_path, config),
            plans,
            results,
            environment,
            browser_resolver,
            BrowserExecutionPolicy(
                frozenset({"playwright-chromium"}),
                frozenset(config.allowed_origins),
                frozenset({"fixture.browser-password"}),
            ),
            PlaywrightChromiumProvider(),
            artifacts,
        )
        result = service.execute(
            BrowserExecutionRequest(
                value.run_id, value.product_id, value.plan_id, value.digest
            )
        )
    finally:
        git_server.shutdown()
        thread.join(timeout=5)
        git_server.server_close()

    network_diagnostics = [
        json.loads(artifacts.resolve(item.artifact_uri).read_text(encoding="utf-8"))
        for item in result.evidence
        if item.kind is EvidenceKind.BROWSER_NETWORK
    ]
    assert result.stage is BrowserExecutionStage.COMPLETED, network_diagnostics
    assert result.commit_sha == commit
    assert {item.kind for item in result.evidence} >= {
        EvidenceKind.MIGRATION,
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    }
    assert all(item.outcome is EvidenceOutcome.PASS for item in result.evidence)
    assert result.journey_results[0].outcome is EvidenceOutcome.PASS
    assert runtime_resolver.calls == ["fixture.product-password"]
    assert browser_resolver.calls == ["fixture.browser-password"]
    assert not any((tmp_path / "environments").rglob("acceptance-run"))
    restored = FileBrowserExecutionStore(tmp_path / "results").load(
        result.product_id, result.run_id, result.plan_id
    )
    assert restored == result
    for item in result.evidence:
        artifact = artifacts.resolve(item.artifact_uri)
        content = artifact.read_bytes()
        assert PASSWORD.encode() not in content
        if item.kind is EvidenceKind.BROWSER_NETWORK:
            rendered = json.loads(content)
            assert "headers" not in content.decode()
            assert "body" not in content.decode()
            assert all("?" not in entry["url"] for entry in rendered["entries"])


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


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_SERVICE_FIXTURE = r'''from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import os
import sys

LOGIN = """<!doctype html><html><head><link rel='icon' href='data:,'></head><body>
<main><h1>Sign in</h1><form id='login'>
<label>Email <input id='email' name='email'></label>
<label>Password <input id='password' name='password' type='password'></label>
<button type='submit'>Log in</button></form><p id='message'></p></main>
<script>
document.getElementById('login').addEventListener('submit', async (event) => {
  event.preventDefault();
  const response = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});
  if (response.ok) { history.pushState({}, '', '/dashboard'); document.querySelector('main').innerHTML='<h1>Welcome learner</h1>'; }
  else { document.getElementById('message').textContent='Login failed'; }
});
</script></body></html>"""

DASHBOARD = """<!doctype html><html><head><link rel='icon' href='data:,'></head><body><main id='app'>Restoring session</main>
<script>
fetch('/api/session').then(response => response.json()).then(value => {
  document.getElementById('app').innerHTML = value.authenticated ? '<h1>Welcome learner</h1>' : '<h1>Sign in required</h1>';
});
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def send(self, status, body=b'', content_type='text/plain', cookie=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == '/health': return self.send(204)
        if self.path == '/login': return self.send(200, LOGIN.encode(), 'text/html')
        if self.path == '/dashboard': return self.send(200, DASHBOARD.encode(), 'text/html')
        if self.path == '/api/session':
            authenticated = 'session=ok' in self.headers.get('Cookie', '')
            return self.send(200, json.dumps({'authenticated': authenticated}).encode(), 'application/json')
        return self.send(404)
    def do_POST(self):
        if self.path != '/api/login': return self.send(404)
        length = int(self.headers.get('Content-Length', '0'))
        value = json.loads(self.rfile.read(length))
        if value.get('email') == 'learner@example.invalid' and value.get('password') == os.environ['APP_PASSWORD']:
            return self.send(200, b'{"ok":true}', 'application/json', 'session=ok; HttpOnly; SameSite=Strict; Path=/')
        return self.send(401, b'{"ok":false}', 'application/json')
    def log_message(self, _format, *_args): return

server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = 0.1
while not Path('stop.flag').exists(): server.handle_request()
server.server_close()
'''
