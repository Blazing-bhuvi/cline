import type { CheckStatus, OverallStatus } from "../types";

const COLORS: Record<string, string> = {
  PASS: "bg-green-100 text-green-800 border-green-300",
  FAIL: "bg-red-100 text-red-800 border-red-300",
  REJECTED: "bg-red-100 text-red-800 border-red-300",
  NOT_APPLICABLE: "bg-slate-100 text-slate-600 border-slate-300",
  UNVERIFIABLE: "bg-amber-100 text-amber-800 border-amber-300",
  INCONCLUSIVE: "bg-amber-100 text-amber-800 border-amber-300",
  PENDING: "bg-slate-100 text-slate-500 border-slate-300",
};

export function StatusBadge({ status }: { status: CheckStatus | OverallStatus }) {
  const color = COLORS[status] ?? COLORS.PENDING;
  return (
    <span className={`inline-block whitespace-nowrap px-2 py-0.5 text-xs font-semibold rounded border ${color}`}>
      {status}
    </span>
  );
}
