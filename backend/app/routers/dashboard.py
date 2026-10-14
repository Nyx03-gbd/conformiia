from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.security import get_current_user, resolve_org_scope

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/incidents")
def dashboard_incidents(
    organisation_id: str | None = None,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    org_filter = resolve_org_scope(utilisateur, organisation_id)
    query = db.query(models.Incident)

    if org_filter:
        query = query.filter(
            models.Incident.organisation_id == org_filter
        )

    incidents = query.order_by(
        models.Incident.date_heure_constatation.desc()
    ).all()

    maintenant = datetime.utcnow()

    total = len(incidents)
    nouveaux = sum(
        1 for incident in incidents
        if incident.statut == models.StatutIncident.nouveau
    )
    en_analyse = sum(
        1 for incident in incidents
        if incident.statut == models.StatutIncident.analyse
    )
    notifies = sum(
        1 for incident in incidents
        if incident.statut == models.StatutIncident.notifie
    )
    hors_delai = sum(
        1 for incident in incidents
        if incident.notification_dans_les_delais is False
    )

    return {
        "total_incidents": total,
        "nouveaux": nouveaux,
        "en_analyse": en_analyse,
        "notifies": notifies,
        "hors_delai": hors_delai,
        "incidents": [
            {
                "id": str(incident.id),
                "statut": incident.statut.value,
                "date_constatation": incident.date_heure_constatation,
                "echeance_notification": incident.echeance_notification,
                "date_notification": incident.date_notification,
                "notification_dans_les_delais": incident.notification_dans_les_delais,
                "delai_depasse": (
                    incident.date_notification is None
                    and maintenant > incident.echeance_notification
                ),
                "etat_delai": (
                    "dans_les_delais"
                    if incident.notification_dans_les_delais is True
                    else "hors_delai"
                    if incident.notification_dans_les_delais is False
                    else "delai_depasse"
                    if maintenant > incident.echeance_notification
                    else "en_attente"
                ),
            }
            for incident in incidents
        ],
    }
