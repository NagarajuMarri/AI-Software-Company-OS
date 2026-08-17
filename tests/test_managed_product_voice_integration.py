from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import wave

import pytest

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
from runtime.managed_product_voice import (
    FileVoiceVerificationPlanStore,
    LOCKED_VOICE_CLAIMS,
    VoiceEvidenceBrowserProvider,
    VoiceJourneyVerification,
    VoiceVerificationPlan,
)
from runtime.runtime_acceptance import (
    AcceptanceStage,
    DeterministicAudioFixture,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    RuntimeAcceptanceRun,
    RuntimeAcceptanceService,
    RuntimeAcceptanceStore,
    VOICE_JOURNEYS,
    speakmate_v1_profile,
)


NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
TRANSCRIPT = "Hello, I would like to practise English."
RESPONSE = "Great start. Please tell me about your day."
NON_BROWSER = {
    "voice.capture": (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.SECURITY),
    "voice.stt": (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.STT),
    "voice.conversation": (EvidenceKind.PERSISTENCE,),
    "voice.llm": (EvidenceKind.LLM, EvidenceKind.SECURITY),
    "voice.tts": (EvidenceKind.TTS, EvidenceKind.SECURITY),
    "voice.audible_playback": (EvidenceKind.AUDIBLE_PLAYBACK,),
    "voice.avatar_synchronization": (EvidenceKind.AVATAR_SYNCHRONIZATION,),
    "voice.repeat_turn": (
        EvidenceKind.AUDIO_FIXTURE,
        EvidenceKind.STT,
        EvidenceKind.LLM,
        EvidenceKind.TTS,
        EvidenceKind.AUDIBLE_PLAYBACK,
        EvidenceKind.AVATAR_SYNCHRONIZATION,
        EvidenceKind.PERSISTENCE,
    ),
}
REQUIRED = {
    "voice.capture": ("capture-verified",),
    "voice.stt": ("transcript-exact",),
    "voice.conversation": ("turn-persisted",),
    "voice.llm": ("response-bounded",),
    "voice.tts": ("tts-generated",),
    "voice.audible_playback": ("audio-played",),
    "voice.avatar_synchronization": ("avatar-synchronized",),
    "voice.repeat_turn": (
        "second-transcript-exact",
        "second-response-bounded",
        "second-turn-complete",
        "second-audio-played",
    ),
}


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
def test_real_voice_media_chain_and_founder_evidence(tmp_path):
    input_audio = _wav(440)
    output_audio = _wav(660)
    source = tmp_path / "source"
    source.mkdir()
    (source / "learner.wav").write_bytes(input_audio)
    (source / "tutor.wav").write_bytes(output_audio)
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
    _git(source, "commit", "-m", "voice fixture")
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
        repository_url = f"http://127.0.0.1:{git_server.server_address[1]}/product.git"
        config = _configuration(repository_url, commit, product_port)
        artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
        input_fixture = _fixture(artifacts, "learner-turn", input_audio, TRANSCRIPT)
        output_fixture = _fixture(artifacts, "tutor-turn", output_audio, RESPONSE)
        browser = _browser_plan(config)
        voice = _voice_plan(browser, input_fixture, output_fixture)
        configurations = InMemoryRuntimeConfigurationStore()
        configurations.save(config)
        environment = ManagedProductEnvironmentService(
            configurations,
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
        voice_plans = FileVoiceVerificationPlanStore(tmp_path / "voice-plans")
        voice_plans.save(voice)
        executions = FileBrowserExecutionStore(tmp_path / "results")
        provider = VoiceEvidenceBrowserProvider(
            voice.provider_id,
            voice.verification_id,
            voice_plans,
            PlaywrightChromiumProvider(),
        )
        service = ManagedProductBrowserService(
            _acceptance_store(tmp_path, config),
            browser_plans,
            executions,
            environment,
            _NoSecrets(),
            BrowserExecutionPolicy(
                frozenset({voice.provider_id}), frozenset(config.allowed_origins)
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
    assert tuple(item.journey_id for item in result.journey_results) == VOICE_JOURNEYS
    assert all(item.outcome is EvidenceOutcome.PASS for item in result.journey_results)
    assert {item.kind for item in result.evidence} >= {
        EvidenceKind.MIGRATION,
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.AUDIO_FIXTURE,
        EvidenceKind.STT,
        EvidenceKind.LLM,
        EvidenceKind.TTS,
        EvidenceKind.AUDIBLE_PLAYBACK,
        EvidenceKind.AVATAR_SYNCHRONIZATION,
        EvidenceKind.PERSISTENCE,
        EvidenceKind.SECURITY,
    }
    assert not any((tmp_path / "environments").rglob(browser.run_id))
    restored = FileBrowserExecutionStore(tmp_path / "results").load(
        result.product_id, result.run_id, result.plan_id
    )
    assert restored == result
    audio_evidence = next(
        item for item in result.evidence if item.kind is EvidenceKind.AUDIO_FIXTURE
    )
    audio_payload = artifacts.read_json(audio_evidence.artifact_uri, audio_evidence.digest)
    assert audio_payload["input_audio_metrics"]["rms_amplitude"] > 100
    assert audio_payload["output_audio_metrics"]["non_silent_samples_milli"] >= 50
    _write_founder_pack(result, browser, voice, artifacts)


def _wav(frequency: int) -> bytes:
    stream = BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(
            b"".join(
                struct.pack("<h", round(10_000 * math.sin(2 * math.pi * frequency * i / 16_000)))
                for i in range(6_400)
            )
        )
    return stream.getvalue()


def _fixture(store, fixture_id, content, transcript):
    uri, digest = store.write_bytes("voice-product", "voice-run", content, "wav")
    return DeterministicAudioFixture(
        fixture_id, uri, digest, "audio/wav", 16_000, 1, 400, transcript
    )


def _configuration(repository_url, commit, port):
    profile = speakmate_v1_profile()
    origin = f"http://127.0.0.1:{port}"
    return ManagedProductRuntimeConfiguration(
        "voice-runtime",
        "voice-product",
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
        item.journey_id: item for item in profile.journeys if item.capability_id == "VOICE"
    }
    journeys = []
    for journey_id in VOICE_JOURNEYS:
        slug = journey_id.split(".", 1)[1].replace("_", "-")
        steps = [
            BrowserStep(
                f"run-{slug}",
                BrowserActionKind.CLICK,
                BrowserLocator(BrowserLocatorKind.TEST_ID, "run-verification"),
            )
        ]
        if journey_id == "voice.stt":
            steps.append(_text_step("transcript-exact", TRANSCRIPT))
        elif journey_id == "voice.llm":
            steps.append(_text_step("response-bounded", RESPONSE))
        elif journey_id == "voice.audible_playback":
            steps.extend(
                (
                    _text_step("playback-complete", "Verified"),
                    _media_step("audio-played"),
                )
            )
        elif journey_id == "voice.avatar_synchronization":
            steps.append(_text_step("avatar-synchronized", "speaking->idle"))
        elif journey_id == "voice.repeat_turn":
            steps.extend(
                (
                    _text_step("second-transcript-exact", TRANSCRIPT),
                    _text_step("second-response-bounded", RESPONSE),
                    _text_step("second-turn-complete", "Turn 2 Verified"),
                    _media_step("second-audio-played"),
                )
            )
        else:
            steps.append(_text_step(REQUIRED[journey_id][0], "Verified"))
        journeys.append(
            BrowserJourneySpecification(
                journey_id,
                "VOICE",
                contracts[journey_id].title,
                f"/verify/{slug}",
                tuple(steps),
                30,
            )
        )
    return BrowserJourneyPlan(
        "voice-browser-v1",
        "voice-run",
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


def _text_step(step_id, expected):
    return BrowserStep(
        step_id,
        BrowserActionKind.ASSERT_TEXT,
        BrowserLocator(BrowserLocatorKind.TEXT, expected),
        expected_text=expected,
    )


def _media_step(step_id):
    return BrowserStep(
        step_id,
        BrowserActionKind.ASSERT_MEDIA_PLAYED,
        BrowserLocator(BrowserLocatorKind.TEST_ID, "tutor-audio"),
    )


def _voice_plan(browser, input_fixture, output_fixture):
    return VoiceVerificationPlan(
        "voice-verification-v1",
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
        "playwright-voice-v1",
        tuple(
            VoiceJourneyVerification(
                journey_id,
                REQUIRED[journey_id],
                LOCKED_VOICE_CLAIMS[journey_id],
                NON_BROWSER[journey_id],
            )
            for journey_id in VOICE_JOURNEYS
        ),
        input_fixture,
        output_fixture,
        "/media/learner.wav",
        "/media/tutor.wav",
        RESPONSE,
        256,
        "test",
        NOW,
    )


def _acceptance_store(tmp_path, config):
    profile = speakmate_v1_profile()
    store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    run = RuntimeAcceptanceRun(
        "voice-run",
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
    service.plan(run)
    service.mark_implemented(run.product_id, run.run_id, NOW)
    automated = tuple(
        EvidenceArtifact(
            f"voice-run.voice.capture.{kind.value}",
            run.run_id,
            "VOICE",
            "voice.capture",
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


def _write_founder_pack(result, browser, voice, artifacts):
    configured = os.environ.get("ASCOS_VOICE_FOUNDER_EVIDENCE_DIR")
    if not configured:
        return
    target = Path(configured).absolute()
    target.mkdir(parents=True, exist_ok=True)
    screenshots = []
    safe_evidence = []
    for item in result.evidence:
        safe_evidence.append(
            {
                "evidence_id": item.evidence_id,
                "journey_id": item.journey_id,
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "digest": item.digest,
            }
        )
        if item.kind is EvidenceKind.SCREENSHOT:
            name = f"{item.journey_id}.png"
            shutil.copy2(artifacts.resolve(item.artifact_uri), target / name)
            screenshots.append({"journey_id": item.journey_id, "file": name, "digest": item.digest})
    for name, fixture in (
        ("learner-input.wav", voice.input_fixture),
        ("tutor-output.wav", voice.output_fixture),
    ):
        (target / name).write_bytes(artifacts.read_bytes(fixture.artifact_uri, fixture.digest))
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "product_commit_sha": result.commit_sha,
        "browser_plan_digest": browser.digest,
        "voice_verification_digest": voice.digest,
        "execution_digest": result.digest,
        "input_fixture_digest": voice.input_fixture.digest,
        "output_fixture_digest": voice.output_fixture.digest,
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

connection = sqlite3.connect('voice.db')
connection.execute('CREATE TABLE turns(session_id TEXT, ordinal INTEGER, transcript TEXT, response TEXT, PRIMARY KEY(session_id, ordinal))')
connection.commit()
connection.close()
'''


_SERVICE_FIXTURE = r'''from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

TRANSCRIPT = 'Hello, I would like to practise English.'
RESPONSE = 'Great start. Please tell me about your day.'
INPUT_DIGEST = hashlib.sha256(Path('learner.wav').read_bytes()).hexdigest()

PAGE = """<!doctype html><html><head><link rel='icon' href='data:,'></head><body><main>
<h1>Voice verification</h1><button data-testid='run-verification'>Run verification</button>
<p id='result'>Ready</p><p id='transcript'></p><p id='response'></p><p id='avatar'>idle</p>
<audio data-testid='tutor-audio' controls preload='auto' src='/media/tutor.wav'></audio>
</main><script>
const result = document.getElementById('result'); const avatar = document.getElementById('avatar');
const audio = document.querySelector('audio'); const slug = location.pathname.split('/').pop();
document.querySelector('button').addEventListener('click', async () => {
  const response = await fetch('/api/verify/' + slug, {method: 'POST'});
  const value = await response.json();
  document.getElementById('transcript').textContent = value.transcript || '';
  document.getElementById('response').textContent = value.response || '';
  if (!response.ok) { result.textContent = 'Verification failed'; return; }
  if (value.play) {
    audio.muted = false; audio.volume = 1;
    audio.onplay = () => { avatar.textContent = 'speaking'; };
    audio.onended = () => {
      avatar.textContent = value.avatar ? 'speaking->idle' : 'idle';
      result.textContent = value.message;
    };
    await audio.play();
  } else { result.textContent = value.message; }
});</script></body></html>"""

def turn(ordinal):
    connection = sqlite3.connect('voice.db')
    connection.execute('INSERT INTO turns VALUES (?, ?, ?, ?)', ('session-1', ordinal, TRANSCRIPT, RESPONSE))
    connection.commit()
    row = connection.execute('SELECT transcript, response FROM turns WHERE session_id=? AND ordinal=?', ('session-1', ordinal)).fetchone()
    count = connection.execute('SELECT COUNT(*) FROM turns WHERE session_id=?', ('session-1',)).fetchone()[0]
    connection.close()
    return row == (TRANSCRIPT, RESPONSE), count

class Handler(BaseHTTPRequestHandler):
    def send(self, status, body=b'', content_type='text/plain'):
        self.send_response(status); self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == '/health': return self.send(204)
        if self.path == '/media/learner.wav': return self.send(200, Path('learner.wav').read_bytes(), 'audio/wav')
        if self.path == '/media/tutor.wav': return self.send(200, Path('tutor.wav').read_bytes(), 'audio/wav')
        if self.path.startswith('/verify/'): return self.send(200, PAGE.encode(), 'text/html')
        return self.send(404)
    def do_POST(self):
        if not self.path.startswith('/api/verify/'): return self.send(404)
        name = self.path.split('/')[-1]
        ok = True; play = False; avatar = False; message = 'Verified'
        if name == 'capture':
            ok = hashlib.sha256(Path('learner.wav').read_bytes()).hexdigest() == INPUT_DIGEST
        elif name == 'stt': message = 'Verified'
        elif name == 'conversation': ok, _ = turn(1)
        elif name == 'llm': message = 'Verified'; ok = len(RESPONSE) <= 256
        elif name == 'tts': ok = Path('tutor.wav').stat().st_size > 44
        elif name == 'audible-playback': play = True
        elif name == 'avatar-synchronization': play = True; avatar = True
        elif name == 'repeat-turn':
            ok, count = turn(2); ok = ok and count == 2; play = True; avatar = True
            message = 'Turn 2 Verified'
        else: ok = False
        body = json.dumps({'message': message, 'play': play, 'avatar': avatar, 'transcript': TRANSCRIPT, 'response': RESPONSE}).encode()
        return self.send(200 if ok else 422, body, 'application/json')
    def log_message(self, _format, *_args): return

server = HTTPServer((sys.argv[1], int(sys.argv[2])), Handler)
server.timeout = 0.1
while not Path('stop.flag').exists(): server.handle_request()
server.server_close()
'''
