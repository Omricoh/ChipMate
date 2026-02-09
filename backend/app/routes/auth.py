"""Authentication route handlers.

Endpoints:
    POST /api/auth/admin/login  -- Admin JWT login.
    GET  /api/auth/me           -- Return current user info (admin or player).
    GET  /api/auth/validate     -- Validate token and return user context.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.auth.jwt import create_access_token, decode_token
from app.auth.player_token import validate_player_token
from app.config import settings
from app.dal.database import get_database
from app.dal.games_dal import GameDAL
from app.middleware.rate_limit import rate_limiter
from app.models.common import GameStatus
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


class AdminLoginUser(BaseModel):
    """User info returned in admin login response."""
    user_id: str
    role: str = "ADMIN"
    username: str


class AdminLoginResponse(BaseModel):
    """Response for a successful admin login."""
    access_token: str
    token_type: str = "bearer"
    user: AdminLoginUser


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


class ValidateUserAdmin(BaseModel):
    """User info for admin in validate response."""
    user_id: str
    role: str
    username: str


class ValidateUserPlayer(BaseModel):
    """User info for player/manager in validate response."""
    user_id: str
    role: str
    player_id: str
    game_id: str
    game_code: str
    is_manager: bool


class ValidateResponseValid(BaseModel):
    """Validate response for a valid token."""
    valid: bool = True
    user: ValidateUserAdmin | ValidateUserPlayer


class ValidateResponseInvalid(BaseModel):
    """Validate response for an invalid token."""
    valid: bool = False
    error: str


# ---------------------------------------------------------------------------
# POST /api/auth/admin/login
# ---------------------------------------------------------------------------

@router.post(
    "/admin/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_login(request: Request, body: AdminLoginRequest) -> AdminLoginResponse:
    """Authenticate admin and return a JWT.

    Validates the provided credentials against ``ADMIN_USERNAME`` and
    ``ADMIN_PASSWORD`` from the application configuration.

    Returns:
        An access token and token type.

    Raises:
        HTTPException 401: Invalid credentials.
        HTTPException 429: Too many failed login attempts.
    """
    # Rate limit: 5 attempts per IP per 15 minutes
    rate_limiter.check_rate_limit(request, "admin_login")

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
    return AdminLoginResponse(
        access_token=token,
        user=AdminLoginUser(
            user_id="admin",
            username=body.username,
        ),
    )


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


# ---------------------------------------------------------------------------
# GET /api/auth/validate
# ---------------------------------------------------------------------------

@router.get("/validate")
async def validate_token(
    authorization: str | None = Header(None),
    x_player_token: str | None = Header(None),
) -> dict[str, Any]:
    """Validate a token and return user context for session restoration.

    Accepts either:
    * ``Authorization: Bearer <jwt>`` for admin,
    * ``X-Player-Token: <uuid>`` for player/manager.

    Returns:
        Valid admin: ``{"valid": true, "user": {"user_id": "admin", "role": "ADMIN", "username": str}}``
        Valid player: ``{"valid": true, "user": {"user_id": str, "role": "MANAGER"|"PLAYER", "player_id": str, "game_id": str, "game_code": str, "is_manager": bool}}``
        Invalid/expired: ``{"valid": false, "error": str}``
    """
    # --- Admin path ---
    if authorization is not None and authorization.startswith("Bearer "):
        from jose import ExpiredSignatureError, JWTError

        token = authorization[len("Bearer "):]
        try:
            payload = decode_token(token)
        except ExpiredSignatureError:
            logger.debug("Validate: admin token expired")
            return {"valid": False, "error": "Token has expired"}
        except JWTError:
            logger.debug("Validate: invalid admin token")
            return {"valid": False, "error": "Invalid token"}

        if payload.get("role") == "admin":
            username = payload.get("sub", "admin")
            logger.debug("Validate: valid admin token for user=%s", username)
            return {
                "valid": True,
                "user": {
                    "user_id": "admin",
                    "role": "ADMIN",
                    "username": username,
                },
            }
        else:
            # JWT is valid but not admin role
            logger.debug("Validate: JWT has non-admin role")
            return {"valid": False, "error": "Invalid token role"}

    # --- Player / Manager path ---
    if x_player_token is not None:
        if not validate_player_token(x_player_token):
            logger.debug("Validate: invalid player token format")
            return {"valid": False, "error": "Invalid player token format"}

        db = get_database()
        player_dal = PlayerDAL(db)
        game_dal = GameDAL(db)

        # Look up player by token only (session restoration doesn't have game_id)
        player = await player_dal.get_by_token_only(x_player_token)

        if player is None:
            logger.debug("Validate: player not found for token")
            return {"valid": False, "error": "Player not found"}

        # Look up game to get game_code and check status
        game = await game_dal.get_by_id(player.game_id)
        if game is None:
            logger.debug("Validate: game not found for player")
            return {"valid": False, "error": "Game not found"}

        # Check if game is closed - players can still reconnect to OPEN or SETTLING games
        if game.status == GameStatus.CLOSED:
            logger.debug("Validate: game is closed, session invalid")
            return {"valid": False, "error": "Game has ended"}

        # Check if player is still active
        if not player.is_active:
            logger.debug("Validate: player is inactive")
            return {"valid": False, "error": "Player is inactive"}

        role = "MANAGER" if player.is_manager else "PLAYER"
        logger.debug(
            "Validate: valid player token, player_id=%s, role=%s",
            player.id,
            role,
        )
        return {
            "valid": True,
            "user": {
                "user_id": player.id or player.player_token,
                "role": role,
                "player_id": player.player_token,
                "game_id": player.game_id,
                "game_code": game.code,
                "is_manager": player.is_manager,
                "display_name": player.display_name,
            },
        }

    # --- No auth provided ---
    logger.debug("Validate: no authentication provided")
    return {"valid": False, "error": "No authentication provided"}
