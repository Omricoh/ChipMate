import type { BankSummary } from '../../api/types';

interface BankSummaryCardProps {
  chips: BankSummary;
  pendingRequests: number;
  creditsOutstanding: number;
}

interface StatItemProps {
  label: string;
  value: number;
  color?: string;
}

function StatItem({ label, value, color = 'text-gray-900' }: StatItemProps) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={`text-xl font-bold tabular-nums ${color}`}>
        {value.toLocaleString()}
      </span>
    </div>
  );
}

/**
 * Compact card showing the game's financial summary.
 * Displays total cash, credit, chips in play, and checked-out totals.
 */
export function BankSummaryCard({
  chips,
  pendingRequests,
  creditsOutstanding,
}: BankSummaryCardProps) {
  return (
    <section
      className="rounded-xl bg-white border border-gray-200 shadow-sm p-4"
      aria-label="Bank summary"
    >
      <h2 className="text-sm font-semibold text-gray-700 mb-3">
        Bank Summary
      </h2>

      <div className="grid grid-cols-2 gap-4">
        <StatItem
          label="Cash In"
          value={chips.total_cash_in}
          color="text-green-700"
        />
        <StatItem
          label="Credit In"
          value={chips.total_credit_in}
          color="text-sky-700"
        />
        <StatItem
          label="In Play"
          value={chips.total_in_play}
        />
        <StatItem
          label="Checked Out"
          value={chips.total_checked_out}
          color="text-gray-500"
        />
      </div>

      {/* Secondary info row */}
      {(pendingRequests > 0 || creditsOutstanding > 0) && (
        <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
          {pendingRequests > 0 && (
            <span>
              <span className="font-semibold text-amber-600">
                {pendingRequests}
              </span>{' '}
              pending request{pendingRequests !== 1 ? 's' : ''}
            </span>
          )}
          {creditsOutstanding > 0 && (
            <span>
              <span className="font-semibold text-sky-600">
                {creditsOutstanding.toLocaleString()}
              </span>{' '}
              credits owed
            </span>
          )}
        </div>
      )}
    </section>
  );
}
