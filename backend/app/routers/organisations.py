from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.security import (
    get_current_user,
    require_admin,
    is_admin,
    assert_org_access,
)

router = APIRouter(prefix="/organisations", tags=["organisations"])


@router.post("", response_model=schemas.OrganisationOut, status_code=201)
def creer_organisation(
    payload: schemas.OrganisationCreate,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(require_admin),
):
    organisation = models.Organisation(**payload.model_dump())
    db.add(organisation)
    db.commit()
    db.refresh(organisation)
    return organisation


@router.get("", response_model=list[schemas.OrganisationOut])
def lister_organisations(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    query = db.query(models.Organisation)
    if not is_admin(utilisateur):
        # Un non-admin ne voit que sa propre organisation.
        if not utilisateur.organisation_id:
            return []
        query = query.filter(models.Organisation.id == utilisateur.organisation_id)
    return query.order_by(models.Organisation.nom).all()


@router.get("/{organisation_id}", response_model=schemas.OrganisationOut)
def lire_organisation(
    organisation_id: str,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    organisation = db.get(models.Organisation, organisation_id)
    if not organisation:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    assert_org_access(utilisateur, organisation.id)
    return organisation
