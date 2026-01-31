import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

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

  // Restore session from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (!stored) return;

      const parsed = JSON.parse(stored) as AuthUser;
      if (!parsed) return;

      if (parsed.kind === 'admin') {
        localStorage.setItem(ADMIN_TOKEN_KEY, parsed.token);
      } else if (parsed.kind === 'player') {
        localStorage.setItem(PLAYER_TOKEN_KEY, parsed.token);
      }

      setUser(parsed);
    } catch {
      // Corrupt storage -- clear it
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(ADMIN_TOKEN_KEY);
      localStorage.removeItem(PLAYER_TOKEN_KEY);
    }
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
      loginAdmin,
      joinGame,
      logout,
    }),
    [user, isAdmin, isManager, isPlayer, isAuthenticated, loginAdmin, joinGame, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
