from fastapi import APIRouter, Depends, HTTPException

from app import models
from app.apdp_documents import get_document, list_documents
from app.services.security import get_current_user

router = APIRouter(
    prefix="/documents-apdp",
    tags=["documents APDP"],
)


@router.get("")
def get_documents(
    category: str | None = None,
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    return {
        "documents": list_documents(category)
    }


@router.get("/{document_id}")
def get_document_by_id(
    document_id: str,
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    try:
        return get_document(document_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Document APDP inconnu : {document_id}",
        )
