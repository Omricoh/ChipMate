import { useCallback, useEffect, useState } from 'react';
import { getSettlementSuggestions } from '../../api/settlement';
import type { SettlementSuggestion } from '../../api/types';

interface SettlementSuggestionsCardProps {
  gameId: string;
  hasDebtors: boolean;
}

export function SettlementSuggestionsCard({
  gameId,
  hasDebtors,
}: SettlementSuggestionsCardProps) {
  const [suggestions, setSuggestions] = useState<SettlementSuggestion[]>([]);
  const [totalDebt, setTotalDebt] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const fetchSuggestions = useCallback(async () => {
    if (!hasDebtors) {
      setSuggestions([]);
      setTotalDebt(0);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await getSettlementSuggestions(gameId);
      setSuggestions(data.suggestions);
      setTotalDebt(data.total_debt);
    } catch {
      setError('Failed to calculate settlement');
    } finally {
      setIsLoading(false);
    }
  }, [gameId, hasDebtors]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  // Don't show card if no debtors
  if (!hasDebtors) {
    return null;
  }

  return (
    <div className="rounded-xl bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setIsCollapsed((prev) => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-indigo-100/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">&#128221;</span>
          <h3 className="text-sm font-semibold text-indigo-900">
            Settlement Suggestions
          </h3>
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
          className={`h-4 w-4 text-indigo-500 transition-transform ${
            isCollapsed ? '' : 'rotate-180'
          }`}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m19.5 8.25-7.5 7.5-7.5-7.5"
          />
        </svg>
      </button>

      {!isCollapsed && (
        <div className="px-4 pb-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600" />
            </div>
          ) : error ? (
            <div className="text-center py-3">
              <p className="text-xs text-red-600">{error}</p>
              <button
                type="button"
                onClick={fetchSuggestions}
                className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-800"
              >
                Retry
              </button>
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-xs text-gray-500 py-2">
              No settlement needed - all debts are resolved.
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-indigo-700">
                Optimal transfers to settle {totalDebt.toLocaleString()} in debt:
              </p>

              <div className="space-y-2">
                {suggestions.map((suggestion, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-2 rounded-lg bg-white/70 border border-indigo-100 px-3 py-2.5"
                  >
                    <span className="flex-shrink-0 text-sm text-gray-600">
                      {index + 1}.
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 text-sm">
                        <span className="font-medium text-gray-900 truncate">
                          {suggestion.from_name}
                        </span>
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          strokeWidth={2}
                          stroke="currentColor"
                          className="h-3.5 w-3.5 flex-shrink-0 text-indigo-400"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"
                          />
                        </svg>
                        <span className="font-medium text-gray-900 truncate">
                          {suggestion.to_name}
                        </span>
                      </div>
                      {suggestion.note && (
                        <p className="text-xs text-gray-500 mt-0.5">
                          {suggestion.note}
                        </p>
                      )}
                    </div>
                    <span className="flex-shrink-0 font-semibold text-indigo-700 tabular-nums">
                      {suggestion.amount.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-indigo-100">
                <p className="text-xs text-gray-500 italic">
                  This is a suggestion only. Use the "Settle Debt" button on each
                  player to record the actual settlement.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
