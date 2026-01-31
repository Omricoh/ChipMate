import { RequestStatusBadge, RequestTypeBadge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import type { ChipRequest } from '../../api/types';

interface RequestHistoryListProps {
  /** Player's chip request history, sorted newest-first */
  requests: ChipRequest[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1_000);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Request Row ──────────────────────────────────────────────────────────────

function RequestRow({ request }: { request: ChipRequest }) {
  const wasEdited =
    request.original_amount !== null && request.original_amount !== request.amount;

  return (
    <li className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
      <div className="flex items-center gap-2.5 min-w-0">
        <RequestTypeBadge type={request.type} />
        <div className="min-w-0">
          <span className="text-base font-semibold tabular-nums text-gray-900">
            {request.amount.toLocaleString()}
          </span>
          {wasEdited && request.original_amount !== null && (
            <span className="ml-1.5 text-xs text-gray-400 line-through tabular-nums">
              {request.original_amount.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2.5 shrink-0">
        <RequestStatusBadge status={request.status} />
        <span className="text-xs text-gray-400 tabular-nums w-14 text-right">
          {formatRelativeTime(request.created_at)}
        </span>
      </div>
    </li>
  );
}

// ── Empty State Icon ─────────────────────────────────────────────────────────

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

// ── Main Component ───────────────────────────────────────────────────────────

/**
 * Displays the player's chip request history.
 * Each row shows the request type badge, amount (with original amount
 * struck through if edited), status badge, and relative timestamp.
 * Shows an empty state when there are no requests.
 */
export function RequestHistoryList({ requests }: RequestHistoryListProps) {
  if (requests.length === 0) {
    return (
      <EmptyState
        icon={<HistoryIcon />}
        message="No requests yet"
        description="Your chip requests will appear here after you submit them."
      />
    );
  }

  return (
    <ul className="divide-y divide-gray-100" role="list" aria-label="Request history">
      {requests.map((request) => (
        <RequestRow key={request.request_id} request={request} />
      ))}
    </ul>
  );
}
