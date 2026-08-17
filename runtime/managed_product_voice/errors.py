"""Typed failures for deterministic voice/media verification."""


class VoiceVerificationError(ValueError):
    """Voice evidence authority, media integrity, or runtime proof was invalid."""


class VoicePlanError(VoiceVerificationError):
    """An immutable voice verification plan was invalid or corrupt."""
