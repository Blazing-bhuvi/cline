import { StatusBadge } from "../components/StatusBadge";
import type { DocumentAnalysisResult } from "../types";

interface Props {
  analysis: DocumentAnalysisResult;
  error: string | null;
  onContinue: () => void;
  onRetry: () => void;
}

function FieldRow({ label, value, confidence }: { label: string; value?: string | null; confidence?: number | null }) {
  return (
    <div className="flex justify-between border-b border-slate-100 py-1.5">
      <span className="text-slate-500">{label}</span>
      <span className="text-right">
        {value ?? <span className="text-amber-600 italic">not read</span>}
        {value && confidence != null && (
          <span className="ml-2 text-xs text-slate-400">{Math.round(confidence * 100)}%</span>
        )}
      </span>
    </div>
  );
}

export function DocumentAnalysis({ analysis, error, onContinue, onRetry }: Props) {
  const { ocr, card_assessment, qr, database, sides } = analysis;
  const fields = ocr.fields;

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl bg-white p-8 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Document Analysis</h2>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Image quality</p>
                <div className="mt-1"><StatusBadge status={analysis.image_quality} /></div>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Card assessment</p>
                <div className="mt-1"><StatusBadge status={card_assessment.overall} /></div>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Database match</p>
                <div className="mt-1"><StatusBadge status={database?.status ?? "PENDING"} /></div>
              </div>
            </div>

            <div className="mt-6">
              <h3 className="font-semibold text-slate-800">Extracted fields</h3>
              <div className="mt-2 rounded-md border p-3">
                <FieldRow label="EPIC number" value={fields.epic?.value} confidence={fields.epic?.confidence} />
                <FieldRow label="Name" value={fields.name?.value} confidence={fields.name?.confidence} />
                <FieldRow label="Relative's name" value={fields.relative_name?.value} confidence={fields.relative_name?.confidence} />
                <FieldRow label="Date of birth" value={fields.dob?.value} confidence={fields.dob?.confidence} />
                <FieldRow label="Gender" value={fields.gender?.value} confidence={fields.gender?.confidence} />
              </div>
            </div>

            <div className="mt-6">
              <h3 className="font-semibold text-slate-800">QR analysis</h3>
              <p className="mt-1 text-sm text-slate-600">{qr?.reason ?? "Not run"}</p>
            </div>

            {database && (
              <div className="mt-6">
                <h3 className="font-semibold text-slate-800">Database cross-verification</h3>
                <p className="mt-1 text-sm text-slate-600">{database.reason}</p>
                {database.record_found && (
                  <p className="mt-1 text-xs text-slate-400">Source: {database.source ?? "unknown"}</p>
                )}
              </div>
            )}

            {sides && sides.back_present && (
              <div className="mt-6">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-slate-800">Front/back correspondence</h3>
                  <StatusBadge status={sides.status} />
                </div>
                <p className="mt-1 text-sm text-slate-600">{sides.reason}</p>
                {sides.front_epic && sides.back_epic && (
                  <p className="mt-1 text-xs text-slate-400">
                    Front EPIC: {sides.front_epic} · Back EPIC: {sides.back_epic}
                  </p>
                )}
              </div>
            )}

            {analysis.preliminary_reasons.length > 0 && (
              <ul className="mt-6 list-disc space-y-1 rounded-md bg-amber-50 p-4 pl-8 text-sm text-amber-800">
                {analysis.preliminary_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}

            {error && <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={onRetry}
                className="rounded-md bg-slate-100 px-4 py-2 font-medium text-slate-700 hover:bg-slate-200"
              >
                Re-upload
              </button>
              {analysis.preliminary_pass && (
                <button
                  type="button"
                  onClick={onContinue}
                  className="rounded-md bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-700"
                >
                  Continue to Camera
                </button>
              )}
            </div>
      </div>
    </div>
  );
}
