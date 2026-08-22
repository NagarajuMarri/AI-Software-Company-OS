"""Small WSGI shell for unified ASCOS local user-acceptance testing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import json


StartResponse = Callable[[str, list[tuple[str, str]]], object]
WsgiApplication = Callable[[dict[str, object], StartResponse], Iterable[bytes]]


class LocalUatApplication:
    """Expose a public welcome/health shell around authenticated ASCOS."""

    def __init__(
        self,
        authenticated: WsgiApplication,
        *,
        execution_configured: bool = False,
        live_execution_enabled: bool = False,
        delivery_configured: bool = False,
        live_delivery_enabled: bool = False,
    ) -> None:
        self._authenticated = authenticated
        self._execution_configured = execution_configured
        self._live_execution_enabled = live_execution_enabled
        self._delivery_configured = delivery_configured
        self._live_delivery_enabled = live_delivery_enabled

    def __call__(
        self,
        environ: dict[str, object],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if path == "/" and method in {"GET", "HEAD"}:
            return _html(
                start_response,
                "200 OK",
                _welcome(
                    self._execution_configured,
                    self._live_execution_enabled,
                    self._delivery_configured,
                    self._live_delivery_enabled,
                ),
                head=method == "HEAD",
            )
        if path == "/healthz" and method in {"GET", "HEAD"}:
            return _json(
                start_response,
                "200 OK",
                {
                    "application": "ascos-local-uat",
                    "mode": "LOCAL_UAT_ONLY",
                    "status": "ok",
                },
                head=method == "HEAD",
            )
        if path == "/favicon.ico" and method == "GET":
            return _empty(start_response, "204 No Content")
        if path in {"/", "/healthz", "/favicon.ico"}:
            return _method_not_allowed(start_response, "GET, HEAD")
        return self._authenticated(environ, start_response)


class LocalUatWorkspaceApplication:
    """Add a truthful authenticated UAT status page to the customer workspace."""

    def __init__(
        self,
        customer_workspace: WsgiApplication,
        *,
        execution_configured: bool = False,
        live_execution_enabled: bool = False,
        delivery_configured: bool = False,
        live_delivery_enabled: bool = False,
    ) -> None:
        self._customer_workspace = customer_workspace
        self._execution_configured = execution_configured
        self._live_execution_enabled = live_execution_enabled
        self._delivery_configured = delivery_configured
        self._live_delivery_enabled = live_delivery_enabled

    def __call__(
        self,
        environ: dict[str, object],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if path == "/uat" and method in {"GET", "HEAD"}:
            customer_id = environ.get("REMOTE_USER")
            csrf = environ.get("ascos.csrf_token")
            if not isinstance(customer_id, str) or not isinstance(csrf, str):
                return _html(
                    start_response,
                    "401 Unauthorized",
                    _message("Sign in required", "A verified customer session is required."),
                    head=method == "HEAD",
                )
            return _html(
                start_response,
                "200 OK",
                _status(
                    customer_id,
                    csrf,
                    self._execution_configured,
                    self._live_execution_enabled,
                    self._delivery_configured,
                    self._live_delivery_enabled,
                ),
                head=method == "HEAD",
            )
        if path == "/uat":
            return _method_not_allowed(start_response, "GET, HEAD")
        return self._customer_workspace(environ, start_response)


def _welcome(
    execution_configured: bool = False,
    live_execution_enabled: bool = False,
    delivery_configured: bool = False,
    live_delivery_enabled: bool = False,
) -> str:
    if execution_configured:
        provider_boundary = (
            "The operator has bound a product workspace. After exact customer approval, this "
            + (
                "launcher can run one chargeable governed Codex coding turn. "
                if live_execution_enabled
                else "launcher still has live Codex execution disabled. "
            )
            + (
                "After exact patch review and a separate repository-write confirmation, it can "
                "create one commit, non-force branch push, and open draft PR. It cannot approve "
                "or merge, deploy, release, or select a pilot product."
                if live_delivery_enabled
                else "Repository delivery remains disabled. It cannot commit, push, open a PR, "
                "merge, deploy, release, or select a pilot product."
                if delivery_configured
                else "It cannot commit, push, open a PR, merge, deploy, release, or select a "
                "pilot product."
            )
        )
    else:
        provider_boundary = (
            "This launcher writes only to its local data directory. It does not call an AI provider, "
            "create a repository, publish preview evidence, merge code, deploy, release, or bill."
        )
    return _page(
        "ASCOS V1 Local UAT",
        f"""<main class="landing"><span class="pill">Unified local UAT launcher</span>
<h1>Test the ASCOS product journey in one browser application.</h1>
<p class="lead">Create a local account, describe a product idea, refine and approve its scope,
generate the PRD and roadmap, review the delivery estimate, inspect project progress, and open the governed execution centre.</p>
<div class="actions"><a class="button" href="/signup">Create local account</a>
<a class="button secondary" href="/login">Sign in</a></div>
<section class="notice"><strong>Local UAT only — not production</strong>
<p>{escape(provider_boundary)}</p></section>
<section class="grid"><article><span>Days 11–21</span><h2>Interactive customer flow</h2>
<p>The browser pages and persisted customer artifacts are real.</p></article>
<article><span>Days 22–37</span><h2>Governed runtime baseline</h2>
<p>The accepted runtime capabilities remain bounded and do not gain live authority here.</p></article>
<article><span>Deployment</span><h2>Separate final gate</h2>
<p>Production hosting, configuration, credentials, migration, and post-deploy checks are still required.</p></article></section>
</main>""",
    )


def _status(
    customer_id: str,
    csrf: str,
    execution_configured: bool = False,
    live_execution_enabled: bool = False,
    delivery_configured: bool = False,
    live_delivery_enabled: bool = False,
) -> str:
    execution_state = (
        "One governed Codex turn is enabled behind exact plan and usage approvals."
        if live_execution_enabled
        else "Governed execution is configured but live Codex turns remain operator-disabled."
        if execution_configured
        else "No product workspace or live provider is configured."
    )
    delivery_state = (
        "Exact patch review and one reviewed draft-PR delivery are enabled."
        if live_delivery_enabled
        else "Patch review is configured, but repository writes remain operator-disabled."
        if delivery_configured
        else "No repository delivery target is configured."
    )
    return _page(
        "ASCOS V1 UAT Status",
        f"""<header><a class="brand" href="/uat"><span>AS</span><strong>ASCOS</strong></a>
<form method="post" action="/logout"><input type="hidden" name="csrf_token"
value="{escape(csrf)}"><button class="text-button" type="submit">Sign out</button></form></header>
<main class="status"><span class="pill">Authenticated local UAT</span>
<h1>ASCOS V1 acceptance workspace</h1>
<p class="lead">Signed in as local customer <code>{escape(customer_id)}</code>. Use the real
customer workflow below; the runtime and delivery capabilities keep their governed boundaries.</p>
<div class="actions"><a class="button" href="/customer">Open customer workspace</a>
<a class="button secondary" href="/customer/requests/new">Describe a product</a></div>
<section class="grid"><article><span>Interactive now</span><h2>Customer application</h2>
<p>Signup, sessions, intake, requirements, approvals, PRD, roadmap, estimate, progress, execution planning, and the evidence waiting state.</p></article>
<article><span>Verified baseline</span><h2>Workforce and delivery runtime</h2>
<p>{escape(execution_state)} {escape(delivery_state)} Merge and deployment remain unavailable.</p></article>
<article><span>Truthful boundary</span><h2>No automatic deployment</h2>
<p>Local acceptance is evidence for a deployment decision; it is not a production release.</p></article></section>
<section class="notice"><strong>What to expect at the end</strong>
<p>Project progress begins at 0% with no operational agents assigned. Preview evidence remains
pending until a separately authorized deployment publishes an exact evidence package.</p></section>
</main>""",
    )


def _message(title: str, detail: str) -> str:
    return _page(
        title,
        f'<main class="landing"><h1>{escape(title)}</h1><p>{escape(detail)}</p></main>',
    )


def _page(title: str, content: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{_CSS}</style></head><body>{content}</body></html>"""


def _html(start_response: StartResponse, status: str, body: str, *, head: bool) -> Iterable[bytes]:
    content = body.encode("utf-8")
    start_response(status, _headers("text/html; charset=utf-8", len(content)))
    return [] if head else [content]


def _json(
    start_response: StartResponse,
    status: str,
    value: dict[str, str],
    *,
    head: bool,
) -> Iterable[bytes]:
    content = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    start_response(status, _headers("application/json; charset=utf-8", len(content)))
    return [] if head else [content]


def _empty(start_response: StartResponse, status: str) -> Iterable[bytes]:
    start_response(status, _headers("text/plain; charset=utf-8", 0))
    return []


def _method_not_allowed(start_response: StartResponse, allow: str) -> Iterable[bytes]:
    content = b"Method not allowed\n"
    headers = _headers("text/plain; charset=utf-8", len(content))
    headers.append(("Allow", allow))
    start_response("405 Method Not Allowed", headers)
    return [content]


def _headers(content_type: str, length: int) -> list[tuple[str, str]]:
    return [
        ("Content-Type", content_type),
        ("Content-Length", str(length)),
        ("Cache-Control", "no-store"),
        (
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        ),
        ("Referrer-Policy", "no-referrer"),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
    ]


_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17233d;background:#f4f7fb;font-synthesis:none}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at top right,#dfe8ff 0,transparent 35%),#f4f7fb;color:#17233d}
a{color:inherit}.landing,.status{width:min(1120px,calc(100% - 40px));margin:0 auto;padding:clamp(72px,9vw,120px) 0}.status{padding-top:72px}
header{width:min(1120px,calc(100% - 40px));height:72px;margin:auto;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #dce3ef}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none}.brand span{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#243b7b;color:#fff;font-weight:900}.brand strong{font-size:18px}
.pill{display:inline-flex;padding:7px 11px;border-radius:999px;background:#e0e8ff;color:#29468f;font-size:12px;font-weight:800;letter-spacing:.09em;text-transform:uppercase}
h1{max-width:860px;margin:22px 0 18px;font-size:clamp(42px,6vw,72px);line-height:1.02;letter-spacing:-.045em}h2{margin:10px 0 8px;font-size:22px}.lead{max-width:800px;font-size:20px;line-height:1.65;color:#536078}
.actions{display:flex;flex-wrap:wrap;gap:12px;margin:30px 0 42px}.button,.text-button{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:12px;background:#243b7b;color:#fff;padding:14px 19px;font:inherit;font-weight:800;text-decoration:none;cursor:pointer}.button.secondary{background:#fff;color:#243b7b;border:1px solid #cbd5e6}.text-button{padding:9px 13px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.grid article,.notice{background:#fff;border:1px solid #dce3ef;border-radius:18px;padding:24px;box-shadow:0 14px 40px #30436c0d}.grid article span{color:#4962a6;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.grid p,.notice p{color:#5d687d;line-height:1.55;margin-bottom:0}.notice{margin-top:20px;border-left:5px solid #e39b42}.notice strong{font-size:18px}code{font-size:.83em;overflow-wrap:anywhere}
@media(max-width:760px){.grid{grid-template-columns:1fr}.landing,.status{width:min(100% - 28px,1120px);padding-top:54px}h1{font-size:42px}.lead{font-size:18px}}
"""
