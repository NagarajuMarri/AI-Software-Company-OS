"""Headless Chromium provider with allow-listed network and secret-safe evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
import time
from urllib.parse import urlsplit, urlunsplit

from runtime.managed_product_browser.contracts import BrowserArtifactStore
from runtime.managed_product_browser.errors import (
    BrowserArtifactError,
    BrowserProviderUnavailable,
)
from runtime.managed_product_browser.models import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
)
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    endpoint_origin,
)
from runtime.runtime_acceptance.models import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)


class PlaywrightChromiumProvider:
    """Drive fresh headless Chromium contexts from declarative accessible steps."""

    provider_id = "playwright-chromium"

    def __init__(
        self,
        *,
        maximum_console_entries: int = 200,
        maximum_network_entries: int = 1_000,
        maximum_entry_characters: int = 2_000,
    ) -> None:
        for value, label, maximum in (
            (maximum_console_entries, "console entries", 5_000),
            (maximum_network_entries, "network entries", 20_000),
            (maximum_entry_characters, "entry characters", 20_000),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"Browser {label} limit is outside policy")
        self.maximum_console_entries = maximum_console_entries
        self.maximum_network_entries = maximum_network_entries
        self.maximum_entry_characters = maximum_entry_characters

    def execute(
        self,
        plan: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
    ) -> BrowserExecutionResult:
        return self.execute_preview(
            plan,
            endpoint_origin(configuration.frontend_url),
            tuple(configuration.allowed_origins),
            inputs,
            redactions,
            artifact_store,
        )

    def execute_preview(
        self,
        plan: BrowserJourneyPlan,
        frontend_url: str,
        allowed_origin_values: tuple[str, ...],
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
        *,
        cdp_endpoint: str | None = None,
    ) -> BrowserExecutionResult:
        """Run a plan against an already-deployed exact-commit preview."""

        expected_inputs = {item.input_id for item in plan.inputs}
        if set(inputs) != expected_inputs:
            raise ValueError("Resolved browser inputs do not match the exact plan")
        if any(
            not isinstance(value, str)
            or not value
            or len(value) > 8_192
            or "\0" in value
            for value in inputs.values()
        ):
            raise ValueError("Resolved browser input is outside policy")
        if cdp_endpoint is not None and (
            not isinstance(cdp_endpoint, str)
            or not cdp_endpoint
            or len(cdp_endpoint) > 8_192
            or "\0" in cdp_endpoint
        ):
            raise ValueError("Cloud browser CDP endpoint is outside policy")
        started = _now()
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserProviderUnavailable(
                "Playwright is not installed; install the ASCOS browser extra"
            ) from error

        evidence: list[EvidenceArtifact] = []
        journey_results: list[JourneyResult] = []
        any_failed = False
        failure_code: str | None = None
        allowed_origins = {endpoint_origin(value) for value in allowed_origin_values}
        frontend_origin = endpoint_origin(frontend_url)
        if frontend_origin not in allowed_origins:
            raise ValueError("Preview frontend origin is outside browser policy")

        try:
            with sync_playwright() as playwright:
                browser = (
                    playwright.chromium.connect_over_cdp(cdp_endpoint)
                    if cdp_endpoint is not None
                    else playwright.chromium.launch(
                        headless=True,
                    )
                )
                try:
                    for journey in plan.journeys:
                        result_evidence, result, code = self._run_journey(
                            browser,
                            plan,
                            journey,
                            frontend_origin,
                            allowed_origins,
                            inputs,
                            redactions,
                            artifact_store,
                            PlaywrightError,
                            PlaywrightTimeoutError,
                        )
                        evidence.extend(result_evidence)
                        journey_results.append(result)
                        if result.outcome is EvidenceOutcome.FAIL:
                            any_failed = True
                            failure_code = failure_code or code or "BROWSER_JOURNEY_FAILED"
                finally:
                    browser.close()
        except (PlaywrightError, PlaywrightTimeoutError, OSError) as error:
            del error
            any_failed = True
            failure_code = failure_code or "BROWSER_PROVIDER_FAILED"
            completed = _now()
            completed_ids = {item.journey_id for item in journey_results}
            for journey in plan.journeys:
                if journey.journey_id in completed_ids:
                    continue
                failed_evidence = self._non_screenshot_failure_evidence(
                    plan,
                    journey,
                    artifact_store,
                    completed,
                    failure_code,
                )
                evidence.extend(failed_evidence)
                journey_results.append(
                    JourneyResult(
                        journey.journey_id,
                        EvidenceOutcome.FAIL,
                        tuple(item.evidence_id for item in failed_evidence),
                        completed,
                    )
                )

        return BrowserExecutionResult(
            plan.run_id,
            plan.product_id,
            plan.plan_id,
            plan.digest,
            plan.commit_sha,
            BrowserExecutionStage.FAILED
            if any_failed
            else BrowserExecutionStage.COMPLETED,
            tuple(evidence),
            tuple(journey_results),
            started,
            _now(),
            failure_code,
        )

    def _run_journey(
        self,
        browser,  # noqa: ANN001
        plan: BrowserJourneyPlan,
        journey: BrowserJourneySpecification,
        frontend_origin: str,
        allowed_origins: set[str],
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
        playwright_error: type[Exception],
        playwright_timeout: type[Exception],
    ) -> tuple[tuple[EvidenceArtifact, ...], JourneyResult, str | None]:
        started = _now()
        console_entries: list[dict[str, object]] = []
        network_entries: list[dict[str, object]] = []
        policy_violations: list[str] = []
        step_results: list[dict[str, object]] = []
        successful_requests: set[object] = set()
        console_failed = False
        network_failed = False
        failure_code: str | None = None
        screenshot: bytes | None = None
        secret_locators = []
        context = browser.new_context(
            accept_downloads=False,
            ignore_https_errors=False,
            java_script_enabled=True,
            locale="en-US",
            service_workers="block",
            timezone_id="UTC",
            viewport={"width": 1280, "height": 720},
        )
        context.set_default_timeout(journey.timeout_seconds * 1_000)
        page = context.new_page()

        def add_console(kind: str, message: str) -> None:
            nonlocal console_failed
            if kind in {"error", "pageerror"}:
                console_failed = True
            if len(console_entries) < self.maximum_console_entries:
                console_entries.append(
                    {
                        "type": kind,
                        "text": _redact(
                            message[: self.maximum_entry_characters], redactions
                        ),
                    }
                )

        def add_network(entry: dict[str, object]) -> None:
            if len(network_entries) < self.maximum_network_entries:
                network_entries.append(entry)

        def route_request(route) -> None:  # noqa: ANN001
            nonlocal network_failed
            requested = route.request.url
            if _request_allowed(requested, allowed_origins):
                route.continue_()
                return
            network_failed = True
            policy_violations.append(_safe_url(requested))
            route.abort("blockedbyclient")

        page.route("**/*", route_request)
        page.on("console", lambda message: add_console(message.type, message.text))
        page.on("pageerror", lambda error: add_console("pageerror", str(error)))

        def response_observer(response) -> None:  # noqa: ANN001
            nonlocal network_failed
            status = int(response.status)
            if status >= 400:
                network_failed = True
            else:
                successful_requests.add(response.request)
            add_network(
                {
                    "method": response.request.method,
                    "resource_type": response.request.resource_type,
                    "status": status,
                    "url": _safe_url(response.url),
                }
            )

        def failed_observer(request) -> None:  # noqa: ANN001
            nonlocal network_failed
            # Chromium may report an aborted data/about resource (for example,
            # an inline favicon) through requestfailed even though it never crossed
            # the network boundary. Preserve the diagnostic entry without turning
            # that browser-local request into a network-policy failure.
            browser_local = _browser_local_url(request.url)
            received_success = request in successful_requests
            if not browser_local and not received_success:
                network_failed = True
            add_network(
                {
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "status": None,
                    "url": _safe_url(request.url),
                    "failure": (
                        "BROWSER_LOCAL_REQUEST_ABORTED"
                        if browser_local
                        else (
                            "REQUEST_ABORTED_AFTER_RESPONSE"
                            if received_success
                            else "REQUEST_FAILED"
                        )
                    ),
                }
            )

        page.on("response", response_observer)
        page.on("requestfailed", failed_observer)
        deadline = time.monotonic() + journey.timeout_seconds
        try:
            page.goto(
                f"{frontend_origin}{journey.start_path}",
                wait_until="domcontentloaded",
                timeout=_remaining_ms(deadline),
            )
            for step in journey.steps:
                remaining = _remaining_ms(deadline)
                locator = (
                    None if step.locator is None else _locator(page, step.locator)
                )
                if step.action is BrowserActionKind.CLICK:
                    assert locator is not None
                    locator.click(timeout=remaining)
                elif step.action is BrowserActionKind.FILL:
                    assert locator is not None
                    locator.fill(inputs[step.input_id], timeout=remaining)
                    if next(
                        item for item in plan.inputs if item.input_id == step.input_id
                    ).is_secret:
                        secret_locators.append(locator)
                elif step.action is BrowserActionKind.ASSERT_VISIBLE:
                    assert locator is not None
                    locator.wait_for(state="visible", timeout=remaining)
                elif step.action is BrowserActionKind.ASSERT_TEXT:
                    assert locator is not None
                    locator.wait_for(state="visible", timeout=remaining)
                    if step.expected_text not in locator.inner_text(timeout=remaining):
                        raise AssertionError("Expected browser text was not visible")
                elif step.action is BrowserActionKind.ASSERT_URL_PATH:
                    if urlsplit(page.url).path != step.expected_path:
                        raise AssertionError("Browser URL path did not match")
                elif step.action is BrowserActionKind.RELOAD:
                    page.reload(wait_until="domcontentloaded", timeout=remaining)
                elif step.action is BrowserActionKind.ASSERT_MEDIA_PLAYED:
                    assert locator is not None
                    locator.wait_for(state="visible", timeout=remaining)
                    media = locator.evaluate(
                        """node => ({
                            ended: Boolean(node.ended),
                            duration: Number(node.duration),
                            currentTime: Number(node.currentTime),
                            muted: Boolean(node.muted),
                            volume: Number(node.volume),
                            readyState: Number(node.readyState)
                        })""",
                    )
                    if not isinstance(media, dict):
                        raise AssertionError("Browser media metrics were malformed")
                    duration = _number(media.get("duration"))
                    current_time = _number(media.get("currentTime"))
                    volume = _number(media.get("volume"))
                    ready_state = _number(media.get("readyState"))
                    if (
                        not media.get("ended")
                        or duration <= 0
                        or current_time + 0.1 < duration
                        or media.get("muted") is not False
                        or volume < 0.5
                        or ready_state < 2
                    ):
                        raise AssertionError("Browser media did not complete audible playback")
                    step_results.append(
                        {
                            "step_id": step.step_id,
                            "outcome": "PASS",
                            "duration_ms": int(duration * 1_000),
                            "played_ms": int(current_time * 1_000),
                            "muted": False,
                            "volume_milli": int(volume * 1_000),
                        }
                    )
                    continue
                step_results.append({"step_id": step.step_id, "outcome": "PASS"})
        except (
            playwright_error,
            playwright_timeout,
            AssertionError,
            KeyError,
            TimeoutError,
        ):
            failure_code = "BROWSER_JOURNEY_FAILED"
            if len(step_results) < len(journey.steps):
                step_results.append(
                    {
                        "step_id": journey.steps[len(step_results)].step_id,
                        "outcome": "FAIL",
                    }
                )
        finally:
            try:
                screenshot_timeout = max(
                    1_000,
                    min(10_000, int(max(1.0, deadline - time.monotonic()) * 1_000)),
                )
                screenshot = page.screenshot(
                    full_page=True,
                    animations="disabled",
                    mask=secret_locators,
                    timeout=screenshot_timeout,
                )
            except (playwright_error, playwright_timeout, TimeoutError):
                failure_code = failure_code or "SCREENSHOT_CAPTURE_FAILED"
            try:
                context.close()
            except playwright_error:
                failure_code = failure_code or "BROWSER_CONTEXT_CLOSE_FAILED"

        if console_failed:
            failure_code = failure_code or "BROWSER_CONSOLE_FAILED"
        if network_failed or policy_violations:
            failure_code = failure_code or "BROWSER_NETWORK_FAILED"
        outcome = EvidenceOutcome.FAIL if failure_code else EvidenceOutcome.PASS
        completed = _now()
        summary_uri, summary_digest = artifact_store.write_json(
            plan.product_id,
            plan.run_id,
            {
                "provider_id": self.provider_id,
                "plan_digest": plan.digest,
                "journey_id": journey.journey_id,
                "outcome": outcome.value,
                "failure_code": failure_code,
                "steps": step_results,
            },
        )
        console_uri, console_digest = artifact_store.write_json(
            plan.product_id,
            plan.run_id,
            {
                "journey_id": journey.journey_id,
                "entries": console_entries,
                "truncated": len(console_entries) >= self.maximum_console_entries,
            },
        )
        network_uri, network_digest = artifact_store.write_json(
            plan.product_id,
            plan.run_id,
            {
                "journey_id": journey.journey_id,
                "entries": network_entries,
                "blocked_origins": tuple(sorted(set(policy_violations))),
                "truncated": len(network_entries) >= self.maximum_network_entries,
            },
        )
        records = [
            _evidence(
                plan,
                journey,
                EvidenceKind.BROWSER,
                outcome,
                summary_uri,
                summary_digest,
                completed,
                "Declarative end-user browser steps completed"
                if outcome is EvidenceOutcome.PASS
                else "Declarative end-user browser steps failed",
                self.provider_id,
            ),
            _evidence(
                plan,
                journey,
                EvidenceKind.BROWSER_CONSOLE,
                EvidenceOutcome.FAIL if console_failed else EvidenceOutcome.PASS,
                console_uri,
                console_digest,
                completed,
                "Browser console contained no errors"
                if not console_failed
                else "Browser console contained an error",
                self.provider_id,
            ),
            _evidence(
                plan,
                journey,
                EvidenceKind.BROWSER_NETWORK,
                EvidenceOutcome.FAIL if network_failed else EvidenceOutcome.PASS,
                network_uri,
                network_digest,
                completed,
                "Browser network stayed within approved origins"
                if not network_failed
                else "Browser network failed or left approved origins",
                self.provider_id,
            ),
        ]
        if screenshot is not None:
            screenshot_uri, screenshot_digest = artifact_store.write_bytes(
                plan.product_id, plan.run_id, screenshot, "png"
            )
            records.append(
                _evidence(
                    plan,
                    journey,
                    EvidenceKind.SCREENSHOT,
                    outcome,
                    screenshot_uri,
                    screenshot_digest,
                    completed,
                    "Final journey state captured with secret input fields masked",
                    self.provider_id,
                )
            )
        result = JourneyResult(
            journey.journey_id,
            outcome,
            tuple(item.evidence_id for item in records),
            completed,
        )
        return tuple(records), result, failure_code

    def _non_screenshot_failure_evidence(
        self,
        plan: BrowserJourneyPlan,
        journey: BrowserJourneySpecification,
        artifact_store: BrowserArtifactStore,
        observed_at: datetime,
        failure_code: str,
    ) -> tuple[EvidenceArtifact, ...]:
        records = []
        for kind, label in (
            (EvidenceKind.BROWSER, "Browser provider failed before journey execution"),
            (EvidenceKind.BROWSER_CONSOLE, "Browser console was not available"),
            (EvidenceKind.BROWSER_NETWORK, "Browser network capture was not available"),
        ):
            uri, digest = artifact_store.write_json(
                plan.product_id,
                plan.run_id,
                {
                    "provider_id": self.provider_id,
                    "journey_id": journey.journey_id,
                    "outcome": "FAIL",
                    "failure_code": failure_code,
                },
            )
            records.append(
                _evidence(
                    plan,
                    journey,
                    kind,
                    EvidenceOutcome.FAIL,
                    uri,
                    digest,
                    observed_at,
                    label,
                    self.provider_id,
                )
            )
        return tuple(records)


def _locator(page, locator: BrowserLocator):  # noqa: ANN001, ANN201
    if locator.kind is BrowserLocatorKind.ROLE:
        return page.get_by_role(
            locator.value,
            name=locator.accessible_name,
            exact=locator.exact,
        )
    if locator.kind is BrowserLocatorKind.LABEL:
        return page.get_by_label(locator.value, exact=locator.exact)
    if locator.kind is BrowserLocatorKind.TEST_ID:
        return page.get_by_test_id(locator.value)
    if locator.kind is BrowserLocatorKind.TEXT:
        return page.get_by_text(locator.value, exact=locator.exact)
    raise AssertionError("Unsupported browser locator")


def _evidence(
    plan: BrowserJourneyPlan,
    journey: BrowserJourneySpecification,
    kind: EvidenceKind,
    outcome: EvidenceOutcome,
    uri: str,
    digest: str,
    observed_at: datetime,
    summary: str,
    provider_id: str,
) -> EvidenceArtifact:
    suffix = kind.value.removesuffix("_EVIDENCE").casefold().replace("_", "-")
    return EvidenceArtifact(
        f"{plan.run_id}.{journey.journey_id}.{suffix}",
        plan.run_id,
        journey.capability_id,
        journey.journey_id,
        kind,
        outcome,
        plan.commit_sha,
        uri,
        digest,
        observed_at,
        summary,
        (("plan_digest", plan.digest), ("provider_id", provider_id)),
    )


def _request_allowed(url: str, allowed_origins: set[str]) -> bool:
    if _browser_local_url(url):
        return True
    if url.startswith("blob:"):
        url = url[5:]
    try:
        parsed = urlsplit(url)
        origin = endpoint_origin(
            urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        )
    except (TypeError, ValueError):
        return False
    return origin in allowed_origins


def _browser_local_url(url: str) -> bool:
    try:
        return urlsplit(url).scheme.casefold() in {"about", "data"}
    except (TypeError, ValueError):
        return False


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"data", "blob", "about"}:
            return f"{parsed.scheme}:"
        host = parsed.hostname or "invalid"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, f"{host}{port}", parsed.path or "/", "", ""))[
            :2_000
        ]
    except (TypeError, ValueError):
        return "invalid://"


def _redact(value: str, redactions: tuple[str, ...]) -> str:
    rendered = value
    for secret in sorted(set(redactions), key=len, reverse=True):
        if secret:
            rendered = rendered.replace(secret, "[REDACTED]")
    rendered = re.sub(
        r"(?i)\b(password|passwd|token|authorization|api[-_ ]?key|access[-_ ]?key)"
        r"\s*[:=]\s*(?:(?:Basic|Bearer)\s+)?[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        rendered,
    )
    rendered = re.sub(
        r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}",
        "[REDACTED]",
        rendered,
    )
    return rendered


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AssertionError("Browser media metric was not finite")
    return float(value)


def _remaining_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1_000)
    if remaining < 1:
        raise TimeoutError("Browser journey exceeded its bounded timeout")
    return remaining


def _now() -> datetime:
    return datetime.now(timezone.utc)
