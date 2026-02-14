import { Badge } from '../common/Badge';
import type { Player } from '../../api/types';
import { GameStatus } from '../../api/types';

interface PlayerListCardProps {
  players: Player[];
  /** Current game status — drives which actions are available */
  gameStatus?: GameStatus;
  /** ID of the player currently being processed */
  processingPlayerId?: string | null;
  /** Called when a player requests mid-game checkout (OPEN state only) */
  onCheckoutRequest?: (playerId: string) => void;
}

/**
 * Shows all players in the game with their chip summary.
 * The manager is listed first, then remaining players alphabetically.
 */
export function PlayerListCard({
  players,
  gameStatus,
  processingPlayerId,
}: PlayerListCardProps) {
  // Sort: manager first, then alphabetical by name
  const sorted = [...players].sort((a, b) => {
    if (a.is_manager && !b.is_manager) return -1;
    if (!a.is_manager && b.is_manager) return 1;
    return a.name.localeCompare(b.name);
  });

  const isClosed = gameStatus === GameStatus.CLOSED;

  return (
    <div className="divide-y divide-gray-100">
      {sorted.map((player) => (
        <PlayerRow
          key={player.player_id}
          player={player}
          isClosed={isClosed}
          isProcessing={processingPlayerId === player.player_id}
        />
      ))}
    </div>
  );
}

// ── Player Row ─────────────────────────────────────────────────────────

interface PlayerRowProps {
  player: Player;
  isClosed: boolean;
  isProcessing: boolean;
}

function PlayerRow({
  player,
  isClosed,
  isProcessing,
}: PlayerRowProps) {
  const totalCashIn = player.total_cash_in ?? 0;
  const totalCreditIn = player.total_credit_in ?? 0;
  const creditsOwed = player.credits_owed ?? 0;
  const currentChips = player.current_chips ?? 0;
  const totalBuyIn = totalCashIn + totalCreditIn;

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        {/* Left: Name + badges */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-900 truncate">
              {player.name}
            </span>
            {player.is_manager && <Badge label="Manager" color="amber" />}
            {!player.is_active && (
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
            {creditsOwed > 0 && (
              <span>
                Credit:{' '}
                <span className="font-medium text-sky-700 tabular-nums">
                  {creditsOwed.toLocaleString()}
                </span>
              </span>
            )}
          </div>
        </div>

        {/* Right: Chip balance */}
        <div className="text-right shrink-0">
          <span className="text-sm font-bold text-gray-900 tabular-nums">
            {currentChips.toLocaleString()}
          </span>
          <span className="block text-[10px] uppercase tracking-wide text-gray-400 font-medium">
            chips
          </span>
        </div>
      </div>
    </div>
  );
}
