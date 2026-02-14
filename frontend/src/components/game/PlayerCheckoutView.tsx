import { useCallback, useEffect, useState } from 'react';
import { submitChips, getPlayerActions } from '../../api/settlement';
import { getPlayerMe } from '../../api/games';
import { usePolling } from '../../hooks/usePolling';
import {
  CheckoutStatus,
  type Player,
  type PlayerAction,
  type FrozenBuyIn,
} from '../../api/types';
import { LoadingSpinner } from '../common/LoadingSpinner';

// ── Props ────────────────────────────────────────────────────────────────────

interface PlayerCheckoutViewProps {
  gameId: string;
  onToast: (variant: 'success' | 'error' | 'info', message: string) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatChips(value: number): string {
  return value.toLocaleString();
}

function plSign(value: number): string {
  if (value > 0) return `+${formatChips(value)}`;
  if (value < 0) return formatChips(value);
  return '0';
}

// ── Sub-Components ───────────────────────────────────────────────────────────

function FrozenBuyInSummary({ frozen }: { frozen: FrozenBuyIn }) {
  return (
    <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 space-y-1">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
        Your Buy-in
      </h4>
      <div className="flex justify-between text-sm">
        <span className="text-gray-600">Cash</span>
        <span className="font-medium text-gray-900">
          {formatChips(frozen.total_cash_in)}
        </span>
      </div>
      <div className="flex justify-between text-sm">
        <span className="text-gray-600">Credit</span>
        <span className="font-medium text-gray-900">
          {formatChips(frozen.total_credit_in)}
        </span>
      </div>
      <div className="flex justify-between text-sm font-semibold border-t border-gray-200 pt-1">
        <span className="text-gray-700">Total</span>
        <span className="text-gray-900">
          {formatChips(frozen.total_buy_in)}
        </span>
      </div>
    </div>
  );
}

function ChipSubmissionForm({
  frozenBuyIn,
  gameId,
  onToast,
  onSubmitted,
}: {
  frozenBuyIn: FrozenBuyIn | null;
  gameId: string;
  onToast: (variant: 'success' | 'error' | 'info', message: string) => void;
  onSubmitted: () => void;
}) {
  const [chipCount, setChipCount] = useState('');
  const [preferredCash, setPreferredCash] = useState('');
  const [preferredCredit, setPreferredCredit] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const chipCountNum = parseInt(chipCount, 10) || 0;
  const cashNum = parseInt(preferredCash, 10) || 0;
  const creditNum = parseInt(preferredCredit, 10) || 0;
  const splitValid = cashNum + creditNum === chipCountNum;

  // Auto-fill: when chip count changes, default all to cash
  useEffect(() => {
    const count = parseInt(chipCount, 10) || 0;
    if (count > 0) {
      setPreferredCash(String(count));
      setPreferredCredit('0');
    }
  }, [chipCount]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (chipCountNum <= 0) {
        onToast('error', 'Enter a valid chip count');
        return;
      }
      if (!splitValid) {
        onToast('error', 'Cash + Credit must equal your chip count');
        return;
      }
      setSubmitting(true);
      try {
        await submitChips(gameId, chipCountNum, cashNum, creditNum);
        onToast('success', 'Chip count submitted!');
        onSubmitted();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'Failed to submit chips';
        onToast('error', message);
      } finally {
        setSubmitting(false);
      }
    },
    [gameId, chipCountNum, cashNum, creditNum, splitValid, onToast, onSubmitted],
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}

      <div>
        <label
          htmlFor="chipCount"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Your Chip Count
        </label>
        <input
          id="chipCount"
          type="number"
          onWheel={(e) => (e.target as HTMLElement).blur()}
          min="0"
          value={chipCount}
          onChange={(e) => setChipCount(e.target.value)}
          placeholder="Enter total chips"
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="preferredCash"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Prefer Cash
          </label>
          <input
            id="preferredCash"
            type="number"
            onWheel={(e) => (e.target as HTMLElement).blur()}
            min="0"
            value={preferredCash}
            onChange={(e) => setPreferredCash(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          />
        </div>
        <div>
          <label
            htmlFor="preferredCredit"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Prefer Credit
          </label>
          <input
            id="preferredCredit"
            type="number"
            onWheel={(e) => (e.target as HTMLElement).blur()}
            min="0"
            value={preferredCredit}
            onChange={(e) => setPreferredCredit(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          />
        </div>
      </div>

      {chipCountNum > 0 && !splitValid && (
        <p className="text-xs text-red-500">
          Cash ({cashNum}) + Credit ({creditNum}) must equal chip count (
          {chipCountNum})
        </p>
      )}

      <button
        type="submit"
        disabled={submitting || chipCountNum <= 0 || !splitValid}
        className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitting ? 'Submitting...' : 'Submit Chip Count'}
      </button>
    </form>
  );
}

function ActionsList({ actions }: { actions: PlayerAction[] }) {
  if (actions.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
        Settlement Actions
      </h4>
      <ul className="space-y-1.5">
        {actions.map((action, idx) => {
          let text = '';
          if (action.type === 'receive_cash') {
            text = `Receive ${formatChips(action.amount)} cash`;
          } else if (action.type === 'receive_credit') {
            text = `Receive ${formatChips(action.amount)} credit from ${action.from ?? 'unknown'}`;
          } else if (action.type === 'pay_credit') {
            text = `Pay ${formatChips(action.amount)} to ${action.to ?? 'unknown'}`;
          }
          return (
            <li
              key={idx}
              className="flex items-center gap-2 text-sm text-gray-700 bg-gray-50 rounded-lg px-3 py-2"
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  action.type === 'pay_credit'
                    ? 'bg-red-400'
                    : 'bg-green-400'
                }`}
              />
              {text}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export function PlayerCheckoutView({ gameId, onToast }: PlayerCheckoutViewProps) {
  const [playerData, setPlayerData] = useState<Player | null>(null);
  const [actions, setActions] = useState<PlayerAction[]>([]);
  const [loading, setLoading] = useState(true);

  const refreshPlayerData = useCallback(async () => {
    try {
      const data = await getPlayerMe(gameId);
      setPlayerData(data);

      // Fetch actions when player is DONE
      if (data.checkout_status === CheckoutStatus.DONE) {
        try {
          const playerActions = await getPlayerActions(gameId);
          setActions(playerActions);
        } catch {
          // Actions may not be available yet
        }
      }
    } catch {
      // Silently fail during polling
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  usePolling(refreshPlayerData, 5_000);

  const handleSubmitted = useCallback(() => {
    refreshPlayerData();
  }, [refreshPlayerData]);

  if (loading && !playerData) {
    return (
      <section
        className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
        aria-label="Settlement"
      >
        <LoadingSpinner size="sm" message="Loading settlement data..." />
      </section>
    );
  }

  const status = playerData?.checkout_status ?? null;
  const frozenBuyIn = playerData?.frozen_buy_in ?? null;
  const inputLocked = playerData?.input_locked ?? false;

  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-sm p-4 space-y-4"
      aria-label="Settlement"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Settlement</h2>
        <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
          {status ?? 'PENDING'}
        </span>
      </div>

      {/* PENDING - Not locked: show submission form */}
      {(!status || (status === CheckoutStatus.PENDING && !inputLocked)) && (
        <ChipSubmissionForm
          frozenBuyIn={frozenBuyIn}
          gameId={gameId}
          onToast={onToast}
          onSubmitted={handleSubmitted}
        />
      )}

      {/* PENDING - Locked: manager is entering */}
      {status === CheckoutStatus.PENDING && inputLocked && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-center">
            <p className="text-sm text-blue-700 font-medium">
              Manager is entering your chip count
            </p>
          </div>
        </div>
      )}

      {/* SUBMITTED: waiting for validation */}
      {status === CheckoutStatus.SUBMITTED && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-center space-y-1">
            <p className="text-sm text-blue-700 font-medium">
              Waiting for manager to validate your submission
            </p>
            <p className="text-sm text-gray-600">
              You submitted: {formatChips(playerData?.submitted_chip_count ?? 0)} chips
            </p>
          </div>
        </div>
      )}

      {/* VALIDATED / CREDIT_DEDUCTED: show credit deduction summary */}
      {(status === CheckoutStatus.VALIDATED ||
        status === CheckoutStatus.CREDIT_DEDUCTED) && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-green-50 border border-green-200 p-3 space-y-2">
            <h4 className="text-xs font-semibold text-green-700 uppercase tracking-wider">
              Checkout Summary
            </h4>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Chips returned</span>
              <span className="font-medium text-gray-900">
                {formatChips(playerData?.validated_chip_count ?? 0)}
              </span>
            </div>
            {(playerData?.credit_repaid ?? 0) > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Credit deducted</span>
                <span className="font-medium text-red-600">
                  -{formatChips(playerData?.credit_repaid ?? 0)}
                </span>
              </div>
            )}
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Remaining chips</span>
              <span className="font-medium text-gray-900">
                {formatChips(playerData?.chips_after_credit ?? 0)}
              </span>
            </div>
            <div className="flex justify-between text-sm font-semibold border-t border-green-200 pt-1">
              <span className="text-gray-700">P/L</span>
              <span
                className={
                  (playerData?.profit_loss ?? 0) >= 0
                    ? 'text-green-600'
                    : 'text-red-600'
                }
              >
                {plSign(playerData?.profit_loss ?? 0)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* AWAITING_DISTRIBUTION */}
      {status === CheckoutStatus.AWAITING_DISTRIBUTION && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-center">
            <p className="text-sm text-amber-700 font-medium">
              Waiting for credit to become available
            </p>
          </div>
        </div>
      )}

      {/* DISTRIBUTED */}
      {status === CheckoutStatus.DISTRIBUTED && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-center">
            <p className="text-sm text-blue-700 font-medium">
              Distribution assigned, waiting for manager confirmation
            </p>
          </div>
        </div>
      )}

      {/* DONE: final summary */}
      {status === CheckoutStatus.DONE && (
        <div className="space-y-3">
          {frozenBuyIn && <FrozenBuyInSummary frozen={frozenBuyIn} />}
          <div className="rounded-lg bg-green-50 border border-green-200 p-3 space-y-2">
            <h4 className="text-xs font-semibold text-green-700 uppercase tracking-wider">
              Final Summary
            </h4>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Chips returned</span>
              <span className="font-medium text-gray-900">
                {formatChips(playerData?.validated_chip_count ?? 0)}
              </span>
            </div>
            {(playerData?.credit_repaid ?? 0) > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Credit deducted</span>
                <span className="font-medium text-red-600">
                  -{formatChips(playerData?.credit_repaid ?? 0)}
                </span>
              </div>
            )}
            <div className="flex justify-between text-sm font-semibold border-t border-green-200 pt-1">
              <span className="text-gray-700">P/L</span>
              <span
                className={
                  (playerData?.profit_loss ?? 0) >= 0
                    ? 'text-green-600'
                    : 'text-red-600'
                }
              >
                {plSign(playerData?.profit_loss ?? 0)}
              </span>
            </div>
          </div>
          <ActionsList actions={actions} />
        </div>
      )}
    </section>
  );
}
