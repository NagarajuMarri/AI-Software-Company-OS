"""WSGI customer signup/login/session middleware."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import hmac
from secrets import token_urlsafe
from urllib.parse import parse_qs

from runtime.customer_authentication.errors import (
    AccountAlreadyExists,
    AuthenticationAuthorityCorrupt,
    InvalidCredentials,
    InvalidSession,
)
from runtime.customer_authentication.service import CustomerAuthenticationService


_SESSION_COOKIE = "ascos_session"
_PREAUTH_COOKIE = "ascos_preauth"
_MAX_BODY = 16_384


class AuthenticatedCustomerApplication:
    """Compose real customer authentication in front of the Day 11 portal."""

    def __init__(
        self,
        authentication: CustomerAuthenticationService,
        portal: Callable[[dict[str, object], Callable], Iterable[bytes]],
        *,
        preauth_secret: bytes,
        secure_cookies: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(preauth_secret) < 32:
            raise ValueError("Pre-authentication secret must contain at least 32 bytes")
        self._authentication = authentication
        self._portal = portal
        self._secret = bytes(preauth_secret)
        self._secure_cookies = secure_cookies
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        if method == "GET" and path in {"/signup", "/login"}:
            token = self._preauth_token()
            return _respond(
                start_response,
                "200 OK",
                _auth_page(path, token),
                cookies=[self._cookie(_PREAUTH_COOKIE, token, max_age=600)],
            )
        if method == "POST" and path == "/signup":
            return self._signup(environ, start_response)
        if method == "POST" and path == "/login":
            return self._login(environ, start_response)
        if method == "POST" and path == "/logout":
            return self._logout(environ, start_response)
        token = _cookie_value(environ, _SESSION_COOKIE)
        try:
            session = self._authentication.authenticate(token)
        except AuthenticationAuthorityCorrupt:
            return _respond(
                start_response,
                "503 Service Unavailable",
                _auth_error("Service unavailable", "Please try again later.", "/login"),
                cookies=[self._clear_cookie(_SESSION_COOKIE)],
            )
        except InvalidSession:
            return _redirect(
                start_response,
                "/login",
                cookies=[self._clear_cookie(_SESSION_COOKIE)],
            )
        delegated = dict(environ)
        delegated["REMOTE_USER"] = session.customer_id
        delegated["ascos.csrf_token"] = session.csrf_token
        return self._portal(delegated, start_response)

    def _signup(self, environ, start_response):
        try:
            fields = self._form(environ, {"csrf_token", "email", "password", "confirm_password"})
            self._verify_preauth(environ, fields["csrf_token"])
            if fields["password"] != fields["confirm_password"]:
                raise ValueError("Password confirmation mismatch")
            issued = self._authentication.register(fields["email"], fields["password"])
        except AuthenticationAuthorityCorrupt:
            return _respond(
                start_response,
                "503 Service Unavailable",
                _auth_error("Service unavailable", "Please try again later.", "/signup"),
            )
        except (ValueError, AccountAlreadyExists):
            return _respond(
                start_response,
                "400 Bad Request",
                _auth_error("Account not created", "Check the form and try again.", "/signup"),
            )
        return _redirect(
            start_response,
            "/customer",
            cookies=[
                self._cookie(_SESSION_COOKIE, issued.token, max_age=43_200),
                self._clear_cookie(_PREAUTH_COOKIE),
            ],
        )

    def _login(self, environ, start_response):
        try:
            fields = self._form(environ, {"csrf_token", "email", "password"})
            self._verify_preauth(environ, fields["csrf_token"])
            issued = self._authentication.login(fields["email"], fields["password"])
        except AuthenticationAuthorityCorrupt:
            return _respond(
                start_response,
                "503 Service Unavailable",
                _auth_error("Service unavailable", "Please try again later.", "/login"),
            )
        except (ValueError, InvalidCredentials):
            return _respond(
                start_response,
                "400 Bad Request",
                _auth_error("Unable to sign in", "Email or password was not accepted.", "/login"),
            )
        return _redirect(
            start_response,
            "/customer",
            cookies=[
                self._cookie(_SESSION_COOKIE, issued.token, max_age=43_200),
                self._clear_cookie(_PREAUTH_COOKIE),
            ],
        )

    def _logout(self, environ, start_response):
        token = _cookie_value(environ, _SESSION_COOKIE)
        try:
            session = self._authentication.authenticate(token)
            fields = self._form(environ, {"csrf_token"})
            if not hmac.compare_digest(fields["csrf_token"], session.csrf_token):
                raise ValueError("CSRF mismatch")
        except AuthenticationAuthorityCorrupt:
            return _respond(
                start_response,
                "503 Service Unavailable",
                _auth_error("Service unavailable", "Please try again later.", "/login"),
                cookies=[self._clear_cookie(_SESSION_COOKIE)],
            )
        except (ValueError, InvalidSession):
            return _respond(
                start_response,
                "400 Bad Request",
                _auth_error("Unable to sign out", "Return to the workspace and retry.", "/customer"),
            )
        self._authentication.logout(token)
        return _redirect(
            start_response,
            "/login",
            cookies=[self._clear_cookie(_SESSION_COOKIE)],
        )

    def _form(self, environ: dict[str, object], expected: set[str]) -> dict[str, str]:
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].lower()
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
            raise ValueError("Invalid authentication request")
        content = stream.read(length)
        if not isinstance(content, bytes) or len(content) != length:
            raise ValueError("Invalid authentication body")
        fields = parse_qs(
            content.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=10,
        )
        if set(fields) != expected or any(len(values) != 1 for values in fields.values()):
            raise ValueError("Invalid authentication fields")
        return {name: values[0] for name, values in fields.items()}

    def _preauth_token(self) -> str:
        nonce = token_urlsafe(24)
        issued_at = int(self._clock().timestamp())
        authority = f"{issued_at}.{nonce}"
        signature = hmac.new(self._secret, authority.encode(), sha256).hexdigest()
        return f"{authority}.{signature}"

    def _verify_preauth(self, environ: dict[str, object], submitted: str) -> None:
        cookie = _cookie_value(environ, _PREAUTH_COOKIE)
        if not cookie or not hmac.compare_digest(cookie, submitted):
            raise ValueError("Pre-authentication CSRF mismatch")
        try:
            issued_text, nonce, signature = cookie.split(".", 2)
            issued_at = int(issued_text)
        except (ValueError, TypeError):
            raise ValueError("Pre-authentication token is malformed") from None
        authority = f"{issued_at}.{nonce}"
        expected = hmac.new(self._secret, authority.encode(), sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Pre-authentication signature mismatch")
        age = int(self._clock().timestamp()) - issued_at
        if not 0 <= age <= 600:
            raise ValueError("Pre-authentication token expired")

    def _cookie(self, name: str, value: str, *, max_age: int) -> str:
        secure = "; Secure" if self._secure_cookies else ""
        return (
            f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; "
            f"SameSite=Strict{secure}"
        )

    def _clear_cookie(self, name: str) -> str:
        secure = "; Secure" if self._secure_cookies else ""
        return (
            f"{name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}"
        )


def _cookie_value(environ: dict[str, object], name: str) -> str:
    header = environ.get("HTTP_COOKIE")
    if not isinstance(header, str) or len(header) > 4_096:
        return ""
    values = []
    for item in header.split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key == name:
            values.append(value)
    if len(values) != 1:
        return ""
    return values[0]


def _auth_page(path: str, csrf: str) -> str:
    signup = path == "/signup"
    title = "Create your ASCOS account" if signup else "Welcome back"
    action = "/signup" if signup else "/login"
    password_confirm = (
        """<label>Confirm password<input type="password" name="confirm_password"
autocomplete="new-password" minlength="12" maxlength="128" required></label>"""
        if signup
        else ""
    )
    switch = (
        'Already have an account? <a href="/login">Sign in</a>'
        if signup
        else 'New to ASCOS? <a href="/signup">Create an account</a>'
    )
    button = "Create account" if signup else "Sign in"
    return _page(
        title,
        f"""<div class="auth-card"><div class="brand"><span>AS</span><strong>ASCOS</strong></div>
<span class="eyebrow">Customer application</span><h1>{title}</h1>
<p>Access your product requests and continue building with ASCOS.</p>
<form method="post" action="{action}"><input type="hidden" name="csrf_token"
value="{escape(csrf)}"><label>Email address<input type="email" name="email"
autocomplete="email" maxlength="254" required></label>
<label>Password<input type="password" name="password"
autocomplete="{'new-password' if signup else 'current-password'}" minlength="12"
maxlength="128" required></label>{password_confirm}<button type="submit">{button}</button></form>
<footer>{switch}</footer></div>""",
    )


def _auth_error(title: str, detail: str, retry: str) -> str:
    return _page(
        title,
        f"""<div class="auth-card"><div class="error">!</div><h1>{escape(title)}</h1>
<p>{escape(detail)}</p><a class="button" href="{escape(retry)}">Try again</a></div>""",
    )


def _page(title: str, content: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{_AUTH_CSS}</style></head><body><main>{content}</main></body></html>"""


def _redirect(start_response, location: str, *, cookies: list[str]) -> Iterable[bytes]:
    return _respond(
        start_response,
        "303 See Other",
        b"",
        extra_headers=[("Location", location)],
        cookies=cookies,
    )


def _respond(
    start_response,
    status: str,
    body: str | bytes,
    *,
    extra_headers: list[tuple[str, str]] | None = None,
    cookies: list[str] | None = None,
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
    headers.extend(("Set-Cookie", value) for value in (cookies or []))
    start_response(status, headers)
    return (content,)


_AUTH_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;color:#15223b;background:#f4f7fb}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 80% 0,#d9e7ff 0,transparent 35%),#f4f7fb}main{min-height:100vh;display:grid;place-items:center;padding:40px}.auth-card{width:min(100%,480px);background:#fff;border:1px solid #dce3ee;border-radius:22px;padding:40px;box-shadow:0 25px 70px #263c6018}.brand{display:flex;align-items:center;gap:10px;margin-bottom:38px;letter-spacing:.08em}.brand span{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#3157d5;color:#fff;font-weight:800}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#3157d5;font-weight:800}h1{font-size:40px;line-height:1.05;letter-spacing:-.04em;margin:12px 0}p{color:#647189;line-height:1.6}form{display:grid;gap:18px;margin-top:30px}label{display:grid;gap:8px;font-weight:700}input{border:1px solid #cbd5e4;border-radius:11px;padding:13px 14px;font:inherit}input:focus{outline:3px solid #dbe4ff;border-color:#3157d5}button,.button{border:0;border-radius:11px;padding:14px 18px;background:#3157d5;color:#fff;text-decoration:none;text-align:center;font:inherit;font-weight:800;cursor:pointer;box-shadow:0 10px 25px #3157d533}footer{margin-top:26px;padding-top:20px;border-top:1px solid #e3e8f0;text-align:center;color:#647189}a{color:#3157d5;font-weight:700}.error{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:#ffe8e8;color:#c23b3b;font-weight:900;margin-bottom:20px}@media(max-width:540px){main{padding:18px}.auth-card{padding:26px}}
"""
