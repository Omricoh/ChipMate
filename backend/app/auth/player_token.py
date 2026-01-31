"""Player token utilities (UUID4-based tokens).

Player tokens are cryptographically random UUID4 strings (128-bit entropy).
They serve as the primary credential for player and manager access to
game-scoped endpoints.
"""

import uuid


def generate_player_token() -> str:
    """Generate a new UUID4 player token.

    Returns:
        A lowercase UUID4 string (e.g. ``'a1b2c3d4-e5f6-4890-abcd-ef1234567890'``).
    """
    return str(uuid.uuid4())


def validate_player_token(token: str) -> bool:
    """Validate that a string is a well-formed UUID4.

    Args:
        token: The candidate token string.

    Returns:
        True if the token is a valid UUID4, False otherwise.
    """
    try:
        parsed = uuid.UUID(token, version=4)
    except (ValueError, AttributeError, TypeError):
        return False
    # Ensure the string round-trips correctly (rejects non-canonical forms).
    return str(parsed) == token
