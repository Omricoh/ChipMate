import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { validateSession } from '../api/auth';

// ── Auth State Types ───────────────────────────────────────────────────────

interface AdminUser {
  kind: 'admin';
  token: string;
  username: string;
}

interface PlayerUser {
  kind: 'player';
  token: string;
  playerId: string;
  gameId: string;
  gameCode: string;
  name: string;
  isManager: boolean;
}

type AuthUser = AdminUser | PlayerUser | null;

export interface AuthContextValue {
  user: AuthUser;
  isAdmin: boolean;
  isManager: boolean;
  isPlayer: boolean;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginAdmin: (token: string, username: string) => void;
  joinGame: (params: {
    token: string;
    playerId: string;
    gameId: string;
    gameCode: string;
    name: string;
    isManager: boolean;
  }) => void;
  logout: () => void;
}

// ── Storage Keys ───────────────────────────────────────────────────────────

const STORAGE_KEY = 'chipmate_auth';
const ADMIN_TOKEN_KEY = 'chipmate_admin_token';
const PLAYER_TOKEN_KEY = 'chipmate_player_token';

// ── Context ────────────────────────────────────────────────────────────────

export const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore and validate session from localStorage on mount
  useEffect(() => {
    const restoreSession = async () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) {
          setIsLoading(false);
          return;
        }

        const parsed = JSON.parse(stored) as AuthUser;
        if (!parsed) {
          setIsLoading(false);
          return;
        }

        // Set token headers for the validation request
        if (parsed.kind === 'admin') {
          localStorage.setItem(ADMIN_TOKEN_KEY, parsed.token);
        } else if (parsed.kind === 'player') {
          localStorage.setItem(PLAYER_TOKEN_KEY, parsed.token);
        }

        // Validate session with the backend
        try {
          const response = await validateSession();

          if (response.valid && response.user) {
            // Session is valid - update local state with fresh data from server
            if (response.user.role === 'ADMIN' && parsed.kind === 'admin') {
              // Admin session still valid
              setUser(parsed);
            } else if (
              (response.user.role === 'MANAGER' || response.user.role === 'PLAYER') &&
              parsed.kind === 'player' &&
              response.user.game_id &&
              response.user.game_code
            ) {
              // Player session still valid - update with fresh data from server
              const updatedPlayer: PlayerUser = {
                kind: 'player',
                token: parsed.token,
                playerId: response.user.player_id || parsed.playerId,
                gameId: response.user.game_id,
                gameCode: response.user.game_code,
                name: response.user.display_name || parsed.name,
                isManager: response.user.is_manager ?? parsed.isManager,
              };
              setUser(updatedPlayer);
              localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedPlayer));
            } else {
              // Role mismatch - clear session
              clearStorage();
            }
          } else {
            // Session invalid - clear storage
            clearStorage();
          }
        } catch {
          // Network error during validation - trust local session
          // This allows offline access while game is active
          setUser(parsed);
        }
      } catch {
        // Corrupt storage -- clear it
        clearStorage();
      } finally {
        setIsLoading(false);
      }
    };

    const clearStorage = () => {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(ADMIN_TOKEN_KEY);
      localStorage.removeItem(PLAYER_TOKEN_KEY);
    };

    restoreSession();
  }, []);

  const persist = useCallback((value: AuthUser) => {
    if (value) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      if (value.kind === 'admin') {
        localStorage.setItem(ADMIN_TOKEN_KEY, value.token);
        localStorage.removeItem(PLAYER_TOKEN_KEY);
      } else {
        localStorage.setItem(PLAYER_TOKEN_KEY, value.token);
        localStorage.removeItem(ADMIN_TOKEN_KEY);
      }
    } else {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(ADMIN_TOKEN_KEY);
      localStorage.removeItem(PLAYER_TOKEN_KEY);
    }
  }, []);

  const loginAdmin = useCallback(
    (token: string, username: string) => {
      const admin: AdminUser = { kind: 'admin', token, username };
      setUser(admin);
      persist(admin);
    },
    [persist],
  );

  const joinGame = useCallback(
    (params: {
      token: string;
      playerId: string;
      gameId: string;
      gameCode: string;
      name: string;
      isManager: boolean;
    }) => {
      const player: PlayerUser = {
        kind: 'player',
        token: params.token,
        playerId: params.playerId,
        gameId: params.gameId,
        gameCode: params.gameCode,
        name: params.name,
        isManager: params.isManager,
      };
      setUser(player);
      persist(player);
    },
    [persist],
  );

  const logout = useCallback(() => {
    setUser(null);
    persist(null);
  }, [persist]);

  const isAdmin = user?.kind === 'admin';
  const isManager = user?.kind === 'player' && user.isManager;
  const isPlayer = user?.kind === 'player';
  const isAuthenticated = user !== null;

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAdmin,
      isManager,
      isPlayer,
      isAuthenticated,
      isLoading,
      loginAdmin,
      joinGame,
      logout,
    }),
    [user, isAdmin, isManager, isPlayer, isAuthenticated, isLoading, loginAdmin, joinGame, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
