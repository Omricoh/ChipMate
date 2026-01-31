import { GameStatus, RequestStatus, RequestType } from '../../api/types';

type BadgeColor =
  | 'green'
  | 'amber'
  | 'red'
  | 'gray'
  | 'sky'
  | 'purple'
  | 'yellow';

interface BadgeProps {
  /** Text to display in the badge */
  label: string;
  /** Color variant */
  color: BadgeColor;
}

const colorClasses: Record<BadgeColor, string> = {
  green: 'bg-green-100 text-green-800',
  amber: 'bg-amber-100 text-amber-800',
  red: 'bg-red-100 text-red-800',
  gray: 'bg-gray-100 text-gray-700',
  sky: 'bg-sky-100 text-sky-800',
  purple: 'bg-purple-100 text-purple-800',
  yellow: 'bg-yellow-100 text-yellow-800',
};

export function Badge({ label, color }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${colorClasses[color]}`}
    >
      {label}
    </span>
  );
}

// ── Convenience Helpers ────────────────────────────────────────────────────

export function GameStatusBadge({ status }: { status: GameStatus }) {
  const map: Record<GameStatus, { label: string; color: BadgeColor }> = {
    [GameStatus.OPEN]: { label: 'Open', color: 'green' },
    [GameStatus.SETTLING]: { label: 'Settling', color: 'amber' },
    [GameStatus.CLOSED]: { label: 'Closed', color: 'gray' },
  };

  const { label, color } = map[status];
  return <Badge label={label} color={color} />;
}

export function RequestStatusBadge({ status }: { status: RequestStatus }) {
  const map: Record<RequestStatus, { label: string; color: BadgeColor }> = {
    [RequestStatus.PENDING]: { label: 'Pending', color: 'yellow' },
    [RequestStatus.APPROVED]: { label: 'Approved', color: 'green' },
    [RequestStatus.DECLINED]: { label: 'Declined', color: 'red' },
    [RequestStatus.EDITED]: { label: 'Edited', color: 'purple' },
  };

  const { label, color } = map[status];
  return <Badge label={label} color={color} />;
}

export function RequestTypeBadge({ type }: { type: RequestType }) {
  const map: Record<RequestType, { label: string; color: BadgeColor }> = {
    [RequestType.CASH]: { label: 'Cash', color: 'green' },
    [RequestType.CREDIT]: { label: 'Credit', color: 'sky' },
  };

  const { label, color } = map[type];
  return <Badge label={label} color={color} />;
}
