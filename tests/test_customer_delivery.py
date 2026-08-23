from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.coding_providers import ProviderOperationStore
from runtime.customer_application import ProductRequestNotFound
from runtime.customer_delivery import (
    ControlledCustomerDeliveryAdapter,
    CustomerDeliveryApplication,
    CustomerDeliveryConfiguration,
    CustomerDeliveryConflict,
    CustomerDeliveryCorrupt,
    CustomerDeliveryPolicyError,
    CustomerDeliveryReconciliationRequired,
    CustomerDeliveryService,
    CustomerDeliveryStatus,
    DraftPullRequest,
    FileCustomerDeliveryStore,
)
from tests.test_customer_execution import _git, _ready
from tests.test_customer_prd_approval import CSRF, NOW, _call


class _Gateway:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.pull_requests: list[DraftPullRequest] = []
        self.create_calls: list[tuple[str, str, str, str, str]] = []
        self.fail_create = fail_create

    def list_for_head(self, repository, base, head):
        return tuple(
            value
            for value in self.pull_requests
            if value.repository_full_name == repository
            and value.base_branch == base
            and value.head_branch == head
        )

    def create_draft(self, repository, base, head, title, body):
        self.create_calls.append((repository, base, head, title, body))
        if self.fail_create:
            raise RuntimeError("draft PR gateway failed after push")
        value = DraftPullRequest(
            len(self.pull_requests) + 1,
            f"https://github.com/{repository}/pull/{len(self.pull_requests) + 1}",
            repository,
            base,
            head,
            title,
            True,
            "OPEN",
        )
        self.pull_requests.append(value)
        return value


def _module4(root: Path, *, enabled: bool = True, gateway: _Gateway | None = None):
    executions, _, workspace, _, _ = _ready(root, real_adapter=True)
    plan = executions.plan("customer-1", "req-1")
    plan = executions.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )
    plan = executions.execute_next(
        "customer-1",
        "req-1",
        expected_scope_digest=plan.scope_digest,
        confirm_scope=True,
        confirm_usage_consumption=True,
    )
    remote = root / "product-remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare")
    _git(workspace, "remote", "add", "origin", str(remote.resolve()))
    configuration = CustomerDeliveryConfiguration(
        workspace,
        "example/product",
        "main",
        enabled=enabled,
        product_write_confirmed=enabled,
    )
    selected_gateway = gateway or _Gateway()
    adapter = ControlledCustomerDeliveryAdapter(
        configuration,
        selected_gateway,
        expected_remote_url=str(remote.resolve()),
    )
    store = FileCustomerDeliveryStore(root / "delivery" / "reviews")
    service = CustomerDeliveryService(
        store,
        executions,
        ProviderOperationStore(root / "execution" / "provider-state"),
        configuration,
        adapter,
        lambda: NOW,
    )
    return service, store, workspace, remote, selected_gateway, plan


def test_prepare_binds_exact_module3_patch_without_repository_write(tmp_path):
    service, store, workspace, remote, gateway, plan = _module4(tmp_path)
    before = _git(workspace, "rev-parse", "HEAD").strip()
    review = service.prepare("customer-1", "req-1")

    assert review.status is CustomerDeliveryStatus.AWAITING_REVIEW
    assert review.execution_plan_digest == plan.digest
    assert review.execution_scope_digest == plan.scope_digest
    assert review.repository_full_name == "example/product"
    assert review.base_branch == "main"
    assert tuple(value.path for value in review.reviewed_files) == ("src/feature.py",)
    assert review.patch_manifest_digest == plan.tasks[0].manifest_digest
    assert len(review.git_diff_digest) == 64
    assert "No merge" not in review.pull_request_body
    assert "did not approve" in review.pull_request_body
    assert _git(workspace, "rev-parse", "HEAD").strip() == before
    assert _git(workspace, "status", "--porcelain").strip()
    assert _git(remote, "for-each-ref", "--format=%(refname)").strip() == ""
    assert gateway.create_calls == []
    assert store.load("customer-1", "req-1") == review


def test_review_requires_exact_digest_and_detects_patch_drift(tmp_path):
    service, _, workspace, _, _, _ = _module4(tmp_path)
    review = service.prepare("customer-1", "req-1")
    with pytest.raises(CustomerDeliveryConflict, match="stale"):
        service.approve(
            "customer-1",
            "req-1",
            expected_review_digest="0" * 64,
            confirm_review=True,
        )
    (workspace / "src" / "feature.py").write_text("TAMPERED = True\n", encoding="utf-8")
    with pytest.raises(CustomerDeliveryPolicyError, match="content changed"):
        service.approve(
            "customer-1",
            "req-1",
            expected_review_digest=review.review_digest,
            confirm_review=True,
        )


def test_approved_patch_creates_one_commit_push_and_open_draft_pr(tmp_path):
    service, store, workspace, remote, gateway, plan = _module4(tmp_path)
    review = service.prepare("customer-1", "req-1")
    approved = service.approve(
        "customer-1",
        "req-1",
        expected_review_digest=review.review_digest,
        confirm_review=True,
    )
    delivered = service.deliver(
        "customer-1",
        "req-1",
        expected_review_digest=approved.review_digest,
        confirm_repository_write=True,
    )

    assert delivered.status is CustomerDeliveryStatus.DRAFT_PR_CREATED
    assert delivered.reviewed_by == "customer-1"
    assert delivered.pull_request_number == 1
    assert delivered.pull_request_url == "https://github.com/example/product/pull/1"
    assert _git(workspace, "rev-parse", "HEAD^").strip() == plan.workspace_commit
    assert _git(workspace, "rev-parse", "HEAD").strip() == delivered.commit_sha
    assert _git(workspace, "rev-parse", "HEAD^{tree}").strip() == delivered.tree_sha
    assert _git(workspace, "status", "--porcelain").strip() == ""
    remote_sha = _git(
        remote, "rev-parse", "refs/heads/agent/customer-product"
    ).strip()
    assert remote_sha == delivered.commit_sha
    assert len(gateway.create_calls) == 1
    assert gateway.pull_requests[0].draft and gateway.pull_requests[0].state == "OPEN"
    assert store.load("customer-1", "req-1") == delivered

    repeated = service.deliver(
        "customer-1",
        "req-1",
        expected_review_digest=delivered.review_digest,
        confirm_repository_write=True,
    )
    assert repeated == delivered
    assert len(gateway.create_calls) == 1


def test_delivery_preflight_stops_duplicate_remote_before_local_mutation(tmp_path):
    service, store, workspace, remote, _, plan = _module4(tmp_path)
    review = service.prepare("customer-1", "req-1")
    approved = service.approve(
        "customer-1",
        "req-1",
        expected_review_digest=review.review_digest,
        confirm_review=True,
    )
    _git(
        workspace,
        "push",
        "origin",
        f"{plan.workspace_commit}:refs/heads/agent/customer-product",
    )

    with pytest.raises(CustomerDeliveryConflict, match="already exists"):
        service.deliver(
            "customer-1",
            "req-1",
            expected_review_digest=approved.review_digest,
            confirm_repository_write=True,
        )
    assert _git(workspace, "rev-parse", "HEAD").strip() == plan.workspace_commit
    assert _git(workspace, "status", "--porcelain").strip()
    assert store.load("customer-1", "req-1").status is CustomerDeliveryStatus.REVIEW_APPROVED


def test_post_push_failure_is_reconciliation_required_and_never_retried(tmp_path):
    gateway = _Gateway(fail_create=True)
    service, store, workspace, remote, _, _ = _module4(tmp_path, gateway=gateway)
    review = service.prepare("customer-1", "req-1")
    approved = service.approve(
        "customer-1",
        "req-1",
        expected_review_digest=review.review_digest,
        confirm_review=True,
    )
    with pytest.raises(CustomerDeliveryReconciliationRequired):
        service.deliver(
            "customer-1",
            "req-1",
            expected_review_digest=approved.review_digest,
            confirm_repository_write=True,
        )
    failed = store.load("customer-1", "req-1")
    assert failed.status is CustomerDeliveryStatus.RECONCILIATION_REQUIRED
    assert failed.failure_classification == "RuntimeError"
    assert _git(workspace, "status", "--porcelain").strip() == ""
    assert _git(remote, "rev-parse", "refs/heads/agent/customer-product").strip()
    with pytest.raises(CustomerDeliveryConflict, match="not approved"):
        service.deliver(
            "customer-1",
            "req-1",
            expected_review_digest=failed.review_digest,
            confirm_repository_write=True,
        )
    assert len(gateway.create_calls) == 1


def test_delivery_is_customer_scoped_and_store_detects_tamper(tmp_path):
    service, store, _, _, _, _ = _module4(tmp_path)
    review = service.prepare("customer-1", "req-1")
    with pytest.raises(ProductRequestNotFound):
        service.find("customer-2", "req-1")
    path = next((tmp_path / "delivery" / "reviews").rglob("delivery-review-v1.json"))
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["record"]["repository_full_name"] = "attacker/product"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(CustomerDeliveryCorrupt, match="corrupt"):
        store.load(review.customer_id, review.request_id)


def test_delivery_store_is_private_and_closed(tmp_path):
    service, store, _, _, _, _ = _module4(tmp_path)
    service.prepare("customer-1", "req-1")
    path = next((tmp_path / "delivery" / "reviews").rglob("delivery-review-v1.json"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CustomerDeliveryCorrupt, match="not closed"):
        store.load("customer-1", "req-1")


def test_dashboard_shows_escaped_patch_and_accepts_no_operator_inputs(tmp_path):
    service, _, workspace, _, gateway, _ = _module4(tmp_path)
    application = CustomerDeliveryApplication(service)
    path = "/customer/requests/req-1/delivery"
    status, headers, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Prepare exact patch review" in content
    assert b'name="repository"' not in content
    assert b'name="branch"' not in content
    assert b'name="token"' not in content
    assert str(workspace).encode() not in content
    assert headers["Cache-Control"] == "no-store"

    assert _call(
        application,
        path=f"{path}/prepare",
        method="POST",
        body=urlencode({"csrf_token": CSRF}),
    )[0] == "303 See Other"
    review = service.find("customer-1", "req-1")
    assert review is not None
    status, _, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Exact escaped Git patch" in content
    assert b"ASCOS_CUSTOMER_EXECUTION_READY" in content
    assert b"Approve exact patch for draft delivery" in content
    assert review.review_digest.encode() in content
    assert str(workspace).encode() not in content

    assert _call(
        application,
        path=f"{path}/approve",
        method="POST",
        body=urlencode(
            {
                "csrf_token": CSRF,
                "review_digest": review.review_digest,
                "confirm_review": "yes",
            }
        ),
    )[0] == "303 See Other"
    approved = service.find("customer-1", "req-1")
    assert approved is not None
    assert _call(
        application,
        path=f"{path}/deliver",
        method="POST",
        body=urlencode(
            {
                "csrf_token": CSRF,
                "review_digest": approved.review_digest,
                "confirm_delivery": "yes",
            }
        ),
    )[0] == "303 See Other"
    status, _, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Durable draft-delivery receipt" in content
    assert b"Open draft" in content and b"unmerged" in content
    assert len(gateway.create_calls) == 1
