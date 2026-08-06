import json
from pathlib import Path


def test_milestone_12_plan_is_locked_and_bounded():
    plan = json.loads(Path("managed_product_plans/spoken-english-ai/product-milestone-12.json").read_text(encoding="utf-8"))
    assert plan["status"] == "LOCKED_NOT_IMPLEMENTED"
    assert len(plan["tasks"]) == 32
    assert plan["baseline_sha"] == "e9575eb544bd5b9288d64eec4e0b115bcd671b83"
    assert not plan["deployment_authorized"] and not plan["real_charges_authorized"]
    assert "parent portal" in plan["scope"]["excluded"]
