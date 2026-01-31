interface LoadingSpinnerProps {
  /** Optional message displayed below the spinner */
  message?: string;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses: Record<string, string> = {
  sm: 'h-6 w-6 border-2',
  md: 'h-10 w-10 border-2',
  lg: 'h-14 w-14 border-[3px]',
};

export function LoadingSpinner({
  message,
  size = 'md',
}: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12" role="status">
      <div
        className={`animate-spin rounded-full border-primary-600 border-t-transparent ${sizeClasses[size]}`}
      />
      {message && (
        <p className="mt-4 text-sm text-gray-500">{message}</p>
      )}
      <span className="sr-only">Loading{message ? `: ${message}` : ''}...</span>
    </div>
  );
}
