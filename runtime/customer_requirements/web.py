"""WSGI guided requirements form, draft review, and customer-app router."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from typing import Protocol
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_requirements.errors import (
    RequirementsDraftConflict,
    RequirementsDraftCorrupt,
    RequirementsDraftLocked,
)
from runtime.customer_requirements.models import (
    ALLOWED_PLATFORMS,
    CustomerRequirementsDraft,
    DataSensitivity,
    DeliveryPriority,
)
from runtime.customer_requirements.service import CustomerRequirementsService


_EDIT = re.compile(r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/requirements$")
_REVIEW = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/requirements/review$"
)
_FIELDS = {
    "csrf_token",
    "expected_revision",
    "primary_user_journey",
    "desired_outcomes",
    "must_have_features",
    "success_metrics",
    "non_goals",
    "platforms",
    "data_sensitivity",
    "delivery_priority",
}
_MAX_BODY = 32_768


class RoutedCustomerApplication(Protocol):
    """Small protocol for customer-app route extensions."""

    def handles(self, path: str) -> bool: ...

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable,
    ) -> Iterable[bytes]: ...


class CustomerWorkspaceApplication:
    """Route guided customer pages while preserving the Day 11 portal boundary."""

    def __init__(
        self,
        portal: Callable,
        requirements: "CustomerRequirementsApplication",
        approval: RoutedCustomerApplication | None = None,
        prd: RoutedCustomerApplication | None = None,
        prd_approval: RoutedCustomerApplication | None = None,
        roadmap: RoutedCustomerApplication | None = None,
        roadmap_approval: RoutedCustomerApplication | None = None,
    ) -> None:
        self._portal = portal
        self._requirements = requirements
        self._extensions = tuple(
            item
            for item in (approval, prd, prd_approval, roadmap, roadmap_approval)
            if item is not None
        )

    def __call__(self, environ: dict[str, object], start_response: Callable) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        for extension in self._extensions:
            if extension.handles(path):
                return extension(environ, start_response)
        if self._requirements.handles(path):
            return self._requirements(environ, start_response)
        return self._portal(environ, start_response)


class CustomerRequirementsApplication:
    """Collect a governed requirements draft without approving or executing it."""

    def __init__(self, service: CustomerRequirementsService) -> None:
        self._service = service

    @staticmethod
    def handles(path: str) -> bool:
        return _EDIT.fullmatch(path) is not None or _REVIEW.fullmatch(path) is not None

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        customer_id = environ.get("REMOTE_USER")
        csrf = _csrf(environ)
        if not isinstance(customer_id, str) or not customer_id or csrf is None:
            return _respond(
                start_response,
                "401 Unauthorized",
                _message("Sign in required", "A verified customer session is required."),
            )
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        edit = _EDIT.fullmatch(path)
        review = _REVIEW.fullmatch(path)
        try:
            if edit and method == "GET":
                request, draft = self._service.context(customer_id, edit.group(1))
                if self._service.is_locked(customer_id, edit.group(1)):
                    return _redirect(
                        start_response,
                        f"/customer/requests/{edit.group(1)}/requirements/approved",
                    )
                return _respond(start_response, "200 OK", _form(request, draft, csrf))
            if edit and method == "POST":
                return self._save(environ, start_response, customer_id, edit.group(1), csrf)
            if review and method == "GET":
                request, draft = self._service.context(customer_id, review.group(1))
                if draft is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{review.group(1)}/requirements",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _review(
                        request.product_name,
                        draft,
                        csrf,
                        self._service.is_locked(customer_id, review.group(1)),
                    ),
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except RequirementsDraftLocked:
            assert edit is not None
            return _redirect(
                start_response,
                f"/customer/requests/{edit.group(1)}/requirements/approved",
            )
        except RequirementsDraftConflict:
            return _respond(
                start_response,
                "409 Conflict",
                _message("Draft changed", "Reload the latest requirements draft and try again."),
            )
        except RequirementsDraftCorrupt:
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("Requirements unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested requirements page does not exist."),
        )

    def _save(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
        customer_id: str,
        request_id: str,
        csrf: str,
    ) -> Iterable[bytes]:
        try:
            fields = _form_fields(environ)
            if not hmac.compare_digest(fields["csrf_token"][0], csrf):
                raise ValueError("CSRF mismatch")
            platforms = tuple(fields["platforms"])
            if len(set(platforms)) != len(platforms):
                raise ValueError("Duplicate platforms")
            value = self._service.save(
                customer_id=customer_id,
                request_id=request_id,
                expected_revision=int(fields["expected_revision"][0]),
                primary_user_journey=_clean(fields["primary_user_journey"][0]),
                desired_outcomes=_lines(fields["desired_outcomes"][0]),
                must_have_features=_lines(fields["must_have_features"][0]),
                success_metrics=_lines(fields["success_metrics"][0]),
                non_goals=_lines(fields["non_goals"][0]),
                platforms=platforms,
                data_sensitivity=DataSensitivity(fields["data_sensitivity"][0]),
                delivery_priority=DeliveryPriority(fields["delivery_priority"][0]),
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Draft not saved", "Check every requirements field and try again."),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/requirements/review",
        )


def _form_fields(environ: dict[str, object]) -> dict[str, list[str]]:
    content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
    try:
        length = int(str(environ.get("CONTENT_LENGTH", "")))
    except ValueError:
        length = -1
    stream = environ.get("wsgi.input")
    if (
        content_type != "application/x-www-form-urlencoded"
        or not 0 <= length <= _MAX_BODY
        or stream is None
        or not hasattr(stream, "read")
    ):
        raise ValueError("Invalid requirements request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid requirements body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=20,
    )
    if set(fields) != _FIELDS:
        raise ValueError("Unexpected requirements fields")
    for name, values in fields.items():
        if name == "platforms":
            if not 1 <= len(values) <= len(ALLOWED_PLATFORMS):
                raise ValueError("Invalid platform count")
        elif len(values) != 1:
            raise ValueError("Requirements fields must be singular")
    return fields


def _csrf(environ: dict[str, object]) -> str | None:
    value = environ.get("ascos.csrf_token")
    return value if isinstance(value, str) and 16 <= len(value) <= 256 else None


def _clean(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _lines(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(line.strip() for line in _clean(value).split("\n") if line.strip()))


def _form(request, draft: CustomerRequirementsDraft | None, csrf: str) -> str:
    revision = 0 if draft is None else draft.revision
    journey = "" if draft is None else draft.primary_user_journey
    outcomes = request.product_summary if draft is None else "\n".join(draft.desired_outcomes)
    features = request.features if draft is None else draft.must_have_features
    metrics = () if draft is None else draft.success_metrics
    non_goals = () if draft is None else draft.non_goals
    platforms = ("WEB",) if draft is None else draft.platforms
    sensitivity = DataSensitivity.NO_PERSONAL_DATA if draft is None else draft.data_sensitivity
    priority = DeliveryPriority.STANDARD if draft is None else draft.delivery_priority
    review_link = (
        ""
        if draft is None
        else f'<a class="draft-link" href="/customer/requests/{escape(request.request_id)}/requirements/review">Review saved draft →</a>'
    )
    checks = "".join(
        f'''<label class="check"><input type="checkbox" name="platforms" value="{item}"
{'checked' if item in platforms else ''}><span>{item.title()}</span></label>'''
        for item in ALLOWED_PLATFORMS
    )
    constraints = (
        "".join(f"<li>{escape(item)}</li>" for item in request.constraints)
        if request.constraints
        else "<li>No constraints supplied in the original request</li>"
    )
    content = f'''<section class="form-shell"><a class="back" href="/customer/requests/{escape(request.request_id)}">← Product request</a>
<span class="eyebrow">Guided requirements · Draft {revision or 1}</span>
<h1>Clarify {escape(request.product_name)}</h1>
<p>Define the user journey, measurable outcomes, scope, and data boundary before ASCOS plans work.</p>
{review_link}
<aside><strong>Original request remains immutable</strong><p>{escape(request.product_summary)}</p>
<ul>{constraints}</ul></aside>
<form method="post" action="/customer/requests/{escape(request.request_id)}/requirements">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_revision" value="{revision}">
<label>Primary user journey<textarea name="primary_user_journey" maxlength="2000" rows="5" required
placeholder="Describe what the primary user does from start to successful outcome.">{escape(journey)}</textarea></label>
<label>Desired outcomes <span>one per line</span><textarea name="desired_outcomes" rows="5" required>{escape(outcomes)}</textarea></label>
<label>Must-have features <span>one per line</span><textarea name="must_have_features" rows="7" required>{escape(chr(10).join(features))}</textarea></label>
<label>Success metrics <span>one measurable signal per line</span><textarea name="success_metrics" rows="5" required>{escape(chr(10).join(metrics))}</textarea></label>
<label>Non-goals <span>optional, one per line</span><textarea name="non_goals" rows="4">{escape(chr(10).join(non_goals))}</textarea></label>
<fieldset><legend>Delivery platforms</legend><div class="checks">{checks}</div></fieldset>
<div class="two"><label>Data sensitivity<select name="data_sensitivity">
{_options(DataSensitivity, sensitivity)}</select></label><label>Delivery priority<select name="delivery_priority">
{_options(DeliveryPriority, priority)}</select></label></div>
<div class="actions"><a href="/customer/requests/{escape(request.request_id)}">Cancel</a>
<button type="submit">Save requirements draft</button></div></form></section>'''
    return _layout(f"Clarify {request.product_name} · ASCOS", content, csrf)


def _options(values, selected) -> str:
    labels = {
        "NO_PERSONAL_DATA": "No personal data",
        "PERSONAL_DATA": "Personal data",
        "SENSITIVE_DATA": "Sensitive data",
        "STANDARD": "Standard",
        "TIME_SENSITIVE": "Time-sensitive",
    }
    return "".join(
        f'<option value="{item.value}" {"selected" if item is selected else ""}>{labels[item.value]}</option>'
        for item in values
    )


def _review(
    product_name: str,
    value: CustomerRequirementsDraft,
    csrf: str,
    locked: bool = False,
) -> str:
    def items(values: tuple[str, ...], empty: str = "None declared") -> str:
        return (
            "".join(f"<li>{escape(item)}</li>" for item in values)
            if values
            else f"<li>{escape(empty)}</li>"
        )

    status = "Approved" if locked else "Draft saved"
    authority = (
        "Approved baseline — implementation has not started"
        if locked
        else "Draft only — no implementation has started"
    )
    authority_detail = (
        "PRD generation, planning, agent assignment, coding, and deployment are separate governed steps."
        if locked
        else "Approval, planning, agent assignment, coding, and deployment are separate governed steps."
    )
    primary_action = (
        f'<a class="button" href="/customer/requests/{escape(value.request_id)}/requirements/approved">View approval receipt</a>'
        if locked
        else f'<a class="button" href="/customer/requests/{escape(value.request_id)}/requirements/approve">Approve requirements</a>'
    )
    edit_action = (
        ""
        if locked
        else f'<a class="button secondary" href="/customer/requests/{escape(value.request_id)}/requirements">Edit draft</a>'
    )
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}">← Product request</a>
<div class="review-head"><div><span class="eyebrow">Requirements draft · Revision {value.revision}</span>
<h1>{escape(product_name)}</h1><p>Review the clarified scope before the later approval step.</p></div>
<span class="status {'approved' if locked else ''}">{status}</span></div>
<article class="journey"><h2>Primary user journey</h2><p>{escape(value.primary_user_journey)}</p></article>
<div class="grid"><article><h2>Desired outcomes</h2><ul>{items(value.desired_outcomes)}</ul></article>
<article><h2>Must-have features</h2><ul>{items(value.must_have_features)}</ul></article>
<article><h2>Success metrics</h2><ul>{items(value.success_metrics)}</ul></article>
<article><h2>Non-goals</h2><ul>{items(value.non_goals)}</ul></article></div>
<div class="signals"><span><strong>Platforms</strong>{escape(', '.join(item.title() for item in value.platforms))}</span>
<span><strong>Data</strong>{escape(value.data_sensitivity.value.replace('_', ' ').title())}</span>
<span><strong>Priority</strong>{escape(value.delivery_priority.value.replace('_', ' ').title())}</span></div>
<div class="notice"><strong>{authority}</strong><p>{authority_detail}</p></div>
<div class="actions">{edit_action}<a class="button secondary" href="/customer">Return to workspace</a>{primary_action}</div>
<footer>Source request <code>{escape(value.source_request_digest[:16])}…</code> · Draft <code>{escape(value.digest[:16])}…</code></footer></section>'''
    return _layout(f"Requirements for {product_name} · ASCOS", content, csrf)


def _message(title: str, detail: str) -> str:
    return _layout(
        title,
        f'<section class="form-shell"><h1>{escape(title)}</h1><p>{escape(detail)}</p>'
        '<a class="button" href="/customer">Return to workspace</a></section>',
    )


def _layout(title: str, content: str, csrf: str | None = None) -> str:
    account = ""
    if csrf is not None:
        account = f'''<form class="logout" method="post" action="/logout"><span></span>
<button type="submit">Sign out</button><input type="hidden" name="csrf_token" value="{escape(csrf)}"></form>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{_CSS}</style></head><body><header><a class="brand" href="/customer"><b>AS</b><strong>ASCOS</strong></a>{account}</header>
<main>{content}</main></body></html>'''


def _redirect(start_response: Callable, location: str) -> Iterable[bytes]:
    return _respond(start_response, "303 See Other", b"", [("Location", location)])


def _respond(
    start_response: Callable,
    status: str,
    body: str | bytes,
    extra_headers: list[tuple[str, str]] | None = None,
) -> Iterable[bytes]:
    content = body.encode() if isinstance(body, str) else body
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(content))),
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
    headers.extend(extra_headers or [])
    start_response(status, headers)
    return (content,)


_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#14213b;background:#f3f6fb}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0,#dce9ff 0,transparent 32%),#f3f6fb;min-height:100vh}header{height:72px;padding:0 max(28px,calc((100vw - 1060px)/2));display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #dce3ee}.brand{display:flex;align-items:center;gap:10px;color:#101d35;text-decoration:none;letter-spacing:.08em}.brand b{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#3157d5;color:#fff}.logout{display:flex;align-items:center;gap:9px;margin:0}.logout span{width:9px;height:9px;border-radius:50%;background:#2bb673;box-shadow:0 0 0 4px #dff6ea}.logout button{border:1px solid #dce3ee;border-radius:10px;padding:8px 11px;background:#fff;color:#53627a;font-weight:750;cursor:pointer}.logout input{display:none}main{max-width:1060px;margin:0 auto;padding:54px 28px 80px}.form-shell,.review{background:#fff;border:1px solid #dce3ee;border-radius:22px;padding:42px;box-shadow:0 22px 60px #263c6012}.back{display:block;margin-bottom:30px;color:#647189;text-decoration:none;font-weight:700}.draft-link{display:inline-flex;margin-top:4px;color:#3157d5;font-weight:800;text-decoration:none}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#3157d5;font-weight:850}h1{font-size:clamp(36px,5vw,54px);line-height:1.04;letter-spacing:-.045em;margin:12px 0 16px}p,li{color:#59677e;line-height:1.65}.form-shell>p{font-size:18px;max-width:760px}aside{margin:30px 0 34px;padding:20px 22px;border:1px solid #dce3ee;background:#f7f9fd;border-radius:14px}aside p{margin:6px 0}aside ul{margin-bottom:0}form{display:grid;gap:23px}label{display:grid;gap:9px;font-weight:780;color:#27344b}label>span{font-size:13px;font-weight:500;color:#7a879a}textarea,select{width:100%;border:1px solid #cbd5e4;border-radius:11px;padding:13px 14px;font:inherit;color:#15223b;background:#fbfcfe}textarea{resize:vertical}textarea:focus,select:focus{outline:3px solid #dbe4ff;border-color:#3157d5}fieldset{border:0;padding:0;margin:0}legend{font-weight:780;margin-bottom:10px}.checks{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.check{display:flex;align-items:center;gap:9px;padding:12px;border:1px solid #dce3ee;border-radius:11px;background:#fbfcfe}.check input{accent-color:#3157d5}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.actions{display:flex;justify-content:flex-end;align-items:center;gap:16px;margin-top:8px}.actions>a:not(.button){color:#647189;text-decoration:none}.button,.actions button{display:inline-flex;border:0;border-radius:11px;padding:13px 18px;background:#3157d5;color:#fff;text-decoration:none;font-weight:800;cursor:pointer;box-shadow:0 10px 25px #3157d52b}.button.secondary{background:#fff;color:#3157d5;border:1px solid #bac8ee;box-shadow:none}.review-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.status{padding:7px 11px;border-radius:999px;background:#fff3d7;color:#966300;font-weight:850;font-size:12px;text-transform:uppercase;letter-spacing:.08em}.journey{margin:28px 0 16px;padding:24px;border-radius:15px;background:#edf3ff;border:1px solid #cbd9fa}.review h2{font-size:16px;margin:0 0 10px}.journey p{margin:0;white-space:pre-wrap}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid article{border:1px solid #e0e6ef;background:#f8fafd;border-radius:14px;padding:21px}.grid ul{margin:0;padding-left:20px}.signals{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}.signals span{display:grid;gap:5px;padding:16px;border:1px solid #e0e6ef;border-radius:12px;color:#647189}.signals strong{color:#26344c;font-size:13px}.notice{margin-top:22px;padding:19px 21px;border-left:4px solid #3157d5;background:#f2f5fc}.notice p{margin:4px 0 0}.review footer{margin-top:24px;padding-top:20px;border-top:1px solid #e0e6ef;color:#7a879a;font-size:12px}.review footer code{color:#53627a}@media(max-width:700px){header{padding:0 18px}.logout{display:none}main{padding:34px 16px}.form-shell,.review{padding:24px}.checks,.two,.grid,.signals{grid-template-columns:1fr}.review-head{display:block}.status{display:inline-flex}.actions{align-items:stretch;flex-direction:column}.actions .button,.actions button{text-align:center;justify-content:center}}
.status.approved{background:#e4f8ec;color:#137447}.confirm{display:grid;grid-template-columns:auto 1fr;align-items:flex-start;gap:12px;padding:18px;border:1px solid #c8d6f2;border-radius:13px;background:#f7f9fd}.confirm input{margin-top:4px;accent-color:#3157d5}.receipt{margin-top:24px;padding:20px;border:1px solid #bde7ce;background:#effaf3;border-radius:14px}.receipt dl{display:grid;grid-template-columns:max-content 1fr;gap:9px 18px;margin:0}.receipt dt{font-weight:800}.receipt dd{margin:0;color:#53627a;overflow-wrap:anywhere}@media(max-width:700px){.receipt dl{grid-template-columns:1fr}}
.prd-list{display:grid;gap:14px;margin-top:24px}.prd-requirement{padding:22px;border:1px solid #dce3ee;border-radius:14px;background:#f8fafd}.prd-requirement h2{margin:7px 0 8px;font-size:20px}.prd-requirement p{margin:0}.prd-meta{display:flex;gap:8px;flex-wrap:wrap}.prd-meta span{padding:5px 8px;border-radius:7px;background:#e9effb;color:#3157d5;font-weight:800;font-size:11px;text-transform:uppercase}.trace{margin-top:13px;padding-top:12px;border-top:1px solid #dce3ee;color:#728097;font-size:12px}.trace code{color:#53627a}.section-title{margin:34px 0 12px}.scope-columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}.scope-columns article{padding:20px;border:1px solid #e0e6ef;border-radius:14px;background:#f8fafd}.scope-columns h2{font-size:16px;margin:0 0 9px}.scope-columns p,.scope-columns ul{margin:0}@media(max-width:700px){.scope-columns{grid-template-columns:1fr}}
"""
