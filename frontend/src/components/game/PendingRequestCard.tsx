import { useState } from 'react';
import { RequestTypeBadge } from '../common/Badge';
import { RequestType } from '../../api/types';
import type { ChipRequest } from '../../api/types';

interface PendingRequestCardProps {
  request: ChipRequest;
  /** Called when the manager taps Approve */
  onApprove: (requestId: string) => void;
  /** Called when the manager taps Decline */
  onDecline: (requestId: string) => void;
  /** Called when the manager edits the amount and confirms */
  onEditApprove: (requestId: string, newAmount: number, newType: RequestType) => void;
  /** Whether any action is currently processing */
  isProcessing?: boolean;
}

/**
 * Card displaying a single pending chip request with
 * approve, decline, and edit-approve actions.
 */
export function PendingRequestCard({
  request,
  onApprove,
  onDecline,
  onEditApprove,
  isProcessing = false,
}: PendingRequestCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editAmount, setEditAmount] = useState(String(request.amount));
  const [editType, setEditType] = useState<RequestType>(request.type);
  const [editError, setEditError] = useState<string | null>(null);

  const handleEditToggle = () => {
    setIsEditing((prev) => !prev);
    setEditAmount(String(request.amount));
    setEditType(request.type);
    setEditError(null);
  };

  const handleEditConfirm = () => {
    const parsed = parseInt(editAmount, 10);
    if (isNaN(parsed) || parsed <= 0) {
      setEditError('Enter a valid amount greater than 0');
      return;
    }
    setEditError(null);
    onEditApprove(request.request_id, parsed, editType);
    setIsEditing(false);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleEditConfirm();
    } else if (e.key === 'Escape') {
      handleEditToggle();
    }
  };

  // Time since request was created
  const timeAgo = formatTimeAgo(request.created_at);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {/* Header row: player name + type badge + amount */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-gray-900 truncate">
            {request.player_name}
          </span>
          <RequestTypeBadge type={request.type} />
        </div>
        <span className="text-lg font-bold text-gray-900 tabular-nums shrink-0">
          {request.amount.toLocaleString()}
        </span>
      </div>

      {/* Timestamp */}
      <p className="text-xs text-gray-400 mb-3">{timeAgo}</p>

      {/* Edit mode */}
      {isEditing ? (
        <div className="space-y-2">
          <fieldset className="flex rounded-lg bg-gray-100 p-1">
            <legend className="sr-only">Request type</legend>
            <button
              type="button"
              onClick={() => setEditType(RequestType.CASH)}
              className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
                editType === RequestType.CASH
                  ? 'bg-white text-green-700 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              aria-pressed={editType === RequestType.CASH}
            >
              Cash
            </button>
            <button
              type="button"
              onClick={() => setEditType(RequestType.CREDIT)}
              className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
                editType === RequestType.CREDIT
                  ? 'bg-white text-sky-700 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              aria-pressed={editType === RequestType.CREDIT}
            >
              Credit
            </button>
          </fieldset>
          <div>
            <label
              htmlFor={`edit-amount-${request.request_id}`}
              className="sr-only"
            >
              New amount
            </label>
            <input
              id={`edit-amount-${request.request_id}`}
              type="number"
              min={1}
              value={editAmount}
              onChange={(e) => {
                setEditAmount(e.target.value);
                if (editError) setEditError(null);
              }}
              onKeyDown={handleEditKeyDown}
              autoFocus
              className={`w-full rounded-lg border-2 px-3 py-2 text-sm tabular-nums focus:outline-none focus:ring-0 ${
                editError
                  ? 'border-red-400 focus:border-red-500'
                  : 'border-gray-300 focus:border-primary-500'
              }`}
              aria-invalid={editError ? 'true' : undefined}
              aria-describedby={
                editError ? `edit-error-${request.request_id}` : undefined
              }
            />
            {editError && (
              <p
                id={`edit-error-${request.request_id}`}
                className="mt-1 text-xs text-red-600"
                role="alert"
              >
                {editError}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleEditConfirm}
              disabled={isProcessing}
              className="flex-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-semibold text-white hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={handleEditToggle}
              disabled={isProcessing}
              className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        /* Action buttons */
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onApprove(request.request_id)}
            disabled={isProcessing}
            className="flex-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-semibold text-white hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
            aria-label={`Approve request from ${request.player_name} for ${request.amount}`}
          >
            Approve
          </button>
          <button
            type="button"
            onClick={() => onDecline(request.request_id)}
            disabled={isProcessing}
            className="flex-1 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 active:bg-red-800 disabled:opacity-60 disabled:cursor-not-allowed"
            aria-label={`Decline request from ${request.player_name}`}
          >
            Decline
          </button>
          <button
            type="button"
            onClick={handleEditToggle}
            disabled={isProcessing}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 disabled:opacity-60 disabled:cursor-not-allowed"
            aria-label={`Edit amount for request from ${request.player_name}`}
          >
            Edit
          </button>
        </div>
      )}
    </div>
  );
}

// ── Time Formatting Helper ─────────────────────────────────────────────

function formatTimeAgo(isoDate: string): string {
  const now = Date.now();
  const then = new Date(isoDate).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
