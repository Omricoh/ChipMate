import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import apiClient from '../api/client';
import type {
  GameStatusResponse,
  Player,
  PlayersListResponse,
} from '../api/types';
import { AuthContext } from './AuthContext';
import { usePolling } from '../hooks/usePolling';

// ── Context Value ──────────────────────────────────────────────────────────

export interface GameContextValue {
  game: GameStatusResponse | null;
  players: Player[];
  isLoading: boolean;
  error: string | null;
  refreshGame: () => Promise<void>;
}

export const GameContext = createContext<GameContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 5_000;

export function GameProvider({
  gameId,
  children,
}: {
  gameId: string;
  children: ReactNode;
}) {
  const auth = useContext(AuthContext);
  const [game, setGame] = useState<GameStatusResponse | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshGame = useCallback(async () => {
    try {
      const statusRes = await apiClient.get<GameStatusResponse>(
        `/api/games/${gameId}/status`,
      );
      setGame(statusRes.data);

      // Only managers/admins can fetch the full player list
      const isManager =
        auth?.user?.kind === 'player' && auth.user.isManager;
      const isAdmin = auth?.user?.kind === 'admin';

      if (isManager || isAdmin) {
        const playersRes = await apiClient.get<PlayersListResponse>(
          `/api/games/${gameId}/players`,
        );
        setPlayers(playersRes.data.players);
      }

      setError(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load game data';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [gameId, auth?.user]);

  // Poll for game updates
  usePolling(refreshGame, POLL_INTERVAL_MS);

  const value = useMemo<GameContextValue>(
    () => ({ game, players, isLoading, error, refreshGame }),
    [game, players, isLoading, error, refreshGame],
  );

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}
