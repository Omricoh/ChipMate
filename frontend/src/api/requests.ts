import apiClient from './client';
import type {
  ChipRequest,
  CreateChipRequestPayload,
} from './types';
import { RequestStatus, RequestType } from './types';

// ── Backend Response Shape ──────────────────────────────────────────────
// The backend returns a slightly different shape than our frontend types.
// We transform to the canonical ChipRequest interface at the API layer.

export interface ChipRequestResponse {
  id: string;
  game_id: string;
  player_token: string;
  requested_by: string;
  request_type: string;
  amount: number;
  status: string;
  edited_amount: number | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

/** @internal Alias for internal use */
type ChipRequestRaw = ChipRequestResponse;

function toChipRequest(raw: ChipRequestRaw): ChipRequest {
  return {
    request_id: raw.id,
    player_id: raw.player_token,
    player_name: raw.requested_by,
    type: raw.request_type as RequestType,
    amount: raw.edited_amount ?? raw.amount,
    original_amount: raw.edited_amount !== null ? raw.amount : null,
    status: raw.status as RequestStatus,
    created_at: raw.created_at,
    processed_at: raw.resolved_at,
    processed_by: raw.resolved_by,
    processed_by_name: null,
    note: null,
    auto_approved: false,
  };
}

// ── Chip Request API Functions ──────────────────────────────────────────

/**
 * Get all pending chip requests for a game (manager only).
 * GET /api/games/{gameId}/requests/pending
 */
export async function getPendingRequests(
  gameId: string,
): Promise<ChipRequest[]> {
  const response = await apiClient.get<ChipRequestRaw[]>(
    `/api/games/${gameId}/requests/pending`,
  );
  return response.data.map(toChipRequest);
}

/**
 * Approve a pending chip request (manager only).
 * POST /api/games/{gameId}/requests/{requestId}/approve
 */
export async function approveRequest(
  gameId: string,
  requestId: string,
): Promise<ChipRequest> {
  const response = await apiClient.post<ChipRequestRaw>(
    `/api/games/${gameId}/requests/${requestId}/approve`,
  );
  return toChipRequest(response.data);
}

/**
 * Decline a pending chip request (manager only).
 * POST /api/games/{gameId}/requests/{requestId}/decline
 */
export async function declineRequest(
  gameId: string,
  requestId: string,
): Promise<ChipRequest> {
  const response = await apiClient.post<ChipRequestRaw>(
    `/api/games/${gameId}/requests/${requestId}/decline`,
  );
  return toChipRequest(response.data);
}

/**
 * Edit the amount and approve a pending chip request (manager only).
 * POST /api/games/{gameId}/requests/{requestId}/edit
 */
export async function editAndApproveRequest(
  gameId: string,
  requestId: string,
  newAmount: number,
): Promise<ChipRequest> {
  const response = await apiClient.post<ChipRequestRaw>(
    `/api/games/${gameId}/requests/${requestId}/edit`,
    { new_amount: newAmount },
  );
  return toChipRequest(response.data);
}

/**
 * Create a new chip request.
 * POST /api/games/{gameId}/requests
 */
export async function createChipRequest(
  gameId: string,
  data: CreateChipRequestPayload,
): Promise<ChipRequest> {
  const response = await apiClient.post<ChipRequestRaw>(
    `/api/games/${gameId}/requests`,
    {
      request_type: data.type,
      amount: data.amount,
      on_behalf_of_player_id: data.on_behalf_of_player_id ?? undefined,
      note: data.note ?? undefined,
    },
  );
  return toChipRequest(response.data);
}

/**
 * Get the authenticated player's request history.
 * GET /api/games/{gameId}/requests/mine
 */
export async function getMyRequests(
  gameId: string,
): Promise<ChipRequest[]> {
  const response = await apiClient.get<ChipRequestRaw[]>(
    `/api/games/${gameId}/requests/mine`,
  );
  return response.data.map(toChipRequest);
}
