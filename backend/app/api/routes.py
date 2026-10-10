"""REST endpoints for the verification workflow."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import resolve_session
from app.core.config import get_settings
from app.database.session import get_db
from app.schemas.schemas import (
    CheckStatus,
    DocumentAnalysisResult,
    DocumentUploadResponse,
    FaceSubmitResponse,
    HealthResponse,
    OverallStatus,
    RetryResponse,
    SessionCreated,
    Side,
    StartRequest,
    UploadedImage,
    VerificationResult,
)
from app.services import verification_service
from app.services.decision_engine import decide
from app.services.session_manager import DocumentImage, FaceCapture, get_session_manager
from app.services.verification_service import liveness_result
from app.utils import image_utils
from app.utils.image_utils import ImageDecodeError

router = APIRouter(prefix="/api")


def _read_upload(file: UploadFile, settings):
    if file.content_type and file.content_type.lower() not in settings.allowed_image_type_list:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {file.content_type}")
    data = file.file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit.")
    try:
        img = image_utils.decode_image(data)
        image_utils.validate_dimensions(img)
    except ImageDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return img


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    from app.services.face_matcher import get_face_matcher

    deps = {
        "database": "ok",
        "ocr": settings.ocr_engine,
        "face_model": "available" if get_face_matcher().is_available() else "unavailable",
    }
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        dependencies=deps,
        demo_mode=settings.demo_mode,
    )


@router.post("/verification/start", response_model=SessionCreated, status_code=201)
def start_verification(req: StartRequest) -> SessionCreated:
    if not req.consent:
        raise HTTPException(status_code=400, detail="Explicit consent is required.")
    session = get_session_manager().create(req.consent, req.side_required.value)
    return SessionCreated(
        session_id=session.session_id,
        token=session.token,
        expires_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(session.expires_at)),
    )


@router.post("/verification/{session_id}/document", response_model=DocumentUploadResponse)
def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    side: str = Form("front"),
    x_session_token: str | None = Header(default=None),
):
    current = resolve_session(session_id, x_session_token)
    settings = get_settings()
    img = _read_upload(file, settings)

    side_enum = Side.FRONT if side.lower() == "front" else Side.BACK
    filename = image_utils.generate_filename(side_enum.value, "png")
    path = get_session_manager().session_dir(session_id) / filename
    image_utils.write_image(img, path)

    h, w = img.shape[:2]
    current.images[side_enum.value] = DocumentImage(
        side=side_enum.value,
        filename=filename,
        path=path,
        width=w,
        height=h,
        size_bytes=path.stat().st_size,
        content_type=file.content_type or "image/png",
    )
    current.stage = "analyze"
    get_session_manager().touch(current)

    return DocumentUploadResponse(
        session_id=session_id,
        images=[
            UploadedImage(
                side=Side(i.side),
                filename=i.filename,
                width=i.width,
                height=i.height,
                size_bytes=i.size_bytes,
                content_type=i.content_type,
            )
            for i in current.images.values()
        ],
        warnings=[],
    )

@router.post("/verification/{session_id}/analyze", response_model=DocumentAnalysisResult)
def analyze(
    session_id: str,
    db: Session = Depends(get_db),
    x_session_token: str | None = Header(default=None),
):
    current = resolve_session(session_id, x_session_token)
    front = current.images.get("front")
    if front is None:
        raise HTTPException(status_code=400, detail="No front document uploaded.")
    back = current.images.get("back")
    analysis = verification_service.analyze_document(
        db, front.path, back.path if back else None
    )
    current.analysis = analysis
    current.stage = "camera" if analysis.preliminary_pass else "result"
    get_session_manager().touch(current)
    return analysis


@router.post("/verification/{session_id}/face", response_model=FaceSubmitResponse)
def submit_face(
    session_id: str,
    file: UploadFile = File(...),
    x_session_token: str | None = Header(default=None),
):
    current = resolve_session(session_id, x_session_token)
    if current.analysis is None:
        raise HTTPException(status_code=400, detail="Document must be analyzed before face capture.")
    if not current.analysis.preliminary_pass:
        raise HTTPException(
            status_code=400,
            detail="Preliminary document checks did not pass; camera stage is not available.",
        )

    settings = get_settings()
    img = _read_upload(file, settings)
    filename = image_utils.generate_filename("live_face", "png")
    path = get_session_manager().session_dir(session_id) / filename
    image_utils.write_image(img, path)

    quality, face_match, result = verification_service.process_face_capture(
        session_id, current.analysis, path
    )
    accepted = quality.status == CheckStatus.PASS
    current.face_capture = FaceCapture(path=path, quality=quality)
    current.face_match = face_match
    if accepted:
        current.result = result
        current.stage = "result"
    else:
        current.result = None
        current.stage = "camera"
    get_session_manager().touch(current)

    return FaceSubmitResponse(
        session_id=session_id,
        face_quality=quality,
        accepted=accepted,
    )


@router.get("/verification/{session_id}/result", response_model=VerificationResult)
def get_result(session_id: str, x_session_token: str | None = Header(default=None)):
    current = resolve_session(session_id, x_session_token)
    if current.result is not None:
        return current.result
    if current.analysis is None:
        return VerificationResult(
            session_id=session_id,
            overall_status=OverallStatus.PENDING,
            summary="No verification has been performed yet.",
            checklist=[],
            disclosures=verification_service.DISCLOSURES,
        )
    return decide(session_id, current.analysis, None, None, liveness_result())


@router.post("/verification/{session_id}/retry", response_model=RetryResponse)
def retry(session_id: str, x_session_token: str | None = Header(default=None)):
    current = resolve_session(session_id, x_session_token)
    if current.stage == "camera":
        current.face_capture = None
        current.face_match = None
        current.result = None
        return RetryResponse(
            session_id=session_id, retriable_stage="face", ok=True, reason="ready to retry face capture"
        )
    if current.stage == "result" and current.analysis is not None and not current.analysis.preliminary_pass:
        return RetryResponse(
            session_id=session_id,
            retriable_stage="document",
            ok=True,
            reason="re-upload a clearer document image",
        )
    return RetryResponse(session_id=session_id, retriable_stage=None, ok=False, reason="no retriable stage")


@router.delete("/verification/{session_id}")
def delete_session(session_id: str, x_session_token: str | None = Header(default=None)):
    resolve_session(session_id, x_session_token)
    get_session_manager().delete(session_id)
    return {"status": "deleted", "session_id": session_id}
