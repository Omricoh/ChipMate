import { useCallback, useState } from 'react';
import type { ChipRequest } from '../api/types';
import {
  getPendingRequests,
  approveRequest,
  declineRequest,
  editAndApproveRequest,
} from '../api/requests';
import { usePolling } from './usePolling';

interface UsePendingRequestsResult {
  requests: ChipRequest[];
  isLoading: boolean;
  error: string | null;
  /** Approve a pending request */
  approve: (requestId: string) => Promise<void>;
  /** Decline a pending request */
  decline: (requestId: string) => Promise<void>;
  /** Edit the amount and approve a pending request */
  editApprove: (requestId: string, newAmount: number) => Promise<void>;
  /** Force a refresh of pending requests */
  refresh: () => Promise<void>;
}

const POLL_INTERVAL_MS = 5_000;

/**
 * Polls pending chip requests for a game and exposes approve/decline/edit actions.
 * Designed for manager use only.
 */
export function usePendingRequests(
  gameId: string | null,
  enabled = true,
): UsePendingRequestsResult {
  const [requests, setRequests] = useState<ChipRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!gameId) return;

    try {
      const data = await getPendingRequests(gameId);
      setRequests(data);
      setError(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load pending requests';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [gameId]);

  usePolling(refresh, POLL_INTERVAL_MS, enabled && !!gameId);

  const approve = useCallback(
    async (requestId: string) => {
      if (!gameId) return;
      await approveRequest(gameId, requestId);
      // Optimistic removal
      setRequests((prev) =>
        prev.filter((r) => r.request_id !== requestId),
      );
    },
    [gameId],
  );

  const decline = useCallback(
    async (requestId: string) => {
      if (!gameId) return;
      await declineRequest(gameId, requestId);
      // Optimistic removal
      setRequests((prev) =>
        prev.filter((r) => r.request_id !== requestId),
      );
    },
    [gameId],
  );

  const editApprove = useCallback(
    async (requestId: string, newAmount: number) => {
      if (!gameId) return;
      await editAndApproveRequest(gameId, requestId, newAmount);
      // Optimistic removal
      setRequests((prev) =>
        prev.filter((r) => r.request_id !== requestId),
      );
    },
    [gameId],
  );

  return {
    requests,
    isLoading,
    error,
    approve,
    decline,
    editApprove,
    refresh,
  };
}
