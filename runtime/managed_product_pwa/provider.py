"""Real Chromium PWA verification with bounded secret-safe evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from time import monotonic, sleep
from urllib.parse import urljoin, urlsplit, urlunsplit

from runtime.managed_product_browser.contracts import BrowserArtifactStore
from runtime.managed_product_browser.models import (
    BrowserExecutionResult,
    BrowserExecutionStage,
)
from runtime.managed_product_pwa.models import PwaVerificationPlan
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


_JOURNEY_ID = "pwa.install_launch"
_CAPABILITY_ID = "PWA"


class PlaywrightPwaProvider:
    """Verify one installable offline shell in a fresh Chromium profile."""

    provider_id = "playwright-pwa-v1"

    def execute(
        self,
        plan: PwaVerificationPlan,
        configuration: ManagedProductRuntimeConfiguration,
        artifact_store: BrowserArtifactStore,
    ) -> BrowserExecutionResult:
        started = _now()
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError:
            return _unavailable(plan, started)

        console: list[dict[str, object]] = []
        network: list[dict[str, object]] = []
        claims: list[str] = []
        failure_code: str | None = None
        screenshot: bytes | None = None
        origin = endpoint_origin(configuration.frontend_url)
        offline = False
        installed_manifest_id: str | None = None
        browser_session = None
        phase = "NAVIGATION"

        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    "",
                    headless=True,
                    executable_path=playwright.chromium.executable_path,
                    args=["--enable-devtools-pwa-handler"],
                    accept_downloads=False,
                    ignore_https_errors=False,
                    java_script_enabled=True,
                    locale="en-US",
                    service_workers="allow",
                    timezone_id="UTC",
                    viewport={"width": 1280, "height": 720},
                )
                browser = context.browser
                if browser is None:
                    raise PlaywrightError("Persistent Chromium browser is unavailable")
                context.set_default_timeout(10_000)
                page = context.pages[0] if context.pages else context.new_page()

                def route_request(route) -> None:  # noqa: ANN001
                    requested = route.request.url
                    if _allowed(requested, origin):
                        route.continue_()
                    else:
                        network.append(
                            {
                                "method": route.request.method,
                                "resource_type": route.request.resource_type,
                                "status": None,
                                "url": _safe_url(requested),
                                "failure": "ORIGIN_BLOCKED",
                            }
                        )
                        route.abort("blockedbyclient")

                page.route("**/*", route_request)
                page.on(
                    "console",
                    lambda message: console.append(
                        {"type": message.type, "message_length": min(len(message.text), 2_000)}
                    ),
                )
                page.on(
                    "pageerror",
                    lambda error: console.append(
                        {"type": "pageerror", "message_length": min(len(str(error)), 2_000)}
                    ),
                )
                page.on(
                    "response",
                    lambda response: network.append(
                        {
                            "method": response.request.method,
                            "resource_type": response.request.resource_type,
                            "status": int(response.status),
                            "url": _safe_url(response.url),
                            "offline": offline,
                        }
                    ),
                )
                page.on(
                    "requestfailed",
                    lambda request: network.append(
                        {
                            "method": request.method,
                            "resource_type": request.resource_type,
                            "status": None,
                            "url": _safe_url(request.url),
                            "failure": "OFFLINE_REQUEST_FAILED"
                            if offline
                            else "REQUEST_FAILED",
                            "offline": offline,
                        }
                    ),
                )
                try:
                    page.goto(f"{origin}{plan.start_path}", wait_until="networkidle")
                    shell = page.get_by_test_id(plan.shell_test_id)
                    shell.wait_for(state="visible")
                    if plan.shell_expected_text not in shell.inner_text():
                        raise AssertionError("PWA shell marker did not match authority")

                    phase = "MANIFEST"
                    linked_manifest = page.locator("link[rel='manifest']").get_attribute("href")
                    if _resolved_path(linked_manifest, origin, page.url) != plan.manifest_path:
                        raise AssertionError("PWA manifest link did not match authority")
                    manifest = _fetch_json(context, f"{origin}{plan.manifest_path}")
                    icon_paths = _validate_manifest(manifest, plan)
                    claims.append("MANIFEST_VERIFIED")
                    phase = "ICONS"
                    for path in icon_paths:
                        _fetch_icon(context, f"{origin}{path}")
                    claims.append("ICONS_VERIFIED")

                    phase = "SERVICE_WORKER"
                    worker = page.evaluate(
                        """async expectedPath => {
                            const registration = await navigator.serviceWorker.ready;
                            const active = registration.active;
                            return {
                                state: active ? active.state : null,
                                path: active ? new URL(active.scriptURL).pathname : null
                            };
                        }""",
                        plan.service_worker_path,
                    )
                    if (
                        not isinstance(worker, dict)
                        or worker.get("state") != "activated"
                        or worker.get("path") != plan.service_worker_path
                    ):
                        raise AssertionError("PWA service worker did not activate")
                    claims.append("SERVICE_WORKER_ACTIVE")
                    page.reload(wait_until="networkidle")
                    if not page.evaluate("Boolean(navigator.serviceWorker.controller)"):
                        raise AssertionError("PWA service worker did not control the page")
                    claims.append("SERVICE_WORKER_CONTROLS_PAGE")

                    phase = "INSTALLABILITY"
                    page_session = context.new_cdp_session(page)
                    installability = page_session.send("Page.getInstallabilityErrors")
                    if installability.get("installabilityErrors"):
                        raise AssertionError("Chromium reported PWA installability errors")
                    phase = "MANIFEST_IDENTITY"
                    app_identity = page_session.send("Page.getAppId")
                    installed_manifest_id = app_identity.get("appId")
                    if installed_manifest_id != f"{origin}/":
                        raise AssertionError("PWA manifest identity did not match authority")
                    browser_session = browser.new_browser_cdp_session()
                    phase = "INSTALL"
                    browser_session.send(
                        "PWA.install",
                        {
                            "manifestId": installed_manifest_id,
                            "installUrlOrBundleUrl": f"{origin}{plan.start_path}",
                        },
                    )
                    phase = "STANDALONE_SETTING"
                    browser_session.send(
                        "PWA.changeAppUserSettings",
                        {
                            "manifestId": installed_manifest_id,
                            "displayMode": "standalone",
                        },
                    )
                    phase = "LAUNCH"
                    launched = browser_session.send(
                        "PWA.launch", {"manifestId": installed_manifest_id}
                    )
                    target_id = launched.get("targetId")
                    if not isinstance(target_id, str) or not target_id:
                        raise AssertionError("PWA standalone launch returned no target")
                    phase = "LAUNCH_TARGET"
                    deadline = monotonic() + 10
                    while True:
                        target = browser_session.send(
                            "Target.getTargetInfo", {"targetId": target_id}
                        ).get("targetInfo")
                        if isinstance(target, dict) and target.get("type") == "page":
                            try:
                                if (
                                    _resolved_path(target.get("url"), origin, page.url)
                                    == plan.start_path
                                ):
                                    break
                            except ValueError:
                                pass
                        if monotonic() >= deadline:
                            raise AssertionError(
                                "PWA standalone launch target was unauthorized"
                            )
                        sleep(0.1)
                    browser_session.send("Target.closeTarget", {"targetId": target_id})
                    claims.append("STANDALONE_DISPLAY")
                    phase = "REFRESH"
                    page.reload(wait_until="networkidle")
                    shell = page.get_by_test_id(plan.shell_test_id)
                    if plan.shell_expected_text not in shell.inner_text():
                        raise AssertionError("PWA shell did not survive refresh")
                    claims.append("REFRESH_SURVIVES")

                    phase = "OFFLINE_SHELL"
                    offline = True
                    context.set_offline(True)
                    page.reload(wait_until="domcontentloaded")
                    shell = page.get_by_test_id(plan.shell_test_id)
                    shell.wait_for(state="visible")
                    if (
                        plan.shell_expected_text not in shell.inner_text()
                        or not page.evaluate("Boolean(navigator.serviceWorker.controller)")
                    ):
                        raise AssertionError("PWA offline shell was unavailable")
                    claims.append("OFFLINE_SHELL_AVAILABLE")
                    screenshot = page.screenshot(full_page=True)
                    if any(item["type"] in {"error", "pageerror"} for item in console):
                        raise AssertionError("PWA browser console contained an error")
                except (PlaywrightError, PlaywrightTimeoutError, AssertionError, ValueError):
                    failure_code = f"PWA_{phase}_FAILED"
                    try:
                        screenshot = page.screenshot(full_page=True)
                    except (PlaywrightError, PlaywrightTimeoutError):
                        screenshot = None
                finally:
                    if offline:
                        context.set_offline(False)
                    if browser_session is not None and installed_manifest_id is not None:
                        try:
                            browser_session.send(
                                "PWA.uninstall", {"manifestId": installed_manifest_id}
                            )
                        except PlaywrightError:
                            failure_code = "PWA_PROVIDER_FAILED"
                    context.close()
        except (PlaywrightError, PlaywrightTimeoutError, OSError):
            failure_code = "PWA_PROVIDER_FAILED"

        outcome = (
            EvidenceOutcome.PASS
            if failure_code is None and tuple(claims) == tuple(value.value for value in plan.claims)
            else EvidenceOutcome.FAIL
        )
        evidence = _evidence(
            plan,
            artifact_store,
            outcome,
            tuple(claims),
            tuple(console),
            tuple(network),
            screenshot,
        )
        completed = _now()
        return BrowserExecutionResult(
            plan.run_id,
            plan.product_id,
            plan.plan_id,
            plan.digest,
            plan.commit_sha,
            BrowserExecutionStage.COMPLETED
            if outcome is EvidenceOutcome.PASS
            else BrowserExecutionStage.FAILED,
            evidence,
            (
                JourneyResult(
                    _JOURNEY_ID,
                    outcome,
                    tuple(item.evidence_id for item in evidence),
                    completed,
                ),
            ),
            started,
            completed,
            failure_code,
        )


def _validate_manifest(value: object, plan: PwaVerificationPlan) -> tuple[str, ...]:
    if not isinstance(value, dict):
        raise ValueError("PWA manifest is not an object")
    if (
        not isinstance(value.get("name"), str)
        or not value["name"].strip()
        or not isinstance(value.get("short_name"), str)
        or not value["short_name"].strip()
        or _manifest_path(value.get("id")) != "/"
        or value.get("display") not in {"standalone", "fullscreen", "minimal-ui"}
        or _manifest_path(value.get("start_url")) != plan.start_path
        or _manifest_path(value.get("scope")) != "/"
    ):
        raise ValueError("PWA manifest is incomplete or mismatched")
    icons = value.get("icons")
    if not isinstance(icons, list):
        raise ValueError("PWA manifest icons are missing")
    selected: dict[str, str] = {}
    for icon in icons:
        if not isinstance(icon, dict) or icon.get("type") != "image/png":
            continue
        source = _manifest_path(icon.get("src"))
        sizes = str(icon.get("sizes", "")).split()
        for size in ("192x192", "512x512"):
            if size in sizes:
                selected[size] = source
    if set(selected) != {"192x192", "512x512"}:
        raise ValueError("PWA manifest lacks required PNG icon sizes")
    return tuple(selected[size] for size in ("192x192", "512x512"))


def _fetch_json(context, url: str) -> object:  # noqa: ANN001
    response = context.request.get(url, max_redirects=0, timeout=5_000)
    if response.status != 200 or response.url != url:
        raise ValueError("PWA manifest request failed or redirected")
    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if media_type not in {"application/manifest+json", "application/json"}:
        raise ValueError("PWA manifest content type is invalid")
    content = response.body()
    if not content or len(content) > 100_000:
        raise ValueError("PWA manifest size is outside policy")
    return json.loads(content)


def _fetch_icon(context, url: str) -> None:  # noqa: ANN001
    response = context.request.get(url, max_redirects=0, timeout=5_000)
    if response.status != 200 or response.url != url:
        raise ValueError("PWA icon request failed or redirected")
    if response.headers.get("content-type", "").split(";", 1)[0].strip() != "image/png":
        raise ValueError("PWA icon content type is invalid")
    content = response.body()
    if not 8 <= len(content) <= 2_000_000 or content[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PWA icon bytes are invalid")


def _evidence(
    plan: PwaVerificationPlan,
    artifact_store: BrowserArtifactStore,
    outcome: EvidenceOutcome,
    claims: tuple[str, ...],
    console: tuple[dict[str, object], ...],
    network: tuple[dict[str, object], ...],
    screenshot: bytes | None,
) -> tuple[EvidenceArtifact, ...]:
    observed = _now()
    records: list[tuple[EvidenceKind, str, str]] = []
    payloads = (
        (
            EvidenceKind.BROWSER,
            {
                "schema_version": 1,
                "provider_id": plan.provider_id,
                "plan_digest": plan.digest,
                "journey_id": _JOURNEY_ID,
                "outcome": outcome.value,
                "claims": list(claims),
            },
        ),
        (EvidenceKind.BROWSER_CONSOLE, {"entries": list(console)}),
        (EvidenceKind.BROWSER_NETWORK, {"entries": list(network)}),
        (
            EvidenceKind.PWA,
            {
                "schema_version": 1,
                "plan_digest": plan.digest,
                "outcome": outcome.value,
                "claims": list(claims),
                "manifest_path": plan.manifest_path,
                "service_worker_path": plan.service_worker_path,
            },
        ),
    )
    for kind, payload in payloads:
        uri, digest = artifact_store.write_json(plan.product_id, plan.run_id, payload)
        records.append((kind, uri, digest))
    if screenshot is not None:
        uri, digest = artifact_store.write_bytes(
            plan.product_id, plan.run_id, screenshot, "png"
        )
        records.append((EvidenceKind.SCREENSHOT, uri, digest))
    values = []
    for kind, uri, digest in records:
        suffix = kind.value.removesuffix("_EVIDENCE").lower().replace("_", "-")
        values.append(
            EvidenceArtifact(
                f"{plan.run_id}.{_JOURNEY_ID}.{suffix}",
                plan.run_id,
                _CAPABILITY_ID,
                _JOURNEY_ID,
                kind,
                outcome,
                plan.commit_sha,
                uri,
                digest,
                observed,
                "PWA install, standalone, refresh, and offline claims passed"
                if outcome is EvidenceOutcome.PASS
                else "PWA verification failed closed",
                (("plan_digest", plan.digest), ("provider_id", plan.provider_id)),
            )
        )
    return tuple(values)


def _unavailable(plan: PwaVerificationPlan, started: datetime) -> BrowserExecutionResult:
    now = _now()
    return BrowserExecutionResult(
        plan.run_id,
        plan.product_id,
        plan.plan_id,
        plan.digest,
        plan.commit_sha,
        BrowserExecutionStage.FAILED,
        (),
        (),
        started,
        now,
        "PWA_PROVIDER_UNAVAILABLE",
    )


def _allowed(url: str, origin: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme in {"about", "blob", "data"}:
        return True
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")) == origin


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or "invalid-host"
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))[:2_000]


def _resolved_path(value: object, origin: str, base_url: str) -> str:
    if not isinstance(value, str):
        raise ValueError("PWA path is missing")
    resolved = urlsplit(urljoin(base_url, value))
    if urlunsplit((resolved.scheme, resolved.netloc, "", "", "")) != origin:
        raise ValueError("PWA path escaped the approved origin")
    if resolved.query or resolved.fragment:
        raise ValueError("PWA path cannot contain query or fragment")
    return _manifest_path(resolved.path)


def _manifest_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\\" in value
        or "//" in value
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise ValueError("PWA manifest path is unsafe")
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)
