import { CheckList } from "../components/CheckList";
import type { VerificationResult } from "../types";

interface Props {
  result: VerificationResult;
  onRetry: () => void;
  onNew: () => void;
}

export function FinalReport({ result, onRetry, onNew }: Props) {
  const { overall_status, summary, reasons, checklist, disclosures, face_match } = result;

  const banner =
    overall_status === "PASS"
      ? "bg-green-100 text-green-800 border-green-300"
      : overall_status === "REJECTED"
        ? "bg-red-100 text-red-800 border-red-300"
        : "bg-amber-100 text-amber-800 border-amber-300";

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl bg-white p-8 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Final Report</h2>

        <div className={`mt-4 rounded-md border p-4 text-center ${banner}`}>
          <p className="text-lg font-bold">{overall_status}</p>
          <p className="mt-1">{summary}</p>
        </div>

        {face_match?.similarity != null && (
          <p className="mt-3 text-center text-sm text-slate-500">
            Face similarity: {(face_match.similarity * 100).toFixed(1)}%
          </p>
        )}

        {reasons.length > 0 && (
          <div className="mt-4">
            <h3 className="font-semibold text-slate-800">Details</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-6">
          <h3 className="font-semibold text-slate-800">Check results</h3>
          <div className="mt-2 rounded-md border p-3">
            <CheckList items={checklist} />
          </div>
        </div>

        <div className="mt-6">
          <h3 className="font-semibold text-slate-800">Disclosures &amp; limitations</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
            {disclosures.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          {overall_status !== "PASS" && (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-md bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-700"
            >
              Retry
            </button>
          )}
          <button
            type="button"
            onClick={onNew}
            className="rounded-md bg-slate-100 px-4 py-2 font-medium text-slate-700 hover:bg-slate-200"
          >
            New verification
          </button>
        </div>
      </div>
    </div>
  );
}
