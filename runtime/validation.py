"""Small reusable validators for runtime domain models."""

from runtime.exceptions import ValidationError


def validate_required_string(value: object, field_name: str) -> None:
    """Require a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")


def validate_optional_string(value: object | None, field_name: str) -> None:
    """Validate a string only when a value is supplied."""
    if value is not None:
        validate_required_string(value, field_name)
