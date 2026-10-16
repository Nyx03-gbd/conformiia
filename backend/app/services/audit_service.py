"""
Journal d'audit métier - trace « qui a fait quoi, quand ».

`journaliser_audit(...)` ajoute une entrée (le commit reste à l'appelant).
`get_current_user_optional` est une dépendance qui renvoie l'utilisateur
connecté si un jeton valide est présent, sinon None - pour pouvoir attribuer
l'action à son auteur sans rendre l'authentification obligatoire.
"""

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app import models
# Dépendance d'authentification facultative : implémentation unique dans security.
# Ré-exportée ici pour les imports existants (ecarts/incidents/traitements).
from app.services.security import get_current_user_optional  # noqa: F401


def journaliser_audit(
    db: Session,
    action: str,
    entite: str,
    entite_id=None,
    description: Optional[str] = None,
    utilisateur: Optional[models.Utilisateur] = None,
    request: Optional[Request] = None,
    details: Optional[dict] = None,
) -> None:
    adresse_ip = None
    if request is not None and request.client:
        adresse_ip = request.client.host

    db.add(
        models.JournalAudit(
            utilisateur_id=(utilisateur.id if utilisateur else None),
            utilisateur_email=(utilisateur.email if utilisateur else None),
            action=action,
            entite=entite,
            entite_id=(str(entite_id) if entite_id is not None else None),
            description=description,
            details=details,
            adresse_ip=adresse_ip,
        )
    )
