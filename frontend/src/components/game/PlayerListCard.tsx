import { Badge } from '../common/Badge';
import type { Player } from '../../api/types';
import { GameStatus } from '../../api/types';

interface PlayerListCardProps {
  players: Player[];
  /** Current game status — drives which actions are available */
  gameStatus?: GameStatus;
  /** ID of the player currently being processed (checkout/settle-debt) */
  processingPlayerId?: string | null;
  /** Called when the manager clicks "Checkout" on an active player */
  onCheckout?: (player: Player) => void;
  /** Called when the manager clicks "Settle Debt" on a checked-out player with debt */
  onSettleDebt?: (player: Player) => void;
}

/**
 * Shows all players in the game with their chip summary.
 * The manager is listed first, then remaining players alphabetically.
 *
 * When the game is in SETTLING status, shows checkout buttons for active
 * players and P/L + debt info for already-checked-out players.
 */
export function PlayerListCard({
  players,
  gameStatus,
  processingPlayerId,
  onCheckout,
  onSettleDebt,
}: PlayerListCardProps) {
  // Sort: manager first, then alphabetical by name
  const sorted = [...players].sort((a, b) => {
    if (a.is_manager && !b.is_manager) return -1;
    if (!a.is_manager && b.is_manager) return 1;
    return a.name.localeCompare(b.name);
  });

  const isSettling = gameStatus === GameStatus.SETTLING;
  const isClosed = gameStatus === GameStatus.CLOSED;

  return (
    <div className="divide-y divide-gray-100">
      {sorted.map((player) => (
        <PlayerRow
          key={player.player_id}
          player={player}
          isSettling={isSettling}
          isClosed={isClosed}
          isProcessing={processingPlayerId === player.player_id}
          onCheckout={onCheckout}
          onSettleDebt={onSettleDebt}
        />
      ))}
    </div>
  );
}

// ── Player Row ─────────────────────────────────────────────────────────

interface PlayerRowProps {
  player: Player;
  isSettling: boolean;
  isClosed: boolean;
  isProcessing: boolean;
  onCheckout?: (player: Player) => void;
  onSettleDebt?: (player: Player) => void;
}

function PlayerRow({
  player,
  isSettling,
  isClosed,
  isProcessing,
  onCheckout,
  onSettleDebt,
}: PlayerRowProps) {
  const totalCashIn = player.total_cash_in ?? 0;
  const totalCreditIn = player.total_credit_in ?? 0;
  const creditsOwed = player.credits_owed ?? 0;
  const currentChips = player.current_chips ?? 0;
  const totalBuyIn = totalCashIn + totalCreditIn;
  const showSettlementInfo = isSettling || isClosed;

  // Calculate P/L for checked-out players
  // When checked out, current_chips represents the final chip count
  const profitLoss = player.checked_out
    ? currentChips - creditsOwed - totalCashIn
    : null;

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
            {player.checked_out && (
              <Badge label="Checked Out" color="green" />
            )}
            {!player.is_active && !player.checked_out && (
              <Badge label="Inactive" color="red" />
            )}
            {player.checked_out && creditsOwed > 0 && (
              <Badge label="Has Debt" color="sky" />
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

        {/* Right: Chip balance or P/L */}
        <div className="text-right shrink-0">
          {showSettlementInfo && player.checked_out && profitLoss !== null ? (
            <>
              <span
                className={`text-sm font-bold tabular-nums ${
                  profitLoss > 0
                    ? 'text-green-600'
                    : profitLoss < 0
                      ? 'text-red-600'
                      : 'text-gray-500'
                }`}
              >
                {profitLoss > 0 ? '+' : ''}
                {profitLoss.toLocaleString()}
              </span>
              <span className="block text-[10px] uppercase tracking-wide text-gray-400 font-medium">
                P/L
              </span>
            </>
          ) : (
            <>
              <span className="text-sm font-bold text-gray-900 tabular-nums">
                {currentChips.toLocaleString()}
              </span>
              <span className="block text-[10px] uppercase tracking-wide text-gray-400 font-medium">
                chips
              </span>
            </>
          )}
        </div>
      </div>

      {/* Settling actions */}
      {isSettling && (
        <div className="mt-2 flex items-center gap-2">
          {/* Checkout button for active, non-checked-out players */}
          {!player.checked_out && player.is_active && onCheckout && (
            <button
              type="button"
              onClick={() => onCheckout(player)}
              disabled={isProcessing}
              className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 active:bg-primary-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Processing...' : 'Checkout'}
            </button>
          )}

          {/* Settle Debt button for checked-out players with outstanding credit */}
          {player.checked_out && creditsOwed > 0 && onSettleDebt && (
            <button
              type="button"
              onClick={() => onSettleDebt(player)}
              disabled={isProcessing}
              className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-sky-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-1 active:bg-sky-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? 'Settling...' : 'Settle Debt'}
            </button>
          )}

          {/* Status indicator for fully-settled players */}
          {player.checked_out && creditsOwed === 0 && (
            <span className="text-xs text-green-600 font-medium">
              Settled
            </span>
          )}
        </div>
      )}
    </div>
  );
}
