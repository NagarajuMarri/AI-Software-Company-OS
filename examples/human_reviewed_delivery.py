"""Run the Milestone 13 human-reviewed delivery lifecycle without live services."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.product_delivery import InMemoryProductStateStore, ProductDeliveryPipeline


class CodexSimulation:
    provider_id = "codex"

    def dispatch(self, plan, mode):
        return f"dispatched {mode.value}: {plan}"


class GitHubSimulation:
    def merge(self, pull_request, authorized_by):
        return f"merged {pull_request} for {authorized_by}"


def main():
    delivery = ProductDeliveryPipeline(InMemoryProductStateStore())
    delivery.plan_milestone("ascos", "13.0", "agent/milestone-13")
    delivery.capture_knowledge("ascos", "snapshot:architecture-and-roadmap")
    delivery.record_plan("ascos", "implement human-reviewed product delivery")
    print(delivery.dispatch("ascos", CodexSimulation(), "codex-agent"))
    delivery.record_implementation("ascos", "2458b77+milestone13", "PR-draft-13")
    delivery.record_verification("ascos", passed=True)
    waiting = delivery.request_review("ascos", "human-reviewer")
    print(f"review={waiting.review_state.value}")
    delivery.approve("ascos", "human-reviewer", "Verified and approved")
    delivery.authorize_merge("ascos", "human-reviewer")
    print(delivery.merge("ascos", GitHubSimulation()))
    next_state = delivery.create_next_milestone(
        "ascos", "13.1", "agent/milestone-13-1"
    )
    print(f"next={next_state.current_milestone} progress={next_state.progress}")


if __name__ == "__main__":
    main()
