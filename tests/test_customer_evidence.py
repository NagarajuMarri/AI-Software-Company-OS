from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.customer_application import CustomerPortalApplication, ProductRequestNotFound
from runtime.customer_estimate import CustomerDeliveryEstimateApplication
from runtime.customer_evidence import (
    PACKAGE_STATUS,
    REQUIRED_EVIDENCE_KINDS,
    REVIEW_CONFIRMATION_VERSION,
    CustomerEvidenceConflict,
    CustomerEvidenceCorrupt,
    CustomerPreviewEvidenceApplication,
    CustomerPreviewEvidenceService,
    FileCustomerPreviewEvidenceStore,
    package_id_for,
    preview_origin,
    review_id_for,
)
from runtime.customer_prd import CustomerPrdApplication, CustomerPrdApprovalApplication
from runtime.customer_progress import (
    CustomerProjectProgressApplication,
    CustomerProjectProgressService,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
)
from runtime.runtime_acceptance import EvidenceArtifact, EvidenceKind, EvidenceOutcome
from tests.test_customer_estimate import _generate, _services
from tests.test_customer_prd_approval import CSRF, NOW, _call


COMMIT_SHA = "a" * 40
PREVIEW_ORIGIN = "https://preview.example.test"
PREVIEW_URL = f"{PREVIEW_ORIGIN}/product"


def _artifacts(
    *,
    commit_sha: str = COMMIT_SHA,
    failed_kind: EvidenceKind | None = None,
) -> tuple[EvidenceArtifact, ...]:
    return tuple(
        EvidenceArtifact(
            f"day21-evidence-{index}",
            "day21-fixture-run",
            "CUSTOMER_PREVIEW",
            "customer.preview.review",
            kind,
            EvidenceOutcome.FAIL if kind is failed_kind else EvidenceOutcome.PASS,
            commit_sha,
            f"artifact://day21/{kind.value.lower()}",
            f"{index + 1:064x}",
            NOW,
            f"{kind.value.replace('_EVIDENCE', '').replace('_', ' ').title()} passed",
            (("fixture", "not-an-official-pilot"),),
        )
        for index, kind in enumerate(REQUIRED_EVIDENCE_KINDS)
    )


def _ready(
    root: Path,
    *,
    publish: bool = True,
    failed_kind: EvidenceKind | None = None,
):
    values = _services(root)
    _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    store = FileCustomerPreviewEvidenceStore(root / "customer-evidence")
    service = CustomerPreviewEvidenceService(
        store,
        progress,
        (PREVIEW_ORIGIN,),
        lambda: NOW,
    )
    package = None
    if publish:
        package = service.publish(
            customer_id="customer-1",
            request_id="req-1",
            preview_label="Browser verification fixture",
            preview_url=PREVIEW_URL,
            commit_sha=COMMIT_SHA,
            evidence=_artifacts(failed_kind=failed_kind),
        )
    return values, progress, store, service, package


def _application(root: Path, *, publish: bool = True, failed_kind=None):
    values, progress, _, service, package = _ready(
        root,
        publish=publish,
        failed_kind=failed_kind,
    )
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(values[12], values[15]),
        CustomerRoadmapApprovalApplication(values[15]),
        CustomerDeliveryEstimateApplication(values[18]),
        CustomerProjectProgressApplication(progress),
        CustomerPreviewEvidenceApplication(service),
    )
    return application, progress, service, package


def _review_form(package, **changes) -> str:
    values = {
        "csrf_token": CSRF,
        "expected_package_digest": package.digest,
        "decision": "ACCEPT",
        "comments": "",
        "confirmation": "REVIEWED",
    }
    values.update(changes)
    return urlencode(values)


def test_preview_evidence_identities_and_origin_policy_are_stable_and_safe():
    assert package_id_for("req-1") == package_id_for("req-1")
    assert review_id_for("req-1") == review_id_for("req-1")
    assert package_id_for("req-1") != package_id_for("req-2")
    assert preview_origin(PREVIEW_URL) == PREVIEW_ORIGIN
    assert preview_origin("http://127.0.0.1:9000/preview") == "http://127.0.0.1:9000"
    for unsafe in (
        "http://example.test/product",
        "https://user:secret@example.test/product",
        "https://example.test/product?token=secret",
        "file:///tmp/product",
    ):
        with pytest.raises(ValueError):
            preview_origin(unsafe)
    with pytest.raises(ValueError):
        package_id_for("../unsafe")


def test_package_binds_exact_project_commit_and_required_evidence(tmp_path):
    _, progress, _, _, package = _ready(tmp_path)
    assert package is not None
    snapshot = progress.view("customer-1", "req-1")

    assert package.status == PACKAGE_STATUS
    assert package.product_id == snapshot.product_id
    assert package.progress_id == snapshot.progress_id
    assert package.progress_digest == snapshot.digest
    assert package.roadmap_digest == snapshot.roadmap_digest
    assert package.estimate_digest == snapshot.estimate_digest
    assert package.commit_sha == COMMIT_SHA
    assert package.all_required_evidence_passed
    assert {item.kind for item in package.evidence} == set(REQUIRED_EVIDENCE_KINDS)
    assert not hasattr(package, "repository")
    assert not hasattr(package, "deployment")
    assert not hasattr(package, "release")

    with pytest.raises(ValueError, match="incomplete"):
        replace(package, evidence=package.evidence[:-1])
    with pytest.raises(ValueError, match="another commit"):
        replace(package, evidence=_artifacts(commit_sha="b" * 40))


def test_package_is_write_once_restart_safe_and_exact_retry_idempotent(tmp_path):
    values, progress, store, service, package = _ready(tmp_path)
    assert package is not None
    retry = service.publish(
        customer_id="customer-1",
        request_id="req-1",
        preview_label=package.preview_label,
        preview_url=package.preview_url,
        commit_sha=package.commit_sha,
        evidence=package.evidence,
    )
    restarted = CustomerPreviewEvidenceService(
        FileCustomerPreviewEvidenceStore(tmp_path / "customer-evidence"),
        CustomerProjectProgressService(values[18]),
        (PREVIEW_ORIGIN,),
        lambda: NOW + timedelta(days=1),
    )

    assert retry == package
    assert restarted.context("customer-1", "req-1")[1] == package
    assert store.load_package("customer-1", "req-1") == package
    path = next((tmp_path / "customer-evidence").rglob("preview-evidence-v0.1.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert progress.view("customer-1", "req-1").progress_percentage == 0
    with pytest.raises(CustomerEvidenceConflict, match="different"):
        service.publish(
            customer_id="customer-1",
            request_id="req-1",
            preview_label="Changed fixture",
            preview_url=PREVIEW_URL,
            commit_sha=COMMIT_SHA,
            evidence=_artifacts(),
        )


def test_package_requires_allowlisted_origin_and_customer_scope(tmp_path):
    values, progress, _, service, _ = _ready(tmp_path, publish=False)
    with pytest.raises(CustomerEvidenceConflict, match="origin"):
        service.publish(
            customer_id="customer-1",
            request_id="req-1",
            preview_label="Untrusted preview",
            preview_url="https://untrusted.example.test/product",
            commit_sha=COMMIT_SHA,
            evidence=_artifacts(),
        )
    with pytest.raises(ProductRequestNotFound):
        service.publish(
            customer_id="customer-2",
            request_id="req-1",
            preview_label="Cross-tenant preview",
            preview_url=PREVIEW_URL,
            commit_sha=COMMIT_SHA,
            evidence=_artifacts(),
        )
    assert service.context("customer-1", "req-1")[1:] == (None, None)
    assert progress.view("customer-1", "req-1").digest
    assert values[18]


def test_accept_is_exact_immutable_and_has_no_execution_side_effect(tmp_path):
    _, progress, store, service, package = _ready(tmp_path)
    assert package is not None
    before = progress.view("customer-1", "req-1")
    review = service.review(
        customer_id="customer-1",
        request_id="req-1",
        expected_package_digest=package.digest,
        decision="ACCEPT",
        comments="Evidence reviewed",
        confirmed=True,
    )
    retry = service.review(
        customer_id="customer-1",
        request_id="req-1",
        expected_package_digest=package.digest,
        decision="ACCEPT",
        comments="Evidence reviewed",
        confirmed=True,
    )

    assert retry == review
    assert review.decision == "ACCEPT"
    assert review.package_digest == package.digest
    assert review.progress_digest == before.digest
    assert review.confirmation_version == REVIEW_CONFIRMATION_VERSION
    assert store.load_review("customer-1", "req-1") == review
    assert progress.view("customer-1", "req-1") == before
    assert before.progress_percentage == 0
    assert before.assigned_agent_ids == ()
    assert not hasattr(review, "merge")
    assert not hasattr(review, "release")
    with pytest.raises(CustomerEvidenceConflict, match="unconfirmed"):
        service.review(
            customer_id="customer-1",
            request_id="req-1",
            expected_package_digest=package.digest,
            decision="ACCEPT",
            comments="Evidence reviewed",
            confirmed=False,
        )
    with pytest.raises(CustomerEvidenceConflict, match="already"):
        service.review(
            customer_id="customer-1",
            request_id="req-1",
            expected_package_digest=package.digest,
            decision="REVISE",
            comments="Change it",
            confirmed=True,
        )


def test_revision_requires_comments_and_failed_evidence_cannot_be_accepted(tmp_path):
    _, _, _, service, package = _ready(
        tmp_path,
        failed_kind=EvidenceKind.SECURITY,
    )
    assert package is not None
    assert not package.all_required_evidence_passed
    with pytest.raises(CustomerEvidenceConflict, match="cannot be accepted"):
        service.review(
            customer_id="customer-1",
            request_id="req-1",
            expected_package_digest=package.digest,
            decision="ACCEPT",
            comments="",
            confirmed=True,
        )
    with pytest.raises(CustomerEvidenceConflict, match="invalid"):
        service.review(
            customer_id="customer-1",
            request_id="req-1",
            expected_package_digest=package.digest,
            decision="REVISE",
            comments="",
            confirmed=True,
        )
    review = service.review(
        customer_id="customer-1",
        request_id="req-1",
        expected_package_digest=package.digest,
        decision="REVISE",
        comments="Resolve the security failure and retest.",
        confirmed=True,
    )
    assert review.decision == "REVISE"


@pytest.mark.parametrize(
    ("expected_digest", "confirmed"),
    [("0" * 64, True), (COMMIT_SHA, False)],
)
def test_review_rejects_stale_or_unconfirmed_authority(
    tmp_path,
    expected_digest,
    confirmed,
):
    _, _, _, service, _ = _ready(tmp_path)
    with pytest.raises(CustomerEvidenceConflict, match="stale or unconfirmed"):
        service.review(
            customer_id="customer-1",
            request_id="req-1",
            expected_package_digest=expected_digest,
            decision="ACCEPT",
            comments="",
            confirmed=confirmed,
        )


def test_store_fails_closed_on_tamper_unknown_entries_and_symlinks(tmp_path):
    _, _, store, _, _ = _ready(tmp_path)
    path = next((tmp_path / "customer-evidence").rglob("preview-evidence-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["commit_sha"] = "b" * 40
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerEvidenceCorrupt):
        store.load_package("customer-1", "req-1")

    path.write_text("{}")
    unknown = path.parent / "unknown.txt"
    unknown.write_text("unsafe")
    with pytest.raises(CustomerEvidenceCorrupt, match="closed"):
        store.find_package("customer-1", "req-1")
    unknown.unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerEvidenceCorrupt, match="unsafe"):
        store.find_package("customer-1", "req-1")


def test_centre_is_customer_scoped_hardened_and_opens_exact_preview(tmp_path):
    application, _, _, package = _application(tmp_path)
    assert package is not None
    path = "/customer/requests/req-1/evidence"
    status, headers, content = _call(application, path=path)

    assert status == "200 OK"
    assert b"Preview and Evidence Centre" in content
    assert b"Open product preview" in content
    assert b"6/6" in content
    assert package.digest.encode() in content
    assert package.commit_sha.encode() in content
    assert b"ACCEPT" in content and b"REVISE" in content
    assert b"artifact://day21/automated_test_evidence" in content
    assert b"no delivery side effect" in content
    assert b"start Day 22" in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]
    assert _call(application, path=path, customer=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, customer="customer-2")[0] == "404 Not Found"
    post = _call(application, path=path, method="POST")
    assert post[0] == "405 Method Not Allowed" and post[1]["Allow"] == "GET"

    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/evidence/preview",
    )
    assert status == "303 See Other"
    assert headers["Location"] == PREVIEW_URL


def test_centre_pending_state_and_progress_navigation_are_safe(tmp_path):
    application, _, _, _ = _application(tmp_path, publish=False)
    evidence = _call(application, path="/customer/requests/req-1/evidence")
    progress = _call(application, path="/customer/requests/req-1/progress")
    preview = _call(
        application,
        path="/customer/requests/req-1/evidence/preview",
    )
    assert evidence[0] == "200 OK"
    assert b"Preview evidence is pending" in evidence[2]
    assert b"No preview creation or deployment authority" in evidence[2]
    assert b"Open preview and evidence centre" in progress[2]
    assert preview[0] == "303 See Other"
    assert preview[1]["Location"].endswith("/evidence")


def test_web_records_exact_accept_and_rejects_bad_csrf_or_fields(tmp_path):
    application, progress, service, package = _application(tmp_path)
    assert package is not None
    path = "/customer/requests/req-1/evidence/review"
    bad = _call(
        application,
        method="POST",
        path=path,
        body=_review_form(package, csrf_token="wrong"),
    )
    assert bad[0] == "400 Bad Request"
    stale = _call(
        application,
        method="POST",
        path=path,
        body=_review_form(package, expected_package_digest="0" * 64),
    )
    assert stale[0] == "409 Conflict"
    accepted = _call(
        application,
        method="POST",
        path=path,
        body=_review_form(package),
    )
    assert accepted[0] == "303 See Other"
    assert accepted[1]["Location"].endswith("/evidence")
    snapshot, reopened, review = service.context("customer-1", "req-1")
    assert reopened == package
    assert review is not None and review.decision == "ACCEPT"
    assert snapshot == progress.view("customer-1", "req-1")
    page = _call(application, path="/customer/requests/req-1/evidence")
    assert b"Immutable customer decision" in page[2]
    assert review.digest.encode() in page[2]


def test_failed_evidence_disables_web_accept_but_allows_explained_revision(tmp_path):
    application, _, service, package = _application(
        tmp_path,
        failed_kind=EvidenceKind.BROWSER,
    )
    assert package is not None
    page = _call(application, path="/customer/requests/req-1/evidence")
    assert b'value="ACCEPT" required disabled' in page[2]
    revised = _call(
        application,
        method="POST",
        path="/customer/requests/req-1/evidence/review",
        body=_review_form(
            package,
            decision="REVISE",
            comments="Repair the browser journey and provide a new governed package.",
        ),
    )
    assert revised[0] == "303 See Other"
    assert service.context("customer-1", "req-1")[2].decision == "REVISE"
