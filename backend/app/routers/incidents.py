from datetime import datetime, timedelta

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


router = APIRouter(prefix="/incidents", tags=["incidents"])

STATUTS_NOTIFIES = {models.StatutIncident.notifie, models.StatutIncident.cloture}


def _alerte_incident(incident: models.Incident) -> schemas.IncidentAlerte:
    now = datetime.utcnow()
    heures = (incident.echeance_notification - now).total_seconds() / 3600.0
    notifie = incident.statut in STATUTS_NOTIFIES
    en_retard = (not notifie) and heures < 0
    if notifie:
        niveau = "notifie"
    elif en_retard:
        niveau = "retard"
    elif heures < 24:
        niveau = "urgent"
    else:
        niveau = "a_suivre"
    return schemas.IncidentAlerte(
        id=str(incident.id),
        organisation_id=str(incident.organisation_id),
        statut=incident.statut.value,
        types_violation=incident.types_violation or [],
        resume_incident=incident.resume_incident,
        date_heure_constatation=incident.date_heure_constatation,
        echeance_notification=incident.echeance_notification,
        date_notification=incident.date_notification,
        heures_restantes=round(heures, 1),
        en_retard=en_retard,
        niveau=niveau,
    )


def _journaliser_etape(db, incident_id, etape, description):
    db.add(
        models.IncidentEtape(
            incident_id=incident_id,
            etape=etape,
            description=description,
        )
    )


@router.post("", response_model=schemas.IncidentOut, status_code=201)
def creer_incident(
    payload: schemas.IncidentCreate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    resolve_org_scope(utilisateur, payload.organisation_id)  # 403 si ce n'est pas son org
    organisation = db.get(models.Organisation, payload.organisation_id)
    if not organisation:
        raise HTTPException(
            status_code=404,
            detail="Organisation introuvable",
        )

    if payload.traitement_id:
        traitement = db.get(models.Traitement, payload.traitement_id)
        if not traitement:
            raise HTTPException(
                status_code=404,
                detail="Traitement introuvable",
            )

    echeance = payload.date_heure_constatation + timedelta(hours=72)

    incident = models.Incident(
        **payload.model_dump(),
        echeance_notification=echeance,
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)

    _journaliser_etape(
        db,
        incident.id,
        "creation",
        "Incident déclaré — début du délai de 72 h à la constatation.",
    )
    journaliser_audit(
        db, "creation", "incident", incident.id,
        "Déclaration d'un incident de sécurité",
        utilisateur=utilisateur, request=request,
    )
    db.commit()

    return incident


@router.get("", response_model=list[schemas.IncidentOut])
def lister_incidents(
    organisation_id: str | None = None,
    statut: models.StatutIncident | None = None,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    org_filter = resolve_org_scope(utilisateur, organisation_id)
    query = db.query(models.Incident)

    if org_filter:
        query = query.filter(
            models.Incident.organisation_id == org_filter
        )

    if statut:
        query = query.filter(
            models.Incident.statut == statut
        )

    return query.order_by(
        models.Incident.date_heure_constatation.desc()
    ).all()


@router.get("/alertes", response_model=schemas.AlertesSummary)
def alertes_incidents(
    organisation_id: str | None = None,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    """Synthèse des alertes du délai de 72 h (en retard, urgents, à suivre)."""
    org_filter = resolve_org_scope(utilisateur, organisation_id)
    query = db.query(models.Incident)
    if org_filter:
        query = query.filter(models.Incident.organisation_id == org_filter)
    incidents = query.order_by(models.Incident.echeance_notification.asc()).all()
    alertes = [_alerte_incident(i) for i in incidents]
    return schemas.AlertesSummary(
        total_ouverts=sum(1 for a in alertes if a.niveau != "notifie"),
        en_retard=sum(1 for a in alertes if a.niveau == "retard"),
        urgents=sum(1 for a in alertes if a.niveau == "urgent"),
        a_suivre=sum(1 for a in alertes if a.niveau == "a_suivre"),
        notifies=sum(1 for a in alertes if a.niveau == "notifie"),
        incidents=alertes,
    )


@router.get("/{incident_id}/etapes", response_model=list[schemas.IncidentEtapeOut])
def lister_etapes(
    incident_id: str,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    incident = db.get(models.Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    assert_org_access(utilisateur, incident.organisation_id)
    return (
        db.query(models.IncidentEtape)
        .filter(models.IncidentEtape.incident_id == incident_id)
        .order_by(models.IncidentEtape.date_etape.asc())
        .all()
    )


@router.post(
    "/{incident_id}/etapes",
    response_model=schemas.IncidentEtapeOut,
    status_code=201,
)
def ajouter_etape(
    incident_id: str,
    payload: schemas.IncidentEtapeCreate,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    incident = db.get(models.Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    assert_org_access(utilisateur, incident.organisation_id)
    etape = models.IncidentEtape(
        incident_id=incident_id,
        etape=payload.etape or "note",
        description=payload.description,
    )
    db.add(etape)
    db.commit()
    db.refresh(etape)
    return etape


@router.get("/{incident_id}", response_model=schemas.IncidentOut)
def lire_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    incident = db.get(models.Incident, incident_id)

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident introuvable",
        )
    assert_org_access(utilisateur, incident.organisation_id)

    return incident


@router.patch("/{incident_id}", response_model=schemas.IncidentOut)
def modifier_incident(
    incident_id: str,
    payload: schemas.IncidentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    incident = db.get(models.Incident, incident_id)

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident introuvable",
        )
    assert_org_access(utilisateur, incident.organisation_id)

    modifications = payload.model_dump(exclude_unset=True)

    if "statut" in modifications:
        try:
            incident.statut = models.StatutIncident(modifications["statut"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Statut d'incident invalide",
            )
        _journaliser_etape(
            db,
            incident.id,
            "statut",
            f"Statut mis à jour : {incident.statut.value.replace('_', ' ')}.",
        )

    if "date_notification" in modifications:
        date_notification = modifications["date_notification"]
        incident.date_notification = date_notification

        incident.notification_dans_les_delais = (
            date_notification <= incident.echeance_notification
        )
        if date_notification is not None:
            dans_delai = incident.notification_dans_les_delais
            _journaliser_etape(
                db,
                incident.id,
                "notification",
                "Notification à l'APDP enregistrée "
                + ("(dans les délais)." if dans_delai else "(hors délai)."),
            )

    journaliser_audit(
        db, "modification", "incident", incident_id,
        "Incident mis à jour",
        utilisateur=utilisateur, request=request, details=modifications,
    )
    db.commit()
    db.refresh(incident)

    return incident
