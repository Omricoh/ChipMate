import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

interface LayoutProps {
  children: ReactNode;
  /** Game code to display in the header */
  gameCode?: string;
  /** Unread notification count for the bell icon */
  notificationCount?: number;
  /** Callback when the notification bell is tapped */
  onNotificationTap?: () => void;
  /** Content to render in the fixed bottom bar */
  bottomBar?: ReactNode;
}

export function Layout({
  children,
  gameCode,
  notificationCount = 0,
  onNotificationTap,
  bottomBar,
}: LayoutProps) {
  const { user, isAdmin, isManager, logout } = useAuth();

  const roleBadge = isAdmin
    ? 'Admin'
    : isManager
      ? 'Manager'
      : user?.kind === 'player'
        ? 'Player'
        : null;

  const roleBadgeColor = isAdmin
    ? 'bg-purple-100 text-purple-800'
    : isManager
      ? 'bg-amber-100 text-amber-800'
      : 'bg-sky-100 text-sky-800';

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ── Header ────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 bg-white border-b border-gray-200 safe-top">
        <div className="max-w-lg mx-auto flex items-center justify-between px-4 h-14">
          {/* Left: Logo */}
          <Link
            to="/"
            className="text-xl font-bold text-primary-700 shrink-0"
            aria-label="ChipMate home"
          >
            ChipMate
          </Link>

          {/* Center: Game code */}
          {gameCode && (
            <span
              className="font-mono text-sm font-semibold tracking-widest text-gray-700 bg-gray-100 px-3 py-1 rounded-md select-all"
              aria-label={`Game code: ${gameCode.split('').join(', ')}`}
            >
              {gameCode}
            </span>
          )}

          {/* Right: Role badge + notification bell + logout */}
          <div className="flex items-center gap-2">
            {roleBadge && (
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full ${roleBadgeColor}`}
              >
                {roleBadge}
              </span>
            )}

            {onNotificationTap && (
              <button
                type="button"
                onClick={onNotificationTap}
                className="relative p-2 -mr-1 rounded-lg hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label={
                  notificationCount > 0
                    ? `${notificationCount} unread notification${notificationCount > 1 ? 's' : ''}`
                    : 'No unread notifications'
                }
              >
                {/* Bell icon (heroicons outline) */}
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-6 w-6 text-gray-600"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
                  />
                </svg>

                {notificationCount > 0 && (
                  <span
                    className="absolute -top-0.5 -right-0.5 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white"
                    aria-hidden="true"
                  >
                    {notificationCount > 99 ? '99+' : notificationCount}
                  </span>
                )}
              </button>
            )}

            {user && (
              <button
                type="button"
                onClick={logout}
                className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                Log out
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Main Content ──────────────────────────────────────────── */}
      <main
        className={`flex-1 max-w-lg mx-auto w-full px-4 py-6 ${bottomBar ? 'pb-24' : ''}`}
      >
        {children}
      </main>

      {/* ── Bottom Bar ────────────────────────────────────────────── */}
      {bottomBar && (
        <div className="fixed bottom-0 inset-x-0 z-20 bg-white border-t border-gray-200 safe-bottom">
          <div className="max-w-lg mx-auto px-4 py-3">{bottomBar}</div>
        </div>
      )}
    </div>
  );
}
