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
import { CheckoutPlayerModal } from './CheckoutPlayerModal';
import { BatchCheckoutModal } from './BatchCheckoutModal';
import { GameStatus } from '../../api/types';
import type { Player } from '../../api/types';
import {
  settleGame,
  checkoutPlayer,
  checkoutAllPlayers,
  settleDebt,
  closeGame,
} from '../../api/settlement';
import axios from 'axios';

interface ManagerDashboardProps {
  gameId: string;
  gameCode?: string;
}

/**
 * Extract a user-facing error message from an axios error or generic error.
 */
function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err) && err.response?.data) {
    const data = err.response.data as Record<string, unknown>;
    if (typeof data.detail === 'string') return data.detail;
    if (typeof data.message === 'string') return data.message;
    if (data.error && typeof (data.error as Record<string, unknown>).message === 'string') {
      return (data.error as Record<string, unknown>).message as string;
    }
  }
  return fallback;
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
  const [isSettleLoading, setIsSettleLoading] = useState(false);
  const [isCloseLoading, setIsCloseLoading] = useState(false);

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

  // ── Checkout Modal State ──────────────────────────────────────────────

  const [checkoutTarget, setCheckoutTarget] = useState<Player | null>(null);
  const [isCheckoutProcessing, setIsCheckoutProcessing] = useState(false);

  // ── Batch Checkout Modal State ────────────────────────────────────────

  const [isBatchCheckoutOpen, setIsBatchCheckoutOpen] = useState(false);
  const [isBatchCheckoutProcessing, setIsBatchCheckoutProcessing] = useState(false);

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

  // ── Settlement Action Handlers ────────────────────────────────────────

  const handleStartSettling = useCallback(() => {
    setConfirmModal({
      isOpen: true,
      title: 'Start Settling',
      message:
        'This will move the game to settling mode. Players will no longer be able to buy more chips. Are you ready to start cashing out?',
      confirmLabel: 'Start Settling',
      isDanger: false,
      onConfirm: async () => {
        closeModal();
        setIsSettleLoading(true);
        try {
          await settleGame(gameId);
          addToast(createToast('success', 'Game is now in settling mode'));
          await refreshGame();
        } catch (err) {
          addToast(
            createToast('error', getErrorMessage(err, 'Failed to start settling')),
          );
        } finally {
          setIsSettleLoading(false);
        }
      },
    });
  }, [gameId, addToast, closeModal, refreshGame]);

  const handleCloseGame = useCallback(() => {
    setConfirmModal({
      isOpen: true,
      title: 'Close Game',
      message:
        'This will permanently close the game. Make sure all players have been settled first. This action cannot be undone.',
      confirmLabel: 'Close Game',
      isDanger: true,
      onConfirm: async () => {
        closeModal();
        setIsCloseLoading(true);
        try {
          await closeGame(gameId);
          addToast(createToast('success', 'Game has been closed'));
          await refreshGame();
        } catch (err) {
          addToast(
            createToast('error', getErrorMessage(err, 'Failed to close game')),
          );
        } finally {
          setIsCloseLoading(false);
        }
      },
    });
  }, [gameId, addToast, closeModal, refreshGame]);

  // ── Checkout Handlers ─────────────────────────────────────────────────

  const handleCheckoutClick = useCallback((player: Player) => {
    setCheckoutTarget(player);
  }, []);

  const handleCheckoutSubmit = useCallback(
    async (finalChipCount: number) => {
      if (!checkoutTarget) return;

      setIsCheckoutProcessing(true);
      try {
        const result = await checkoutPlayer(
          gameId,
          checkoutTarget.player_id,
          finalChipCount,
        );
        const plSign = result.profit_loss >= 0 ? '+' : '';
        addToast(
          createToast(
            'success',
            `${result.player_name} checked out (${plSign}${result.profit_loss.toLocaleString()} P/L)`,
          ),
        );
        setCheckoutTarget(null);
        await refreshGame();
      } catch (err) {
        addToast(
          createToast(
            'error',
            getErrorMessage(err, `Failed to checkout ${checkoutTarget.name}`),
          ),
        );
      } finally {
        setIsCheckoutProcessing(false);
      }
    },
    [gameId, checkoutTarget, addToast, refreshGame],
  );

  const handleCheckoutCancel = useCallback(() => {
    setCheckoutTarget(null);
  }, []);

  // ── Batch Checkout Handlers ───────────────────────────────────────────

  const handleBatchCheckoutSubmit = useCallback(
    async (playerChips: Array<{ player_id: string; final_chip_count: number }>) => {
      setIsBatchCheckoutProcessing(true);
      try {
        const result = await checkoutAllPlayers(gameId, playerChips);
        addToast(
          createToast(
            'success',
            `Checked out ${result.summary.total_checked_out} player${result.summary.total_checked_out !== 1 ? 's' : ''}`,
          ),
        );
        setIsBatchCheckoutOpen(false);
        await refreshGame();
      } catch (err) {
        addToast(
          createToast(
            'error',
            getErrorMessage(err, 'Failed to batch checkout players'),
          ),
        );
      } finally {
        setIsBatchCheckoutProcessing(false);
      }
    },
    [gameId, addToast, refreshGame],
  );

  // ── Settle Debt Handler ───────────────────────────────────────────────

  const handleSettleDebt = useCallback(
    (player: Player) => {
      setConfirmModal({
        isOpen: true,
        title: 'Settle Debt',
        message: `Mark ${player.name}'s credit debt of ${player.credits_owed.toLocaleString()} as settled? This means they have repaid their credit.`,
        confirmLabel: 'Settle Debt',
        isDanger: false,
        onConfirm: async () => {
          closeModal();
          setProcessingId(player.player_id);
          try {
            const result = await settleDebt(gameId, player.player_id);
            addToast(
              createToast(
                'success',
                `${result.player_name}'s debt of ${result.previous_credits_owed.toLocaleString()} has been settled`,
              ),
            );
            await refreshGame();
          } catch (err) {
            addToast(
              createToast(
                'error',
                getErrorMessage(err, `Failed to settle debt for ${player.name}`),
              ),
            );
          } finally {
            setProcessingId(null);
          }
        },
      });
    },
    [gameId, addToast, closeModal, refreshGame],
  );

  // ── Loading State ─────────────────────────────────────────────────────

  const resolvedGameCode = gameCode ?? game?.game.game_code;

  if (isLoading) {
    return (
      <Layout gameCode={resolvedGameCode} notificationCount={unreadCount}>
        <LoadingSpinner message="Loading game..." />
      </Layout>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────

  if (error || !game) {
    return (
      <Layout gameCode={resolvedGameCode}>
        <ErrorBanner
          message={error ?? 'Could not load game data'}
          onRetry={refreshGame}
        />
      </Layout>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────

  const gameStatus = game.game.status;
  const bankSummary = game.chips ?? {
    total_cash_in: 0,
    total_credit_in: 0,
    total_in_play: 0,
    total_checked_out: 0,
  };
  const pendingRequestsCount = game.pending_requests ?? 0;
  const creditsOutstanding =
    typeof game.credits_outstanding === 'number' ? game.credits_outstanding : 0;
  const activePlayers = players.filter((p) => p.is_active && !p.checked_out);
  const checkedOutCount = players.filter((p) => p.checked_out).length;

  return (
    <Layout gameCode={resolvedGameCode} notificationCount={unreadCount}>
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
          chips={bankSummary}
          pendingRequests={pendingRequestsCount}
          creditsOutstanding={creditsOutstanding}
        />

        {/* Settling progress banner */}
        {gameStatus === GameStatus.SETTLING && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
            <p className="text-sm font-medium text-amber-800">
              Settling in progress
            </p>
            <p className="text-xs text-amber-600 mt-0.5">
              {checkedOutCount} of {players.length} players checked out
              {activePlayers.length > 0
                ? ` \u2014 ${activePlayers.length} remaining`
                : ' \u2014 all done!'}
            </p>
          </div>
        )}

        {/* Pending Requests -- only shown when game is OPEN */}
        {gameStatus === GameStatus.OPEN && (
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
        )}

        {/* Player List */}
        <section aria-label="Player list">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Players
              {players.length > 0 && (
                <span className="ml-2 text-xs font-normal text-gray-400">
                  ({players.length})
                </span>
              )}
            </h2>

            {/* Batch Checkout button -- only when settling and there are active players */}
            {gameStatus === GameStatus.SETTLING && activePlayers.length > 1 && (
              <button
                type="button"
                onClick={() => setIsBatchCheckoutOpen(true)}
                className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 active:bg-primary-800"
              >
                Checkout All
              </button>
            )}
          </div>

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
              <PlayerListCard
                players={players}
                gameStatus={gameStatus}
                processingPlayerId={processingId}
                onCheckout={handleCheckoutClick}
                onSettleDebt={handleSettleDebt}
              />
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
            {resolvedGameCode ? (
              <GameShareSection gameCode={resolvedGameCode} onToast={addToast} />
            ) : (
              <div className="rounded-xl bg-white border border-gray-200 shadow-sm p-4 text-sm text-gray-500">
                Loading game code...
              </div>
            )}

            {/* Status-dependent controls */}
            {gameStatus === GameStatus.OPEN && (
              <button
                type="button"
                onClick={handleStartSettling}
                disabled={isSettleLoading}
                className="w-full rounded-xl bg-amber-500 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 active:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSettleLoading ? 'Starting...' : 'Start Settling'}
              </button>
            )}

            {gameStatus === GameStatus.SETTLING && (
              <button
                type="button"
                onClick={handleCloseGame}
                disabled={isCloseLoading}
                className="w-full rounded-xl bg-red-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 active:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCloseLoading ? 'Closing...' : 'Close Game'}
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

      {/* Checkout Player Modal */}
      {checkoutTarget && (
        <CheckoutPlayerModal
          player={checkoutTarget}
          isOpen={true}
          isProcessing={isCheckoutProcessing}
          onSubmit={handleCheckoutSubmit}
          onCancel={handleCheckoutCancel}
        />
      )}

      {/* Batch Checkout Modal */}
      <BatchCheckoutModal
        players={activePlayers}
        isOpen={isBatchCheckoutOpen}
        isProcessing={isBatchCheckoutProcessing}
        onSubmit={handleBatchCheckoutSubmit}
        onCancel={() => setIsBatchCheckoutOpen(false)}
      />

      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  );
}
