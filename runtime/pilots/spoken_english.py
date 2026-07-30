"""First real product pilot definition; contains no product repository writes."""

from datetime import datetime, timezone

from runtime.planning import ChangePriority, ManagedProductChangeRequest

PILOT_ID = "personalised-daily-speaking-practice"
PILOT_TITLE = "Personalised Daily Speaking Practice Session"

EXPECTED_PRODUCT_AREAS = (
    "authenticated learner-owned API endpoint",
    "daily session service and deterministic generator interface",
    "persistent session repository and schema",
    "same-learner/date duplicate prevention",
    "service, repository, schema, and API tests",
)

OUT_OF_SCOPE = (
    "voice recording", "STT", "TTS", "payments", "frontend",
    "mobile UI", "deployment", "secrets",
)


def managed_change_request(
    *, requested_by="product-owner", requested_at=None,
):
    return ManagedProductChangeRequest(
        PILOT_ID,
        "spoken-english-ai",
        PILOT_TITLE,
        (
            "Generate and persist one deterministic learner-owned daily speaking "
            "practice session from proficiency, goal, recent mistakes, streak, "
            "completed lessons, explanation language, and available duration."
        ),
        "First commercial ASCOS managed-product pilot",
        EXPECTED_PRODUCT_AREAS,
        (
            "Session includes warm-up, situation, vocabulary, grammar, pronunciation, "
            "response instructions, completion criteria, and estimated duration.",
            "One session per learner/date unless an explicit regeneration policy permits.",
            "Authenticated API enforces learner ownership.",
            "Generation remains behind an interface with a deterministic test implementation.",
        ),
        (),
        OUT_OF_SCOPE,
        ChangePriority.HIGH,
        requested_by,
        requested_at or datetime.now(timezone.utc),
    )
