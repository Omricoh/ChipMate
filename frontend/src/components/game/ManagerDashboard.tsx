import { useCallback, useState } from 'react';
import { useGame } from '../../hooks/useGame';
import { usePendingRequests } from '../../hooks/usePendingRequests';
import { useNotifications } from '../../hooks/useNotifications';
import { Layout } from '../common/Layout';
import { LoadingSpinner } from '../common/LoadingSpinner';
import { ErrorBanner } from '../common/ErrorBanner';
import { EmptyState } from '../common/EmptyState';
import { ConfirmModal } from '../common/ConfirmModal';
import { GameStatusBadge } from '../common/Badge';
import {
  ToastContainer,
  createToast,
  type ToastMessage,
} from '../common/Toast';
import { BankSummaryCard } from './BankSummaryCard';
import { PendingRequestCard } from './PendingRequestCard';
import { PlayerListCard } from './PlayerListCard';
import { GameShareSection } from './GameShareSection';
import { GameStatus } from '../../api/types';

interface ManagerDashboardProps {
  gameId: string;
  gameCode: string;
}

/**
 * Manager's primary game dashboard.
 * Composes the bank summary, pending request queue, player list,
 * and game controls into a single scrollable mobile-first layout.
 */
export function ManagerDashboard({ gameId, gameCode }: ManagerDashboardProps) {
  const { game, players, isLoading, error, refreshGame } = useGame();
  const {
    requests: pendingRequests,
    isLoading: isRequestsLoading,
    approve,
    decline,
    editApprove,
    refresh: refreshRequests,
  } = usePendingRequests(gameId);

  const { unreadCount } = useNotifications(gameId);

  // ── Toast State ───────────────────────────────────────────────────────

  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((toast: ToastMessage) => {
    setToasts((prev) => [...prev, toast]);
  }, []);

  // ── Processing State ──────────────────────────────────────────────────

  const [processingId, setProcessingId] = useState<string | null>(null);

  // ── Confirm Modal State ───────────────────────────────────────────────

  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    isDanger: boolean;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    confirmLabel: 'Confirm',
    isDanger: false,
    onConfirm: () => {},
  });

  const closeModal = useCallback(() => {
    setConfirmModal((prev) => ({ ...prev, isOpen: false }));
  }, []);

  // ── Request Action Handlers ───────────────────────────────────────────

  const handleApprove = useCallback(
    async (requestId: string) => {
      setProcessingId(requestId);
      try {
        await approve(requestId);
        addToast(createToast('success', 'Request approved'));
        refreshGame();
      } catch {
        addToast(createToast('error', 'Failed to approve request'));
        refreshRequests();
      } finally {
        setProcessingId(null);
      }
    },
    [approve, addToast, refreshGame, refreshRequests],
  );

  const handleDecline = useCallback(
    (requestId: string) => {
      const request = pendingRequests.find((r) => r.request_id === requestId);
      const playerName = request?.player_name ?? 'this player';

      setConfirmModal({
        isOpen: true,
        title: 'Decline Request',
        message: `Are you sure you want to decline the chip request from ${playerName}?`,
        confirmLabel: 'Decline',
        isDanger: true,
        onConfirm: async () => {
          closeModal();
          setProcessingId(requestId);
          try {
            await decline(requestId);
            addToast(createToast('info', 'Request declined'));
            refreshGame();
          } catch {
            addToast(createToast('error', 'Failed to decline request'));
            refreshRequests();
          } finally {
            setProcessingId(null);
          }
        },
      });
    },
    [pendingRequests, decline, addToast, closeModal, refreshGame, refreshRequests],
  );

  const handleEditApprove = useCallback(
    async (requestId: string, newAmount: number) => {
      setProcessingId(requestId);
      try {
        await editApprove(requestId, newAmount);
        addToast(createToast('success', `Approved with adjusted amount: ${newAmount.toLocaleString()}`));
        refreshGame();
      } catch {
        addToast(createToast('error', 'Failed to edit and approve request'));
        refreshRequests();
      } finally {
        setProcessingId(null);
      }
    },
    [editApprove, addToast, refreshGame, refreshRequests],
  );

  // ── Loading State ─────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <Layout gameCode={gameCode} notificationCount={unreadCount}>
        <LoadingSpinner message="Loading game..." />
      </Layout>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────

  if (error || !game) {
    return (
      <Layout gameCode={gameCode}>
        <ErrorBanner
          message={error ?? 'Could not load game data'}
          onRetry={refreshGame}
        />
      </Layout>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────

  const gameStatus = game.game.status;

  return (
    <Layout gameCode={gameCode} notificationCount={unreadCount}>
      <div className="space-y-6">
        {/* Game Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900">
              Game Dashboard
            </h1>
            <p className="text-xs text-gray-500">
              {game.players.total} player{game.players.total !== 1 ? 's' : ''}{' '}
              &middot; Managed by {game.game.manager_name}
            </p>
          </div>
          <GameStatusBadge status={gameStatus} />
        </div>

        {/* Bank Summary */}
        <BankSummaryCard
          chips={game.chips}
          pendingRequests={game.pending_requests}
          creditsOutstanding={game.credits_outstanding}
        />

        {/* Pending Requests */}
        <section aria-label="Pending chip requests">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Pending Requests
            </h2>
            {pendingRequests.length > 0 && (
              <span className="inline-flex items-center justify-center h-5 min-w-[1.25rem] rounded-full bg-amber-100 px-1.5 text-xs font-bold text-amber-800">
                {pendingRequests.length}
              </span>
            )}
          </div>

          {isRequestsLoading ? (
            <LoadingSpinner size="sm" />
          ) : pendingRequests.length === 0 ? (
            <EmptyState
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-10 w-10"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                  />
                </svg>
              }
              message="No pending requests"
              description="New chip requests from players will appear here"
            />
          ) : (
            <div className="space-y-3">
              {pendingRequests.map((request) => (
                <PendingRequestCard
                  key={request.request_id}
                  request={request}
                  onApprove={handleApprove}
                  onDecline={handleDecline}
                  onEditApprove={handleEditApprove}
                  isProcessing={processingId === request.request_id}
                />
              ))}
            </div>
          )}
        </section>

        {/* Player List */}
        <section aria-label="Player list">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Players
            {players.length > 0 && (
              <span className="ml-2 text-xs font-normal text-gray-400">
                ({players.length})
              </span>
            )}
          </h2>

          {players.length === 0 ? (
            <EmptyState
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-10 w-10"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z"
                  />
                </svg>
              }
              message="No players yet"
              description="Share the game code to invite players"
            />
          ) : (
            <div className="rounded-xl bg-white border border-gray-200 shadow-sm p-4">
              <PlayerListCard players={players} />
            </div>
          )}
        </section>

        {/* Game Controls */}
        <section aria-label="Game controls">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Game Controls
          </h2>

          <div className="space-y-4">
            {/* Share section -- always visible */}
            <GameShareSection gameCode={gameCode} onToast={addToast} />

            {/* Status-dependent controls */}
            {gameStatus === GameStatus.OPEN && (
              <button
                type="button"
                onClick={() => {
                  setConfirmModal({
                    isOpen: true,
                    title: 'Start Settling',
                    message:
                      'This will move the game to settling mode. Players will no longer be able to buy more chips. Are you ready to start cashing out?',
                    confirmLabel: 'Start Settling',
                    isDanger: false,
                    onConfirm: () => {
                      closeModal();
                      addToast(
                        createToast(
                          'info',
                          'Settling mode is not yet implemented',
                        ),
                      );
                    },
                  });
                }}
                className="w-full rounded-xl bg-amber-500 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 active:bg-amber-700"
              >
                Start Settling
              </button>
            )}

            {gameStatus === GameStatus.SETTLING && (
              <button
                type="button"
                onClick={() => {
                  setConfirmModal({
                    isOpen: true,
                    title: 'Close Game',
                    message:
                      'This will permanently close the game. Make sure all players have been settled first. This action cannot be undone.',
                    confirmLabel: 'Close Game',
                    isDanger: true,
                    onConfirm: () => {
                      closeModal();
                      addToast(
                        createToast(
                          'info',
                          'Close game is not yet implemented',
                        ),
                      );
                    },
                  });
                }}
                className="w-full rounded-xl bg-red-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 active:bg-red-800"
              >
                Close Game
              </button>
            )}

            {gameStatus === GameStatus.CLOSED && (
              <div className="rounded-xl bg-gray-100 px-6 py-4 text-center">
                <p className="text-sm font-medium text-gray-600">
                  This game has been closed
                </p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Confirm Modal */}
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        isDanger={confirmModal.isDanger}
        onConfirm={confirmModal.onConfirm}
        onCancel={closeModal}
      />

      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  );
}
