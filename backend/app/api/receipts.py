from uuid import UUID

from fastapi import APIRouter, Request, UploadFile

from app.schemas import ReceiptDraft, ReceiptOutput, UploadOutput
from app.security.session import Database, User
from app.services.receipts import MAX_BYTES, Receipts

router = APIRouter(prefix="/receipts", tags=["Receipt drafts and confirmation"])


def service(request: Request, db: Database):
    return Receipts(db, request.app.state.receipts)


@router.get("/capabilities")
def capabilities(request: Request):
    return {"automatedExtraction": request.app.state.receipts.available(), "maxBytes": MAX_BYTES}


@router.get("")
def receipts(request: Request, db: Database, user: User):
    return service(request, db).list(user)


@router.post("")
def manual(request: Request, db: Database, user: User):
    return {"id": service(request, db).manual(user)}


@router.post("/extract", response_model=UploadOutput)
def extract(file: UploadFile, request: Request, db: Database, user: User):
    try:
        return service(request, db).upload(user, file.file.read(MAX_BYTES + 1), file.content_type)
    finally:
        file.file.close()


@router.get("/{id}", response_model=ReceiptOutput)
def receipt(id: UUID, request: Request, db: Database, user: User):
    return service(request, db).get(user, id)


@router.put("/{id}", response_model=ReceiptOutput)
def save(id: UUID, data: ReceiptDraft, request: Request, db: Database, user: User):
    return service(request, db).save(user, id, data)


@router.post("/{id}/confirm", response_model=ReceiptOutput)
def confirm(id: UUID, request: Request, db: Database, user: User):
    return service(request, db).confirm(user, id)
