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
import struct
import subprocess
import threading
import zlib

import pytest

from runtime.managed_product_browser import (
    BrowserExecutionStage,
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
)
from runtime.managed_product_environment import (
    EnvironmentExecutionPolicy,
    LocalManagedProductEnvironmentProvider,
    ManagedProductEnvironmentService,
)
from runtime.managed_product_pwa import (
    FilePwaVerificationPlanStore,
    LOCKED_PWA_CLAIMS,
    ManagedProductPwaService,
    PlaywrightPwaProvider,
    PwaExecutionPolicy,
    PwaVerificationPlan,
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


NOW = datetime(2026, 8, 18, 8, tzinfo=timezone.utc)


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
def test_real_pwa_install_standalone_refresh_and_offline_shell(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text(_INDEX_FIXTURE, encoding="utf-8")
    (source / "app.js").write_text(_APP_FIXTURE, encoding="utf-8")
    (source / "manifest.webmanifest").write_text(
        json.dumps(_MANIFEST_FIXTURE), encoding="utf-8"
    )
    (source / "service-worker.js").write_text(_WORKER_FIXTURE, encoding="utf-8")
    (source / "icon-192.png").write_bytes(_png(192, 192))
    (source / "icon-512.png").write_bytes(_png(512, 512))
    (source / "migrate.py").write_text(
        "from pathlib import Path\nPath('migrated.flag').write_text('ok')\n",
        encoding="utf-8",
    )
    (source / "service.py").write_text(_SERVICE_FIXTURE, encoding="utf-8")
    (source / "stop.py").write_text(
        "from pathlib import Path\nPath('stop.flag').write_text('stop')\n",
        encoding="utf-8",
    )
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "ASCOS Test")
    _git(source, "config", "user.email", "ascos@example.invalid")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "installable PWA fixture")
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
        port = _free_port()
        repository_url = (
            f"http://127.0.0.1:{git_server.server_address[1]}/product.git"
        )
        configuration = _configuration(repository_url, commit, port)
        profile = speakmate_v1_profile()
        plan = PwaVerificationPlan(
            "pwa-plan-v1",
            "pwa-run",
            configuration.project_id,
            configuration.configuration_id,
            configuration.revision,
            configuration.digest,
            commit,
            profile.profile_id,
            profile.version,
            profile.digest,
            "playwright-pwa-v1",
            "/",
            "/manifest.webmanifest",
            "/service-worker.js",
            "app-shell",
            "SpeakMate ready offline",
            LOCKED_PWA_CLAIMS,
            "ascos",
            NOW,
        )
        configurations = InMemoryRuntimeConfigurationStore()
        configurations.save(configuration)
        environment = ManagedProductEnvironmentService(
            configurations,
            LocalManagedProductEnvironmentProvider(tmp_path / "environments"),
            _NoSecrets(),
            EnvironmentExecutionPolicy(
                frozenset({"127.0.0.1"}),
                frozenset({"python"}),
                frozenset(configuration.allowed_origins),
                frozenset({"ASCOS_TEST_PUBLIC"}),
            ),
        )
        acceptance = _acceptance_service(tmp_path, configuration)
        plans = FilePwaVerificationPlanStore(tmp_path / "plans")
        plans.save(plan)
        results = FileBrowserExecutionStore(tmp_path / "results")
        artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
        service = ManagedProductPwaService(
            acceptance,
            plans,
            results,
            environment,
            artifacts,
            PwaExecutionPolicy(
                frozenset({plan.provider_id}),
                frozenset(configuration.allowed_origins),
            ),
            PlaywrightPwaProvider(),
        )
        result = service.execute(
            plan.product_id, plan.run_id, plan.plan_id, plan.digest
        )
    finally:
        git_server.shutdown()
        thread.join(timeout=5)
        git_server.server_close()

    pwa_artifact = next(item for item in result.evidence if item.kind is EvidenceKind.PWA)
    payload = artifacts.read_json(pwa_artifact.artifact_uri, pwa_artifact.digest)
    assert result.stage is BrowserExecutionStage.COMPLETED, {
        "failure_code": result.failure_code,
        "claims": payload["claims"],
    }
    assert result.commit_sha == commit
    assert result.journey_results[0].journey_id == "pwa.install_launch"
    assert result.journey_results[0].outcome is EvidenceOutcome.PASS
    assert {item.kind for item in result.evidence} >= {
        EvidenceKind.MIGRATION,
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.PWA,
        EvidenceKind.SCREENSHOT,
    }
    assert tuple(payload["claims"]) == tuple(item.value for item in LOCKED_PWA_CLAIMS)
    assert not any((tmp_path / "environments").rglob(plan.run_id))
    assert FileBrowserExecutionStore(tmp_path / "results").load(
        result.product_id, result.run_id, result.plan_id
    ) == result
    _write_founder_pack(result, plan, artifacts)


def _configuration(repository_url, commit, port):
    profile = speakmate_v1_profile()
    origin = f"http://127.0.0.1:{port}"
    return ManagedProductRuntimeConfiguration(
        "pwa-runtime",
        "spoken-english-ai",
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


def _acceptance_service(tmp_path, configuration):
    profile = speakmate_v1_profile()
    store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    service = RuntimeAcceptanceService(store)
    run = RuntimeAcceptanceRun(
        "pwa-run",
        configuration.project_id,
        "1.0",
        configuration.commit_sha,
        AcceptanceStage.PLANNED,
        profile.capabilities,
        profile.journeys,
        NOW,
        NOW,
        runtime_configuration_id=configuration.configuration_id,
        runtime_configuration_revision=configuration.revision,
        runtime_configuration_digest=configuration.digest,
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
    )
    service.plan(run)
    service.mark_implemented(run.product_id, run.run_id, NOW)
    automated = tuple(
        EvidenceArtifact(
            f"pwa-run.automated.{kind.value}",
            run.run_id,
            "PWA",
            "pwa.install_launch",
            kind,
            EvidenceOutcome.PASS,
            configuration.commit_sha,
            f"artifact://automated/{kind.value}",
            hashlib.sha256(kind.value.encode()).hexdigest(),
            NOW,
            f"Verified {kind.value}",
        )
        for kind in (EvidenceKind.CODE, EvidenceKind.AUTOMATED_TEST)
    )
    service.record_automated_verification(run.product_id, run.run_id, automated, NOW)
    return service


def _write_founder_pack(result, plan, artifacts):
    configured = os.environ.get("ASCOS_PWA_FOUNDER_EVIDENCE_DIR")
    if not configured:
        return
    target = Path(configured).absolute()
    target.mkdir(parents=True, exist_ok=True)
    screenshot = next(item for item in result.evidence if item.kind is EvidenceKind.SCREENSHOT)
    shutil.copy2(artifacts.resolve(screenshot.artifact_uri), target / "pwa-install-offline.png")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "product_commit_sha": result.commit_sha,
        "pwa_plan_digest": plan.digest,
        "execution_digest": result.digest,
        "claims": [item.value for item in LOCKED_PWA_CLAIMS],
        "screenshot": {
            "file": "pwa-install-offline.png",
            "digest": screenshot.digest,
        },
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "digest": item.digest,
            }
            for item in result.evidence
        ],
        "redaction_contract": "no credentials, cookies, headers, bodies, storage values, or URL queries",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _png(width, height):
    signature = b"\x89PNG\r\n\x1a\n"
    raw = b"".join(b"\x00" + (b"\x39\x72\xc2\xff" * width) for _ in range(height))

    def chunk(kind, content):
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)
        )

    return (
        signature
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _git(cwd, *arguments):
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def _free_port():
    with socket.socket() as value:
        value.bind(("127.0.0.1", 0))
        return value.getsockname()[1]


_INDEX_FIXTURE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="manifest" href="/manifest.webmanifest"><title>SpeakMate PWA</title>
</head><body><main data-testid="app-shell">SpeakMate ready offline</main>
<script src="/app.js"></script></body></html>
"""

_APP_FIXTURE = """if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js');
}
"""

_WORKER_FIXTURE = """const CACHE = 'speakmate-v1';
const SHELL = ['/', '/index.html', '/app.js', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request))));
"""

_MANIFEST_FIXTURE = {
    "name": "SpeakMate",
    "short_name": "SpeakMate",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}

_SERVICE_FIXTURE = """from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import sys

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webmanifest': 'application/manifest+json',
                      '.js': 'text/javascript'}
    def do_GET(self):
        if self.path == '/health':
            self.send_response(204); self.end_headers(); return
        return super().do_GET()
    def log_message(self, _format, *_args):
        return

ThreadingHTTPServer((sys.argv[1], int(sys.argv[2])), Handler).serve_forever()
"""
