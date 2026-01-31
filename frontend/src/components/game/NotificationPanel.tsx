import type { Notification } from '../../api/types';

interface NotificationPanelProps {
  /** List of notifications to display */
  notifications: Notification[];
  /** Whether notification data is still loading */
  isLoading: boolean;
  /** Callback to mark a single notification as read */
  onMarkRead: (notificationId: string) => void;
  /** Callback to mark all notifications as read */
  onMarkAllRead: () => void;
  /** Callback to close/dismiss the panel */
  onClose: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1_000);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Notification Row ─────────────────────────────────────────────────────────

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
}) {
  const handleClick = () => {
    if (!notification.is_read) {
      onMarkRead(notification.notification_id);
    }
  };

  return (
    <li>
      <button
        type="button"
        onClick={handleClick}
        className={`w-full text-left px-4 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 ${
          notification.is_read
            ? 'bg-white'
            : 'bg-primary-50 hover:bg-primary-100'
        }`}
        aria-label={
          notification.is_read
            ? notification.message
            : `Unread: ${notification.message}. Tap to mark as read.`
        }
      >
        <div className="flex items-start gap-2.5">
          {/* Unread indicator dot */}
          <span
            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
              notification.is_read ? 'bg-transparent' : 'bg-primary-600'
            }`}
            aria-hidden="true"
          />

          <div className="flex-1 min-w-0">
            <p
              className={`text-sm leading-snug ${
                notification.is_read
                  ? 'text-gray-500'
                  : 'text-gray-900 font-medium'
              }`}
            >
              {notification.message}
            </p>
            <p className="mt-0.5 text-xs text-gray-400">
              {formatRelativeTime(notification.created_at)}
            </p>
          </div>
        </div>
      </button>
    </li>
  );
}

// ── Empty State ──────────────────────────────────────────────────────────────

function EmptyNotifications() {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center px-4">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        className="h-10 w-10 text-gray-300 mb-3"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
        />
      </svg>
      <p className="text-sm font-medium text-gray-500">All caught up</p>
      <p className="text-xs text-gray-400 mt-0.5">No notifications right now.</p>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

/**
 * A slide-down notification panel that displays the player's
 * notifications. Unread notifications are highlighted and can be
 * tapped to mark as read. Includes a "Mark all read" action.
 */
export function NotificationPanel({
  notifications,
  isLoading,
  onMarkRead,
  onMarkAllRead,
  onClose,
}: NotificationPanelProps) {
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-lg overflow-hidden"
      aria-label="Notifications"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-700">
          Notifications
          {unreadCount > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center h-5 min-w-[1.25rem] rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
              {unreadCount}
            </span>
          )}
        </h2>

        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={onMarkAllRead}
              className="text-xs font-medium text-primary-600 hover:text-primary-700 focus:outline-none focus-visible:underline"
            >
              Mark all read
            </button>
          )}

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label="Close notifications"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-4 w-4 text-gray-400"
              aria-hidden="true"
            >
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Notification list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
          <span className="sr-only">Loading notifications...</span>
        </div>
      ) : notifications.length === 0 ? (
        <EmptyNotifications />
      ) : (
        <ul
          className="max-h-80 overflow-y-auto divide-y divide-gray-50"
          role="list"
          aria-label="Notification list"
        >
          {notifications.map((notification) => (
            <NotificationRow
              key={notification.notification_id}
              notification={notification}
              onMarkRead={onMarkRead}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
