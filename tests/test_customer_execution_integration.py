from __future__ import annotations

from pathlib import Path
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from runtime.customer_execution import CustomerExecutionApplication
from tests.test_customer_execution import _ready
from tests.test_customer_prd_approval import CSRF


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _post(origin: str, path: str, fields: dict[str, str]) -> str:
    content = urlencode(fields).encode("utf-8")
    request = Request(
        f"{origin}{path}",
        data=content,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def test_real_http_dashboard_plans_approves_executes_and_stops_for_review(
    tmp_path: Path,
) -> None:
    service, _, workspace, adapter, _ = _ready(tmp_path)
    routed = CustomerExecutionApplication(service)

    def authenticated(environ, start_response):
        environ["REMOTE_USER"] = "customer-1"
        environ["ascos.csrf_token"] = CSRF
        return routed(environ, start_response)

    server = make_server(
        "127.0.0.1",
        0,
        authenticated,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    path = "/customer/requests/req-1/execution"
    try:
        with urlopen(f"{origin}{path}", timeout=10) as response:
            initial = response.read().decode("utf-8")
        assert "Create governed execution plan" in initial

        planned = _post(origin, f"{path}/plan", {"csrf_token": CSRF})
        plan = service.find("customer-1", "req-1")
        assert plan is not None
        assert "Approve exact execution plan" in planned
        assert plan.scope_digest in planned

        approved = _post(
            origin,
            f"{path}/approve",
            {
                "csrf_token": CSRF,
                "scope_digest": plan.scope_digest,
                "confirm_plan": "yes",
            },
        )
        assert "Start one governed Codex coding turn" in approved
        completed = _post(
            origin,
            f"{path}/execute",
            {
                "csrf_token": CSRF,
                "scope_digest": plan.scope_digest,
                "confirm_scope": "yes",
                "confirm_usage": "yes",
            },
        )
        assert "Durable Codex receipt" in completed
        assert "Human review required" in completed
        assert "ChatGPT plan" in completed
        assert str(workspace) not in completed
        assert len(adapter.calls) == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
