"""Traceable deterministic PRD draft generated from approved customer scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re

from runtime.customer_requirements import (
    ALLOWED_PLATFORMS,
    DataSensitivity,
    DeliveryPriority,
)
from runtime.product_requirements import (
    ProductRequirement,
    ProductRequirementsDocument,
    RequirementCategory,
    RequirementGroup,
    RequirementPriority,
    RequirementStatus,
    RevisionRecord,
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^REQ-[A-Z0-9][A-Z0-9-]{0,59}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
GENERATION_PROFILE = "ascos-deterministic-customer-prd-v1"


@dataclass(frozen=True)
class CustomerPrdRequirement:
    """One draft requirement with an exact approved-source reference."""

    requirement_id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    category: RequirementCategory
    priority: RequirementPriority
    source_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not _REQUIREMENT_ID.fullmatch(
            self.requirement_id
        ):
            raise ValueError("Customer PRD requirement ID is invalid")
        _text(self.title, "customer PRD requirement title", 300)
        _text(self.description, "customer PRD requirement description", 2_000)
        _items(self.acceptance_criteria, "customer PRD acceptance criteria", 1, 10, 500)
        if not isinstance(self.category, RequirementCategory):
            raise ValueError("Customer PRD requirement category is invalid")
        if not isinstance(self.priority, RequirementPriority):
            raise ValueError("Customer PRD requirement priority is invalid")
        _text(self.source_reference, "customer PRD source reference", 200)


@dataclass(frozen=True)
class CustomerPrdDraft:
    """Write-once PRD draft bound to an exact customer approval receipt."""

    artifact_id: str
    customer_id: str
    request_id: str
    product_id: str
    prd_id: str
    version: str
    generation_profile: str
    source_request_digest: str
    requirements_digest: str
    approval_digest: str
    title: str
    problem_statement: str
    target_users: str
    primary_user_journey: str
    requirements: tuple[CustomerPrdRequirement, ...]
    success_metrics: tuple[str, ...]
    explicit_exclusions: tuple[str, ...]
    platforms: tuple[str, ...]
    data_sensitivity: DataSensitivity
    delivery_priority: DeliveryPriority
    generated_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "customer PRD artifact ID"),
            (self.customer_id, "customer PRD customer ID"),
            (self.request_id, "customer PRD request ID"),
            (self.product_id, "customer PRD product ID"),
            (self.prd_id, "customer PRD ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.version != "0.1":
            raise ValueError("Customer PRD draft version is invalid")
        if self.generation_profile != GENERATION_PROFILE:
            raise ValueError("Customer PRD generation profile is invalid")
        for value, label in (
            (self.source_request_digest, "source request digest"),
            (self.requirements_digest, "requirements digest"),
            (self.approval_digest, "requirements approval digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        _text(self.title, "customer PRD title", 300)
        _text(self.problem_statement, "customer PRD problem statement", 4_000)
        _text(self.target_users, "customer PRD target users", 2_000)
        _text(self.primary_user_journey, "customer PRD primary journey", 4_000)
        if (
            not isinstance(self.requirements, tuple)
            or not 1 <= len(self.requirements) <= 100
            or any(not isinstance(item, CustomerPrdRequirement) for item in self.requirements)
            or len({item.requirement_id for item in self.requirements}) != len(self.requirements)
        ):
            raise ValueError("Customer PRD requirements are invalid")
        _items(self.success_metrics, "customer PRD success metrics", 1, 10, 500)
        _items(self.explicit_exclusions, "customer PRD exclusions", 0, 30, 500)
        if (
            not isinstance(self.platforms, tuple)
            or not self.platforms
            or len(set(self.platforms)) != len(self.platforms)
            or tuple(item for item in ALLOWED_PLATFORMS if item in self.platforms)
            != self.platforms
        ):
            raise ValueError("Customer PRD platforms are invalid")
        if not isinstance(self.data_sensitivity, DataSensitivity):
            raise ValueError("Customer PRD data sensitivity is invalid")
        if not isinstance(self.delivery_priority, DeliveryPriority):
            raise ValueError("Customer PRD delivery priority is invalid")
        if (
            not isinstance(self.generated_at, datetime)
            or self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("Customer PRD generated_at must be UTC")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()

    def to_governed_document(self) -> ProductRequirementsDocument:
        """Project this customer artifact into the existing governed PRD domain."""

        author = "ascos-product-manager"
        requirements = tuple(
            ProductRequirement(
                requirement_id=item.requirement_id,
                title=item.title,
                description=item.description,
                rationale=f"Derived from approved source: {item.source_reference}",
                acceptance_criteria=item.acceptance_criteria,
                priority=item.priority,
                milestone="Customer MVP",
                status=RequirementStatus.DRAFT,
                version=self.version,
                author=author,
                approver=None,
                created_at=self.generated_at,
                updated_at=self.generated_at,
                affected_products=(self.product_id,),
                tags=("customer-approved-source", item.category.value.casefold()),
                category=item.category,
                product_id=self.product_id,
            )
            for item in self.requirements
        )
        functional = tuple(
            item.requirement_id
            for item in self.requirements
            if item.category is RequirementCategory.FUNCTIONAL
        )
        governance = tuple(
            item.requirement_id
            for item in self.requirements
            if item.category is not RequirementCategory.FUNCTIONAL
        )
        groups: tuple[RequirementGroup, ...] = (
            RequirementGroup("core", "Core product scope", functional),
        )
        if governance:
            groups += (RequirementGroup("boundaries", "Delivery and data boundaries", governance),)
        return ProductRequirementsDocument(
            prd_id=self.prd_id,
            product_id=self.product_id,
            title=self.title,
            version=self.version,
            status=RequirementStatus.DRAFT,
            author=author,
            approver=None,
            requirements=requirements,
            explicit_exclusions=self.explicit_exclusions,
            future_roadmap=(),
            revision_history=(
                RevisionRecord(
                    self.version,
                    author,
                    "CREATED",
                    "Generated from exact customer-approved requirements",
                    self.generated_at,
                ),
            ),
            created_at=self.generated_at,
            updated_at=self.generated_at,
            requirement_groups=groups,
        )


def ids_for(request_id: str) -> tuple[str, str, str]:
    """Derive bounded artifact, product, and PRD identities."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Customer PRD request ID is invalid")
    digest = hashlib.sha256(f"customer-prd:{request_id}".encode()).hexdigest()[:24]
    return f"customer-prd-{digest}", f"product-{digest}", f"prd-{digest}"


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or "\x7f" in value
    ):
        raise ValueError(f"{label} is invalid")


def _items(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    item_limit: int,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len({value.casefold() for value in values if isinstance(value, str)}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_limit)


def _canonical(value: CustomerPrdDraft) -> bytes:
    payload = asdict(value)
    payload["data_sensitivity"] = value.data_sensitivity.value
    payload["delivery_priority"] = value.delivery_priority.value
    payload["generated_at"] = value.generated_at.isoformat()
    for requirement, source in zip(payload["requirements"], value.requirements, strict=True):
        requirement["category"] = source.category.value
        requirement["priority"] = source.priority.value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
