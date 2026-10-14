from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.audit_service import journaliser_audit
from app.services.security import (
    get_current_user,
    assert_can_write,
    assert_org_access,
    resolve_org_scope,
)

router = APIRouter(prefix="/traitements", tags=["traitements"])


@router.post("", response_model=schemas.TraitementOut, status_code=201)
def creer_traitement(
    payload: schemas.TraitementCreate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    org_id = resolve_org_scope(utilisateur, payload.organisation_id)
    if not org_id:
        raise HTTPException(status_code=422, detail="organisation_id requis.")

    traitement = models.Traitement(
        nom=payload.nom,
        organisation_id=org_id,
        service_responsable=payload.service_responsable,
        finalite=payload.finalite,
        base_legale=payload.base_legale,
        justification_base_legale=payload.justification_base_legale,
        sensibilite_donnees=payload.sensibilite_donnees,
        niveau_mesures_securite=payload.niveau_mesures_securite,
        sous_traitance_transferts=payload.sous_traitance_transferts,
        exposition=payload.exposition,
        volume=payload.volume,
    )
    traitement.categories_donnees = [
        models.CategorieDonnee(categorie=c.categorie, sensible=c.sensible)
        for c in payload.categories_donnees
    ]
    db.add(traitement)
    db.flush()
    journaliser_audit(
        db, "creation", "traitement", traitement.id,
        f"Traitement créé : {payload.nom}",
        utilisateur=utilisateur, request=request,
    )
    db.commit()
    db.refresh(traitement)
    return traitement


@router.get("", response_model=list[schemas.TraitementOut])
def lister_traitements(
    organisation_id: str | None = None,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    org_filter = resolve_org_scope(utilisateur, organisation_id)
    query = db.query(models.Traitement)
    if org_filter:
        query = query.filter(models.Traitement.organisation_id == org_filter)
    return query.order_by(models.Traitement.derniere_revision.desc()).all()


@router.get("/{traitement_id}", response_model=schemas.TraitementOut)
def lire_traitement(
    traitement_id: str,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    traitement = db.get(models.Traitement, traitement_id)
    if not traitement:
        raise HTTPException(status_code=404, detail="Traitement introuvable")
    assert_org_access(utilisateur, traitement.organisation_id)
    return traitement


@router.patch("/{traitement_id}", response_model=schemas.TraitementOut)
def modifier_traitement(
    traitement_id: str,
    payload: schemas.TraitementUpdate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    traitement = db.get(models.Traitement, traitement_id)
    if not traitement:
        raise HTTPException(status_code=404, detail="Traitement introuvable")
    assert_org_access(utilisateur, traitement.organisation_id)

    modifs = payload.model_dump(exclude_unset=True)
    for champ, valeur in modifs.items():
        setattr(traitement, champ, valeur)

    journaliser_audit(
        db, "modification", "traitement", traitement_id,
        f"Traitement modifié : {traitement.nom}",
        utilisateur=utilisateur, request=request,
        details={k: str(v) for k, v in modifs.items()},
    )
    db.commit()
    db.refresh(traitement)
    return traitement


@router.delete("/{traitement_id}", status_code=204)
def supprimer_traitement(
    traitement_id: str,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    traitement = db.get(models.Traitement, traitement_id)
    if not traitement:
        raise HTTPException(status_code=404, detail="Traitement introuvable")
    assert_org_access(utilisateur, traitement.organisation_id)
    journaliser_audit(
        db, "suppression", "traitement", traitement_id,
        f"Traitement supprimé : {traitement.nom}",
        utilisateur=utilisateur, request=request,
    )
    db.delete(traitement)
    db.commit()
