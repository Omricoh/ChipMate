import { useCallback } from 'react';
import { QRCode } from './QRCode';
import {
  createToast,
  type ToastMessage,
} from '../common/Toast';

interface GameShareSectionProps {
  gameCode: string;
  /** Callback to surface toast messages to the parent */
  onToast: (toast: ToastMessage) => void;
}

/**
 * Section displaying the game code prominently, a QR code,
 * and copy/share action buttons for inviting players.
 */
export function GameShareSection({ gameCode, onToast }: GameShareSectionProps) {
  const joinUrl = `${window.location.origin}/join/${gameCode}`;

  const handleCopyCode = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(gameCode);
      onToast(createToast('success', 'Game code copied!'));
    } catch {
      onToast(createToast('error', 'Failed to copy code'));
    }
  }, [gameCode, onToast]);

  const handleCopyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(joinUrl);
      onToast(createToast('success', 'Join link copied!'));
    } catch {
      onToast(createToast('error', 'Failed to copy link'));
    }
  }, [joinUrl, onToast]);

  const handleShare = useCallback(async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: 'Join my ChipMate game',
          text: `Join my poker game on ChipMate! Game code: ${gameCode}`,
          url: joinUrl,
        });
      } catch (err) {
        // User cancelled share -- not an error
        if (err instanceof Error && err.name !== 'AbortError') {
          onToast(createToast('error', 'Failed to share'));
        }
      }
    } else {
      // Fallback: copy link
      await handleCopyLink();
    }
  }, [gameCode, joinUrl, onToast, handleCopyLink]);

  const gameCodeChars = gameCode.split('');
  const ariaLabel = `Game code: ${gameCodeChars.join(', ')}`;

  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
      aria-label="Share game"
    >
      <h2 className="text-sm font-semibold text-gray-700 mb-4">
        Invite Players
      </h2>

      {/* Game Code Display */}
      <div className="flex justify-center mb-4">
        <div
          className="bg-gray-900 rounded-xl px-6 py-3"
          role="status"
          aria-label={ariaLabel}
        >
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-widest mb-1 text-center">
            Game Code
          </p>
          <p className="font-mono text-2xl font-bold text-white tracking-[0.25em] text-center select-all">
            {gameCode}
          </p>
        </div>
      </div>

      {/* QR Code */}
      <div className="flex justify-center mb-4">
        <QRCode gameCode={gameCode} size={160} />
      </div>

      {/* Action Buttons */}
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={handleCopyCode}
          className="flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:bg-gray-100"
        >
          {/* Copy icon (heroicons mini) */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
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
          className="flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:bg-gray-100"
        >
          {/* Share icon (heroicons mini) */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path d="M13 4.5a2.5 2.5 0 1 1 .702 1.737L6.97 9.604a2.518 2.518 0 0 1 0 .799l6.733 3.366a2.5 2.5 0 1 1-.671 1.341l-6.733-3.366a2.5 2.5 0 1 1 0-3.48l6.733-3.367A2.52 2.52 0 0 1 13 4.5Z" />
          </svg>
          Share Link
        </button>
      </div>
    </section>
  );
}
