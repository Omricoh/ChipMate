import { useEffect, useRef, useState } from 'react';
import type { Player } from '../../api/types';

interface PlayerChipEntry {
  player_id: string;
  name: string;
  current_chips: number;
  total_buy_in: number;
  final_chip_count: string;
}

interface BatchCheckoutModalProps {
  /** Active (non-checked-out) players to batch checkout */
  players: Player[];
  /** Whether the modal is currently visible */
  isOpen: boolean;
  /** Whether the batch checkout request is in flight */
  isProcessing: boolean;
  /** Called with the player chip entries when the manager submits */
  onSubmit: (
    playerChips: Array<{ player_id: string; final_chip_count: number }>,
  ) => void;
  /** Called when the manager cancels */
  onCancel: () => void;
}

/**
 * Modal for batch-checking-out all active players at once.
 * Shows a form with one input per player, pre-filled with current chip counts.
 */
export function BatchCheckoutModal({
  players,
  isOpen,
  isProcessing,
  onSubmit,
  onCancel,
}: BatchCheckoutModalProps) {
  const [entries, setEntries] = useState<PlayerChipEntry[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  // Initialize entries when modal opens
  useEffect(() => {
    if (isOpen) {
      setEntries(
        players.map((p) => ({
          player_id: p.player_id,
          name: p.name,
          current_chips: p.current_chips,
          total_buy_in: p.total_cash_in + p.total_credit_in,
          final_chip_count: String(p.current_chips),
        })),
      );
      setValidationError(null);
      requestAnimationFrame(() => {
        firstInputRef.current?.focus();
        firstInputRef.current?.select();
      });
    }
  }, [isOpen, players]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const updateEntry = (index: number, value: string) => {
    setEntries((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], final_chip_count: value };
      return next;
    });
    setValidationError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const parsed: Array<{ player_id: string; final_chip_count: number }> = [];

    for (const entry of entries) {
      const count = parseInt(entry.final_chip_count, 10);
      if (isNaN(count) || count < 0) {
        setValidationError(
          `Invalid chip count for ${entry.name}. Please enter 0 or higher.`,
        );
        return;
      }
      parsed.push({ player_id: entry.player_id, final_chip_count: count });
    }

    setValidationError(null);
    onSubmit(parsed);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="batch-checkout-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative w-full max-w-md max-h-[85vh] flex flex-col rounded-xl bg-white shadow-xl">
        <form onSubmit={handleSubmit} className="flex flex-col min-h-0">
          {/* Header */}
          <div className="px-6 pt-6 pb-2 shrink-0">
            <h2
              id="batch-checkout-title"
              className="text-lg font-semibold text-gray-900"
            >
              Checkout All Players
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Enter the final chip count for each player.
            </p>
          </div>

          {/* Scrollable player list */}
          <div className="flex-1 overflow-y-auto px-6 py-3 space-y-4">
            {validationError && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                {validationError}
              </div>
            )}

            {entries.map((entry, index) => {
              const parsed = parseInt(entry.final_chip_count, 10);
              const isValid =
                entry.final_chip_count.trim() !== '' &&
                !isNaN(parsed) &&
                parsed >= 0;
              const profitLoss = isValid ? parsed - entry.total_buy_in : null;

              return (
                <div key={entry.player_id} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label
                      htmlFor={`batch-chips-${entry.player_id}`}
                      className="text-sm font-medium text-gray-900"
                    >
                      {entry.name}
                    </label>
                    <span className="text-xs text-gray-400 tabular-nums">
                      Buy-in: {entry.total_buy_in.toLocaleString()}
                    </span>
                  </div>

                  <input
                    ref={index === 0 ? firstInputRef : undefined}
                    id={`batch-chips-${entry.player_id}`}
                    type="number"
                    inputMode="numeric"
                    min="0"
                    step="1"
                    value={entry.final_chip_count}
                    onChange={(e) => updateEntry(index, e.target.value)}
                    disabled={isProcessing}
                    className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1"
                  />

                  {profitLoss !== null && (
                    <p
                      className={`text-xs font-medium tabular-nums ${
                        profitLoss > 0
                          ? 'text-green-600'
                          : profitLoss < 0
                            ? 'text-red-600'
                            : 'text-gray-500'
                      }`}
                    >
                      {profitLoss > 0 ? '+' : ''}
                      {profitLoss.toLocaleString()} P/L
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Actions */}
          <div className="border-t border-gray-100 px-6 py-4 flex gap-3 justify-end shrink-0">
            <button
              type="button"
              onClick={onCancel}
              disabled={isProcessing}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 disabled:opacity-50"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isProcessing || entries.length === 0}
              className="rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing
                ? 'Processing...'
                : `Checkout ${entries.length} Player${entries.length !== 1 ? 's' : ''}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
