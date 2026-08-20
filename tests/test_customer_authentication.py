from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlencode

import pytest

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
)
from runtime.customer_authentication import (
    AccountAlreadyExists,
    AuthenticatedCustomerApplication,
    AuthenticationAuthorityCorrupt,
    CustomerAuthenticationService,
    FileCustomerAccountStore,
    FileCustomerSessionStore,
    InvalidCredentials,
    InvalidSession,
    normalize_email,
)


NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
PASSWORD = "SecureFounder123"


def _tokens() -> Callable[[], str]:
    counter = 0

    def next_token() -> str:
        nonlocal counter
        counter += 1
        return f"token-{counter:04d}-" + "x" * 32

    return next_token


def _service(root: Path, clock=lambda: NOW) -> CustomerAuthenticationService:
    return CustomerAuthenticationService(
        FileCustomerAccountStore(root / "accounts"),
        FileCustomerSessionStore(root / "sessions"),
        clock=clock,
        token_factory=_tokens(),
        salt_factory=lambda: bytes.fromhex("00" * 16),
    )


def _application(root: Path, *, secure_cookies: bool = True):
    authentication = _service(root / "authentication")
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(root / "requests"),
        lambda: NOW,
    )
    portal = CustomerPortalApplication(requests)
    return (
        AuthenticatedCustomerApplication(
            authentication,
            portal,
            preauth_secret=b"day-12-test-preauth-secret-32-bytes-minimum",
            secure_cookies=secure_cookies,
            clock=lambda: NOW,
        ),
        authentication,
        requests,
    )


def _call(application, method="GET", path="/customer", body="", cookie=""):
    encoded = body.encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "CONTENT_LENGTH": str(len(encoded)),
        "wsgi.input": BytesIO(encoded),
    }
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    observed = {}

    def start_response(status, headers):
        observed["status"] = status
        observed["headers"] = headers

    content = b"".join(application(environ, start_response))
    return observed["status"], observed["headers"], content


def _header(headers, name):
    return [value for key, value in headers if key.lower() == name.lower()]


def _value(content: bytes, name: str) -> str:
    match = re.search(
        rf'name="{re.escape(name)}"\s+value="([^"]+)"'.encode(),
        content,
    )
    assert match is not None
    return match.group(1).decode()


def _cookie(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0]


def _signup(application, email="founder@example.com", password=PASSWORD):
    status, headers, content = _call(application, path="/signup")
    assert status == "200 OK"
    preauth = _cookie(_header(headers, "Set-Cookie")[0])
    csrf = _value(content, "csrf_token")
    status, headers, content = _call(
        application,
        method="POST",
        path="/signup",
        cookie=preauth,
        body=urlencode(
            {
                "csrf_token": csrf,
                "email": email,
                "password": password,
                "confirm_password": password,
            }
        ),
    )
    return status, headers, content


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Founder@Example.COM", "founder@example.com"),
        (" product.owner+pilot@sub.example.com ", "product.owner+pilot@sub.example.com"),
    ],
)
def test_email_normalization_is_explicit_and_ascii(value, expected):
    assert normalize_email(value) == expected


@pytest.mark.parametrize(
    "value",
    ["missing-at.example.com", "a@localhost", ".a@example.com", "a@-example.com", "ü@example.com"],
)
def test_invalid_customer_emails_fail_closed(value):
    with pytest.raises(ValueError):
        normalize_email(value)


def test_registration_persists_only_scrypt_digest_and_session_token_digest(tmp_path):
    service = _service(tmp_path)

    issued = service.register("Founder@Example.com", PASSWORD)

    persisted = b"".join(path.read_bytes() for path in tmp_path.rglob("*.*"))
    assert PASSWORD.encode() not in persisted
    assert issued.token.encode() not in persisted
    assert issued.session.token_digest.encode() in persisted
    account = FileCustomerAccountStore(tmp_path / "accounts").load("founder@example.com")
    assert account.password_salt == "00" * 16
    assert len(account.password_digest) == 64
    assert service.authenticate(issued.token).customer_id == account.customer_id


def test_duplicate_registration_and_bad_login_are_generic(tmp_path):
    service = _service(tmp_path)
    service.register("founder@example.com", PASSWORD)

    with pytest.raises(AccountAlreadyExists):
        service.register("FOUNDER@example.com", PASSWORD)
    with pytest.raises(InvalidCredentials, match="Invalid email or password"):
        service.login("founder@example.com", "WrongPassword123")
    with pytest.raises(InvalidCredentials, match="Invalid email or password"):
        service.login("unknown@example.com", "WrongPassword123")


@pytest.mark.parametrize(
    "password",
    ["Short1A", "alllowercase123", "ALLUPPERCASE123", "NoDigitsAllowed"],
)
def test_registration_enforces_password_policy(tmp_path, password):
    with pytest.raises(ValueError):
        _service(tmp_path).register("founder@example.com", password)


def test_login_issues_new_restart_safe_session_and_logout_is_durable(tmp_path):
    service = _service(tmp_path)
    registered = service.register("founder@example.com", PASSWORD)
    logged_in = service.login("FOUNDER@EXAMPLE.COM", PASSWORD)
    assert logged_in.token != registered.token
    assert logged_in.session.customer_id == registered.session.customer_id

    restarted = CustomerAuthenticationService(
        FileCustomerAccountStore(tmp_path / "accounts"),
        FileCustomerSessionStore(tmp_path / "sessions"),
        clock=lambda: NOW,
        token_factory=_tokens(),
    )
    assert restarted.authenticate(logged_in.token) == logged_in.session
    restarted.logout(logged_in.token)
    restarted.logout(logged_in.token)
    with pytest.raises(InvalidSession):
        restarted.authenticate(logged_in.token)


def test_expired_session_is_rejected_and_revoked(tmp_path):
    now = NOW
    service = _service(tmp_path, clock=lambda: now)
    issued = service.register("founder@example.com", PASSWORD)
    now += timedelta(hours=13)

    with pytest.raises(InvalidSession, match="expired"):
        service.authenticate(issued.token)
    with pytest.raises(InvalidSession):
        service.authenticate(issued.token)


def test_tampered_and_symlinked_authority_fail_closed(tmp_path):
    service = _service(tmp_path)
    service.register("founder@example.com", PASSWORD)
    account_path = next((tmp_path / "accounts").rglob("*.json"))
    envelope = json.loads(account_path.read_text())
    envelope["record"]["email"] = "attacker@example.com"
    account_path.write_text(json.dumps(envelope))
    with pytest.raises(AuthenticationAuthorityCorrupt):
        FileCustomerAccountStore(tmp_path / "accounts").load("founder@example.com")

    root = tmp_path / "unsafe"
    (root / "accounts").mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    name = __import__("hashlib").sha256(b"founder@example.com").hexdigest()
    (root / "accounts" / f"{name}.json").symlink_to(outside)
    with pytest.raises(AuthenticationAuthorityCorrupt):
        FileCustomerAccountStore(root).load("founder@example.com")


def test_tampered_revocation_authority_fails_closed(tmp_path):
    service = _service(tmp_path)
    issued = service.register("founder@example.com", PASSWORD)
    service.logout(issued.token)
    marker = next((tmp_path / "sessions").rglob("*.revoked"))
    envelope = json.loads(marker.read_text())
    envelope["record"]["revoked_at"] = "not-a-time"
    marker.write_text(json.dumps(envelope))

    with pytest.raises(AuthenticationAuthorityCorrupt):
        FileCustomerSessionStore(tmp_path / "sessions").load(issued.session.token_digest)


def test_signed_preauthentication_authority_expires_server_side(tmp_path):
    now = NOW
    application, _, _ = _application(tmp_path)
    application._clock = lambda: now
    status, headers, content = _call(application, path="/signup")
    assert status == "200 OK"
    preauth = _cookie(_header(headers, "Set-Cookie")[0])
    now += timedelta(seconds=601)

    status, _, _ = _call(
        application,
        method="POST",
        path="/signup",
        cookie=preauth,
        body=urlencode(
            {
                "csrf_token": _value(content, "csrf_token"),
                "email": "founder@example.com",
                "password": PASSWORD,
                "confirm_password": PASSWORD,
            }
        ),
    )
    assert status == "400 Bad Request"


def test_web_signup_cookie_workspace_logout_and_revocation(tmp_path):
    application, authentication, _ = _application(tmp_path)

    status, headers, _ = _signup(application)
    assert status == "303 See Other"
    assert _header(headers, "Location") == ["/customer"]
    cookies = _header(headers, "Set-Cookie")
    session_cookie = _cookie(next(item for item in cookies if item.startswith("ascos_session=")))
    assert all("HttpOnly" in item and "SameSite=Strict" in item and "Secure" in item for item in cookies)

    status, headers, content = _call(application, cookie=session_cookie)
    assert status == "200 OK"
    assert b"Build your next product with ASCOS" in content
    assert b"Sign out" in content
    assert _header(headers, "Cache-Control") == ["no-store"]
    logout_csrf = _value(content, "csrf_token")

    raw_token = session_cookie.partition("=")[2]
    status, headers, _ = _call(
        application,
        method="POST",
        path="/logout",
        cookie=session_cookie,
        body=urlencode({"csrf_token": logout_csrf}),
    )
    assert status == "303 See Other"
    assert _header(headers, "Location") == ["/login"]
    with pytest.raises(InvalidSession):
        authentication.authenticate(raw_token)
    status, headers, _ = _call(application, cookie=session_cookie)
    assert status == "303 See Other"
    assert _header(headers, "Location") == ["/login"]


def test_web_login_recovers_existing_customer_requests(tmp_path):
    application, _, requests = _application(tmp_path, secure_cookies=False)
    status, headers, _ = _signup(application)
    session_cookie = _cookie(
        next(item for item in _header(headers, "Set-Cookie") if item.startswith("ascos_session="))
    )
    status, _, content = _call(application, cookie=session_cookie)
    csrf = _value(content, "csrf_token")
    status, headers, _ = _call(
        application,
        method="POST",
        path="/customer/requests",
        cookie=session_cookie,
        body=urlencode(
            {
                "csrf_token": csrf,
                "request_id": "req-returning-customer",
                "product_name": "AI clinic receptionist",
                "product_summary": "Answer calls and book appointments.",
                "target_users": "Clinic teams",
                "features": "Answer calls\nBook appointments",
                "constraints": "No medical advice",
            }
        ),
    )
    assert status == "303 See Other"
    customer_id = requests.dashboard(next(path.name for path in (tmp_path / "requests").iterdir()))
    assert len(customer_id) == 1

    status, headers, content = _call(application, path="/login")
    preauth = _cookie(_header(headers, "Set-Cookie")[0])
    status, headers, _ = _call(
        application,
        method="POST",
        path="/login",
        cookie=preauth,
        body=urlencode(
            {
                "csrf_token": _value(content, "csrf_token"),
                "email": "FOUNDER@EXAMPLE.COM",
                "password": PASSWORD,
            }
        ),
    )
    assert status == "303 See Other"
    returning_cookie = _cookie(
        next(item for item in _header(headers, "Set-Cookie") if item.startswith("ascos_session="))
    )
    status, _, content = _call(application, cookie=returning_cookie)
    assert status == "200 OK"
    assert b"AI clinic receptionist" in content


def test_authentication_forms_reject_csrf_and_do_not_leak_account_state(tmp_path):
    application, _, _ = _application(tmp_path)
    status, _, content = _call(
        application,
        method="POST",
        path="/signup",
        body=urlencode(
            {
                "csrf_token": "invented",
                "email": "founder@example.com",
                "password": PASSWORD,
                "confirm_password": PASSWORD,
            }
        ),
    )
    assert status == "400 Bad Request"
    assert b"Check the form and try again" in content

    status, headers, content = _call(application, path="/login")
    preauth = _cookie(_header(headers, "Set-Cookie")[0])
    status, _, failure = _call(
        application,
        method="POST",
        path="/login",
        cookie=preauth,
        body=urlencode(
            {
                "csrf_token": _value(content, "csrf_token"),
                "email": "unknown@example.com",
                "password": "WrongPassword123",
            }
        ),
    )
    assert status == "400 Bad Request"
    assert b"Email or password was not accepted" in failure
    assert b"unknown@example.com" not in failure
