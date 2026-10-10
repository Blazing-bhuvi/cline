import { useState } from "react";
import * as api from "./api";
import type { DocumentAnalysisResult, VerificationResult } from "./types";
import { Welcome } from "./pages/Welcome";
import { UploadDocument } from "./pages/UploadDocument";
import { DocumentAnalysis } from "./pages/DocumentAnalysis";
import { CameraVerification } from "./pages/CameraVerification";
import { FinalReport } from "./pages/FinalReport";

type Stage = "welcome" | "upload" | "analysis" | "camera" | "report";

function message(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

export default function App() {
  const [stage, setStage] = useState<Stage>("welcome");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<DocumentAnalysisResult | null>(null);
  const [result, setResult] = useState<VerificationResult | null>(null);

  const [busy, setBusy] = useState<{ active: boolean; message: string }>({
    active: false,
    message: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string[]>([]);

  async function handleStart() {
    setError(null);
    setBusy({ active: true, message: "Starting a verification session…" });
    try {
      const s = await api.startVerification(true, "front");
      setSessionId(s.session_id);
      setToken(s.token);
      setStage("upload");
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy({ active: false, message: "" });
    }
  }

  async function handleUpload(front: File | null, back: File | null) {
    if (!sessionId || !token) return;
    setError(null);

    setBusy({ active: true, message: "Uploading document image(s)…" });
    try {
      if (front) await api.uploadDocument(sessionId, token, front, "front");
      if (back) await api.uploadDocument(sessionId, token, back, "back");
    } catch (e) {
      setError(message(e));
      setBusy({ active: false, message: "" });
      return;
    }

    setBusy({ active: true, message: "Analyzing document (OCR, QR, database)…" });
    try {
      const a = await api.analyzeDocument(sessionId, token);
      setAnalysis(a);
      setStage("analysis");
    } catch (e) {
      setError(message(e));
      setStage("upload");
    } finally {
      setBusy({ active: false, message: "" });
    }
  }

  async function handleFace(blob: Blob) {
    if (!sessionId || !token) return;
    setError(null);
    setInstructions([]);
    setBusy({ active: true, message: "Comparing your face with the ID portrait…" });
    try {
      const resp = await api.submitFace(sessionId, token, blob);
      if (resp.accepted) {
        const res = await api.getResult(sessionId, token);
        setResult(res);
        setStage("report");
      } else {
        setInstructions(resp.face_quality.instructions);
      }
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy({ active: false, message: "" });
    }
  }

  async function handleRetry() {
    if (analysis?.preliminary_pass) {
      setStage("camera");
    } else {
      setStage("upload");
    }
  }

  async function handleNew() {
    if (sessionId && token) {
      try {
        await api.deleteSession(sessionId, token);
      } catch {
        /* ignore */
      }
    }
    setSessionId(null);
    setToken(null);
    setAnalysis(null);
    setResult(null);
    setError(null);
    setInstructions([]);
    setStage("welcome");
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-4">
          <h1 className="text-lg font-bold text-slate-900">Voter ID Verification</h1>
          <span className="text-xs text-slate-400">Local demo prototype</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        {stage === "welcome" && <Welcome onStart={handleStart} />}

        {stage === "upload" && <UploadDocument onUpload={handleUpload} error={error} />}

        {stage === "analysis" && analysis && (
          <DocumentAnalysis
            analysis={analysis}
            error={error}
            onContinue={() => setStage("camera")}
            onRetry={() => setStage("upload")}
          />
        )}

        {stage === "camera" && (
          <CameraVerification
            onSubmit={handleFace}
            onCancel={() => setStage("analysis")}
            submitting={busy.active}
            instructions={instructions}
          />
        )}

        {stage === "report" && result && (
          <FinalReport result={result} onRetry={handleRetry} onNew={handleNew} />
        )}

        {error && stage === "welcome" && (
          <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
        )}
      </main>

      {busy.active && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/70 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-lg bg-white p-6 shadow-lg">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <p className="text-sm font-medium text-slate-700">{busy.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}

