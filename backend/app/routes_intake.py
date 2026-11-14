"""Upload a bill: POST /api/claims/upload (multipart, field "file"). Reads it, builds the check and queues the agent."""
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from .intake import MAX_BYTES, IntakeError, build_claim, load_kit_building, read_document

router = APIRouter(prefix="/api/claims")
ALLOWED = (".pdf", ".txt", ".eml", ".md")


@router.post("/upload")
async def upload(request: Request, file: UploadFile, building_id: str | None = Form(None)):
    """building_id: a CoStar kit property id, when the bill is uploaded from that building's page."""
    name = (file.filename or "bill").split("/")[-1].split("\\")[-1]
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(415, "Upload a PDF, a text file or a saved email (.eml).")
    data = await file.read(MAX_BYTES + 1)
    engine = request.app.state.engine
    try:
        extracted = read_document(data, name)
        key = load_kit_building(building_id) if building_id else None
        claim = build_claim(extracted, name, engine.next_upload_id(), building_key=key)
    except IntakeError as e:
        raise HTTPException(422, str(e))
    engine.add_claim(claim)
    return {"id": claim["id"], "reader": extracted.reader, "state": engine.snapshot()}
