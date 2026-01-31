import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorBanner } from '../components/common/ErrorBanner';
import { getGameByCode, joinGame } from '../api/games';
import { useAuth } from '../hooks/useAuth';
import type { GameByCodeResponse } from '../api/types';
import { GameStatus } from '../api/types';

// ── Name Validation ───────────────────────────────────────────────────────

const NAME_MIN = 2;
const NAME_MAX = 30;
const CODE_LENGTH = 6;

function validateName(name: string): string | null {
  const trimmed = name.trim();
  if (trimmed.length === 0) return 'Display name is required';
  if (trimmed.length < NAME_MIN) return `Name must be at least ${NAME_MIN} characters`;
  if (trimmed.length > NAME_MAX) return `Name must be at most ${NAME_MAX} characters`;
  return null;
}

function validateCode(code: string): string | null {
  const trimmed = code.trim();
  if (trimmed.length === 0) return 'Game code is required';
  if (trimmed.length !== CODE_LENGTH) return `Game code must be ${CODE_LENGTH} characters`;
  if (!/^[A-Za-z0-9]+$/.test(trimmed)) return 'Game code must be letters and numbers only';
  return null;
}

// ── Status Badge ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: GameStatus }) {
  const colorMap: Record<GameStatus, string> = {
    [GameStatus.OPEN]: 'bg-green-100 text-green-800',
    [GameStatus.SETTLING]: 'bg-amber-100 text-amber-800',
    [GameStatus.CLOSED]: 'bg-red-100 text-red-800',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${colorMap[status]}`}
    >
      {status}
    </span>
  );
}

// ── Component ─────────────────────────────────────────────────────────────

export default function JoinGame() {
  const { gameCode: urlGameCode } = useParams<{ gameCode?: string }>();
  const navigate = useNavigate();
  const { joinGame: authJoinGame } = useAuth();

  // Code input state (used when no URL param)
  const [codeInput, setCodeInput] = useState(urlGameCode ?? '');
  const [codeError, setCodeError] = useState<string | null>(null);

  // Game lookup state
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [gameInfo, setGameInfo] = useState<GameByCodeResponse | null>(null);

  // Name input state
  const [playerName, setPlayerName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);

  // Join submission state
  const [isJoining, setIsJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);

  // ── Look Up Game ──────────────────────────────────────────────────────

  const lookupGame = useCallback(async (code: string) => {
    setIsLookingUp(true);
    setLookupError(null);
    setGameInfo(null);

    try {
      const result = await getGameByCode(code.trim());
      setGameInfo(result);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Game not found. Check the code and try again.';
      setLookupError(message);
    } finally {
      setIsLookingUp(false);
    }
  }, []);

  // Auto-lookup when game code comes from URL
  useEffect(() => {
    if (urlGameCode && urlGameCode.trim().length > 0) {
      lookupGame(urlGameCode);
    }
  }, [urlGameCode, lookupGame]);

  // ── Handle Code Submit ────────────────────────────────────────────────

  const handleCodeSubmit = () => {
    const error = validateCode(codeInput);
    if (error) {
      setCodeError(error);
      return;
    }
    setCodeError(null);
    lookupGame(codeInput);
  };

  const handleCodeKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isLookingUp) {
      handleCodeSubmit();
    }
  };

  // ── Handle Join ───────────────────────────────────────────────────────

  const handleJoin = async () => {
    if (!gameInfo) return;

    const error = validateName(playerName);
    if (error) {
      setNameError(error);
      return;
    }

    setNameError(null);
    setJoinError(null);
    setIsJoining(true);

    try {
      const result = await joinGame(gameInfo.game_id, playerName.trim());

      authJoinGame({
        token: result.player_token,
        playerId: result.player_id,
        gameId: result.game.game_id,
        gameCode: result.game.game_code,
        name: playerName.trim(),
        isManager: false,
      });

      navigate(`/game/${result.game.game_id}`, { replace: true });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Could not join game. Please try again.';
      setJoinError(message);
    } finally {
      setIsJoining(false);
    }
  };

  const handleJoinKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isJoining) {
      handleJoin();
    }
  };

  // ── Handle Change Code (reset back to code input) ─────────────────────

  const handleChangeCode = () => {
    setGameInfo(null);
    setLookupError(null);
    setJoinError(null);
    setPlayerName('');
    setNameError(null);
  };

  // ── Derived State ─────────────────────────────────────────────────────

  const isGameJoinable = gameInfo?.can_join === true;
  const hasGameCode = !!urlGameCode;

  // ── Render: Loading Game Info ─────────────────────────────────────────

  if (isLookingUp) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center min-h-[70vh]">
          <LoadingSpinner message="Looking up game..." />
        </div>
      </Layout>
    );
  }

  // ── Render: Game Found — Show Join Form ───────────────────────────────

  if (gameInfo) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center min-h-[70vh]">
          <div className="w-full max-w-sm">
            <div className="text-center mb-8">
              <h1 className="text-2xl font-bold text-gray-900">
                Join Game
              </h1>
              <p className="text-gray-500 mt-1">
                Enter your name to join the table
              </p>
            </div>

            {/* Game Info Card */}
            <div className="rounded-xl border border-gray-200 bg-white p-5 mb-6">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-widest">
                  Game Info
                </p>
                <StatusBadge status={gameInfo.status} />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Manager</span>
                  <span className="text-sm font-semibold text-gray-900">
                    {gameInfo.manager_name}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Players</span>
                  <span className="text-sm font-semibold text-gray-900">
                    {gameInfo.player_count}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Code</span>
                  <span className="font-mono text-sm font-semibold text-gray-900 tracking-widest select-all">
                    {gameInfo.game_code}
                  </span>
                </div>
              </div>

              {!hasGameCode && (
                <button
                  type="button"
                  onClick={handleChangeCode}
                  className="mt-3 text-xs text-primary-600 hover:text-primary-700 font-medium focus:outline-none focus-visible:underline"
                >
                  Use a different code
                </button>
              )}
            </div>

            {/* Game Not Joinable */}
            {!isGameJoinable && (
              <div className="mb-6">
                <ErrorBanner message="This game is no longer accepting players." />
              </div>
            )}

            {/* Join Error */}
            {joinError && (
              <div className="mb-6">
                <ErrorBanner message={joinError} onRetry={handleJoin} />
              </div>
            )}

            {/* Name Input — only show if game is joinable */}
            {isGameJoinable && (
              <>
                <div className="mb-6">
                  <label
                    htmlFor="player-name"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    Your Display Name
                  </label>
                  <input
                    id="player-name"
                    type="text"
                    value={playerName}
                    onChange={(e) => {
                      setPlayerName(e.target.value);
                      if (nameError) setNameError(null);
                    }}
                    onKeyDown={handleJoinKeyDown}
                    placeholder="e.g. Alex"
                    maxLength={NAME_MAX}
                    autoFocus
                    autoComplete="off"
                    enterKeyHint="done"
                    aria-invalid={nameError ? 'true' : undefined}
                    aria-describedby={nameError ? 'name-error' : undefined}
                    className={`w-full rounded-xl border-2 px-4 py-3 text-lg placeholder:text-gray-400 focus:outline-none focus:ring-0 ${
                      nameError
                        ? 'border-red-400 focus:border-red-500'
                        : 'border-gray-300 focus:border-primary-500'
                    }`}
                  />
                  {nameError && (
                    <p id="name-error" className="mt-2 text-sm text-red-600" role="alert">
                      {nameError}
                    </p>
                  )}
                </div>

                {/* Submit Button */}
                <button
                  type="button"
                  onClick={handleJoin}
                  disabled={isJoining}
                  className="w-full rounded-xl bg-primary-600 px-6 py-4 text-lg font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isJoining ? (
                    <span className="flex items-center justify-center gap-2">
                      <LoadingSpinner size="sm" />
                      <span>Joining...</span>
                    </span>
                  ) : (
                    'Join Game'
                  )}
                </button>
              </>
            )}

            {/* Back to Home link when game is not joinable */}
            {!isGameJoinable && (
              <button
                type="button"
                onClick={() => navigate('/')}
                className="w-full rounded-xl border-2 border-gray-300 px-6 py-4 text-lg font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-gray-100"
              >
                Back to Home
              </button>
            )}
          </div>
        </div>
      </Layout>
    );
  }

  // ── Render: Code Input Form (no URL param or lookup error) ────────────

  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[70vh]">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900">
              Join Game
            </h1>
            <p className="text-gray-500 mt-1">
              Enter a game code to find the table
            </p>
          </div>

          {/* Lookup Error */}
          {lookupError && (
            <div className="mb-6">
              <ErrorBanner
                message={lookupError}
                onRetry={codeInput.trim().length > 0 ? handleCodeSubmit : undefined}
              />
            </div>
          )}

          {/* Code Input */}
          <div className="mb-6">
            <label
              htmlFor="game-code"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Game Code
            </label>
            <input
              id="game-code"
              type="text"
              value={codeInput}
              onChange={(e) => {
                const upper = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
                setCodeInput(upper);
                if (codeError) setCodeError(null);
                if (lookupError) setLookupError(null);
              }}
              onKeyDown={handleCodeKeyDown}
              placeholder="e.g. ABC123"
              maxLength={CODE_LENGTH}
              autoFocus
              autoComplete="off"
              enterKeyHint="go"
              autoCapitalize="characters"
              aria-invalid={codeError ? 'true' : undefined}
              aria-describedby={codeError ? 'code-error' : undefined}
              className={`w-full rounded-xl border-2 px-4 py-3 text-lg text-center font-mono tracking-[0.3em] uppercase placeholder:text-gray-400 placeholder:tracking-normal placeholder:font-sans focus:outline-none focus:ring-0 ${
                codeError
                  ? 'border-red-400 focus:border-red-500'
                  : 'border-gray-300 focus:border-primary-500'
              }`}
            />
            {codeError && (
              <p id="code-error" className="mt-2 text-sm text-red-600" role="alert">
                {codeError}
              </p>
            )}
          </div>

          {/* Lookup Button */}
          <button
            type="button"
            onClick={handleCodeSubmit}
            disabled={isLookingUp}
            className="w-full rounded-xl bg-primary-600 px-6 py-4 text-lg font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLookingUp ? (
              <span className="flex items-center justify-center gap-2">
                <LoadingSpinner size="sm" />
                <span>Looking up...</span>
              </span>
            ) : (
              'Find Game'
            )}
          </button>
        </div>
      </div>
    </Layout>
  );
}
