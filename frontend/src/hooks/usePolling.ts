import { useEffect, useRef } from 'react';

/**
 * Polls a callback at a regular interval.
 * Automatically pauses when the browser tab is hidden and
 * resumes with an immediate fetch when the tab becomes visible again.
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled = true,
): void {
  const savedCallback = useRef(callback);

  // Keep the callback ref up to date without triggering re-subscriptions
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;

    // Fire immediately on mount
    savedCallback.current();

    let timerId: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timerId !== null) return;
      timerId = setInterval(() => {
        savedCallback.current();
      }, intervalMs);
    };

    const stop = () => {
      if (timerId !== null) {
        clearInterval(timerId);
        timerId = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Fetch immediately when tab becomes visible, then resume interval
        savedCallback.current();
        start();
      } else {
        stop();
      }
    };

    // Start the interval
    start();

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      stop();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [intervalMs, enabled]);
}
