"""JWT token utilities for admin authentication.

Uses HS256 algorithm with a shared secret. Tokens carry `sub`, `exp`, and `iat`
claims. The secret MUST be a 256-bit (32-byte) value loaded from the JWT_SECRET
environment variable -- never hardcoded.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

logger = logging.getLogger("chipmate.auth.jwt")

ALGORITHM = "HS256"
DEFAULT_EXPIRE_HOURS = 24


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        data: Claims to embed in the token.  Must include at least ``sub``.
        expires_delta: Custom token lifetime.  Defaults to 24 hours.

    Returns:
        A compact JWS string.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=DEFAULT_EXPIRE_HOURS))

    to_encode.update({"exp": expire, "iat": now})
    token = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    logger.debug("Created JWT for sub=%s, expires=%s", data.get("sub"), expire.isoformat())
    return token


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: The compact JWS string.

    Returns:
        The decoded claims dictionary.

    Raises:
        ExpiredSignatureError: If the token has expired.
        JWTError: If the token is malformed or the signature is invalid.
    """
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    return payload
