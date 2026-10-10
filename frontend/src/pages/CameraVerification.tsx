import { useEffect, useState } from "react";
import { useCamera } from "../hooks/useCamera";

interface Props {
  onSubmit: (blob: Blob) => Promise<void>;
  onCancel: () => void;
  submitting: boolean;
  instructions: string[];
}

export function CameraVerification({ onSubmit, onCancel, submitting, instructions }: Props) {
  const { videoRef, error, start, stop, capture } = useCamera();
  const [capturedUrl, setCapturedUrl] = useState<string | null>(null);
  const [capturedBlob, setCapturedBlob] = useState<Blob | null>(null);

  useEffect(() => {
    start();
  }, [start]);

  const handleCapture = async () => {
    try {
      const blob = await capture();
      setCapturedBlob(blob);
      setCapturedUrl(URL.createObjectURL(blob));
      stop();
    } catch {
      /* ignore */
    }
  };

  const handleRetake = () => {
    if (capturedUrl) URL.revokeObjectURL(capturedUrl);
    setCapturedUrl(null);
    setCapturedBlob(null);
    start();
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl bg-white p-8 shadow-sm">
        <h2 className="text-xl font-bold text-slate-900">Camera Verification</h2>
        <p className="mt-1 text-sm text-slate-600">
          Position your face inside the guide, keep steady, and capture.
        </p>

        {error && (
          <div className="mt-4 rounded-md bg-red-50 p-4 text-sm text-red-700">
            <p>{error}</p>
            <button type="button" onClick={onCancel} className="mt-2 underline">
              Cancel
            </button>
          </div>
        )}

        {!error && (
          <div className="relative mt-4 overflow-hidden rounded-lg bg-black">
            {capturedUrl ? (
              <img src={capturedUrl} alt="Captured face" className="w-full" />
            ) : (
              <>
                <video ref={videoRef} muted playsInline className="w-full" />
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <div className="h-56 w-56 rounded-full border-2 border-dashed border-white/70" />
                </div>
              </>
            )}
          </div>
        )}

        {instructions.length > 0 && (
          <ul className="mt-4 list-disc space-y-1 rounded-md bg-amber-50 p-4 pl-8 text-sm text-amber-800">
            {instructions.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}

        <div className="mt-6 flex justify-center gap-3">
          {!capturedUrl ? (
            <button
              type="button"
              onClick={handleCapture}
              className="rounded-md bg-blue-600 px-6 py-2 font-semibold text-white hover:bg-blue-700"
            >
              Capture
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={handleRetake}
                className="rounded-md bg-slate-100 px-4 py-2 font-medium text-slate-700 hover:bg-slate-200"
              >
                Retake
              </button>
              <button
                type="button"
                disabled={submitting || !capturedBlob}
                onClick={() => capturedBlob && onSubmit(capturedBlob)}
                className="rounded-md bg-green-600 px-5 py-2 font-semibold text-white hover:bg-green-700 disabled:opacity-50"
              >
                {submitting ? "Comparing…" : "Use this photo"}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md bg-slate-100 px-4 py-2 font-medium text-slate-700 hover:bg-slate-200"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
