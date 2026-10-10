import type {
  DocumentAnalysisResult,
  FaceSubmitResponse,
  HealthResponse,
  SessionCreated,
  VerificationResult,
} from "./types";

const BASE = "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function tokenHeaders(token: string): Record<string, string> {
  return { "X-Session-Token": token };
}

export async function startVerification(consent: boolean, side_required = "front"): Promise<SessionCreated> {
  return request<SessionCreated>("/api/verification/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ consent, side_required }),
  });
}

export async function uploadDocument(
  sessionId: string,
  token: string,
  file: File,
  side: "front" | "back"
): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  form.append("side", side);
  await request(`/api/verification/${sessionId}/document`, {
    method: "POST",
    headers: tokenHeaders(token),
    body: form,
  });
}

export async function analyzeDocument(sessionId: string, token: string): Promise<DocumentAnalysisResult> {
  return request<DocumentAnalysisResult>(`/api/verification/${sessionId}/analyze`, {
    method: "POST",
    headers: tokenHeaders(token),
  });
}

export async function submitFace(
  sessionId: string,
  token: string,
  blob: Blob
): Promise<FaceSubmitResponse> {
  const form = new FormData();
  form.append("file", blob, "capture.png");
  return request<FaceSubmitResponse>(`/api/verification/${sessionId}/face`, {
    method: "POST",
    headers: tokenHeaders(token),
    body: form,
  });
}

export async function getResult(sessionId: string, token: string): Promise<VerificationResult> {
  return request<VerificationResult>(`/api/verification/${sessionId}/result`, {
    method: "GET",
    headers: tokenHeaders(token),
  });
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export async function deleteSession(sessionId: string, token: string): Promise<void> {
  await request(`/api/verification/${sessionId}`, {
    method: "DELETE",
    headers: tokenHeaders(token),
  });
}
