import json
from pathlib import Path

from runtime.product_requirements import RequirementStatus, load_prd_artifact


PLAN_PATH=Path("managed_product_plans/spoken-english-ai/product-milestone-9.json")


def load_plan(): return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_plan_is_locked_prd_backed_and_planning_only():
    plan=load_plan()
    prd=load_prd_artifact("product_requirements/spoken-english-ai/prd-v1.0.json")
    assert prd.version=="1.0" and prd.status is RequirementStatus.LOCKED
    assert plan["prd"]["version"]==prd.version and plan["prd"]["status"]=="LOCKED"
    assert set(plan["prd"]["requirement_ids"]) <= {item.requirement_id for item in prd.requirements}
    assert plan["status"]=="PLANNED_NOT_IMPLEMENTED"
    assert not plan["request"]["implementation_authorized"]


def test_epics_tasks_and_dependencies_are_complete():
    plan=load_plan(); tasks={item["task_id"]:item for item in plan["tasks"]}
    assert len(plan["epics"])==8 and len(tasks)==24
    assert {task for epic in plan["epics"] for task in epic["task_ids"]}==set(tasks)
    assert all(item["acceptance_criteria"] for item in tasks.values())
    assert all(set(item["dependencies"]) <= set(tasks) for item in tasks.values())


def test_decisions_cost_risks_and_human_gate_are_explicit():
    plan=load_plan()
    assert len(plan["provider_decision_placeholders"])==10
    assert plan["provider_evaluation_matrix"]["status"]=="AWAITING_EVIDENCE"
    assert plan["estimated_sandbox_cost_model"]["status"]=="FORMULA_DEFINED_PRICES_PENDING_EVIDENCE"
    assert len(plan["risks"])==10 and len(plan["go_no_go_checklist"])==12
    assert plan["human_approval_gate"]["default"]=="NO_GO"


def test_safety_exclusions_are_frozen():
    plan=load_plan(); safety=plan["safety"]
    assert not any(safety.values())
    assert {"payments implementation","production deployment","public customer release",
            "non-Indian accents","native mobile apps","photorealistic avatars","video avatars"} <= set(plan["exclusions"])
