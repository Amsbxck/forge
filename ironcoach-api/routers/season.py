import os
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import SeasonContext
from services.pdf_extractor import extract_text_from_pdf
from core.config import settings

router = APIRouter()


class SeasonContextOut(BaseModel):
    id: int
    label: str
    content_type: str
    filename: str | None
    text_preview: str

    class Config:
        from_attributes = True


class SeasonTextIn(BaseModel):
    label: str
    text: str


@router.get("/season", response_model=list[SeasonContextOut])
def list_season_contexts(db: Session = Depends(get_db)):
    items = db.query(SeasonContext).order_by(SeasonContext.created_at.desc()).all()
    return [
        SeasonContextOut(
            id=i.id,
            label=i.label,
            content_type=i.content_type,
            filename=i.filename,
            text_preview=i.text[:200] + "..." if len(i.text) > 200 else i.text,
        )
        for i in items
    ]


@router.get("/season/{item_id}/text")
def get_season_text(item_id: int, db: Session = Depends(get_db)):
    item = db.query(SeasonContext).filter(SeasonContext.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return {"id": item.id, "label": item.label, "text": item.text}


@router.post("/season/text", response_model=SeasonContextOut)
def add_season_text(body: SeasonTextIn, db: Session = Depends(get_db)):
    item = SeasonContext(label=body.label, content_type="text", text=body.text)
    db.add(item)
    db.commit()
    db.refresh(item)
    return SeasonContextOut(
        id=item.id,
        label=item.label,
        content_type=item.content_type,
        filename=item.filename,
        text_preview=item.text[:200] + "..." if len(item.text) > 200 else item.text,
    )


@router.post("/season/pdf", response_model=SeasonContextOut)
async def upload_season_pdf(
    label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF zu groß (max 20MB)")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_name = (file.filename or "plan.pdf").replace(" ", "_")
    file_path = os.path.join(settings.UPLOAD_DIR, f"season_{safe_name}")
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        text = extract_text_from_pdf(file_path)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"PDF konnte nicht gelesen werden: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="PDF enthält keinen lesbaren Text (möglicherweise gescannt)")

    item = SeasonContext(
        label=label,
        content_type="pdf",
        text=text,
        filename=safe_name,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return SeasonContextOut(
        id=item.id,
        label=item.label,
        content_type=item.content_type,
        filename=item.filename,
        text_preview=text[:200] + "..." if len(text) > 200 else text,
    )


@router.delete("/season/{item_id}")
def delete_season_context(item_id: int, db: Session = Depends(get_db)):
    item = db.query(SeasonContext).filter(SeasonContext.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    db.delete(item)
    db.commit()
    return {"message": "Gelöscht"}
