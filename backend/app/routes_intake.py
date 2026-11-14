"""Upload a bill: POST /api/claims/upload (multipart, field "file"). Reads it, builds the check and queues the agent."""
from fastapi import APIRouter, HTTPException, Request, UploadFile

from .intake import MAX_BYTES, IntakeError, build_claim, read_document

router = APIRouter(prefix="/api/claims")
ALLOWED = (".pdf", ".txt", ".eml", ".md")


@router.post("/upload")
async def upload(request: Request, file: UploadFile):
    name = (file.filename or "bill").split("/")[-1].split("\\")[-1]
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(415, "Upload a PDF, a text file or a saved email (.eml).")
    data = await file.read(MAX_BYTES + 1)
    engine = request.app.state.engine
    try:
        extracted = read_document(data, name)
        claim = build_claim(extracted, name, engine.next_upload_id())
    except IntakeError as e:
        raise HTTPException(422, str(e))
    engine.add_claim(claim)
    return {"id": claim["id"], "reader": extracted.reader, "state": engine.snapshot()}
