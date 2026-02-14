import apiClient from './client';
import type {
  StartSettlingResponse,
  PoolStateResponse,
  DistributionSuggestion,
  PlayerAction,
  PlayerDistribution,
} from './types';

/** Start settling — transitions game from OPEN to SETTLING. */
export async function startSettling(gameId: string): Promise<StartSettlingResponse> {
  const response = await apiClient.post<StartSettlingResponse>(
    `/api/games/${gameId}/settlement/start`,
  );
  return response.data;
}

/** Player submits chip count and payout preferences. */
export async function submitChips(
  gameId: string,
  chipCount: number,
  preferredCash: number,
  preferredCredit: number,
): Promise<void> {
  await apiClient.post(`/api/games/${gameId}/settlement/submit-chips`, {
    chip_count: chipCount,
    preferred_cash: preferredCash,
    preferred_credit: preferredCredit,
  });
}

/** Manager rejects a player's submitted chip count. */
export async function rejectChips(
  gameId: string,
  playerToken: string,
): Promise<void> {
  await apiClient.post(
    `/api/games/${gameId}/settlement/reject-chips/${playerToken}`,
  );
}

/** Manager inputs chip count on behalf of a player. */
export async function managerInput(
  gameId: string,
  playerToken: string,
  chipCount: number,
  preferredCash: number,
  preferredCredit: number,
): Promise<void> {
  await apiClient.post(
    `/api/games/${gameId}/settlement/manager-input/${playerToken}`,
    {
      chip_count: chipCount,
      preferred_cash: preferredCash,
      preferred_credit: preferredCredit,
    },
  );
}

/** Get current pool state (cash/credit available). */
export async function getPoolState(
  gameId: string,
): Promise<PoolStateResponse> {
  const response = await apiClient.get<PoolStateResponse>(
    `/api/games/${gameId}/settlement/pool`,
  );
  return response.data;
}

/** Get distribution suggestion from algorithm. */
export async function getDistribution(
  gameId: string,
): Promise<DistributionSuggestion> {
  const response = await apiClient.get<DistributionSuggestion>(
    `/api/games/${gameId}/settlement/distribution`,
  );
  return response.data;
}

/** Manager overrides distribution for all players. */
export async function overrideDistribution(
  gameId: string,
  distribution: Record<string, PlayerDistribution>,
): Promise<void> {
  await apiClient.put(`/api/games/${gameId}/settlement/distribution`, {
    distribution,
  });
}

/** Confirm distribution for a player (marks DONE). */
export async function confirmDistribution(
  gameId: string,
  playerToken: string,
): Promise<void> {
  await apiClient.post(
    `/api/games/${gameId}/settlement/confirm/${playerToken}`,
  );
}

/** Get the authenticated player's settlement actions. */
export async function getPlayerActions(
  gameId: string,
): Promise<PlayerAction[]> {
  const response = await apiClient.get<PlayerAction[]>(
    `/api/games/${gameId}/settlement/actions`,
  );
  return response.data;
}

/** Player requests mid-game checkout during OPEN state. */
export async function requestCheckout(gameId: string): Promise<void> {
  await apiClient.post(`/api/games/${gameId}/settlement/checkout-request`);
}

/** Manager initiates mid-game checkout for a player. */
export async function managerCheckoutRequest(
  gameId: string,
  playerToken: string,
): Promise<void> {
  await apiClient.post(
    `/api/games/${gameId}/settlement/checkout-request/${playerToken}`,
  );
}

/** Close the game after all players are DONE. */
export async function closeGame(gameId: string): Promise<void> {
  await apiClient.post(`/api/games/${gameId}/settlement/close`);
}
