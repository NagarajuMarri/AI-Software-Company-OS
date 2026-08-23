"""Strict operator-owned JSON loader for declarative browser journeys."""

from __future__ import annotations

import json
from pathlib import Path

from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserInputBinding,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
)


_MAX_BYTES = 256_000


def load_acceptance_plan(
    path: Path,
) -> tuple[
    str,
    str,
    tuple[str, ...],
    tuple[BrowserJourneySpecification, ...],
    tuple[BrowserInputBinding, ...],
]:
    """Load one closed schema without resolving opaque secret references."""

    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError("Acceptance plan must be a regular file")
    content = source.read_bytes()
    if not content or len(content) > _MAX_BYTES:
        raise ValueError("Acceptance plan is empty or too large")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Acceptance plan must be valid UTF-8 JSON") from error
    expected = {
        "schema_version",
        "acceptance_profile_id",
        "acceptance_profile_version",
        "allowed_origins",
        "journeys",
        "inputs",
    }
    if not isinstance(payload, dict) or set(payload) != expected or payload["schema_version"] != 1:
        raise ValueError("Acceptance plan schema is invalid")
    if not isinstance(payload["allowed_origins"], list) or not isinstance(
        payload["journeys"], list
    ) or not isinstance(payload["inputs"], list):
        raise ValueError("Acceptance plan collections are invalid")
    journeys = tuple(_journey(value) for value in payload["journeys"])
    inputs = tuple(_input(value) for value in payload["inputs"])
    return (
        payload["acceptance_profile_id"],
        payload["acceptance_profile_version"],
        tuple(payload["allowed_origins"]),
        journeys,
        inputs,
    )


def _journey(value: object) -> BrowserJourneySpecification:
    expected = {"journey_id", "capability_id", "title", "start_path", "steps"}
    optional = {"timeout_seconds"}
    if (
        not isinstance(value, dict)
        or not expected <= set(value) <= expected | optional
        or not isinstance(value["steps"], list)
    ):
        raise ValueError("Acceptance journey is invalid")
    return BrowserJourneySpecification(
        journey_id=value["journey_id"],
        capability_id=value["capability_id"],
        title=value["title"],
        start_path=value["start_path"],
        steps=tuple(_step(item) for item in value["steps"]),
        timeout_seconds=value.get("timeout_seconds", 30),
    )


def _step(value: object) -> BrowserStep:
    expected = {"step_id", "action"}
    optional = {"locator", "input_id", "expected_text", "expected_path"}
    if not isinstance(value, dict) or not expected <= set(value) <= expected | optional:
        raise ValueError("Acceptance browser step is invalid")
    locator = value.get("locator")
    return BrowserStep(
        step_id=value["step_id"],
        action=BrowserActionKind(value["action"]),
        locator=_locator(locator) if locator is not None else None,
        input_id=value.get("input_id", ""),
        expected_text=value.get("expected_text", ""),
        expected_path=value.get("expected_path", ""),
    )


def _locator(value: object) -> BrowserLocator:
    expected = {"kind", "value"}
    optional = {"accessible_name", "exact"}
    if not isinstance(value, dict) or not expected <= set(value) <= expected | optional:
        raise ValueError("Acceptance browser locator is invalid")
    return BrowserLocator(
        kind=BrowserLocatorKind(value["kind"]),
        value=value["value"],
        accessible_name=value.get("accessible_name", ""),
        exact=value.get("exact", True),
    )


def _input(value: object) -> BrowserInputBinding:
    if not isinstance(value, dict) or "input_id" not in value:
        raise ValueError("Acceptance browser input is invalid")
    allowed = {"input_id", "public_value", "secret_reference"}
    if not set(value) <= allowed or len(set(value) & {"public_value", "secret_reference"}) != 1:
        raise ValueError("Acceptance browser input binding is invalid")
    return BrowserInputBinding(
        input_id=value["input_id"],
        public_value=value.get("public_value"),
        secret_reference=value.get("secret_reference"),
    )
