import { type ReactNode } from 'react';

interface EmptyStateProps {
  /** Icon rendered above the message (pass an SVG or emoji) */
  icon?: ReactNode;
  /** Primary message */
  message: string;
  /** Optional secondary description */
  description?: string;
  /** Optional action button label */
  actionLabel?: string;
  /** Callback when the action button is pressed */
  onAction?: () => void;
}

export function EmptyState({
  icon,
  message,
  description,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && (
        <div className="mb-4 text-gray-300" aria-hidden="true">
          {icon}
        </div>
      )}

      <h3 className="text-base font-semibold text-gray-700">{message}</h3>

      {description && (
        <p className="mt-1 text-sm text-gray-500 max-w-xs">{description}</p>
      )}

      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-6 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
