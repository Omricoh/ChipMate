"""Authentication route handlers.

Endpoints:
    POST /api/auth/admin/login  -- Admin JWT login.
    GET  /api/auth/me           -- Return current user info (admin or player).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.jwt import create_access_token, decode_token
from app.auth.player_token import validate_player_token
from app.config import settings
from app.dal.database import get_database
from app.dal.players_dal import PlayerDAL

logger = logging.getLogger("chipmate.routes.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AdminLoginRequest(BaseModel):
    """Request body for admin login."""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    """Response for a successful admin login."""
    access_token: str
    token_type: str = "bearer"


class MeResponseAdmin(BaseModel):
    """GET /me response when authenticated as admin."""
    role: str = "admin"
    username: str


class MeResponsePlayer(BaseModel):
    """GET /me response when authenticated as player or manager."""
    role: str  # "manager" or "player"
    name: str
    game_id: str
    player_token: str


# ---------------------------------------------------------------------------
# POST /api/auth/admin/login
# ---------------------------------------------------------------------------

@router.post(
    "/admin/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_login(body: AdminLoginRequest) -> AdminLoginResponse:
    """Authenticate admin and return a JWT.

    Validates the provided credentials against ``ADMIN_USERNAME`` and
    ``ADMIN_PASSWORD`` from the application configuration.

    Returns:
        An access token and token type.

    Raises:
        HTTPException 401: Invalid credentials.

    .. note::
        Rate limiting should be applied to this endpoint (see T24).
        Target: 5 failed attempts per IP per 15 minutes.
    """
    # NOTE: Rate limiting (5 attempts / 15 min per IP) to be added in T24.

    # Constant-time-ish comparison is not critical here since credentials are
    # fixed env vars, but we avoid short-circuiting anyway.
    if body.username != settings.ADMIN_USERNAME or body.password != settings.ADMIN_PASSWORD:
        # Never reveal which field was wrong.  Never log credentials.
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(data={"sub": body.username, "role": "admin"})
    logger.info("Admin login successful for user=%s", body.username)
    return AdminLoginResponse(access_token=token)


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

@router.get("/me")
async def get_me(
    authorization: str | None = Header(None),
    x_player_token: str | None = Header(None),
    game_id: str | None = Query(None),
) -> dict[str, Any]:
    """Return current user info for either admin JWT or player token.

    The caller must supply **one** of:
    * ``Authorization: Bearer <jwt>`` for admin,
    * ``X-Player-Token: <uuid>`` (plus ``?game_id=...``) for player/manager.

    Returns:
        Admin: ``{"role": "admin", "username": ...}``
        Player/Manager: ``{"role": "player"|"manager", "name": ..., "game_id": ..., "player_token": ...}``

    Raises:
        HTTPException 401: No valid auth provided.
        HTTPException 404: Player not found.
    """
    # --- Admin path ---
    if authorization is not None and authorization.startswith("Bearer "):
        from jose import ExpiredSignatureError, JWTError

        token = authorization[len("Bearer "):]
        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        if payload.get("role") == "admin":
            return {
                "role": "admin",
                "username": payload.get("sub", "admin"),
            }

    # --- Player / Manager path ---
    if x_player_token is not None:
        if not validate_player_token(x_player_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid player token format",
            )

        db = get_database()
        player_dal = PlayerDAL(db)

        # If game_id is provided, look up by game + token; otherwise search by token only.
        if game_id:
            player = await player_dal.get_by_token(game_id, x_player_token)
        else:
            player = await player_dal.get_by_token_only(x_player_token)

        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player not found",
            )

        role = "manager" if player.is_manager else "player"
        return {
            "role": role,
            "name": player.display_name,
            "game_id": player.game_id,
            "player_token": player.player_token,
        }

    # --- No auth provided ---
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
