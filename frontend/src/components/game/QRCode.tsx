import { useState } from 'react';
import { getQrCodeUrl } from '../../api/games';

interface QRCodeProps {
  /** The 6-character game code */
  gameCode: string;
  /** Size of the QR code in pixels (default 256) */
  size?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Renders a QR code image for a game join link.
 * The image is loaded from the backend QR endpoint.
 * Shows a loading placeholder while the image loads and
 * a fallback message if the image fails to load.
 */
export function QRCode({ gameCode, size = 256, className = '' }: QRCodeProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  const src = getQrCodeUrl(gameCode);

  if (hasError) {
    return (
      <div
        className={`flex items-center justify-center rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 ${className}`}
        style={{ width: size, height: size }}
        role="img"
        aria-label={`QR code for game ${gameCode} could not be loaded`}
      >
        <div className="text-center px-4">
          <p className="text-sm text-gray-500">QR code unavailable</p>
          <p className="text-xs text-gray-400 mt-1">
            Share the game code instead
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`} style={{ width: size, height: size }}>
      {/* Loading placeholder */}
      {isLoading && (
        <div
          className="absolute inset-0 flex items-center justify-center rounded-xl bg-gray-100 animate-pulse"
          role="status"
        >
          <span className="sr-only">Loading QR code...</span>
        </div>
      )}

      <img
        src={src}
        alt={`QR code to join game ${gameCode}`}
        width={size}
        height={size}
        className={`rounded-xl transition-opacity duration-200 ${
          isLoading ? 'opacity-0' : 'opacity-100'
        }`}
        onLoad={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setHasError(true);
        }}
      />
    </div>
  );
}
