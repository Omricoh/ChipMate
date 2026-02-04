import { useEffect, useRef, useState } from 'react';
import type { Player } from '../../api/types';

interface CheckoutPlayerModalProps {
  /** The player being checked out */
  player: Player;
  /** Whether the modal is currently visible */
  isOpen: boolean;
  /** Whether the checkout request is in flight */
  isProcessing: boolean;
  /** Called with the final chip count when the manager submits */
  onSubmit: (finalChipCount: number) => void;
  /** Called when the manager cancels */
  onCancel: () => void;
}

/**
 * Modal dialog for entering a player's final chip count during checkout.
 * Displays the player's current chips as a reference, and calculates
 * a live P/L preview as the manager types.
 */
export function CheckoutPlayerModal({
  player,
  isOpen,
  isProcessing,
  onSubmit,
  onCancel,
}: CheckoutPlayerModalProps) {
  const [chipCount, setChipCount] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const totalCashIn = player.total_cash_in ?? 0;
  const creditsOwed = player.credits_owed ?? 0;
  const totalBuyIn = (player.total_cash_in ?? 0) + (player.total_credit_in ?? 0);

  // Focus the input when the modal opens and reset state
  useEffect(() => {
    if (isOpen) {
      setChipCount(String(player.current_chips));
      setValidationError(null);
      // Slight delay to allow the DOM to render
      requestAnimationFrame(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      });
    }
  }, [isOpen, player.current_chips]);

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

  const parsedCount = parseInt(chipCount, 10);
  const isValidNumber = chipCount.trim() !== '' && !isNaN(parsedCount) && parsedCount >= 0;
  const profitLoss = isValidNumber ? parsedCount - creditsOwed - totalCashIn : null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!isValidNumber) {
      setValidationError('Please enter a valid chip count (0 or higher)');
      return;
    }

    setValidationError(null);
    onSubmit(parsedCount);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="checkout-modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative w-full max-w-sm rounded-xl bg-white shadow-xl">
        <form onSubmit={handleSubmit}>
          <div className="p-6">
            <h2
              id="checkout-modal-title"
              className="text-lg font-semibold text-gray-900"
            >
              Checkout {player.name}
            </h2>

            {/* Player summary */}
            <div className="mt-3 rounded-lg bg-gray-50 p-3 space-y-1.5">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Total Buy-in</span>
                <span className="font-medium text-gray-900 tabular-nums">
                  {totalBuyIn.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Current Chips</span>
                <span className="font-medium text-gray-900 tabular-nums">
                  {player.current_chips.toLocaleString()}
                </span>
              </div>
              {player.credits_owed > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Credits Owed</span>
                  <span className="font-medium text-sky-700 tabular-nums">
                    {player.credits_owed.toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            {/* Final chip count input */}
            <label
              htmlFor="final-chip-count"
              className="mt-4 block text-sm font-medium text-gray-700"
            >
              Final Chip Count
            </label>
            <input
              ref={inputRef}
              id="final-chip-count"
              type="number"
              inputMode="numeric"
              min="0"
              step="1"
              value={chipCount}
              onChange={(e) => {
                setChipCount(e.target.value);
                setValidationError(null);
              }}
              disabled={isProcessing}
              className={`mt-1.5 block w-full rounded-lg border px-4 py-3 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                validationError
                  ? 'border-red-300 focus:ring-red-500'
                  : 'border-gray-300 focus:ring-primary-500'
              }`}
              aria-invalid={validationError ? 'true' : undefined}
              aria-describedby={validationError ? 'chip-count-error' : 'chip-count-preview'}
            />

            {validationError && (
              <p id="chip-count-error" className="mt-1.5 text-xs text-red-600">
                {validationError}
              </p>
            )}

            {/* Live P/L preview */}
            {profitLoss !== null && !validationError && (
              <p
                id="chip-count-preview"
                className={`mt-2 text-sm font-medium tabular-nums ${
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

          {/* Actions */}
          <div className="border-t border-gray-100 px-6 py-4 flex gap-3 justify-end">
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
              disabled={isProcessing || !isValidNumber}
              className="rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Processing...' : 'Checkout'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
