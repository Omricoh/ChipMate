"""FastAPI dependency-injection callables for authentication and authorization.

Each callable is designed to be used with ``Depends()`` in route signatures.
They extract credentials from request headers, validate them, and return
either an admin context dict or a Player model instance.
"""

import logging
from typing import Any

from fastapi import Depends, Header, HTTPException, Path, status
from jose import ExpiredSignatureError, JWTError

from app.auth.jwt import decode_token
from app.auth.player_token import validate_player_token
from app.dal.database import get_database
from app.dal.players_dal import PlayerDAL
from app.models.player import Player

logger = logging.getLogger("chipmate.auth.dependencies")


# ---------------------------------------------------------------------------
# Admin JWT dependency
# ---------------------------------------------------------------------------

async def get_current_admin(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Validate an admin JWT from the Authorization header.

    Returns:
        A dict with admin context, e.g.
        ``{"role": "admin", "username": ..., "sub": ...}``.

    Raises:
        HTTPException 401: Missing or invalid token.
        HTTPException 403: Token is valid but lacks admin role.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = authorization[len("Bearer "):]

    try:
        payload = decode_token(token)
    except ExpiredSignatureError:
        logger.warning("Expired admin JWT presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError:
        logger.warning("Invalid admin JWT presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return {
        "role": "admin",
        "username": payload.get("sub", "admin"),
    }


# ---------------------------------------------------------------------------
# Player token dependency
# ---------------------------------------------------------------------------

async def get_current_player(
    x_player_token: str | None = Header(None),
    game_id: str = Path(...),
) -> Player:
    """Look up a player by ``X-Player-Token`` header and path ``game_id``.

    Returns:
        The matching Player model from the database.

    Raises:
        HTTPException 401: Header missing or token format invalid.
        HTTPException 404: No player found for this token in the given game.
    """
    if x_player_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Player-Token header",
        )

    if not validate_player_token(x_player_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid player token format",
        )

    db = get_database()
    player_dal = PlayerDAL(db)
    player = await player_dal.get_by_token(game_id, x_player_token)

    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found in this game",
        )

    return player


# ---------------------------------------------------------------------------
# Manager dependency (player with is_manager=True)
# ---------------------------------------------------------------------------

async def get_current_manager(
    player: Player = Depends(get_current_player),
) -> Player:
    """Verify the authenticated player is a manager.

    Returns:
        The Player model (guaranteed to have ``is_manager=True``).

    Raises:
        HTTPException 403: Player is not a manager.
    """
    if not player.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required",
        )
    return player


# ---------------------------------------------------------------------------
# Combined: admin OR manager
# ---------------------------------------------------------------------------

async def get_admin_or_manager(
    authorization: str | None = Header(None),
    x_player_token: str | None = Header(None),
    game_id: str = Path(...),
) -> dict[str, Any]:
    """Accept either an admin JWT or a manager player token.

    Tries admin JWT first; if the header is absent, falls through to
    the player token path.

    Returns:
        A context dict with ``auth_type`` (``"admin"`` or ``"manager"``),
        plus either admin info or the Player model under ``"player"``.

    Raises:
        HTTPException 401/403/404: Depending on which auth path fails.
    """
    # Try admin path if Authorization header is present
    if authorization is not None and authorization.startswith("Bearer "):
        admin_ctx = await get_current_admin(authorization=authorization)
        return {"auth_type": "admin", **admin_ctx}

    # Fall through to player/manager path
    player = await get_current_player(
        x_player_token=x_player_token, game_id=game_id
    )
    if not player.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required",
        )
    return {"auth_type": "manager", "player": player}


# ---------------------------------------------------------------------------
# Combined: admin OR any player
# ---------------------------------------------------------------------------

async def get_admin_or_player(
    authorization: str | None = Header(None),
    x_player_token: str | None = Header(None),
    game_id: str = Path(...),
) -> dict[str, Any]:
    """Accept either an admin JWT or any player token.

    Tries admin JWT first; if the header is absent, falls through to
    the player token path.

    Returns:
        A context dict with ``auth_type`` (``"admin"`` or ``"player"``),
        plus either admin info or the Player model under ``"player"``.

    Raises:
        HTTPException 401/404: Depending on which auth path fails.
    """
    # Try admin path if Authorization header is present
    if authorization is not None and authorization.startswith("Bearer "):
        admin_ctx = await get_current_admin(authorization=authorization)
        return {"auth_type": "admin", **admin_ctx}

    # Fall through to any-player path
    player = await get_current_player(
        x_player_token=x_player_token, game_id=game_id
    )
    role = "manager" if player.is_manager else "player"
    return {"auth_type": role, "player": player}
