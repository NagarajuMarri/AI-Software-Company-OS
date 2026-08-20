"""Dependency-free WSGI customer portal for Day 11 product-request intake."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import timezone
from html import escape
import hmac
import re
from secrets import token_urlsafe
from urllib.parse import parse_qs

from runtime.customer_application.errors import (
    ProductRequestConflict,
    ProductRequestNotFound,
)
from runtime.customer_application.models import CustomerProductRequest
from runtime.customer_application.service import CustomerProductRequestService


_DETAIL = re.compile(r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})$")
_FORM_FIELDS = {
    "csrf_token",
    "request_id",
    "product_name",
    "product_summary",
    "target_users",
    "features",
    "constraints",
}
_MAX_BODY = 32_768


class CustomerPortalApplication:
    """Render a customer dashboard and accept one secure product brief."""

    def __init__(self, service: CustomerProductRequestService) -> None:
        self._service = service

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        customer_id = environ.get("REMOTE_USER")
        if not isinstance(customer_id, str) or not customer_id:
            return _respond(
                start_response,
                "401 Unauthorized",
                _message("Sign in required", "A verified customer session is required."),
            )
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        if method == "GET" and path in {"/", "/customer"}:
            return _respond(
                start_response,
                "200 OK",
                self._dashboard(customer_id, _csrf(environ)),
            )
        if method == "GET" and path == "/customer/requests/new":
            csrf = _csrf(environ)
            if csrf is None:
                return _respond(
                    start_response,
                    "503 Service Unavailable",
                    _message("Session unavailable", "Please sign in again and retry."),
                )
            return _respond(start_response, "200 OK", _new_request(csrf))
        match = _DETAIL.fullmatch(path)
        if method == "GET" and match:
            try:
                value = self._service.get(customer_id, match.group(1))
            except ProductRequestNotFound:
                return _respond(
                    start_response,
                    "404 Not Found",
                    _message("Request not found", "This product request is unavailable."),
                )
            return _respond(
                start_response,
                "200 OK",
                _request_detail(value, _csrf(environ)),
            )
        if method == "POST" and path == "/customer/requests":
            return self._submit(environ, start_response, customer_id)
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested customer page does not exist."),
        )

    def _dashboard(self, customer_id: str, csrf: str | None) -> str:
        requests = tuple(reversed(self._service.dashboard(customer_id)))
        if requests:
            cards = "".join(
                f"""<a class="request-card" href="/customer/requests/{escape(item.request_id)}">
<span class="status">Submitted</span><strong>{escape(item.product_name)}</strong>
<small>{escape(item.submitted_at.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC"))}</small>
</a>"""
                for item in requests
            )
        else:
            cards = """<div class="empty"><strong>No product requests yet</strong>
<p>Describe your idea and ASCOS will turn it into a governed delivery plan.</p></div>"""
        content = f"""<section class="hero"><div><span class="eyebrow">Customer workspace</span>
<h1>Build your next product with ASCOS</h1>
<p>Tell us the problem, users, and features. Your request becomes the authority for planning.</p></div>
<a class="button" href="/customer/requests/new">Describe a product</a></section>
<section><div class="section-title"><h2>Your product requests</h2>
<span>{len(requests)} submitted</span></div><div class="request-grid">{cards}</div></section>"""
        return _layout("ASCOS Customer Workspace", content, csrf)

    def _submit(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
        customer_id: str,
    ) -> Iterable[bytes]:
        expected_csrf = _csrf(environ)
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "")))
        except ValueError:
            length = -1
        if expected_csrf is None or content_type != "application/x-www-form-urlencoded":
            return _bad_request(start_response)
        if not 0 <= length <= _MAX_BODY:
            return _bad_request(start_response)
        stream = environ.get("wsgi.input")
        if stream is None or not hasattr(stream, "read"):
            return _bad_request(start_response)
        body = stream.read(length)
        if not isinstance(body, bytes) or len(body) != length:
            return _bad_request(start_response)
        try:
            fields = parse_qs(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=20,
            )
            if set(fields) != _FORM_FIELDS or any(len(values) != 1 for values in fields.values()):
                raise ValueError("Unexpected form fields")
            if not hmac.compare_digest(fields["csrf_token"][0], expected_csrf):
                raise ValueError("CSRF mismatch")
            value = self._service.submit(
                request_id=fields["request_id"][0],
                customer_id=customer_id,
                product_name=_clean(fields["product_name"][0]),
                product_summary=_clean(fields["product_summary"][0]),
                target_users=_clean(fields["target_users"][0]),
                features=_lines(fields["features"][0]),
                constraints=_lines(fields["constraints"][0]),
            )
        except (UnicodeDecodeError, ValueError, ProductRequestConflict):
            return _bad_request(start_response)
        return _respond(
            start_response,
            "303 See Other",
            b"",
            extra_headers=[("Location", f"/customer/requests/{value.request_id}")],
        )


def _csrf(environ: dict[str, object]) -> str | None:
    value = environ.get("ascos.csrf_token")
    return value if isinstance(value, str) and 16 <= len(value) <= 256 else None


def _clean(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _lines(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(line.strip() for line in _clean(value).split("\n") if line.strip()))


def _bad_request(
    start_response: Callable[[str, list[tuple[str, str]]], object],
) -> Iterable[bytes]:
    return _respond(
        start_response,
        "400 Bad Request",
        _message("Request not submitted", "Check the form and try again."),
    )


def _new_request(csrf: str) -> str:
    request_id = f"req-{token_urlsafe(18)}"
    content = f"""<section class="form-shell"><a class="back" href="/customer">← Workspace</a>
<span class="eyebrow">New product request</span><h1>What should ASCOS build?</h1>
<p>Give the product team enough detail to understand the outcome before planning begins.</p>
<form method="post" action="/customer/requests">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="request_id" value="{escape(request_id)}">
<label>Product name<input name="product_name" maxlength="120" required
placeholder="Example: AI receptionist for clinics"></label>
<label>Product summary<textarea name="product_summary" maxlength="2000" rows="5" required
placeholder="What problem should the product solve?"></textarea></label>
<label>Target users<textarea name="target_users" maxlength="500" rows="3" required
placeholder="Who will use it and why?"></textarea></label>
<label>Required features <span>one per line</span><textarea name="features" rows="6" required
placeholder="Answer incoming calls&#10;Book appointments&#10;Send WhatsApp confirmations"></textarea></label>
<label>Constraints <span>optional, one per line</span><textarea name="constraints" rows="4"
placeholder="Telugu and English&#10;India data residency"></textarea></label>
<div class="form-actions"><a href="/customer">Cancel</a>
<button type="submit">Submit product request</button></div></form></section>"""
    return _layout("New Product Request · ASCOS", content, csrf)


def _request_detail(value: CustomerProductRequest, csrf: str | None) -> str:
    features = "".join(f"<li>{escape(item)}</li>" for item in value.features)
    constraints = (
        "".join(f"<li>{escape(item)}</li>" for item in value.constraints)
        if value.constraints
        else "<li>No additional constraints supplied</li>"
    )
    content = f"""<section class="detail"><a class="back" href="/customer">← Workspace</a>
<div class="success"><span>✓</span><div><strong>Request submitted</strong>
<p>ASCOS saved your product brief as immutable planning authority.</p></div></div>
<div class="detail-header"><div><span class="eyebrow">Product request</span>
<h1>{escape(value.product_name)}</h1></div><span class="status">Submitted</span></div>
<div class="detail-grid"><article><h2>Product outcome</h2>
<p>{escape(value.product_summary)}</p></article><article><h2>Target users</h2>
<p>{escape(value.target_users)}</p></article><article><h2>Required features</h2>
<ul>{features}</ul></article><article><h2>Constraints</h2><ul>{constraints}</ul></article></div>
<footer class="authority">Request ID <code>{escape(value.request_id)}</code> ·
Integrity digest <code>{escape(value.digest[:16])}…</code></footer></section>"""
    return _layout(f"{value.product_name} · ASCOS", content, csrf)


def _message(title: str, detail: str) -> str:
    return _layout(title, f"""<section class="form-shell"><h1>{escape(title)}</h1>
<p>{escape(detail)}</p><a class="button" href="/customer">Return to workspace</a></section>""")


def _layout(title: str, content: str, csrf: str | None = None) -> str:
    account = '<div class="account"><span></span>Customer workspace</div>'
    if csrf is not None:
        account = f'''<form class="account logout" method="post" action="/logout">
<span></span><button type="submit">Sign out</button>
<input type="hidden" name="csrf_token" value="{escape(csrf)}"></form>'''
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{_CSS}</style></head><body>
<header><a class="brand" href="/customer"><span>AS</span><strong>ASCOS</strong></a>
{account}</header>
<main>{content}</main></body></html>"""


def _respond(
    start_response: Callable[[str, list[tuple[str, str]]], object],
    status: str,
    body: str | bytes,
    *,
    extra_headers: list[tuple[str, str]] | None = None,
) -> Iterable[bytes]:
    content = body.encode("utf-8") if isinstance(body, str) else body
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(content))),
        ("Cache-Control", "no-store"),
        ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
        ("Referrer-Policy", "no-referrer"),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    start_response(status, headers)
    return (content,)


_CSS = """
:root{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#15223b;background:#f4f7fb}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 10%,#dce9ff 0,transparent 30%),#f4f7fb;min-height:100vh}
header{height:72px;padding:0 max(28px,calc((100vw - 1120px)/2));display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #dce3ee}
.brand{display:flex;align-items:center;gap:10px;color:#101d35;text-decoration:none}.brand span{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#3157d5;color:#fff;font-weight:800}.brand strong{letter-spacing:.08em}
.account{font-size:14px;color:#53627a;display:flex;align-items:center;gap:9px}.account span{width:9px;height:9px;border-radius:50%;background:#2bb673;box-shadow:0 0 0 4px #dff6ea}
.logout{margin:0}.logout button{padding:8px 11px;border:1px solid #dce3ee;background:transparent;color:#53627a;box-shadow:none}.logout input{display:none}
main{max-width:1120px;margin:0 auto;padding:64px 28px 80px}.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:30px;margin-bottom:58px}.hero>div{max-width:720px}
h1{font-size:clamp(34px,5vw,58px);line-height:1.05;letter-spacing:-.04em;margin:12px 0 18px;color:#101d35}p{color:#53627a;line-height:1.7}.hero p{font-size:19px;max-width:650px}
.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#3157d5;font-weight:800}.button,button{display:inline-flex;border:0;border-radius:12px;padding:14px 20px;background:#3157d5;color:#fff;text-decoration:none;font-weight:750;white-space:nowrap;cursor:pointer;box-shadow:0 10px 28px #3157d533}
.section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.section-title h2{margin:0}.section-title span{font-size:14px;color:#728096}.request-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.request-card,.empty{display:flex;flex-direction:column;gap:10px;padding:24px;border:1px solid #dce3ee;border-radius:16px;background:#fff;text-decoration:none;color:#101d35;box-shadow:0 7px 22px #2c42600a}.request-card:hover{border-color:#9fb2ed;transform:translateY(-1px)}.request-card small{color:#728096}.empty{grid-column:1/-1;text-align:center;padding:45px}
.status{display:inline-flex;width:max-content;padding:6px 10px;border-radius:999px;background:#dff6ea;color:#137a49;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}
.form-shell,.detail{max-width:820px;margin:0 auto;background:#fff;border:1px solid #dce3ee;border-radius:22px;padding:40px;box-shadow:0 22px 60px #263c6012}.form-shell h1,.detail h1{font-size:42px}.back{display:block;margin-bottom:32px;color:#53627a;text-decoration:none;font-weight:650}
form{display:grid;gap:22px;margin-top:34px}label{display:grid;gap:9px;font-weight:750;color:#27344b}label span{font-weight:500;color:#7a879a;font-size:13px}input,textarea{width:100%;border:1px solid #cbd5e4;border-radius:11px;padding:13px 14px;font:inherit;color:#15223b;background:#fbfcfe;resize:vertical}input:focus,textarea:focus{outline:3px solid #dbe4ff;border-color:#3157d5}.form-actions{display:flex;align-items:center;justify-content:flex-end;gap:22px;padding-top:8px}.form-actions a{color:#53627a;text-decoration:none}
.success{display:flex;gap:15px;background:#eaf9f1;border:1px solid #bde9d1;border-radius:14px;padding:18px;margin-bottom:34px}.success>span{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#24a865;color:#fff}.success p{margin:3px 0 0}.detail-header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:24px}.detail-grid article{background:#f7f9fc;border:1px solid #e0e6ef;border-radius:14px;padding:20px}.detail-grid h2{font-size:15px;margin:0 0 10px}.detail-grid p{margin:0;white-space:pre-wrap}.detail-grid ul{margin:0;padding-left:20px;color:#53627a;line-height:1.7}.authority{margin-top:26px;padding-top:20px;border-top:1px solid #e0e6ef;color:#7a879a;font-size:12px}.authority code{color:#53627a}
@media(max-width:700px){header{padding:0 18px}.account{display:none}main{padding:36px 18px}.hero{align-items:flex-start;flex-direction:column}.form-shell,.detail{padding:24px}.detail-grid{grid-template-columns:1fr}.form-actions{justify-content:space-between}}
"""
