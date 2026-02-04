import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorBanner } from '../components/common/ErrorBanner';
import {
  ToastContainer,
  createToast,
  type ToastMessage,
} from '../components/common/Toast';
import { GameStatusBadge } from '../components/common/Badge';
import { PlayerStatusCard } from '../components/game/PlayerStatusCard';
import { ChipRequestForm } from '../components/game/ChipRequestForm';
import { RequestHistoryList } from '../components/game/RequestHistoryList';
import { NotificationPanel } from '../components/game/NotificationPanel';
import { ManagerDashboard } from '../components/game/ManagerDashboard';
import { BankSummaryCard } from '../components/game/BankSummaryCard';
import { GameProvider } from '../context/GameContext';
import { useGame } from '../hooks/useGame';
import { useAuth } from '../hooks/useAuth';
import { useNotifications } from '../hooks/useNotifications';
import { usePolling } from '../hooks/usePolling';
import { createChipRequest, getMyRequests } from '../api/requests';
import {
  GameStatus,
  RequestStatus,
  RequestType,
  type ChipRequest,
} from '../api/types';

// ── Player View ──────────────────────────────────────────────────────────────

function PlayerView({ gameId }: { gameId: string }) {
  const { user } = useAuth();
  const { game, isLoading: gameLoading, error: gameError, refreshGame } = useGame();

  // ── Notifications ────────────────────────────────────────────────────────
  const {
    notifications,
    unreadCount,
    isLoading: notificationsLoading,
    markAsRead,
    markAllAsRead,
  } = useNotifications(gameId);

  const [isNotificationPanelOpen, setIsNotificationPanelOpen] = useState(false);

  const handleNotificationTap = useCallback(() => {
    setIsNotificationPanelOpen((prev) => !prev);
  }, []);

  const handleMarkRead = useCallback(
    async (notificationId: string) => {
      try {
        await markAsRead(notificationId);
      } catch {
        // Silent -- optimistic update already applied in hook
      }
    },
    [markAsRead],
  );

  const handleMarkAllRead = useCallback(async () => {
    try {
      await markAllAsRead();
    } catch {
      // Silent
    }
  }, [markAllAsRead]);

  // ── Request History ──────────────────────────────────────────────────────
  const [requests, setRequests] = useState<ChipRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(true);

  const refreshRequests = useCallback(async () => {
    try {
      const list = await getMyRequests(gameId);

      // Sort newest first
      const sorted = [...list].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      setRequests(sorted);
    } catch {
      // Silently fail during polling; the game error state covers
      // hard failures (401, network down, etc.)
    } finally {
      setRequestsLoading(false);
    }
  }, [gameId]);

  usePolling(refreshRequests, 5_000);

  // ── Toasts ───────────────────────────────────────────────────────────────
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (variant: 'success' | 'error' | 'info', message: string) => {
      setToasts((prev) => [...prev, createToast(variant, message)]);
    },
    [],
  );

  // ── Chip Request Submit ──────────────────────────────────────────────────
  const handleChipRequest = useCallback(
    async (requestType: RequestType, amount: number) => {
      await createChipRequest(gameId, { type: requestType, amount });
      addToast(
        'success',
        `${requestType === 'CASH' ? 'Cash' : 'Credit'} request submitted!`,
      );
      // Immediately refresh so the new request appears in history
      await refreshRequests();
    },
    [gameId, addToast, refreshRequests],
  );

  // ── Derived Values ───────────────────────────────────────────────────────
  const playerName = user?.kind === 'player' ? user.name : 'Player';
  const gameCode = user?.kind === 'player' ? user.gameCode : undefined;

  // Calculate player totals from approved/edited requests.
  // The `amount` field on ChipRequest already reflects any edits
  // (the API layer maps edited_amount -> amount, original -> original_amount).
  const playerTotals = requests.reduce(
    (acc, req) => {
      if (
        req.status === RequestStatus.APPROVED ||
        req.status === RequestStatus.EDITED
      ) {
        if (req.type === RequestType.CASH) {
          acc.totalCashIn += req.amount;
        } else if (req.type === RequestType.CREDIT) {
          acc.totalCreditIn += req.amount;
          acc.creditsOwed += req.amount;
        }
      }
      return acc;
    },
    { totalCashIn: 0, totalCreditIn: 0, creditsOwed: 0 },
  );

  // ── Loading State ────────────────────────────────────────────────────────
  if (gameLoading && !game) {
    return (
      <Layout gameCode={gameCode}>
        <LoadingSpinner message="Loading game..." />
      </Layout>
    );
  }

  // ── Error State ──────────────────────────────────────────────────────────
  if (gameError && !game) {
    return (
      <Layout gameCode={gameCode}>
        <div className="py-8">
          <ErrorBanner message={gameError} onRetry={refreshGame} />
        </div>
      </Layout>
    );
  }

  const gameStatus = game?.game.status ?? GameStatus.OPEN;

  return (
    <Layout
      gameCode={gameCode}
      notificationCount={unreadCount}
      onNotificationTap={handleNotificationTap}
    >
      <div className="space-y-4">
        {/* Notification Panel (conditionally visible) */}
        {isNotificationPanelOpen && (
          <NotificationPanel
            notifications={notifications}
            isLoading={notificationsLoading}
            onMarkRead={handleMarkRead}
            onMarkAllRead={handleMarkAllRead}
            onClose={() => setIsNotificationPanelOpen(false)}
          />
        )}

        {/* Player Status Card */}
        <PlayerStatusCard
          playerName={playerName}
          totalCashIn={playerTotals.totalCashIn}
          totalCreditIn={playerTotals.totalCreditIn}
          creditsOwed={playerTotals.creditsOwed}
          gameStatus={gameStatus}
        />

        {/* Bank Summary */}
        {game && (
          <BankSummaryCard
            chips={game.chips}
            pendingRequests={game.pending_requests ?? 0}
            creditsOutstanding={game.credits_outstanding ?? 0}
          />
        )}

        {gameStatus === GameStatus.CLOSED && (
          <section className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-center space-y-3">
            <p className="text-sm font-medium text-gray-600">
              This game has been closed
            </p>
            <div className="flex flex-col gap-2">
              <Link
                to="/create"
                className="rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
              >
                Create New Game
              </Link>
              <Link
                to="/join"
                className="rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                Join a Game
              </Link>
            </div>
          </section>
        )}

        {/* Chip Request Form */}
        <ChipRequestForm
          gameStatus={gameStatus}
          onSubmit={handleChipRequest}
        />

        {/* Request History */}
        <section
          className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
          aria-label="Request history"
        >
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Request History
          </h2>
          {requestsLoading && requests.length === 0 ? (
            <LoadingSpinner size="sm" message="Loading requests..." />
          ) : (
            <RequestHistoryList requests={requests} />
          )}
        </section>

        {/* Game Info Footer */}
        {game && (
          <section
            className="rounded-xl bg-gray-50 border border-gray-200 p-4"
            aria-label="Game information"
          >
            <h2 className="text-sm font-semibold text-gray-700 mb-3">
              Game Info
            </h2>
            <dl className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-gray-500">Game Code</dt>
                <dd className="font-mono font-semibold tracking-widest text-gray-900 select-all">
                  {game.game.game_code}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-gray-500">Manager</dt>
                <dd className="font-medium text-gray-900">
                  {game.game.manager_name}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-gray-500">Players</dt>
                <dd className="font-medium text-gray-900">
                  {game.players.active} active
                  {game.players.checked_out > 0 && (
                    <span className="text-gray-400 ml-1">
                      ({game.players.checked_out} checked out)
                    </span>
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-gray-500">Status</dt>
                <dd>
                  <GameStatusBadge status={game.game.status} />
                </dd>
              </div>
            </dl>
          </section>
        )}
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  );
}

// ── GameView Page ────────────────────────────────────────────────────────────

export default function GameView() {
  const { gameId } = useParams<{ gameId: string }>();
  const { user, isManager } = useAuth();

  const gameCode = user?.kind === 'player' ? user.gameCode : undefined;

  // Guard: gameId is required (should always be present due to route config)
  if (!gameId) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
          <p className="text-gray-500">Invalid game URL</p>
        </div>
      </Layout>
    );
  }

  // ── Manager Dashboard ─────────────────────────────────────────────────

  if (isManager) {
    return (
      <GameProvider gameId={gameId}>
        <ManagerDashboard gameId={gameId} gameCode={gameCode} />
      </GameProvider>
    );
  }

  // ── Player View ─────────────────────────────────────────────────────────

  return (
    <GameProvider gameId={gameId}>
      <PlayerView gameId={gameId} />
    </GameProvider>
  );
}
