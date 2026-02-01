import apiClient from './client';
import type {
  AdminLoginRequest,
  AdminLoginResponse,
  AdminStats,
  AdminGamesResponse,
  AdminGameDetail,
} from './types';

// ── Admin Auth ────────────────────────────────────────────────────────────

/**
 * Authenticate as an admin user.
 * POST /api/auth/admin/login
 */
export async function adminLogin(
  credentials: AdminLoginRequest,
): Promise<AdminLoginResponse> {
  const response = await apiClient.post<AdminLoginResponse>(
    '/api/auth/admin/login',
    credentials,
  );
  return response.data;
}

// ── Admin Dashboard ───────────────────────────────────────────────────────

/**
 * Fetch high-level dashboard stats.
 * GET /api/admin/stats
 */
export async function getAdminStats(): Promise<AdminStats> {
  const response = await apiClient.get<AdminStats>('/api/admin/stats');
  return response.data;
}

/**
 * List games with optional filtering and pagination.
 * GET /api/admin/games
 */
export async function getAdminGames(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminGamesResponse> {
  const response = await apiClient.get<AdminGamesResponse>('/api/admin/games', {
    params,
  });
  return response.data;
}

/**
 * Get detailed info for a single game, including players and request stats.
 * GET /api/admin/games/{gameId}
 */
export async function getAdminGameDetail(
  gameId: string,
): Promise<AdminGameDetail> {
  const response = await apiClient.get<AdminGameDetail>(
    `/api/admin/games/${gameId}`,
  );
  return response.data;
}

/**
 * Force-close a game (admin action).
 * POST /api/admin/games/{gameId}/force-close
 */
export async function forceCloseGame(gameId: string): Promise<void> {
  await apiClient.post(`/api/admin/games/${gameId}/force-close`);
}
