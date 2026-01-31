import { GameStatusBadge } from '../common/Badge';
import type { GameStatus } from '../../api/types';

interface PlayerStatusCardProps {
  /** Player display name */
  playerName: string;
  /** Total cash bought in */
  totalCashIn: number;
  /** Total credit bought in */
  totalCreditIn: number;
  /** Credits currently owed */
  creditsOwed: number;
  /** Current game status */
  gameStatus: GameStatus;
}

interface StatItemProps {
  label: string;
  value: number;
  color?: string;
}

function StatItem({ label, value, color = 'text-gray-900' }: StatItemProps) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={`text-xl font-bold tabular-nums ${color}`}>
        {value.toLocaleString()}
      </span>
    </div>
  );
}

/**
 * Displays the authenticated player's status within the game,
 * including their name, buy-in totals, credits owed, and the
 * current game status.
 */
export function PlayerStatusCard({
  playerName,
  totalCashIn,
  totalCreditIn,
  creditsOwed,
  gameStatus,
}: PlayerStatusCardProps) {
  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
      aria-label="Your status"
    >
      {/* Header row: name + game status badge */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900 truncate">
          {playerName}
        </h2>
        <GameStatusBadge status={gameStatus} />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3">
        <StatItem
          label="Cash In"
          value={totalCashIn}
          color="text-green-700"
        />
        <StatItem
          label="Credit In"
          value={totalCreditIn}
          color="text-sky-700"
        />
        <StatItem
          label="Credits Owed"
          value={creditsOwed}
          color={creditsOwed > 0 ? 'text-red-600' : 'text-gray-400'}
        />
      </div>
    </section>
  );
}
