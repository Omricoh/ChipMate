import { useCallback, useState } from 'react';
import apiClient from '../api/client';
import type { Notification, NotificationsResponse } from '../api/types';
import { usePolling } from './usePolling';

interface UseNotificationsResult {
  notifications: Notification[];
  unreadCount: number;
  isLoading: boolean;
  error: string | null;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  refresh: () => Promise<void>;
}

const NOTIFICATION_POLL_INTERVAL_MS = 5_000;

/**
 * Polls unread notifications for the current game.
 * Pass `gameId` and `enabled` to control when polling is active.
 */
export function useNotifications(
  gameId: string | null,
  enabled = true,
): UseNotificationsResult {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!gameId) return;

    try {
      const res = await apiClient.get<NotificationsResponse>(
        `/api/v2/games/${gameId}/notifications`,
      );
      setNotifications(res.data.notifications);
      setUnreadCount(res.data.unread_count);
      setError(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load notifications';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [gameId]);

  usePolling(refresh, NOTIFICATION_POLL_INTERVAL_MS, enabled && !!gameId);

  const markAsRead = useCallback(
    async (notificationId: string) => {
      if (!gameId) return;

      await apiClient.post(
        `/api/v2/games/${gameId}/notifications/${notificationId}/read`,
      );
      setNotifications((prev) =>
        prev.map((n) =>
          n.notification_id === notificationId ? { ...n, is_read: true } : n,
        ),
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    },
    [gameId],
  );

  const markAllAsRead = useCallback(async () => {
    if (!gameId) return;

    await apiClient.post(`/api/v2/games/${gameId}/notifications/read-all`);
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  }, [gameId]);

  return {
    notifications,
    unreadCount,
    isLoading,
    error,
    markAsRead,
    markAllAsRead,
    refresh,
  };
}
