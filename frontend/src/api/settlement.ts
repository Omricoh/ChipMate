import apiClient from './client';
import type {
  SettleGameResponse,
  CheckoutPlayerResponse,
  CheckoutAllResponse,
  SettleDebtResponse,
  CloseGameResponse,
} from './types';

// ── Settlement API Functions ────────────────────────────────────────────────

/**
 * Move a game from OPEN to SETTLING status.
 * POST /api/games/{gameId}/settle
 */
export async function settleGame(
  gameId: string,
): Promise<SettleGameResponse> {
  const response = await apiClient.post<SettleGameResponse>(
    `/api/games/${gameId}/settle`,
  );
  return response.data;
}

/**
 * Check out a single player with their final chip count.
 * POST /api/games/{gameId}/players/{playerToken}/checkout
 */
export async function checkoutPlayer(
  gameId: string,
  playerToken: string,
  finalChipCount: number,
): Promise<CheckoutPlayerResponse> {
  const response = await apiClient.post<CheckoutPlayerResponse>(
    `/api/games/${gameId}/players/${playerToken}/checkout`,
    { final_chip_count: finalChipCount },
  );
  return response.data;
}

/**
 * Batch checkout all active players at once.
 * POST /api/games/{gameId}/checkout-all
 */
export async function checkoutAllPlayers(
  gameId: string,
  playerChips: Array<{ player_id: string; final_chip_count: number }>,
): Promise<CheckoutAllResponse> {
  const response = await apiClient.post<CheckoutAllResponse>(
    `/api/games/${gameId}/checkout-all`,
    { player_chips: playerChips },
  );
  return response.data;
}

/**
 * Mark a player's credit debt as settled.
 * POST /api/games/{gameId}/players/{playerToken}/settle-debt
 */
export async function settleDebt(
  gameId: string,
  playerToken: string,
): Promise<SettleDebtResponse> {
  const response = await apiClient.post<SettleDebtResponse>(
    `/api/games/${gameId}/players/${playerToken}/settle-debt`,
  );
  return response.data;
}

/**
 * Close a game (SETTLING -> CLOSED). All players must be checked out first.
 * POST /api/games/{gameId}/close
 */
export async function closeGame(
  gameId: string,
): Promise<CloseGameResponse> {
  const response = await apiClient.post<CloseGameResponse>(
    `/api/games/${gameId}/close`,
  );
  return response.data;
}
