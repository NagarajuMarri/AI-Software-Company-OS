"""Locked SpeakMate V1 capability contracts used as ASCOS regressions."""

from runtime.runtime_acceptance.models import (
    AcceptanceJourney,
    CapabilityAcceptanceContract,
    EvidenceKind,
    RuntimeAcceptanceProfile,
)


AUTHENTICATION_JOURNEYS = (
    "authentication.registration",
    "authentication.login",
    "authentication.logout",
    "authentication.session_restore",
    "authentication.password_recovery",
    "authentication.security_error_paths",
)

VOICE_JOURNEYS = (
    "voice.capture",
    "voice.stt",
    "voice.conversation",
    "voice.llm",
    "voice.tts",
    "voice.audible_playback",
    "voice.avatar_synchronization",
    "voice.repeat_turn",
)


def speakmate_v1_contracts() -> tuple[CapabilityAcceptanceContract, ...]:
    return (
        CapabilityAcceptanceContract(
            "AUTHENTICATION",
            "1.0",
            "Closed-beta learner authentication",
            AUTHENTICATION_JOURNEYS,
            ("SEA-PRD-018", "SEA-PRD-020"),
            human_acceptance_required=True,
        ),
        CapabilityAcceptanceContract(
            "VOICE",
            "1.0",
            "Repeatable spoken tutor conversation",
            VOICE_JOURNEYS,
            ("SEA-PRD-007", "SEA-PRD-008", "SEA-PRD-013"),
            human_acceptance_required=True,
        ),
        CapabilityAcceptanceContract(
            "PWA",
            "1.0",
            "Installable standalone learner application",
            ("pwa.install_launch",),
            ("SEA-PRD-001",),
            human_acceptance_required=True,
        ),
    )


def speakmate_v1_journeys() -> tuple[AcceptanceJourney, ...]:
    browser = (
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    )
    return (
        AcceptanceJourney(
            "authentication.registration",
            "AUTHENTICATION",
            "New learner registers exactly once and receives a session",
            browser + (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "authentication.login",
            "AUTHENTICATION",
            "Existing learner logs in with the registered password",
            browser + (EvidenceKind.SECURITY,),
        ),
        AcceptanceJourney(
            "authentication.logout",
            "AUTHENTICATION",
            "Learner logs out and refresh credentials are revoked",
            browser + (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "authentication.session_restore",
            "AUTHENTICATION",
            "Refresh restores only a valid authenticated session",
            browser + (EvidenceKind.SECURITY,),
        ),
        AcceptanceJourney(
            "authentication.password_recovery",
            "AUTHENTICATION",
            "Single-use reset changes password and revokes old sessions",
            browser + (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "authentication.security_error_paths",
            "AUTHENTICATION",
            "Duplicates, partial failure, unknown email, and invalid tokens fail safely",
            (EvidenceKind.BROWSER_NETWORK, EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "voice.capture",
            "VOICE",
            "Consent-bound microphone capture produces deterministic audio",
            browser + (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "voice.stt",
            "VOICE",
            "Captured fixture is transcribed through the STT boundary",
            (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.STT),
        ),
        AcceptanceJourney(
            "voice.conversation",
            "VOICE",
            "Transcript enters the governed conversation turn",
            (EvidenceKind.BROWSER_NETWORK, EvidenceKind.PERSISTENCE),
        ),
        AcceptanceJourney(
            "voice.llm",
            "VOICE",
            "Conversation produces a bounded tutor response",
            (EvidenceKind.LLM, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "voice.tts",
            "VOICE",
            "Tutor response produces playable speech through the TTS boundary",
            (EvidenceKind.TTS, EvidenceKind.SECURITY),
        ),
        AcceptanceJourney(
            "voice.audible_playback",
            "VOICE",
            "Generated speech becomes audibly playable in the browser",
            browser + (EvidenceKind.AUDIBLE_PLAYBACK,),
        ),
        AcceptanceJourney(
            "voice.avatar_synchronization",
            "VOICE",
            "Avatar speaking state is synchronized with audio playback",
            browser + (EvidenceKind.AVATAR_SYNCHRONIZATION,),
        ),
        AcceptanceJourney(
            "voice.repeat_turn",
            "VOICE",
            "A second complete voice turn succeeds in the same session",
            browser
            + (
                EvidenceKind.AUDIO_FIXTURE,
                EvidenceKind.STT,
                EvidenceKind.LLM,
                EvidenceKind.TTS,
                EvidenceKind.AUDIBLE_PLAYBACK,
                EvidenceKind.AVATAR_SYNCHRONIZATION,
                EvidenceKind.PERSISTENCE,
            ),
        ),
        AcceptanceJourney(
            "pwa.install_launch",
            "PWA",
            "Install, standalone launch, refresh, and offline shell operate",
            browser + (EvidenceKind.PWA, EvidenceKind.READINESS),
        ),
    )


def speakmate_v1_profile() -> RuntimeAcceptanceProfile:
    """Return the versioned SpeakMate contract used by configuration binding."""

    return RuntimeAcceptanceProfile(
        profile_id="speakmate-v1",
        version="1.0",
        capabilities=speakmate_v1_contracts(),
        journeys=speakmate_v1_journeys(),
    )
