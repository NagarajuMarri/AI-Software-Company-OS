import json
from pathlib import Path


DESIGN = Path("managed_product_plans/spoken-english-ai/product-milestone-10-commercial-design.json")
DECISION = Path("managed_product_plans/spoken-english-ai/product-milestone-10-human-decision.json")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_commercial_package_is_planning_only():
    plan = load(DESIGN)
    assert plan["planning_id"] == "spoken-english-ai-product-milestone-10-v1"
    assert plan["status"] == "PLANNING_ONLY"
    assert not plan["implementation_authorized"] and not any(plan["safety"].values())
    assert {item["plan_id"] for item in plan["commercial_plans"]} == {"FREE", "PREMIUM_MONTHLY", "PREMIUM_YEARLY"}


def test_epics_tasks_rules_and_dependencies_are_complete():
    plan = load(DESIGN)
    tasks = {item["task_id"]: item for item in plan["tasks"]}
    assert len(plan["epics"]) == 12 and len(tasks) == 24 and len(plan["business_rules"]) == 18
    assert {task for epic in plan["epics"] for task in epic["task_ids"]} == set(tasks)
    assert all(set(task["dependencies"]) <= set(tasks) for task in tasks.values())


def test_provider_pricing_analytics_legal_and_risks_are_complete():
    plan = load(DESIGN)
    assert len(plan["payment_provider_comparison"]) == 7
    assert all(item["integration_status"] == "NOT_INTEGRATED" for item in plan["payment_provider_comparison"])
    assert len(plan["pricing_scenarios"]) == 3 and not plan["pricing_formula"]["hard_coded_prices"]
    assert len(plan["founder_metrics"]) == 19 and len(plan["analytics"]) == 8
    assert len(plan["legal_placeholders"]) == 8 and len(plan["risks"]) == 8


def test_human_package_waits_for_approval():
    package = load(DECISION)
    assert package["package_id"] == "spoken-english-ai-milestone-10-commercial-human-decision-v1"
    assert package["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert not package["implementation_authorized"]
    assert not package["provider_activation_authorized"]
    assert not package["deployment_authorized"]
