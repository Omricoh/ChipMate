import { useEffect, useMemo, useState } from 'react';
import type { Player } from '../../api/types';

interface AllocationRow {
  recipient_token: string;
  amount: string;
}

interface SettleDebtModalProps {
  debtor: Player;
  recipients: Player[];
  isOpen: boolean;
  isProcessing: boolean;
  onSubmit: (allocations: Array<{ recipient_token: string; amount: number }>) => void;
  onCancel: () => void;
}

export function SettleDebtModal({
  debtor,
  recipients,
  isOpen,
  isProcessing,
  onSubmit,
  onCancel,
}: SettleDebtModalProps) {
  const [rows, setRows] = useState<AllocationRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const availableRecipients = useMemo(
    () => recipients.filter((p) => p.player_id !== debtor.player_id),
    [recipients, debtor.player_id],
  );

  useEffect(() => {
    if (!isOpen) return;
    if (availableRecipients.length === 0) {
      setRows([]);
      return;
    }
    setRows([
      {
        recipient_token: availableRecipients[0].player_id,
        amount: String(debtor.credits_owed ?? 0),
      },
    ]);
    setError(null);
  }, [isOpen, availableRecipients, debtor.credits_owed]);

  if (!isOpen) return null;

  const usedTokens = new Set(rows.map((r) => r.recipient_token).filter(Boolean));
  const totalAllocated = rows.reduce((sum, row) => {
    const amount = Number(row.amount);
    return sum + (Number.isFinite(amount) ? amount : 0);
  }, 0);
  const remaining = (debtor.credits_owed ?? 0) - totalAllocated;

  const handleAddRow = () => {
    const nextRecipient = availableRecipients.find(
      (p) => !usedTokens.has(p.player_id),
    );
    if (!nextRecipient) return;
    setRows((prev) => [
      ...prev,
      { recipient_token: nextRecipient.player_id, amount: '' },
    ]);
  };

  const handleRemoveRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (rows.length === 0) {
      setError('Add at least one recipient.');
      return;
    }

    for (const row of rows) {
      const amount = Number(row.amount);
      if (!row.recipient_token) {
        setError('Select a recipient for each allocation.');
        return;
      }
      if (!Number.isFinite(amount) || amount <= 0) {
        setError('Each allocation must be greater than 0.');
        return;
      }
    }

    if (totalAllocated !== debtor.credits_owed) {
      setError('Allocated total must equal the debt amount.');
      return;
    }

    setError(null);
    onSubmit(
      rows.map((row) => ({
        recipient_token: row.recipient_token,
        amount: Number(row.amount),
      })),
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settle-debt-title"
    >
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onCancel}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg rounded-xl bg-white shadow-xl">
        <form onSubmit={handleSubmit}>
          <div className="p-6">
            <h2 id="settle-debt-title" className="text-lg font-semibold text-gray-900">
              Settle Debt for {debtor.name}
            </h2>

            <div className="mt-3 rounded-lg bg-gray-50 p-3 space-y-1.5">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Debt Amount</span>
                <span className="font-medium text-gray-900 tabular-nums">
                  {(debtor.credits_owed ?? 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Allocated</span>
                <span
                  className={`font-medium tabular-nums ${
                    remaining === 0 ? 'text-green-600' : 'text-amber-600'
                  }`}
                >
                  {totalAllocated.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Remaining</span>
                <span className="font-medium text-gray-900 tabular-nums">
                  {remaining.toLocaleString()}
                </span>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {rows.map((row, index) => {
                const usedByOthers = new Set(
                  rows
                    .filter((_, i) => i !== index)
                    .map((r) => r.recipient_token)
                    .filter(Boolean),
                );
                return (
                  <div key={index} className="grid grid-cols-5 gap-3 items-center">
                    <div className="col-span-3">
                      <label className="sr-only" htmlFor={`recipient-${index}`}>
                        Recipient
                      </label>
                      <select
                        id={`recipient-${index}`}
                        value={row.recipient_token}
                        onChange={(e) => {
                          const value = e.target.value;
                          setRows((prev) =>
                            prev.map((r, i) =>
                              i === index ? { ...r, recipient_token: value } : r,
                            ),
                          );
                          if (error) setError(null);
                        }}
                        disabled={isProcessing}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      >
                        {availableRecipients.map((player) => (
                          <option
                            key={player.player_id}
                            value={player.player_id}
                            disabled={usedByOthers.has(player.player_id)}
                          >
                            {player.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="col-span-2 flex items-center gap-2">
                      <label className="sr-only" htmlFor={`amount-${index}`}>
                        Amount
                      </label>
                      <input
                        id={`amount-${index}`}
                        type="number"
                        inputMode="numeric"
                        min={1}
                        step={1}
                        value={row.amount}
                        onChange={(e) => {
                          const value = e.target.value;
                          setRows((prev) =>
                            prev.map((r, i) =>
                              i === index ? { ...r, amount: value } : r,
                            ),
                          );
                          if (error) setError(null);
                        }}
                        disabled={isProcessing}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      {rows.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveRow(index)}
                          className="text-xs text-gray-400 hover:text-gray-600"
                          aria-label="Remove recipient"
                          disabled={isProcessing}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {availableRecipients.length > rows.length && (
              <button
                type="button"
                onClick={handleAddRow}
                disabled={isProcessing}
                className="mt-3 text-xs font-semibold text-primary-600 hover:text-primary-700"
              >
                Add recipient
              </button>
            )}

            {error && (
              <p className="mt-3 text-xs text-red-600">{error}</p>
            )}
          </div>

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
              disabled={isProcessing || remaining !== 0}
              className="rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Settling...' : 'Settle Debt'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
