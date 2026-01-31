import apiClient from './client';
import type {
  CreateGameResponse,
  GameByCodeResponse,
  GameStatusResponse,
  JoinGameResponse,
  PlayersListResponse,
} from './types';

// ── Game API Functions ────────────────────────────────────────────────────

/**
 * Create a new game. The caller becomes the manager.
 * POST /api/games
 */
export async function createGame(managerName: string): Promise<CreateGameResponse> {
  const response = await apiClient.post<CreateGameResponse>('/api/games', {
    manager_name: managerName,
  });
  return response.data;
}

/**
 * Look up a game by its 6-character join code (public, no auth).
 * GET /api/games/code/{code}
 */
export async function getGameByCode(code: string): Promise<GameByCodeResponse> {
  const response = await apiClient.get<GameByCodeResponse>(
    `/api/games/code/${code.toUpperCase()}`,
  );
  return response.data;
}

/**
 * Join an existing game.
 * POST /api/games/{gameId}/join
 */
export async function joinGame(
  gameId: string,
  playerName: string,
): Promise<JoinGameResponse> {
  const response = await apiClient.post<JoinGameResponse>(
    `/api/games/${gameId}/join`,
    { player_name: playerName },
  );
  return response.data;
}

/**
 * Get game details by ID (auth required).
 * GET /api/games/{gameId}
 */
export async function getGame(gameId: string) {
  const response = await apiClient.get(`/api/games/${gameId}`);
  return response.data;
}

/**
 * Get comprehensive game status with financial summary.
 * GET /api/games/{gameId}/status
 */
export async function getGameStatus(gameId: string): Promise<GameStatusResponse> {
  const response = await apiClient.get<GameStatusResponse>(
    `/api/games/${gameId}/status`,
  );
  return response.data;
}

/**
 * List all players in a game (manager/admin only).
 * GET /api/games/{gameId}/players
 */
export async function getGamePlayers(gameId: string): Promise<PlayersListResponse> {
  const response = await apiClient.get<PlayersListResponse>(
    `/api/games/${gameId}/players`,
  );
  return response.data;
}

/**
 * Get the QR code image URL for a game.
 * The backend returns a PNG image at GET /api/games/{gameCode}/qr
 */
export function getQrCodeUrl(gameCode: string): string {
  const baseUrl = apiClient.defaults.baseURL ?? '';
  return `${baseUrl}/api/games/${gameCode.toUpperCase()}/qr`;
}
