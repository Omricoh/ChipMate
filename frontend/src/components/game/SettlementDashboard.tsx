import { useCallback, useEffect, useState } from 'react';
import { Badge } from '../common/Badge';
import {
  validateChips,
  rejectChips,
  managerInput,
  getPoolState,
  getDistribution,
  overrideDistribution,
  confirmDistribution,
  closeGame,
} from '../../api/settlement';
import type {
  CheckoutStatus,
  Player,
  PoolStateResponse,
  DistributionSuggestion,
} from '../../api/types';
import type { ToastMessage } from '../common/Toast';
import { createToast } from '../common/Toast';
import axios from 'axios';

interface SettlementDashboardProps {
  gameId: string;
  players: Player[];
  onToast: (toast: ToastMessage) => void;
  refreshGame: () => void;
}

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

function checkoutStatusBadge(status: CheckoutStatus | null | undefined) {
  const map: Record<string, { label: string; color: 'gray' | 'amber' | 'sky' | 'purple' | 'green' }> = {
    PENDING: { label: 'Waiting for input', color: 'gray' },
    SUBMITTED: { label: 'Submitted', color: 'amber' },
    VALIDATED: { label: 'Validated', color: 'sky' },
    CREDIT_DEDUCTED: { label: 'Credit Deducted', color: 'purple' },
    AWAITING_DISTRIBUTION: { label: 'Awaiting Distribution', color: 'amber' },
    DISTRIBUTED: { label: 'Distribution Assigned', color: 'sky' },
    DONE: { label: 'Done', color: 'green' },
  };
  const entry = map[status ?? 'PENDING'] ?? { label: status ?? 'Unknown', color: 'gray' as const };
  return <Badge label={entry.label} color={entry.color} />;
}

function sortPlayers(players: Player[]): Player[] {
  return [...players].sort((a, b) => {
    if (a.is_manager && !b.is_manager) return -1;
    if (!a.is_manager && b.is_manager) return 1;
    return a.name.localeCompare(b.name);
  });
}

export function SettlementDashboard({
  gameId,
  players,
  onToast,
  refreshGame,
}: SettlementDashboardProps) {
  // ── Pool State ──────────────────────────────────────────────────────────
  const [pool, setPool] = useState<PoolStateResponse | null>(null);

  const fetchPool = useCallback(async () => {
    try {
      const data = await getPoolState(gameId);
      setPool(data);
    } catch {
      // silent – pool display is informational
    }
  }, [gameId]);

  useEffect(() => {
    fetchPool();
  }, [fetchPool]);

  // ── Manager Input Form State ────────────────────────────────────────────
  const [inputPlayer, setInputPlayer] = useState('');
  const [inputChips, setInputChips] = useState('');
  const [inputCash, setInputCash] = useState('');
  const [inputCredit, setInputCredit] = useState('');
  const [inputLoading, setInputLoading] = useState(false);

  // ── Distribution State ──────────────────────────────────────────────────
  const [suggestion, setSuggestion] = useState<DistributionSuggestion | null>(null);
  const [suggestionText, setSuggestionText] = useState('');
  const [distLoading, setDistLoading] = useState(false);
  const [applied, setApplied] = useState(false);

  // ── Loading tracker for per-player actions ──────────────────────────────
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const sortedPlayers = sortPlayers(players);
  const pendingPlayers = sortedPlayers.filter(
    (p) => !p.checkout_status || p.checkout_status === 'PENDING',
  );
  const allCreditDeductedOrLater = sortedPlayers.length > 0 && sortedPlayers.every(
    (p) =>
      p.checkout_status === 'CREDIT_DEDUCTED' ||
      p.checkout_status === 'AWAITING_DISTRIBUTION' ||
      p.checkout_status === 'DISTRIBUTED' ||
      p.checkout_status === 'DONE',
  );
  const allDone = sortedPlayers.length > 0 && sortedPlayers.every(
    (p) => p.checkout_status === 'DONE',
  );

  // ── Action Handlers ─────────────────────────────────────────────────────

  const handleValidate = useCallback(
    async (playerToken: string) => {
      setActionLoading(playerToken);
      try {
        await validateChips(gameId, playerToken);
        onToast(createToast('success', 'Chips validated'));
        refreshGame();
        fetchPool();
      } catch (err) {
        onToast(createToast('error', getErrorMessage(err, 'Failed to validate')));
      } finally {
        setActionLoading(null);
      }
    },
    [gameId, onToast, refreshGame, fetchPool],
  );

  const handleReject = useCallback(
    async (playerToken: string) => {
      setActionLoading(playerToken);
      try {
        await rejectChips(gameId, playerToken);
        onToast(createToast('info', 'Chips rejected'));
        refreshGame();
        fetchPool();
      } catch (err) {
        onToast(createToast('error', getErrorMessage(err, 'Failed to reject')));
      } finally {
        setActionLoading(null);
      }
    },
    [gameId, onToast, refreshGame, fetchPool],
  );

  const handleManagerInput = useCallback(async () => {
    if (!inputPlayer) return;
    const chips = Number(inputChips);
    const cash = Number(inputCash);
    const credit = Number(inputCredit);
    if (!Number.isFinite(chips) || chips < 0) {
      onToast(createToast('error', 'Enter a valid chip count'));
      return;
    }
    setInputLoading(true);
    try {
      await managerInput(gameId, inputPlayer, chips, cash || 0, credit || 0);
      onToast(createToast('success', 'Input submitted'));
      setInputChips('');
      setInputCash('');
      setInputCredit('');
      refreshGame();
      fetchPool();
    } catch (err) {
      onToast(createToast('error', getErrorMessage(err, 'Failed to submit input')));
    } finally {
      setInputLoading(false);
    }
  }, [gameId, inputPlayer, inputChips, inputCash, inputCredit, onToast, refreshGame, fetchPool]);

  const handleGetSuggestion = useCallback(async () => {
    setDistLoading(true);
    try {
      const data = await getDistribution(gameId);
      setSuggestion(data);
      setSuggestionText(JSON.stringify(data, null, 2));
      setApplied(false);
    } catch (err) {
      onToast(createToast('error', getErrorMessage(err, 'Failed to get distribution')));
    } finally {
      setDistLoading(false);
    }
  }, [gameId, onToast]);

  const handleApplyDistribution = useCallback(async () => {
    setDistLoading(true);
    try {
      const parsed = JSON.parse(suggestionText);
      await overrideDistribution(gameId, parsed);
      onToast(createToast('success', 'Distribution applied'));
      setApplied(true);
      refreshGame();
      fetchPool();
    } catch (err) {
      onToast(createToast('error', getErrorMessage(err, 'Failed to apply distribution')));
    } finally {
      setDistLoading(false);
    }
  }, [gameId, suggestionText, onToast, refreshGame, fetchPool]);

  const handleConfirm = useCallback(
    async (playerToken: string) => {
      setActionLoading(playerToken);
      try {
        await confirmDistribution(gameId, playerToken);
        onToast(createToast('success', 'Player confirmed'));
        refreshGame();
        fetchPool();
      } catch (err) {
        onToast(createToast('error', getErrorMessage(err, 'Failed to confirm')));
      } finally {
        setActionLoading(null);
      }
    },
    [gameId, onToast, refreshGame, fetchPool],
  );

  const handleCloseGame = useCallback(async () => {
    try {
      await closeGame(gameId);
      onToast(createToast('success', 'Game closed'));
      refreshGame();
    } catch (err) {
      onToast(createToast('error', getErrorMessage(err, 'Failed to close game')));
    }
  }, [gameId, onToast, refreshGame]);

  // Set default player for input form
  useEffect(() => {
    if (pendingPlayers.length > 0 && !inputPlayer) {
      setInputPlayer(pendingPlayers[0].player_id);
    }
  }, [pendingPlayers, inputPlayer]);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Pool Status Bar */}
      <section className="rounded-xl bg-white border border-gray-200 shadow-sm p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Pool Status</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-500">Cash Available</p>
            <p className="text-lg font-bold text-green-700 tabular-nums">
              {pool ? pool.cash_pool.toLocaleString() : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Credit Available</p>
            <p className="text-lg font-bold text-sky-700 tabular-nums">
              {pool ? pool.credit_pool.toLocaleString() : '—'}
            </p>
          </div>
        </div>
      </section>

      {/* Player Checkout List */}
      <section className="rounded-xl bg-white border border-gray-200 shadow-sm p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Player Checkout</h2>
        <div className="space-y-3">
          {sortedPlayers.map((player) => (
            <div
              key={player.player_id}
              className="rounded-lg border border-gray-100 bg-gray-50 p-3"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900">
                  {player.name}
                  {player.is_manager && (
                    <span className="ml-1 text-xs text-gray-400">(Manager)</span>
                  )}
                </span>
                {checkoutStatusBadge(player.checkout_status as CheckoutStatus | null)}
              </div>

              {/* SUBMITTED: show chip count and validate/reject */}
              {player.checkout_status === 'SUBMITTED' && (
                <div className="mt-2 space-y-2">
                  <p className="text-xs text-gray-600">
                    Submitted chips:{' '}
                    <span className="font-semibold">
                      {player.submitted_chip_count?.toLocaleString() ?? '—'}
                    </span>
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleValidate(player.player_id)}
                      disabled={actionLoading === player.player_id}
                      className="flex-1 rounded-lg bg-green-600 px-3 py-2 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-60"
                    >
                      Validate
                    </button>
                    <button
                      type="button"
                      onClick={() => handleReject(player.player_id)}
                      disabled={actionLoading === player.player_id}
                      className="flex-1 rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}

              {/* CREDIT_DEDUCTED: show credit math */}
              {player.checkout_status === 'CREDIT_DEDUCTED' && (
                <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                  <p>
                    P/L:{' '}
                    <span
                      className={`font-semibold ${
                        (player.profit_loss ?? 0) >= 0 ? 'text-green-700' : 'text-red-700'
                      }`}
                    >
                      {(player.profit_loss ?? 0) >= 0 ? '+' : ''}
                      {player.profit_loss?.toLocaleString() ?? '0'}
                    </span>
                  </p>
                  <p>
                    Credit repaid:{' '}
                    <span className="font-semibold">
                      {player.credit_repaid?.toLocaleString() ?? '0'}
                    </span>
                  </p>
                  <p>
                    Chips after credit:{' '}
                    <span className="font-semibold">
                      {player.chips_after_credit?.toLocaleString() ?? '0'}
                    </span>
                  </p>
                </div>
              )}

              {/* DISTRIBUTED */}
              {player.checkout_status === 'DISTRIBUTED' && (
                <div className="mt-2 flex items-center justify-between">
                  <p className="text-xs text-gray-500">Distribution assigned</p>
                  <button
                    type="button"
                    onClick={() => handleConfirm(player.player_id)}
                    disabled={actionLoading === player.player_id}
                    className="rounded-lg bg-primary-600 px-3 py-2 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
                  >
                    Confirm
                  </button>
                </div>
              )}

              {/* DONE */}
              {player.checkout_status === 'DONE' && (
                <div className="mt-2 flex items-center gap-2">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="h-4 w-4 text-green-600"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm3.857-9.809a.75.75 0 0 0-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 1 0-1.06 1.061l2.5 2.5a.75.75 0 0 0 1.137-.089l4-5.5Z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <span className="text-xs text-gray-600">
                    P/L:{' '}
                    <span
                      className={`font-semibold ${
                        (player.profit_loss ?? 0) >= 0 ? 'text-green-700' : 'text-red-700'
                      }`}
                    >
                      {(player.profit_loss ?? 0) >= 0 ? '+' : ''}
                      {player.profit_loss?.toLocaleString() ?? '0'}
                    </span>
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Manager Input Form */}
      {pendingPlayers.length > 0 && (
        <section className="rounded-xl bg-white border border-gray-200 shadow-sm p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            Input on Behalf of Player
          </h2>
          <div className="space-y-3">
            <div>
              <label
                htmlFor="settlement-input-player"
                className="block text-sm font-medium text-gray-700 mb-1.5"
              >
                Player
              </label>
              <select
                id="settlement-input-player"
                value={inputPlayer}
                onChange={(e) => setInputPlayer(e.target.value)}
                disabled={inputLoading}
                className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-0 focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-400"
              >
                {pendingPlayers.map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    {p.name}
                    {p.is_manager ? ' (Manager)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="settlement-input-chips"
                className="block text-sm font-medium text-gray-700 mb-1.5"
              >
                Chip Count
              </label>
              <input
                id="settlement-input-chips"
                type="number"
                onWheel={(e) => (e.target as HTMLElement).blur()}
                inputMode="numeric"
                min={0}
                step={1}
                value={inputChips}
                onChange={(e) => setInputChips(e.target.value)}
                disabled={inputLoading}
                placeholder="Enter chip count"
                className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-lg tabular-nums placeholder:text-gray-400 focus:outline-none focus:ring-0 focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="settlement-input-cash"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  Preferred Cash
                </label>
                <input
                  id="settlement-input-cash"
                  type="number"
                  onWheel={(e) => (e.target as HTMLElement).blur()}
                  inputMode="numeric"
                  min={0}
                  step={1}
                  value={inputCash}
                  onChange={(e) => setInputCash(e.target.value)}
                  disabled={inputLoading}
                  placeholder="0"
                  className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-sm tabular-nums placeholder:text-gray-400 focus:outline-none focus:ring-0 focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-400"
                />
              </div>
              <div>
                <label
                  htmlFor="settlement-input-credit"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  Preferred Credit
                </label>
                <input
                  id="settlement-input-credit"
                  type="number"
                  onWheel={(e) => (e.target as HTMLElement).blur()}
                  inputMode="numeric"
                  min={0}
                  step={1}
                  value={inputCredit}
                  onChange={(e) => setInputCredit(e.target.value)}
                  disabled={inputLoading}
                  placeholder="0"
                  className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-sm tabular-nums placeholder:text-gray-400 focus:outline-none focus:ring-0 focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-400"
                />
              </div>
            </div>

            <button
              type="button"
              onClick={handleManagerInput}
              disabled={inputLoading || !inputPlayer}
              className="w-full rounded-xl bg-primary-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {inputLoading ? 'Submitting...' : 'Submit Input'}
            </button>
          </div>
        </section>
      )}

      {/* Distribution Section */}
      {allCreditDeductedOrLater && (
        <section className="rounded-xl bg-white border border-gray-200 shadow-sm p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Distribution</h2>
          <div className="space-y-3">
            {!suggestion && (
              <button
                type="button"
                onClick={handleGetSuggestion}
                disabled={distLoading}
                className="w-full rounded-xl bg-sky-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 disabled:opacity-60"
              >
                {distLoading ? 'Loading...' : 'Get Suggestion'}
              </button>
            )}

            {suggestion && (
              <>
                <label
                  htmlFor="distribution-json"
                  className="block text-sm font-medium text-gray-700"
                >
                  Distribution JSON
                </label>
                <textarea
                  id="distribution-json"
                  value={suggestionText}
                  onChange={(e) => setSuggestionText(e.target.value)}
                  rows={8}
                  className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-xs font-mono tabular-nums focus:outline-none focus:ring-0 focus:border-primary-500"
                />

                {!applied && (
                  <button
                    type="button"
                    onClick={handleApplyDistribution}
                    disabled={distLoading}
                    className="w-full rounded-xl bg-primary-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-60"
                  >
                    {distLoading ? 'Applying...' : 'Apply Distribution'}
                  </button>
                )}
              </>
            )}
          </div>
        </section>
      )}

      {/* Close Game */}
      {allDone && (
        <button
          type="button"
          onClick={handleCloseGame}
          className="w-full rounded-xl bg-red-600 px-6 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 active:bg-red-800"
        >
          Close Game
        </button>
      )}
    </div>
  );
}
