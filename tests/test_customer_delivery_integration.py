from __future__ import annotations

from pathlib import Path
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from runtime.customer_delivery import CustomerDeliveryApplication, CustomerDeliveryStatus
from tests.test_customer_delivery import _module4
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


def test_real_http_dashboard_reviews_and_creates_only_a_draft_delivery(
    tmp_path: Path,
) -> None:
    service, _, workspace, _, gateway, _ = _module4(tmp_path)
    routed = CustomerDeliveryApplication(service)

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
    path = "/customer/requests/req-1/delivery"
    try:
        with urlopen(f"{origin}{path}", timeout=10) as response:
            initial = response.read().decode("utf-8")
        assert "Prepare exact patch review" in initial
        assert str(workspace) not in initial

        prepared = _post(origin, f"{path}/prepare", {"csrf_token": CSRF})
        review = service.find("customer-1", "req-1")
        assert review is not None
        assert "Exact escaped Git patch" in prepared
        assert "ASCOS_CUSTOMER_EXECUTION_READY" in prepared
        assert "Approve exact patch for draft delivery" in prepared
        assert str(workspace) not in prepared

        approved = _post(
            origin,
            f"{path}/approve",
            {
                "csrf_token": CSRF,
                "review_digest": review.review_digest,
                "confirm_review": "yes",
            },
        )
        assert "Create reviewed draft delivery" in approved
        delivered = _post(
            origin,
            f"{path}/deliver",
            {
                "csrf_token": CSRF,
                "review_digest": review.review_digest,
                "confirm_delivery": "yes",
            },
        )
        final = service.find("customer-1", "req-1")
        assert final is not None
        assert final.status is CustomerDeliveryStatus.DRAFT_PR_CREATED
        assert "Durable draft-delivery receipt" in delivered
        assert "Open draft" in delivered and "unmerged" in delivered
        assert "Merge and deployment remain unavailable" in delivered
        assert len(gateway.create_calls) == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
