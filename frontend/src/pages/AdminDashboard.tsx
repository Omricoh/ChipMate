import { useCallback, useEffect, useState } from 'react';
import { Layout } from '../components/common/Layout';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorBanner } from '../components/common/ErrorBanner';
import { EmptyState } from '../components/common/EmptyState';
import { GameStatusBadge } from '../components/common/Badge';
import { ConfirmModal } from '../components/common/ConfirmModal';
import { usePolling } from '../hooks/usePolling';
import {
  getAdminStats,
  getAdminGames,
  getAdminGameDetail,
  forceCloseGame,
  impersonateManager,
} from '../api/admin';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { GameStatus } from '../api/types';
import type {
  AdminStats,
  AdminGameSummary,
  AdminGameDetail,
} from '../api/types';

// ── Constants ────────────────────────────────────────────────────────────

const STATS_POLL_INTERVAL = 30_000;
const GAMES_PAGE_SIZE = 20;

type FilterTab = 'ALL' | 'OPEN' | 'SETTLING' | 'CLOSED';

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: 'ALL', label: 'All' },
  { key: 'OPEN', label: 'Open' },
  { key: 'SETTLING', label: 'Settling' },
  { key: 'CLOSED', label: 'Closed' },
];

// ── Helpers ───────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatCurrency(amount: number): string {
  return `$${amount.toLocaleString()}`;
}

// ── Stat Card Component ───────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: number | string;
  color: string;
  icon: React.ReactNode;
}

function StatCard({ label, value, color, icon }: StatCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${color}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-xs font-medium text-gray-500 truncate">{label}</p>
        </div>
      </div>
    </div>
  );
}

// ── Game Detail Panel Component ───────────────────────────────────────────

interface GameDetailPanelProps {
  detail: AdminGameDetail;
  isForceClosing: boolean;
  isImpersonating: boolean;
  onForceClose: () => void;
  onImpersonate: () => void;
  onClose: () => void;
}

function GameDetailPanel({
  detail,
  isForceClosing,
  isImpersonating,
  onForceClose,
  onImpersonate,
  onClose,
}: GameDetailPanelProps) {
  const isCloseable = detail.status !== GameStatus.CLOSED;
  const canImpersonate = detail.status !== GameStatus.CLOSED;

  return (
    <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">
          Game Detail: {detail.game_code}
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 p-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
          aria-label="Close game detail"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-5 w-5"
            aria-hidden="true"
          >
            <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
          </svg>
        </button>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-gray-500">Status</span>
          <div className="mt-0.5">
            <GameStatusBadge status={detail.status} />
          </div>
        </div>
        <div>
          <span className="text-gray-500">Manager</span>
          <p className="font-medium text-gray-900 mt-0.5">{detail.manager_name}</p>
        </div>
        <div>
          <span className="text-gray-500">Created</span>
          <p className="font-medium text-gray-900 mt-0.5">{formatDate(detail.created_at)}</p>
        </div>
        {detail.closed_at && (
          <div>
            <span className="text-gray-500">Closed</span>
            <p className="font-medium text-gray-900 mt-0.5">{formatDate(detail.closed_at)}</p>
          </div>
        )}
      </div>

      {/* Bank summary */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Bank Summary
        </h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-lg bg-white border border-gray-200 px-3 py-2">
            <p className="text-xs text-gray-500">Cash In</p>
            <p className="font-semibold text-gray-900">{formatCurrency(detail.bank.total_cash_in)}</p>
          </div>
          <div className="rounded-lg bg-white border border-gray-200 px-3 py-2">
            <p className="text-xs text-gray-500">Credit In</p>
            <p className="font-semibold text-gray-900">{formatCurrency(detail.bank.total_credit_in)}</p>
          </div>
          <div className="rounded-lg bg-white border border-gray-200 px-3 py-2">
            <p className="text-xs text-gray-500">In Play</p>
            <p className="font-semibold text-gray-900">{formatCurrency(detail.bank.total_in_play)}</p>
          </div>
          <div className="rounded-lg bg-white border border-gray-200 px-3 py-2">
            <p className="text-xs text-gray-500">Checked Out</p>
            <p className="font-semibold text-gray-900">{formatCurrency(detail.bank.total_checked_out)}</p>
          </div>
        </div>
      </div>

      {/* Request stats */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Request Stats
        </h4>
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-gray-500">Total:</span>{' '}
            <span className="font-semibold text-gray-900">{detail.request_stats.total}</span>
          </div>
          <div>
            <span className="text-gray-500">Pending:</span>{' '}
            <span className="font-semibold text-yellow-600">{detail.request_stats.pending}</span>
          </div>
          <div>
            <span className="text-gray-500">Approved:</span>{' '}
            <span className="font-semibold text-green-600">{detail.request_stats.approved}</span>
          </div>
          <div>
            <span className="text-gray-500">Declined:</span>{' '}
            <span className="font-semibold text-red-600">{detail.request_stats.declined}</span>
          </div>
        </div>
      </div>

      {/* Players list */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Players ({detail.players.length})
        </h4>
        {detail.players.length === 0 ? (
          <p className="text-sm text-gray-400">No players in this game.</p>
        ) : (
          <div className="space-y-1">
            {detail.players.map((player) => (
              <div
                key={player.player_id}
                className="flex items-center justify-between rounded-lg bg-white border border-gray-200 px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-medium text-gray-900 truncate">
                    {player.name}
                  </span>
                  {player.is_manager && (
                    <span className="shrink-0 text-[10px] font-semibold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded-full">
                      MGR
                    </span>
                  )}
                  {player.checked_out && (
                    <span className="shrink-0 text-[10px] font-semibold text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded-full">
                      OUT
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500 shrink-0">
                  <span>Chips: {formatCurrency(player.current_chips)}</span>
                  <span>Cash: {formatCurrency(player.total_cash_in)}</span>
                  {player.credits_owed > 0 && (
                    <span className="text-red-500">
                      Owes: {formatCurrency(player.credits_owed)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      {(isCloseable || canImpersonate) && (
        <div className="pt-2 border-t border-gray-200 flex gap-2">
          {canImpersonate && (
            <button
              type="button"
              onClick={onImpersonate}
              disabled={isImpersonating}
              className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-purple-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2 active:bg-purple-800 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isImpersonating ? 'Loading...' : 'Open as Manager'}
            </button>
          )}
          {isCloseable && (
            <button
              type="button"
              onClick={onForceClose}
              disabled={isForceClosing}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 active:bg-red-800 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isForceClosing ? 'Closing...' : 'Force Close Game'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard Component ──────────────────────────────────────────────

export default function AdminDashboard() {
  // ── Stats state ───────────────────────────────────────────────────────
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);

  // ── Games state ───────────────────────────────────────────────────────
  const [games, setGames] = useState<AdminGameSummary[]>([]);
  const [gamesTotal, setGamesTotal] = useState(0);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [gamesError, setGamesError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterTab>('ALL');
  const [offset, setOffset] = useState(0);

  // ── Detail state ──────────────────────────────────────────────────────
  const [expandedGameId, setExpandedGameId] = useState<string | null>(null);
  const [gameDetail, setGameDetail] = useState<AdminGameDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // ── Force close state ─────────────────────────────────────────────────
  const [forceCloseTarget, setForceCloseTarget] = useState<AdminGameSummary | null>(null);
  const [isForceClosing, setIsForceClosing] = useState(false);

  // ── Impersonate state ────────────────────────────────────────────────
  const [isImpersonating, setIsImpersonating] = useState(false);
  const { joinGame } = useAuth();
  const navigate = useNavigate();

  // ── Fetch stats (polled) ──────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const data = await getAdminStats();
      setStats(data);
      setStatsError(null);
    } catch {
      setStatsError('Failed to load stats.');
    }
  }, []);

  usePolling(fetchStats, STATS_POLL_INTERVAL);

  // ── Fetch games ───────────────────────────────────────────────────────

  const fetchGames = useCallback(async () => {
    setGamesLoading(true);
    setGamesError(null);

    try {
      const statusParam = activeFilter === 'ALL' ? undefined : activeFilter;
      const data = await getAdminGames({
        status: statusParam,
        limit: GAMES_PAGE_SIZE,
        offset,
      });
      setGames(data.games);
      setGamesTotal(data.total);
    } catch {
      setGamesError('Failed to load games.');
    } finally {
      setGamesLoading(false);
    }
  }, [activeFilter, offset]);

  useEffect(() => {
    fetchGames();
  }, [fetchGames]);

  // ── Fetch game detail ─────────────────────────────────────────────────

  const fetchDetail = useCallback(async (gameId: string) => {
    setDetailLoading(true);
    setDetailError(null);

    try {
      const data = await getAdminGameDetail(gameId);
      setGameDetail(data);
    } catch {
      setDetailError('Failed to load game detail.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleToggleDetail = useCallback(
    (gameId: string) => {
      if (expandedGameId === gameId) {
        setExpandedGameId(null);
        setGameDetail(null);
        setDetailError(null);
      } else {
        setExpandedGameId(gameId);
        fetchDetail(gameId);
      }
    },
    [expandedGameId, fetchDetail],
  );

  // ── Filter change ─────────────────────────────────────────────────────

  const handleFilterChange = useCallback((tab: FilterTab) => {
    setActiveFilter(tab);
    setOffset(0);
    setExpandedGameId(null);
    setGameDetail(null);
  }, []);

  // ── Pagination ────────────────────────────────────────────────────────

  const hasMore = offset + GAMES_PAGE_SIZE < gamesTotal;
  const hasPrev = offset > 0;
  const currentPage = Math.floor(offset / GAMES_PAGE_SIZE) + 1;
  const totalPages = Math.ceil(gamesTotal / GAMES_PAGE_SIZE);

  const handleNextPage = useCallback(() => {
    if (hasMore) {
      setOffset((prev) => prev + GAMES_PAGE_SIZE);
      setExpandedGameId(null);
      setGameDetail(null);
    }
  }, [hasMore]);

  const handlePrevPage = useCallback(() => {
    if (hasPrev) {
      setOffset((prev) => Math.max(0, prev - GAMES_PAGE_SIZE));
      setExpandedGameId(null);
      setGameDetail(null);
    }
  }, [hasPrev]);

  // ── Force close ───────────────────────────────────────────────────────

  const handleForceCloseConfirm = useCallback(async () => {
    if (!forceCloseTarget) return;

    setIsForceClosing(true);
    try {
      await forceCloseGame(forceCloseTarget.game_id);
      setForceCloseTarget(null);

      // Refresh data
      fetchStats();
      fetchGames();

      // If this game was expanded, refresh its detail
      if (expandedGameId === forceCloseTarget.game_id) {
        fetchDetail(forceCloseTarget.game_id);
      }
    } catch {
      // The confirm modal is already dismissed; let the refreshed data show the actual state.
      setForceCloseTarget(null);
    } finally {
      setIsForceClosing(false);
    }
  }, [forceCloseTarget, expandedGameId, fetchStats, fetchGames, fetchDetail]);

  // ── Impersonate ──────────────────────────────────────────────────────

  const handleImpersonate = useCallback(async () => {
    if (!gameDetail) return;

    setIsImpersonating(true);
    try {
      const result = await impersonateManager(gameDetail.game_id);

      // Join game as manager
      joinGame({
        token: result.manager_player_token,
        playerId: result.manager_player_token, // Use token as ID for manager
        gameId: result.game_id,
        gameCode: result.game_code,
        name: result.manager_name,
        isManager: true,
      });

      // Navigate to game page
      navigate(`/game/${result.game_id}`);
    } catch (err) {
      console.error('Failed to impersonate manager:', err);
    } finally {
      setIsImpersonating(false);
    }
  }, [gameDetail, joinGame, navigate]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <Layout>
      <div className="space-y-6">
        {/* ── Page Header ──────────────────────────────────────────── */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            System overview and game management
          </p>
        </div>

        {/* ── Stats Section ────────────────────────────────────────── */}
        {statsError && (
          <ErrorBanner message={statsError} onRetry={fetchStats} />
        )}

        {stats ? (
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Active Games"
              value={stats.active_games}
              color="bg-green-100"
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5 text-green-600"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm3.857-9.809a.75.75 0 0 0-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 1 0-1.06 1.061l2.5 2.5a.75.75 0 0 0 1.137-.089l4-5.5Z"
                    clipRule="evenodd"
                  />
                </svg>
              }
            />
            <StatCard
              label="Settling Games"
              value={stats.settling_games}
              color="bg-amber-100"
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5 text-amber-600"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm.75-13a.75.75 0 0 0-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 0 0 0-1.5h-3.25V5Z"
                    clipRule="evenodd"
                  />
                </svg>
              }
            />
            <StatCard
              label="Closed Games"
              value={stats.closed_games}
              color="bg-gray-100"
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5 text-gray-500"
                  aria-hidden="true"
                >
                  <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                </svg>
              }
            />
            <StatCard
              label="Total Players"
              value={stats.total_players}
              color="bg-purple-100"
              icon={
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5 text-purple-600"
                  aria-hidden="true"
                >
                  <path d="M7 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM14.5 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM1.615 16.428a1.224 1.224 0 0 1-.569-1.175 6.002 6.002 0 0 1 11.908 0c.058.467-.172.92-.57 1.174A9.953 9.953 0 0 1 7 18a9.953 9.953 0 0 1-5.385-1.572ZM14.5 16h-.106c.07-.297.088-.611.048-.933a7.47 7.47 0 0 0-1.588-3.755 4.502 4.502 0 0 1 5.874 2.636.818.818 0 0 1-.36.98A7.465 7.465 0 0 1 14.5 16Z" />
                </svg>
              }
            />
          </div>
        ) : (
          !statsError && <LoadingSpinner size="sm" message="Loading stats..." />
        )}

        {/* ── Games Section ────────────────────────────────────────── */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Games</h2>

          {/* Filter tabs */}
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1 mb-4" role="tablist">
            {FILTER_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={activeFilter === tab.key}
                onClick={() => handleFilterChange(tab.key)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 ${
                  activeFilter === tab.key
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Error state */}
          {gamesError && (
            <ErrorBanner message={gamesError} onRetry={fetchGames} />
          )}

          {/* Loading state */}
          {gamesLoading && !gamesError && (
            <LoadingSpinner message="Loading games..." />
          )}

          {/* Empty state */}
          {!gamesLoading && !gamesError && games.length === 0 && (
            <EmptyState
              message="No games found"
              description={
                activeFilter === 'ALL'
                  ? 'No games have been created yet.'
                  : `No ${activeFilter.toLowerCase()} games at this time.`
              }
            />
          )}

          {/* Games list */}
          {!gamesLoading && !gamesError && games.length > 0 && (
            <div className="space-y-2">
              {games.map((game) => (
                <div key={game.game_id}>
                  <button
                    type="button"
                    onClick={() => handleToggleDetail(game.game_id)}
                    className={`w-full text-left rounded-xl border bg-white p-4 shadow-sm transition-colors hover:border-purple-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 ${
                      expandedGameId === game.game_id
                        ? 'border-purple-300 ring-1 ring-purple-200'
                        : 'border-gray-200'
                    }`}
                    aria-expanded={expandedGameId === game.game_id}
                  >
                    <div className="flex items-center justify-between gap-3">
                      {/* Left: code + manager */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-bold text-gray-900 tracking-wider">
                            {game.game_code}
                          </span>
                          <GameStatusBadge status={game.status} />
                        </div>
                        <p className="text-sm text-gray-500 mt-0.5 truncate">
                          {game.manager_name}
                        </p>
                      </div>

                      {/* Right: player count + date + force-close */}
                      <div className="flex items-center gap-3 shrink-0">
                        <div className="text-right">
                          <p className="text-sm font-medium text-gray-700">
                            {game.player_count} player{game.player_count !== 1 ? 's' : ''}
                          </p>
                          <p className="text-xs text-gray-400">
                            {formatDate(game.created_at)}
                          </p>
                        </div>

                        {game.status !== GameStatus.CLOSED && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setForceCloseTarget(game);
                            }}
                            className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                            aria-label={`Force close game ${game.game_code}`}
                          >
                            Force Close
                          </button>
                        )}

                        {/* Chevron */}
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className={`h-5 w-5 text-gray-400 transition-transform ${
                            expandedGameId === game.game_id ? 'rotate-180' : ''
                          }`}
                          aria-hidden="true"
                        >
                          <path
                            fillRule="evenodd"
                            d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {expandedGameId === game.game_id && (
                    <>
                      {detailLoading && (
                        <div className="mt-3">
                          <LoadingSpinner size="sm" message="Loading detail..." />
                        </div>
                      )}
                      {detailError && (
                        <div className="mt-3">
                          <ErrorBanner
                            message={detailError}
                            onRetry={() => fetchDetail(game.game_id)}
                          />
                        </div>
                      )}
                      {gameDetail && !detailLoading && !detailError && (
                        <GameDetailPanel
                          detail={gameDetail}
                          isForceClosing={isForceClosing}
                          isImpersonating={isImpersonating}
                          onForceClose={() => setForceCloseTarget(game)}
                          onImpersonate={handleImpersonate}
                          onClose={() => {
                            setExpandedGameId(null);
                            setGameDetail(null);
                          }}
                        />
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {!gamesLoading && !gamesError && gamesTotal > GAMES_PAGE_SIZE && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={handlePrevPage}
                disabled={!hasPrev}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="text-sm text-gray-500">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                onClick={handleNextPage}
                disabled={!hasMore}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Force Close Confirm Modal ──────────────────────────────── */}
      <ConfirmModal
        isOpen={forceCloseTarget !== null}
        title="Force Close Game"
        message={
          forceCloseTarget
            ? `Are you sure you want to force close game ${forceCloseTarget.game_code}? This will end the game immediately for all players. This action cannot be undone.`
            : ''
        }
        confirmLabel="Force Close"
        cancelLabel="Cancel"
        isDanger
        onConfirm={handleForceCloseConfirm}
        onCancel={() => setForceCloseTarget(null)}
      />
    </Layout>
  );
}
