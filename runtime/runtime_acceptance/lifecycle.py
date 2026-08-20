"""Controlled runtime product acceptance lifecycle."""

from dataclasses import replace
from datetime import datetime

from runtime.runtime_acceptance.models import AcceptanceStage, RuntimeAcceptanceRun


TRANSITIONS = {
    AcceptanceStage.PLANNED: (AcceptanceStage.IMPLEMENTED,),
    AcceptanceStage.IMPLEMENTED: (AcceptanceStage.AUTOMATED_VERIFIED,),
    AcceptanceStage.AUTOMATED_VERIFIED: (AcceptanceStage.RUNTIME_VERIFIED,),
    AcceptanceStage.RUNTIME_VERIFIED: (
        AcceptanceStage.HUMAN_ACCEPTANCE_REQUIRED,
        AcceptanceStage.ACCEPTED,
    ),
    AcceptanceStage.HUMAN_ACCEPTANCE_REQUIRED: (AcceptanceStage.ACCEPTED,),
    AcceptanceStage.ACCEPTED: (AcceptanceStage.COMPLETED,),
    AcceptanceStage.COMPLETED: (),
}


def transition(
    run: RuntimeAcceptanceRun, target: AcceptanceStage, now: datetime
) -> RuntimeAcceptanceRun:
    if target not in TRANSITIONS[run.stage]:
        raise ValueError(
            f"Invalid runtime acceptance transition: {run.stage.value} -> {target.value}"
        )
    return replace(
        run,
        stage=target,
        updated_at=now,
        completed_at=now if target is AcceptanceStage.COMPLETED else run.completed_at,
    )
