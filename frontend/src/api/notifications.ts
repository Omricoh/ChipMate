import apiClient from './client';
import type { NotificationsResponse } from './types';

// ── Notification API Functions ──────────────────────────────────────────

/**
 * Get notifications for the authenticated player.
 * GET /api/games/{gameId}/notifications
 */
export async function getNotifications(
  gameId: string,
  unreadOnly = true,
  limit = 20,
): Promise<NotificationsResponse> {
  const response = await apiClient.get<NotificationsResponse>(
    `/api/games/${gameId}/notifications`,
    { params: { unread_only: unreadOnly, limit } },
  );
  return response.data;
}

/**
 * Mark a single notification as read.
 * POST /api/games/{gameId}/notifications/{notificationId}/read
 */
export async function markNotificationRead(
  gameId: string,
  notificationId: string,
): Promise<void> {
  await apiClient.post(
    `/api/games/${gameId}/notifications/${notificationId}/read`,
  );
}

/**
 * Mark all notifications as read for the current player.
 * POST /api/games/{gameId}/notifications/read-all
 */
export async function markAllNotificationsRead(
  gameId: string,
): Promise<{ marked_count: number }> {
  const response = await apiClient.post<{ marked_count: number }>(
    `/api/games/${gameId}/notifications/read-all`,
  );
  return response.data;
}
