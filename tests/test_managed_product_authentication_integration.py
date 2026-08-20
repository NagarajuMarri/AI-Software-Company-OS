from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading

import pytest

from runtime.managed_product_authentication import (
    AuthenticationEvidenceBrowserProvider,
    AuthenticationJourneyVerification,
    AuthenticationVerificationPlan,
    FileAuthenticationVerificationPlanStore,
    LOCKED_AUTHENTICATION_CLAIMS,
)
from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserExecutionPolicy,
    BrowserExecutionRequest,
    BrowserExecutionStage,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
    FileBrowserJourneyPlanStore,
    ManagedProductBrowserService,
    PlaywrightChromiumProvider,
)
from runtime.managed_product_environment import (
    EnvironmentExecutionPolicy,
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
)
from runtime.runtime_acceptance import (
    AcceptanceStage,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    RuntimeAcceptanceRun,
    RuntimeAcceptanceService,
    RuntimeAcceptanceStore,
    speakmate_v1_profile,
)
from runtime.runtime_acceptance.profiles import AUTHENTICATION_JOURNEYS


NOW = datetime(2026, 8, 17, 9, tzinfo=timezone.utc)
RAW_PASSWORD = "fixture-password-value"
RAW_TOKEN = "fixture-session-token-value"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


class _NoSecrets:
    def resolve(self, reference):
        raise AssertionError(f"Unexpected secret resolution: {reference}")


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_authentication_persistence_security_and_founder_evidence(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "migrate.py").write_text(_MIGRATION_FIXTURE, encoding="utf-8")
    (source / "service.py").write_text(_SERVICE_FIXTURE, encoding="utf-8")
    (source / "stop.py").write_text(
        "from pathlib import Path\nPath('stop.flag').write_text('stop')\n",
        encoding="utf-8",
    )
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "ASCOS Test")
    _git(source, "config", "user.email", "ascos@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "authentication fixture")
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
        config = _configuration(repository_url, commit, product_port)
        browser = _browser_plan(config)
        authentication = _authentication_plan(browser)
        configs = InMemoryRuntimeConfigurationStore()
        configs.save(config)
        environment = ManagedProductEnvironmentService(
            configs,
            LocalManagedProductEnvironmentProvider(tmp_path / "environments"),
            _NoSecrets(),
            EnvironmentExecutionPolicy(
                frozenset({"127.0.0.1"}),
                frozenset({"python"}),
                frozenset(config.allowed_origins),
                frozenset({"ASCOS_TEST_PUBLIC"}),
            ),
        )
        browser_plans = FileBrowserJourneyPlanStore(tmp_path / "browser-plans")
        browser_plans.save(browser)
        authentication_plans = FileAuthenticationVerificationPlanStore(
            tmp_path / "authentication-plans"
        )
        authentication_plans.save(authentication)
        artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
        executions = FileBrowserExecutionStore(tmp_path / "results")
        provider = AuthenticationEvidenceBrowserProvider(
            authentication.provider_id,
            authentication.verification_id,
            authentication_plans,
            PlaywrightChromiumProvider(),
        )
        service = ManagedProductBrowserService(
            _acceptance_store(tmp_path, config),
            browser_plans,
            executions,
            environment,
            _NoSecrets(),
            BrowserExecutionPolicy(
                frozenset({authentication.provider_id}),
                frozenset(config.allowed_origins),
            ),
            provider,
            artifacts,
        )
        result = service.execute(
            BrowserExecutionRequest(
                browser.run_id, browser.product_id, browser.plan_id, browser.digest
            )
        )
    finally:
        git_server.shutdown()
        thread.join(timeout=5)
        git_server.server_close()

    assert result.stage is BrowserExecutionStage.COMPLETED
    assert result.commit_sha == commit
    assert tuple(item.journey_id for item in result.journey_results) == AUTHENTICATION_JOURNEYS
    assert all(item.outcome is EvidenceOutcome.PASS for item in result.journey_results)
    assert {item.kind for item in result.evidence} >= {
        EvidenceKind.MIGRATION,
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.PERSISTENCE,
        EvidenceKind.SECURITY,
    }
    assert not any((tmp_path / "environments").rglob(browser.run_id))
    restored = FileBrowserExecutionStore(tmp_path / "results").load(
        result.product_id, result.run_id, result.plan_id
    )
    assert restored == result
    for item in result.evidence:
        content = artifacts.resolve(item.artifact_uri).read_bytes()
        assert RAW_PASSWORD.encode() not in content
        assert RAW_TOKEN.encode() not in content
    _write_founder_pack(result, browser, authentication, artifacts)


def _configuration(repository_url: str, commit: str, port: int):
    profile = speakmate_v1_profile()
    origin = f"http://127.0.0.1:{port}"
    return ManagedProductRuntimeConfiguration(
        "authentication-runtime",
        "speakmate",
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
                ReadinessProbe("app-ready", f"{origin}/health", (204,), 15, 1),
                OneShotCommand("stop-app", CommandSpec("python", ("stop.py",)), 10),
                15,
                5,
            ),
        ),
        (),
        (),
        (),
        profile.profile_id,
        profile.version,
        profile.digest,
        "test",
        NOW,
    )


def _browser_plan(config):
    profile = speakmate_v1_profile()
    contracts = {
        item.journey_id: item
        for item in profile.journeys
        if item.capability_id == "AUTHENTICATION"
    }
    journeys = []
    for journey_id in AUTHENTICATION_JOURNEYS:
        slug = journey_id.split(".", 1)[1].replace("_", "-")
        journeys.append(
            BrowserJourneySpecification(
                journey_id,
                "AUTHENTICATION",
                contracts[journey_id].title,
                f"/verify/{slug}",
                (
                    BrowserStep(
                        f"run-{slug}",
                        BrowserActionKind.CLICK,
                        BrowserLocator(BrowserLocatorKind.TEST_ID, "run-verification"),
                    ),
                    BrowserStep(
                        f"claim-{slug}",
                        BrowserActionKind.ASSERT_TEXT,
                        BrowserLocator(BrowserLocatorKind.TEXT, "Verified"),
                        expected_text="Verified",
                    ),
                ),
                30,
            )
        )
    return BrowserJourneyPlan(
        "authentication-browser-v1",
        "authentication-run",
        config.project_id,
        config.configuration_id,
        config.revision,
        config.digest,
        config.commit_sha,
        profile.profile_id,
        profile.version,
        profile.digest,
        tuple(journeys),
        (),
        "test",
        NOW,
    )


def _authentication_plan(browser):
    profile = speakmate_v1_profile()
    required = {
        item.journey_id: tuple(
            kind
            for kind in item.required_evidence
            if kind in {EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY}
        )
        for item in profile.journeys
        if item.capability_id == "AUTHENTICATION"
    }
    journeys = []
    for journey_id in AUTHENTICATION_JOURNEYS:
        slug = journey_id.split(".", 1)[1].replace("_", "-")
        journeys.append(
            AuthenticationJourneyVerification(
                journey_id,
                (f"claim-{slug}",),
                LOCKED_AUTHENTICATION_CLAIMS[journey_id],
                required[journey_id],
            )
        )
    return AuthenticationVerificationPlan(
        "authentication-verification-v1",
        browser.run_id,
        browser.product_id,
        browser.plan_id,
        browser.digest,
        browser.configuration_id,
        browser.configuration_revision,
        browser.configuration_digest,
        browser.commit_sha,
        browser.acceptance_profile_id,
        browser.acceptance_profile_version,
        browser.acceptance_profile_digest,
        "playwright-authentication-v1",
        tuple(journeys),
        "test",
        NOW,
    )


def _acceptance_store(tmp_path, config):
    profile = speakmate_v1_profile()
    store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    run = RuntimeAcceptanceRun(
        "authentication-run",
        config.project_id,
        "1.0",
        config.commit_sha,
        AcceptanceStage.PLANNED,
        profile.capabilities,
        profile.journeys,
        NOW,
        NOW,
        runtime_configuration_id=config.configuration_id,
        runtime_configuration_revision=config.revision,
        runtime_configuration_digest=config.digest,
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
    )
    service = RuntimeAcceptanceService(store)
    run = service.plan(run)
    service.mark_implemented(run.product_id, run.run_id, NOW)
    automated = tuple(
        EvidenceArtifact(
            f"authentication-run.authentication.registration.{kind.value}",
            run.run_id,
            "AUTHENTICATION",
            "authentication.registration",
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


def _write_founder_pack(result, browser, authentication, artifacts):
    configured = os.environ.get("ASCOS_FOUNDER_EVIDENCE_DIR")
    if not configured:
        return
    target = Path(configured).absolute()
    target.mkdir(parents=True, exist_ok=True)
    screenshots = []
    safe_evidence = []
    for item in result.evidence:
        record = {
            "evidence_id": item.evidence_id,
            "journey_id": item.journey_id,
            "kind": item.kind.value,
            "outcome": item.outcome.value,
            "digest": item.digest,
        }
        safe_evidence.append(record)
        if item.kind is EvidenceKind.SCREENSHOT:
            name = f"{item.journey_id}.png"
            shutil.copy2(artifacts.resolve(item.artifact_uri), target / name)
            screenshots.append({"journey_id": item.journey_id, "file": name, "digest": item.digest})
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "product_commit_sha": result.commit_sha,
        "browser_plan_digest": browser.digest,
        "authentication_verification_digest": authentication.digest,
        "execution_digest": result.digest,
        "journeys": [
            {"journey_id": item.journey_id, "outcome": item.outcome.value}
            for item in result.journey_results
        ],
        "screenshots": screenshots,
        "evidence": safe_evidence,
        "redaction_contract": "no credentials, cookies, headers, bodies, storage values, or URL queries",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _git(cwd, *arguments):
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_MIGRATION_FIXTURE = r'''import sqlite3

db = sqlite3.connect('auth.db')
db.executescript("""
CREATE TABLE users(email TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE resets(token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE attempts(subject TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0);
""")
db.commit()
db.close()
'''


_SERVICE_FIXTURE = r'''from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import hashlib
import hmac
import json
import os
import sqlite3
import sys

PASSWORD = 'fixture-password-value'
NEW_PASSWORD = 'fixture-new-password-value'
SESSION = 'fixture-session-token-value'
RESET = 'fixture-reset-token-value'

def password_hash(value, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', value.encode(), salt, 120000)
    return salt.hex() + ':' + digest.hex()

def password_ok(value, encoded):
    salt, expected = encoded.split(':', 1)
    actual = password_hash(value, bytes.fromhex(salt)).split(':', 1)[1]
    return hmac.compare_digest(actual, expected)

def token_hash(value): return hashlib.sha256(value.encode()).hexdigest()
def db(): return sqlite3.connect('auth.db')

def registration():
    connection = db()
    encoded = password_hash(PASSWORD)
    connection.execute('INSERT INTO users VALUES (?, ?)', ('learner@example.invalid', encoded))
    connection.execute('INSERT INTO sessions VALUES (?, ?, 0)', (token_hash(SESSION), 'learner@example.invalid'))
    connection.commit()
    row = connection.execute('SELECT password_hash FROM users WHERE email=?', ('learner@example.invalid',)).fetchone()
    session = connection.execute('SELECT token_hash FROM sessions').fetchone()
    connection.close()
    return row is not None and row[0] != PASSWORD and password_ok(PASSWORD, row[0]) and session[0] != SESSION

def login():
    connection = db()
    row = connection.execute('SELECT password_hash FROM users WHERE email=?', ('learner@example.invalid',)).fetchone()
    connection.close()
    return row is not None and password_ok(PASSWORD, row[0])

def logout():
    connection = db()
    hashed = token_hash(SESSION + '-logout')
    connection.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, 0)', (hashed, 'learner@example.invalid'))
    connection.execute('UPDATE sessions SET revoked=1 WHERE token_hash=?', (hashed,))
    connection.commit()
    row = connection.execute('SELECT revoked, token_hash FROM sessions WHERE token_hash=?', (hashed,)).fetchone()
    connection.close()
    return row == (1, hashed) and row[1] != SESSION + '-logout'

def session_restore():
    connection = db()
    hashed = token_hash(SESSION + '-restore')
    connection.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, 0)', (hashed, 'learner@example.invalid'))
    connection.commit()
    row = connection.execute('SELECT email FROM sessions WHERE token_hash=? AND revoked=0', (hashed,)).fetchone()
    connection.close()
    return row == ('learner@example.invalid',)

def password_recovery():
    connection = db()
    hashed = token_hash(RESET)
    connection.execute('INSERT INTO resets VALUES (?, ?, 0)', (hashed, 'learner@example.invalid'))
    row = connection.execute('SELECT email FROM resets WHERE token_hash=? AND used=0', (hashed,)).fetchone()
    if not row: return False
    connection.execute('UPDATE users SET password_hash=? WHERE email=?', (password_hash(NEW_PASSWORD), row[0]))
    connection.execute('UPDATE resets SET used=1 WHERE token_hash=?', (hashed,))
    connection.execute('UPDATE sessions SET revoked=1 WHERE email=?', (row[0],))
    connection.commit()
    user = connection.execute('SELECT password_hash FROM users WHERE email=?', (row[0],)).fetchone()[0]
    reused = connection.execute('SELECT 1 FROM resets WHERE token_hash=? AND used=0', (hashed,)).fetchone()
    active = connection.execute('SELECT 1 FROM sessions WHERE email=? AND revoked=0', (row[0],)).fetchone()
    connection.close()
    return password_ok(NEW_PASSWORD, user) and not password_ok(PASSWORD, user) and reused is None and active is None

def security_error_paths():
    connection = db()
    before = connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    duplicate = False
    try:
        connection.execute('INSERT INTO users VALUES (?, ?)', ('learner@example.invalid', password_hash('other')))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback(); duplicate = True
    unknown_message = 'If the account exists, recovery instructions were sent'
    known_message = 'If the account exists, recovery instructions were sent'
    invalid = connection.execute('SELECT 1 FROM resets WHERE token_hash=? AND used=0', (token_hash('invalid'),)).fetchone() is None
    try:
        connection.execute('BEGIN')
        connection.execute('INSERT INTO users VALUES (?, ?)', ('partial@example.invalid', password_hash('partial')))
        raise RuntimeError('forced partial failure')
    except RuntimeError:
        connection.rollback()
    partial_absent = connection.execute('SELECT 1 FROM users WHERE email=?', ('partial@example.invalid',)).fetchone() is None
    connection.execute('INSERT OR REPLACE INTO attempts VALUES (?, 6)', ('learner@example.invalid',))
    connection.commit()
    throttled = connection.execute('SELECT failures FROM attempts WHERE subject=?', ('learner@example.invalid',)).fetchone()[0] >= 5
    after = connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    connection.close()
    return duplicate and before == after and unknown_message == known_message and invalid and partial_absent and throttled

CHECKS = {
    'registration': registration,
    'login': login,
    'logout': logout,
    'session-restore': session_restore,
    'password-recovery': password_recovery,
    'security-error-paths': security_error_paths,
}

PAGE = """<!doctype html><html><head><link rel='icon' href='data:,'></head><body><main>
<h1>Authentication verification</h1><button data-testid='run-verification'>Run verification</button>
<p id='result'>Ready</p></main><script>
document.querySelector('button').addEventListener('click', async () => {
  const response = await fetch('/api' + location.pathname, {method: 'POST'});
  const value = await response.json(); document.getElementById('result').textContent = value.message;
});</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def send(self, status, body=b'', content_type='text/plain'):
        self.send_response(status); self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == '/health': return self.send(204)
        if self.path.startswith('/verify/') and self.path.split('/')[-1] in CHECKS:
            return self.send(200, PAGE.encode(), 'text/html')
        return self.send(404)
    def do_POST(self):
        if not self.path.startswith('/api/verify/'): return self.send(404)
        name = self.path.split('/')[-1]; check = CHECKS.get(name)
        ok = bool(check and check())
        body = json.dumps({'ok': ok, 'message': 'Verified' if ok else 'Verification failed'}).encode()
        return self.send(200 if ok else 422, body, 'application/json')
    def log_message(self, _format, *_args): return

server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = 0.1
while not Path('stop.flag').exists(): server.handle_request()
server.server_close()
'''
