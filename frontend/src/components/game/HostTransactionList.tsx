import { useState } from 'react';
import { EmptyState } from '../common/EmptyState';
import { RequestTypeBadge } from '../common/Badge';
import { RequestStatus, RequestType } from '../../api/types';
import type { ChipRequest } from '../../api/types';

interface HostTransactionListProps {
  requests: ChipRequest[];
  canManage: boolean;
  processingId: string | null;
  onUpdate: (requestId: string, newAmount: number, newType: RequestType) => void;
  onDelete: (requestId: string) => void;
}

export function HostTransactionList({
  requests,
  canManage,
  processingId,
  onUpdate,
  onDelete,
}: HostTransactionListProps) {
  if (requests.length === 0) {
    return (
      <EmptyState
        icon={<HistoryIcon />}
        message="No transactions yet"
        description="Approved buy-ins will appear here for the host."
      />
    );
  }

  return (
    <div className="space-y-3">
      {requests.map((request) => (
        <HostTransactionRow
          key={request.request_id}
          request={request}
          canManage={canManage}
          isProcessing={processingId === request.request_id}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

interface HostTransactionRowProps {
  request: ChipRequest;
  canManage: boolean;
  isProcessing: boolean;
  onUpdate: (requestId: string, newAmount: number, newType: RequestType) => void;
  onDelete: (requestId: string) => void;
}

function HostTransactionRow({
  request,
  canManage,
  isProcessing,
  onUpdate,
  onDelete,
}: HostTransactionRowProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [amount, setAmount] = useState(String(request.amount));
  const [type, setType] = useState<RequestType>(request.type);
  const [error, setError] = useState<string | null>(null);

  const handleCancel = () => {
    setIsEditing(false);
    setAmount(String(request.amount));
    setType(request.type);
    setError(null);
  };

  const handleSave = () => {
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError('Enter a valid amount greater than 0.');
      return;
    }
    setError(null);
    onUpdate(request.request_id, parsed, type);
    setIsEditing(false);
  };

  const originalAmountChanged =
    request.original_amount !== null && request.original_amount !== request.amount;
  const isEdited = request.status === RequestStatus.EDITED || originalAmountChanged;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold text-gray-900">
              {request.player_name}
            </p>
            <RequestTypeBadge type={request.type} />
            {isEdited && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                Edited
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-400">{formatDateTime(request.created_at)}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-lg font-bold tabular-nums text-gray-900">
            {request.amount.toLocaleString()}
          </p>
          {originalAmountChanged && request.original_amount !== null && (
            <p className="text-xs tabular-nums text-gray-400 line-through">
              {request.original_amount.toLocaleString()}
            </p>
          )}
        </div>
      </div>

      {isEditing ? (
        <div className="mt-3 space-y-2">
          <fieldset className="flex rounded-lg bg-gray-100 p-1">
            <legend className="sr-only">Transaction type</legend>
            <button
              type="button"
              onClick={() => setType(RequestType.CASH)}
              className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold ${
                type === RequestType.CASH
                  ? 'bg-white text-green-700 shadow-sm'
                  : 'text-gray-500'
              }`}
            >
              Cash
            </button>
            <button
              type="button"
              onClick={() => setType(RequestType.CREDIT)}
              className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold ${
                type === RequestType.CREDIT
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-gray-500'
              }`}
            >
              Credit
            </button>
          </fieldset>
          <div>
            <input
              type="number"
              min={1}
              onWheel={(e) => (e.target as HTMLElement).blur()}
              value={amount}
              onChange={(e) => {
                setAmount(e.target.value);
                if (error) setError(null);
              }}
              className={`w-full rounded-lg border px-3 py-2 text-sm tabular-nums focus:outline-none ${
                error ? 'border-red-400' : 'border-gray-300'
              }`}
            />
            {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={isProcessing}
              className="flex-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              Save
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={isProcessing}
              className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : canManage ? (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            disabled={isProcessing}
            className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => onDelete(request.request_id)}
            disabled={isProcessing}
            className="flex-1 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            Remove
          </button>
        </div>
      ) : (
        <p className="mt-3 text-xs text-gray-400">
          Transactions can only be edited while the game is open.
        </p>
      )}
    </div>
  );
}

function formatDateTime(isoString: string): string {
  return new Date(isoString).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function HistoryIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className="h-12 w-12"
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
      />
    </svg>
  );
}
