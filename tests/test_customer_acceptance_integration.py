from __future__ import annotations

from pathlib import Path
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from runtime.customer_acceptance import CustomerAcceptanceApplication, CustomerAcceptanceStatus
from tests.test_customer_acceptance import _module5
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


def test_real_http_dashboard_approves_preview_and_publishes_browser_evidence(
    tmp_path: Path,
) -> None:
    service, _, _, evidence, adapter, delivery, _ = _module5(tmp_path)
    routed = CustomerAcceptanceApplication(service)

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
    path = "/customer/requests/req-1/acceptance"
    try:
        with urlopen(f"{origin}{path}", timeout=10) as response:
            initial = response.read().decode("utf-8")
        assert "Prepare exact preview acceptance" in initial

        prepared = _post(origin, f"{path}/prepare", {"csrf_token": CSRF})
        record = service.find("customer-1", "req-1")
        assert record is not None
        assert (delivery.commit_sha or "")[:12] in prepared
        assert "Approve exact preview acceptance" in prepared

        approved_page = _post(
            origin,
            f"{path}/approve",
            {
                "csrf_token": CSRF,
                "approval_digest": record.approval_digest,
                "confirm_scope": "yes",
            },
        )
        assert "Deploy preview and run acceptance" in approved_page
        approved = service.find("customer-1", "req-1")
        assert approved is not None

        final_page = _post(
            origin,
            f"{path}/execute",
            {
                "csrf_token": CSRF,
                "approval_digest": approved.approval_digest,
                "confirm_preview": "yes",
                "confirm_browser": "yes",
            },
        )
        final = service.find("customer-1", "req-1")
        assert final is not None
        assert final.status is CustomerAcceptanceStatus.EVIDENCE_READY
        assert "Durable preview acceptance receipt" in final_page
        assert "Review preview evidence" in final_page
        assert adapter.execute_count == 1
        assert len(evidence.calls) == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
