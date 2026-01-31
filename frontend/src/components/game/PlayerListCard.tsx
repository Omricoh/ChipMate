import { Badge } from '../common/Badge';
import type { Player } from '../../api/types';

interface PlayerListCardProps {
  players: Player[];
}

/**
 * Shows all players in the game with their chip summary.
 * The manager is listed first, then remaining players alphabetically.
 */
export function PlayerListCard({ players }: PlayerListCardProps) {
  // Sort: manager first, then alphabetical by name
  const sorted = [...players].sort((a, b) => {
    if (a.is_manager && !b.is_manager) return -1;
    if (!a.is_manager && b.is_manager) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="divide-y divide-gray-100">
      {sorted.map((player) => (
        <PlayerRow key={player.player_id} player={player} />
      ))}
    </div>
  );
}

// ── Player Row ─────────────────────────────────────────────────────────

function PlayerRow({ player }: { player: Player }) {
  const totalBuyIn = player.total_cash_in + player.total_credit_in;

  return (
    <div className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      {/* Left: Name + badges */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-900 truncate">
            {player.name}
          </span>
          {player.is_manager && <Badge label="Manager" color="amber" />}
          {player.checked_out && <Badge label="Out" color="gray" />}
          {!player.is_active && !player.checked_out && (
            <Badge label="Inactive" color="red" />
          )}
        </div>

        {/* Secondary stats */}
        <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
          <span>
            Buy-in:{' '}
            <span className="font-medium text-gray-700 tabular-nums">
              {totalBuyIn.toLocaleString()}
            </span>
          </span>
          {player.credits_owed > 0 && (
            <span>
              Credit:{' '}
              <span className="font-medium text-sky-700 tabular-nums">
                {player.credits_owed.toLocaleString()}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Right: Current chip balance */}
      <div className="text-right shrink-0">
        <span className="text-sm font-bold text-gray-900 tabular-nums">
          {player.current_chips.toLocaleString()}
        </span>
        <span className="block text-[10px] uppercase tracking-wide text-gray-400 font-medium">
          chips
        </span>
      </div>
    </div>
  );
}
