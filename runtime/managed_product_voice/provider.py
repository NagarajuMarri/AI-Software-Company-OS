"""Browser-provider wrapper that proves deterministic Voice media evidence."""

from __future__ import annotations

from array import array
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import math
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import wave

from runtime.managed_product_browser.contracts import (
    BrowserArtifactStore,
    ManagedProductBrowserProvider,
)
from runtime.managed_product_browser.errors import BrowserArtifactError
from runtime.managed_product_browser.models import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
)
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    endpoint_origin,
)
from runtime.managed_product_voice.contracts import VoiceVerificationPlanStore
from runtime.managed_product_voice.errors import VoiceVerificationError
from runtime.managed_product_voice.models import VoiceVerificationPlan
from runtime.runtime_acceptance.models import (
    DeterministicAudioFixture,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class VoiceEvidenceBrowserProvider:
    """Derive Voice evidence from exact media bytes and passed browser assertions."""

    def __init__(
        self,
        provider_id: str,
        verification_id: str,
        plan_store: VoiceVerificationPlanStore,
        browser_provider: ManagedProductBrowserProvider,
    ) -> None:
        self.provider_id = provider_id
        self.verification_id = verification_id
        self.plan_store = plan_store
        self.browser_provider = browser_provider

    def execute(
        self,
        plan: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
    ) -> BrowserExecutionResult:
        verification = self.plan_store.load(plan.product_id, plan.run_id, self.verification_id)
        self._authorize(verification, plan, configuration)
        browser = self.browser_provider.execute(
            plan, configuration, inputs, redactions, artifact_store
        )
        if browser.stage is not BrowserExecutionStage.COMPLETED:
            return browser
        try:
            evidence, results = self._verify(
                verification, browser, configuration, artifact_store
            )
        except (VoiceVerificationError, BrowserArtifactError):
            evidence, results = self._failure_evidence(
                verification, browser, artifact_store
            )
            return replace(
                browser,
                stage=BrowserExecutionStage.FAILED,
                evidence=browser.evidence + evidence,
                journey_results=results,
                completed_at=max(browser.completed_at, _now()),
                failure_code="VOICE_EVIDENCE_FAILED",
            )
        return replace(
            browser,
            evidence=browser.evidence + evidence,
            journey_results=results,
            completed_at=max(browser.completed_at, _now()),
        )

    def _authorize(
        self,
        verification: VoiceVerificationPlan,
        browser: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
    ) -> None:
        if verification.provider_id != self.provider_id:
            raise VoiceVerificationError("Voice provider does not match persisted authority")
        if (
            verification.run_id,
            verification.product_id,
            verification.browser_plan_id,
            verification.browser_plan_digest,
            verification.configuration_id,
            verification.configuration_revision,
            verification.configuration_digest,
            verification.commit_sha,
            verification.acceptance_profile_id,
            verification.acceptance_profile_version,
            verification.acceptance_profile_digest,
        ) != (
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
        ):
            raise VoiceVerificationError("Voice plan does not match browser authority")
        if (
            configuration.project_id,
            configuration.configuration_id,
            configuration.revision,
            configuration.digest,
            configuration.commit_sha,
            configuration.acceptance_profile_id,
            configuration.acceptance_profile_version,
            configuration.acceptance_profile_digest,
        ) != (
            verification.product_id,
            verification.configuration_id,
            verification.configuration_revision,
            verification.configuration_digest,
            verification.commit_sha,
            verification.acceptance_profile_id,
            verification.acceptance_profile_version,
            verification.acceptance_profile_digest,
        ):
            raise VoiceVerificationError("Voice plan does not match runtime configuration")
        specifications = {item.journey_id: item for item in browser.journeys}
        if tuple(specifications) != tuple(item.journey_id for item in verification.journeys) or any(
            item.capability_id != "VOICE" for item in browser.journeys
        ):
            raise VoiceVerificationError("Voice browser plan does not cover the locked journeys")
        for contract in verification.journeys:
            specification = specifications[contract.journey_id]
            steps = {item.step_id: item for item in specification.steps}
            if not set(contract.required_step_ids) <= set(steps):
                raise VoiceVerificationError("Voice verification references an undeclared step")
            if contract.journey_id in {"voice.audible_playback", "voice.repeat_turn"} and not any(
                steps[step_id].action is BrowserActionKind.ASSERT_MEDIA_PLAYED
                for step_id in contract.required_step_ids
            ):
                raise VoiceVerificationError("Voice playback requires a provider-owned media assertion")
            if contract.journey_id == "voice.stt" and not any(
                steps[step_id].expected_text == verification.input_fixture.expected_transcript
                for step_id in contract.required_step_ids
            ):
                raise VoiceVerificationError("Voice STT authority lacks its exact transcript assertion")
            if contract.journey_id == "voice.llm" and not any(
                steps[step_id].expected_text == verification.expected_response
                for step_id in contract.required_step_ids
            ):
                raise VoiceVerificationError("Voice LLM authority lacks its exact response assertion")
            if contract.journey_id == "voice.repeat_turn" and (
                not any(
                    steps[step_id].expected_text == verification.input_fixture.expected_transcript
                    for step_id in contract.required_step_ids
                )
                or not any(
                    steps[step_id].expected_text == verification.expected_response
                    for step_id in contract.required_step_ids
                )
            ):
                raise VoiceVerificationError("Voice repeat authority lacks transcript or response assertions")

    def _verify(
        self,
        verification: VoiceVerificationPlan,
        browser: BrowserExecutionResult,
        configuration: ManagedProductRuntimeConfiguration,
        artifact_store: BrowserArtifactStore,
    ) -> tuple[tuple[EvidenceArtifact, ...], tuple[JourneyResult, ...]]:
        input_bytes = artifact_store.read_bytes(
            verification.input_fixture.artifact_uri, verification.input_fixture.digest
        )
        output_bytes = artifact_store.read_bytes(
            verification.output_fixture.artifact_uri, verification.output_fixture.digest
        )
        if _fetch_media(configuration, verification.input_media_path) != input_bytes:
            raise VoiceVerificationError("Managed product input media differs from locked fixture")
        if _fetch_media(configuration, verification.output_media_path) != output_bytes:
            raise VoiceVerificationError("Managed product output media differs from locked fixture")
        input_metrics = _analyze_wav(input_bytes, verification.input_fixture)
        output_metrics = _analyze_wav(output_bytes, verification.output_fixture)
        summaries: dict[str, list[EvidenceArtifact]] = {}
        for item in browser.evidence:
            if item.kind is EvidenceKind.BROWSER:
                summaries.setdefault(item.journey_id, []).append(item)
        prior_results = {item.journey_id: item for item in browser.journey_results}
        generated: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        for contract in verification.journeys:
            prior = prior_results.get(contract.journey_id)
            candidates = summaries.get(contract.journey_id, [])
            if prior is None or prior.outcome is not EvidenceOutcome.PASS or len(candidates) != 1:
                raise VoiceVerificationError("Voice journey lacks passing browser evidence")
            summary = candidates[0]
            payload = artifact_store.read_json(summary.artifact_uri, summary.digest)
            if (
                not isinstance(payload, dict)
                or payload.get("provider_id") != self.browser_provider.provider_id
                or payload.get("plan_digest") != verification.browser_plan_digest
                or payload.get("journey_id") != contract.journey_id
                or payload.get("outcome") != EvidenceOutcome.PASS.value
                or not isinstance(payload.get("steps"), list)
            ):
                raise VoiceVerificationError("Voice browser summary does not match authority")
            passed = {
                value.get("step_id"): value
                for value in payload["steps"]
                if isinstance(value, dict) and value.get("outcome") == "PASS"
            }
            if not set(contract.required_step_ids) <= set(passed):
                raise VoiceVerificationError("Voice claim lacks a passed browser assertion")
            if contract.journey_id in {"voice.audible_playback", "voice.repeat_turn"}:
                media = [
                    passed[step_id]
                    for step_id in contract.required_step_ids
                    if "duration_ms" in passed[step_id]
                ]
                if len(media) != 1 or not _valid_playback(media[0], output_metrics["duration_ms"]):
                    raise VoiceVerificationError("Voice media playback metrics are incomplete")
            created = self._evidence_for_contract(
                verification,
                contract,
                summary,
                artifact_store,
                EvidenceOutcome.PASS,
                input_metrics,
                output_metrics,
            )
            generated.extend(created)
            results.append(
                JourneyResult(
                    contract.journey_id,
                    EvidenceOutcome.PASS,
                    prior.evidence_ids + tuple(item.evidence_id for item in created),
                    _now(),
                )
            )
        return tuple(generated), tuple(results)

    def _failure_evidence(
        self,
        verification: VoiceVerificationPlan,
        browser: BrowserExecutionResult,
        artifact_store: BrowserArtifactStore,
    ) -> tuple[tuple[EvidenceArtifact, ...], tuple[JourneyResult, ...]]:
        prior_results = {item.journey_id: item for item in browser.journey_results}
        generated: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        for contract in verification.journeys:
            created = self._evidence_for_contract(
                verification,
                contract,
                None,
                artifact_store,
                EvidenceOutcome.FAIL,
                {},
                {},
            )
            generated.extend(created)
            prior = prior_results.get(contract.journey_id)
            results.append(
                JourneyResult(
                    contract.journey_id,
                    EvidenceOutcome.FAIL,
                    (() if prior is None else prior.evidence_ids)
                    + tuple(item.evidence_id for item in created),
                    _now(),
                )
            )
        return tuple(generated), tuple(results)

    def _evidence_for_contract(
        self,
        verification: VoiceVerificationPlan,
        contract,
        source: EvidenceArtifact | None,
        artifact_store: BrowserArtifactStore,
        outcome: EvidenceOutcome,
        input_metrics: dict[str, int],
        output_metrics: dict[str, int],
    ) -> tuple[EvidenceArtifact, ...]:
        values: list[EvidenceArtifact] = []
        observed = _now()
        for kind in contract.evidence_kinds:
            payload = {
                "schema_version": 1,
                "verification_id": verification.verification_id,
                "verification_digest": verification.digest,
                "browser_plan_digest": verification.browser_plan_digest,
                "journey_id": contract.journey_id,
                "evidence_kind": kind.value,
                "outcome": outcome.value,
                "claims": [value.value for value in contract.claims],
                "required_step_ids": list(contract.required_step_ids),
                "source_browser_evidence_id": None if source is None else source.evidence_id,
                "source_browser_digest": None if source is None else source.digest,
                "input_fixture_digest": verification.input_fixture.digest,
                "output_fixture_digest": verification.output_fixture.digest,
                "input_audio_metrics": input_metrics,
                "output_audio_metrics": output_metrics,
                "expected_response_characters": len(verification.expected_response),
            }
            uri, digest = artifact_store.write_json(
                verification.product_id, verification.run_id, payload
            )
            suffix = kind.value.removesuffix("_EVIDENCE").lower().replace("_", "-")
            values.append(
                EvidenceArtifact(
                    f"{verification.run_id}.{contract.journey_id}.voice-{suffix}",
                    verification.run_id,
                    "VOICE",
                    contract.journey_id,
                    kind,
                    outcome,
                    verification.commit_sha,
                    uri,
                    digest,
                    observed,
                    "Locked voice/media claims verified from exact fixtures and browser assertions"
                    if outcome is EvidenceOutcome.PASS
                    else "Voice/media claim verification failed closed",
                    (
                        ("verification_digest", verification.digest),
                        ("provider_id", verification.provider_id),
                    ),
                )
            )
        return tuple(values)


def _fetch_media(configuration: ManagedProductRuntimeConfiguration, path: str) -> bytes:
    url = f"{endpoint_origin(configuration.frontend_url)}{path}"
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(Request(url, method="GET"), timeout=5) as response:
            if response.status != 200:
                raise VoiceVerificationError("Voice media endpoint did not return HTTP 200")
            media_type = response.headers.get_content_type()
            if media_type not in {"audio/wav", "audio/x-wav"}:
                raise VoiceVerificationError("Voice media endpoint returned an unsafe type")
            content = response.read(10_000_001)
    except (HTTPError, URLError, OSError, TimeoutError) as error:
        raise VoiceVerificationError("Voice media endpoint verification failed") from error
    if not content or len(content) > 10_000_000:
        raise VoiceVerificationError("Voice media endpoint response is outside policy")
    return content


def _analyze_wav(content: bytes, fixture: DeterministicAudioFixture) -> dict[str, int]:
    try:
        with wave.open(BytesIO(content), "rb") as audio:
            if audio.getcomptype() != "NONE" or audio.getsampwidth() != 2:
                raise VoiceVerificationError("Voice fixture must be uncompressed 16-bit PCM")
            sample_rate = audio.getframerate()
            channels = audio.getnchannels()
            frame_count = audio.getnframes()
            samples = array("h", audio.readframes(frame_count))
    except (EOFError, wave.Error) as error:
        raise VoiceVerificationError("Voice fixture is not a readable WAV file") from error
    if sys.byteorder != "little":
        samples.byteswap()
    duration_ms = round(frame_count * 1_000 / sample_rate)
    if (
        sample_rate != fixture.sample_rate_hz
        or channels != fixture.channels
        or abs(duration_ms - fixture.duration_ms) > 2
        or not samples
    ):
        raise VoiceVerificationError("Voice fixture dimensions differ from locked authority")
    peak = max(abs(value) for value in samples)
    rms = round(math.sqrt(sum(value * value for value in samples) / len(samples)))
    non_silent_milli = round(
        sum(1 for value in samples if abs(value) >= 200) * 1_000 / len(samples)
    )
    if peak < 1_000 or rms < 100 or non_silent_milli < 50:
        raise VoiceVerificationError("Voice fixture does not contain sufficient audible signal")
    return {
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "duration_ms": duration_ms,
        "peak_amplitude": peak,
        "rms_amplitude": rms,
        "non_silent_samples_milli": non_silent_milli,
    }


def _valid_playback(value: dict[str, object], expected_duration_ms: int) -> bool:
    duration = value.get("duration_ms")
    played = value.get("played_ms")
    volume = value.get("volume_milli")
    return (
        isinstance(duration, int)
        and isinstance(played, int)
        and abs(duration - expected_duration_ms) <= 100
        and played + 100 >= duration
        and value.get("muted") is False
        and isinstance(volume, int)
        and volume >= 500
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
