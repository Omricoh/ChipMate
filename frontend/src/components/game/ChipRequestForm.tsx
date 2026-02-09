import { useState } from 'react';
import { RequestType, GameStatus } from '../../api/types';
import { ErrorBanner } from '../common/ErrorBanner';
import { LoadingSpinner } from '../common/LoadingSpinner';

interface ChipRequestFormProps {
  /** Current game status -- form is disabled when not OPEN */
  gameStatus: GameStatus;
  /** Called when the player submits a valid request */
  onSubmit: (requestType: RequestType, amount: number) => Promise<void>;
}

/**
 * A form that lets a player request chip buy-ins.
 * The player selects CASH or CREDIT via toggle tabs, enters an
 * amount, and submits. The form resets on successful submission.
 * Disabled when the game is not in OPEN status.
 */
export function ChipRequestForm({ gameStatus, onSubmit }: ChipRequestFormProps) {
  const [requestType, setRequestType] = useState<RequestType | null>(null);
  const [amount, setAmount] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDisabled = gameStatus !== GameStatus.OPEN;
  const parsedAmount = Number(amount);
  const isValidAmount = amount.trim() !== '' && Number.isFinite(parsedAmount) && parsedAmount > 0;
  const isFormValid = requestType !== null && isValidAmount;

  const handleSubmit = async () => {
    if (requestType === null) {
      setError('Please select Cash or Credit.');
      return;
    }
    if (!isValidAmount) {
      setError('Please enter a valid amount greater than 0.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await onSubmit(requestType!, parsedAmount);
      // Reset form on success
      setRequestType(null);
      setAmount('');
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to submit request. Please try again.';
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSubmitting && !isDisabled) {
      handleSubmit();
    }
  };

  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
      aria-label="Request chips"
    >
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        Request Chips
      </h2>

      {isDisabled && (
        <div className="mb-3 rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
          <p className="text-xs text-gray-500">
            Chip requests are only available when the game is open.
          </p>
        </div>
      )}

      {error && (
        <div className="mb-3">
          <ErrorBanner message={error} />
        </div>
      )}

      {/* Request type toggle */}
      <fieldset className="mb-4" disabled={isDisabled || isSubmitting}>
        <legend className="sr-only">Request type</legend>
        <div className="flex rounded-lg bg-gray-100 p-1">
          <button
            type="button"
            onClick={() => setRequestType(RequestType.CASH)}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
              requestType === RequestType.CASH
                ? 'bg-white text-green-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
            aria-pressed={requestType === RequestType.CASH}
          >
            Cash
          </button>
          <button
            type="button"
            onClick={() => setRequestType(RequestType.CREDIT)}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
              requestType === RequestType.CREDIT
                ? 'bg-white text-sky-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
            aria-pressed={requestType === RequestType.CREDIT}
          >
            Credit
          </button>
        </div>
      </fieldset>

      {/* Amount input */}
      <div className="mb-4">
        <label
          htmlFor="chip-amount"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Amount
        </label>
        <input
          id="chip-amount"
          type="number"
          inputMode="numeric"
          min={1}
          step={1}
          value={amount}
          onChange={(e) => {
            setAmount(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Enter chip amount"
          disabled={isDisabled || isSubmitting}
          autoComplete="off"
          enterKeyHint="send"
          aria-invalid={error ? 'true' : undefined}
          className="w-full rounded-xl border-2 border-gray-300 px-4 py-3 text-lg tabular-nums placeholder:text-gray-400 focus:outline-none focus:ring-0 focus:border-primary-500 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed"
        />
      </div>

      {/* Submit button */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={isDisabled || isSubmitting || !isFormValid}
        className="w-full rounded-xl bg-primary-600 px-6 py-3.5 text-base font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {isSubmitting ? (
          <span className="flex items-center justify-center gap-2">
            <LoadingSpinner size="sm" />
            <span>Submitting...</span>
          </span>
        ) : requestType === null ? (
          'Request Chips'
        ) : (
          `Request ${requestType === RequestType.CASH ? 'Cash' : 'Credit'}`
        )}
      </button>
    </section>
  );
}
