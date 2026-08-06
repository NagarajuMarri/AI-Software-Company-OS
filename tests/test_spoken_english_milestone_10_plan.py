import json
from pathlib import Path

from runtime.product_requirements import RequirementStatus, load_prd_artifact


PLAN_PATH = Path("managed_product_plans/spoken-english-ai/product-milestone-10.json")
BASELINE_PATH = Path(".ascos-state/product-delivery/spoken-english-ai.json")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_milestone_10_is_locked_prd_backed_planning_only():
    plan = load(PLAN_PATH)
    prd = load_prd_artifact("product_requirements/spoken-english-ai/prd-v1.0.json")
    assert prd.status is RequirementStatus.LOCKED and prd.version == "1.0"
    assert set(plan["prd"]["requirement_ids"]) <= {item.requirement_id for item in prd.requirements}
    assert plan["status"] == "PLANNED_NOT_IMPLEMENTED"
    assert not plan["implementation_authorized"]
    assert not any(plan["safety"].values())


def test_dependencies_and_human_gate_are_complete():
    plan = load(PLAN_PATH)
    tasks = {item["task_id"]: item for item in plan["tasks"]}
    assert {task for epic in plan["epics"] for task in epic["task_ids"]} == set(tasks)
    assert all(set(item["dependencies"]) <= set(tasks) for item in tasks.values())
    assert all(item["acceptance_criteria"] for item in tasks.values())
    assert plan["human_gate"] == {"required": True, "implementation_authority": False, "status": "WAITING_FOR_HUMAN_SCOPE_LOCK"}


def test_baseline_records_completion_and_estimate_classification():
    baseline = load(BASELINE_PATH)
    assert baseline["managed_baseline_sha"] == "e9575eb544bd5b9288d64eec4e0b115bcd671b83"
    assert baseline["milestone_id"] == "product-milestone-11"
    assert baseline["milestone_completion"]["status"] == "COMPLETED"
    estimate = baseline["architectural_estimates"][0]
    assert estimate["value_percent"] == 55
    assert estimate["classification"] == "ARCHITECTURAL_ESTIMATE"
    assert not estimate["guaranteed_invoice_reduction"]
