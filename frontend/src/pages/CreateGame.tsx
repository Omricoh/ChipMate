import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { ErrorBanner } from '../components/common/ErrorBanner';
import {
  ToastContainer,
  createToast,
  type ToastMessage,
} from '../components/common/Toast';
import { QRCode } from '../components/game/QRCode';
import { createGame } from '../api/games';
import { useAuth } from '../hooks/useAuth';
import type { CreateGameResponse } from '../api/types';

// ── Name Validation ───────────────────────────────────────────────────────

const NAME_MIN = 2;
const NAME_MAX = 30;

function validateName(name: string): string | null {
  const trimmed = name.trim();
  if (trimmed.length === 0) return 'Display name is required';
  if (trimmed.length < NAME_MIN) return `Name must be at least ${NAME_MIN} characters`;
  if (trimmed.length > NAME_MAX) return `Name must be at most ${NAME_MAX} characters`;
  return null;
}

// ── Component ─────────────────────────────────────────────────────────────

export default function CreateGame() {
  const navigate = useNavigate();
  const { joinGame: authJoinGame } = useAuth();

  // Form state
  const [managerName, setManagerName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Success state
  const [gameData, setGameData] = useState<CreateGameResponse | null>(null);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((variant: 'success' | 'error' | 'info', message: string) => {
    setToasts((prev) => [...prev, createToast(variant, message)]);
  }, []);

  // ── Create Game Handler ───────────────────────────────────────────────

  const handleCreate = async () => {
    const error = validateName(managerName);
    if (error) {
      setNameError(error);
      return;
    }

    setNameError(null);
    setApiError(null);
    setIsSubmitting(true);

    try {
      const result = await createGame(managerName.trim());
      setGameData(result);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Could not create game. Check your connection.';
      setApiError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSubmitting) {
      handleCreate();
    }
  };

  // ── Copy Code Handler ─────────────────────────────────────────────────

  const handleCopyCode = async () => {
    if (!gameData) return;
    try {
      await navigator.clipboard.writeText(gameData.game_code);
      addToast('success', 'Game code copied!');
    } catch {
      addToast('error', 'Failed to copy code');
    }
  };

  // ── Share Handler ─────────────────────────────────────────────────────

  const handleShare = async () => {
    if (!gameData) return;

    const joinUrl = `${window.location.origin}/join/${gameData.game_code}`;

    if (navigator.share) {
      try {
        await navigator.share({
          title: 'Join my ChipMate game',
          text: `Join my poker game on ChipMate! Game code: ${gameData.game_code}`,
          url: joinUrl,
        });
      } catch (err) {
        // User cancelled share -- not an error
        if (err instanceof Error && err.name !== 'AbortError') {
          addToast('error', 'Failed to share');
        }
      }
    } else {
      // Fallback: copy link to clipboard
      try {
        await navigator.clipboard.writeText(joinUrl);
        addToast('success', 'Link copied!');
      } catch {
        addToast('error', 'Failed to copy link');
      }
    }
  };

  // ── Enter Game Handler ────────────────────────────────────────────────

  const handleEnterGame = () => {
    if (!gameData) return;

    authJoinGame({
      token: gameData.player_token,
      playerId: gameData.manager_player_id,
      gameId: gameData.game_id,
      gameCode: gameData.game_code,
      name: managerName.trim(),
      isManager: true,
    });

    navigate(`/game/${gameData.game_id}`, { replace: true });
  };

  // ── Render: Success State ─────────────────────────────────────────────

  if (gameData) {
    const gameCodeChars = gameData.game_code.split('');
    const ariaLabel = `Game code: ${gameCodeChars.join(', ')}`;

    return (
      <Layout>
        <div className="flex flex-col items-center py-6">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold text-gray-900">
              Game Created
            </h1>
            <p className="text-gray-500 mt-1">
              Share the code or QR with your players
            </p>
          </div>

          {/* Game Code Display */}
          <div
            className="bg-gray-900 rounded-2xl px-8 py-5 mb-6"
            role="status"
            aria-label={ariaLabel}
          >
            <p className="text-xs font-medium text-gray-400 uppercase tracking-widest mb-2 text-center">
              Game Code
            </p>
            <p className="font-mono text-4xl font-bold text-white tracking-[0.3em] text-center select-all">
              {gameData.game_code}
            </p>
          </div>

          {/* QR Code */}
          <div className="mb-6">
            <QRCode gameCode={gameData.game_code} size={200} />
          </div>

          {/* Action Buttons */}
          <div className="w-full space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={handleCopyCode}
                className="flex items-center justify-center gap-2 rounded-xl border-2 border-gray-300 px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-gray-100"
              >
                {/* Copy icon */}
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5"
                  aria-hidden="true"
                >
                  <path d="M7 3.5A1.5 1.5 0 0 1 8.5 2h3.879a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 17 6.622V12.5a1.5 1.5 0 0 1-1.5 1.5h-1v-3.379a3 3 0 0 0-.879-2.121L10.5 5.379A3 3 0 0 0 8.379 4.5H7v-1Z" />
                  <path d="M4.5 6A1.5 1.5 0 0 0 3 7.5v9A1.5 1.5 0 0 0 4.5 18h7a1.5 1.5 0 0 0 1.5-1.5v-5.879a1.5 1.5 0 0 0-.44-1.06L9.44 6.439A1.5 1.5 0 0 0 8.378 6H4.5Z" />
                </svg>
                Copy Code
              </button>

              <button
                type="button"
                onClick={handleShare}
                className="flex items-center justify-center gap-2 rounded-xl border-2 border-gray-300 px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-gray-100"
              >
                {/* Share icon */}
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-5 w-5"
                  aria-hidden="true"
                >
                  <path d="M13 4.5a2.5 2.5 0 1 1 .702 1.737L6.97 9.604a2.518 2.518 0 0 1 0 .799l6.733 3.366a2.5 2.5 0 1 1-.671 1.341l-6.733-3.366a2.5 2.5 0 1 1 0-3.48l6.733-3.367A2.52 2.52 0 0 1 13 4.5Z" />
                </svg>
                Share
              </button>
            </div>

            <button
              type="button"
              onClick={handleEnterGame}
              className="w-full rounded-xl bg-primary-600 px-6 py-4 text-lg font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800"
            >
              Enter Game
            </button>
          </div>
        </div>

        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      </Layout>
    );
  }

  // ── Render: Create Form ───────────────────────────────────────────────

  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[70vh]">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900">
              New Game
            </h1>
            <p className="text-gray-500 mt-1">
              Enter your name to create a poker game
            </p>
          </div>

          {/* API Error */}
          {apiError && (
            <div className="mb-6">
              <ErrorBanner message={apiError} onRetry={handleCreate} />
            </div>
          )}

          {/* Name Input */}
          <div className="mb-6">
            <label
              htmlFor="manager-name"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Your Display Name
            </label>
            <input
              id="manager-name"
              type="text"
              value={managerName}
              onChange={(e) => {
                setManagerName(e.target.value);
                if (nameError) setNameError(null);
              }}
              onKeyDown={handleKeyDown}
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
            onClick={handleCreate}
            disabled={isSubmitting}
            className="w-full rounded-xl bg-primary-600 px-6 py-4 text-lg font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <span className="flex items-center justify-center gap-2">
                <LoadingSpinner size="sm" />
                <span>Creating...</span>
              </span>
            ) : (
              'Create Game'
            )}
          </button>
        </div>
      </div>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  );
}
