export type CheckStatus =
  | "PASS"
  | "FAIL"
  | "NOT_APPLICABLE"
  | "UNVERIFIABLE"
  | "INCONCLUSIVE"
  | "PENDING";

export type OverallStatus = "PASS" | "REJECTED" | "INCONCLUSIVE" | "PENDING";

export type MatchResult = "MATCH" | "MISMATCH" | "INCONCLUSIVE";

export interface SessionCreated {
  session_id: string;
  token: string;
  expires_at?: string | null;
}

export interface OcrField {
  value?: string | null;
  confidence?: number | null;
  normalized?: string | null;
  raw?: string | null;
}

export interface OCRResult {
  fields: Record<string, OcrField>;
  confidence: Record<string, number>;
  warnings: string[];
  unreadable_fields: string[];
  text_lines: string[];
  portrait_extracted: boolean;
  portrait_path?: string | null;
  overall_quality_score: number;
}

export interface CardCheck {
  name: string;
  status: CheckStatus;
  reason: string;
  details?: Record<string, unknown>;
}

export interface CardAssessment {
  format_matched: boolean;
  quality_score: number;
  checks: CardCheck[];
  overall: CheckStatus;
  summary: string;
}

export interface QRResult {
  status: CheckStatus;
  detected: boolean;
  decoded: boolean;
  payload?: string | null;
  payload_type?: string | null;
  fields?: Record<string, unknown>;
  epic_matches_ocr?: boolean | null;
  reason: string;
}

export interface FieldMatch {
  field: string;
  ocr_value?: string | null;
  db_value?: string | null;
  matched?: boolean | null;
  similarity?: number | null;
  reason: string;
}

export interface DatabaseMatchResult {
  status: CheckStatus;
  record_found: boolean;
  record_id?: number | null;
  epic_matched: boolean;
  name_matched?: boolean | null;
  field_matches: FieldMatch[];
  source?: string | null;
  reason: string;
}

export interface DocumentSides {
  back_present: boolean;
  back_analyzed: boolean;
  front_epic?: string | null;
  back_epic?: string | null;
  epic_matches?: boolean | null;
  back_looks_like_front?: boolean | null;
  status: CheckStatus;
  reason: string;
}

export interface DocumentAnalysisResult {
  image_quality: CheckStatus;
  image_quality_reason: string;
  ocr: OCRResult;
  card_assessment: CardAssessment;
  qr?: QRResult | null;
  database?: DatabaseMatchResult | null;
  sides?: DocumentSides | null;
  preliminary_pass: boolean;
  preliminary_reasons: string[];
}

export interface FaceQualityResult {
  status: CheckStatus;
  face_detected: boolean;
  face_count: number;
  size_ok: boolean;
  centered: boolean;
  sharp: boolean;
  exposure_ok: boolean;
  obstructed?: boolean | null;
  instructions: string[];
  score: number;
  reason: string;
}

export interface FaceMatchResult {
  status: CheckStatus;
  match_result?: MatchResult | null;
  similarity?: number | null;
  threshold_match?: number | null;
  threshold_review?: number | null;
  id_face_available: boolean;
  live_face_available: boolean;
  reason: string;
}

export interface CheckItem {
  key: string;
  label: string;
  status: CheckStatus;
  reason: string;
  details?: Record<string, unknown>;
}

export interface VerificationResult {
  session_id: string;
  overall_status: OverallStatus;
  summary: string;
  reasons: string[];
  checklist: CheckItem[];
  document_analysis?: DocumentAnalysisResult | null;
  face_match?: FaceMatchResult | null;
  liveness?: Record<string, unknown> | null;
  disclosures: string[];
}

export interface FaceSubmitResponse {
  session_id: string;
  face_quality: FaceQualityResult;
  accepted: boolean;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  dependencies: Record<string, string>;
  demo_mode: boolean;
}
