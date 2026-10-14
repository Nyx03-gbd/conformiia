"""
Authentification et cloisonnement par organisation — priorité 5 (RBAC côté API).

- `get_current_user` : dépendance stricte (401 sans jeton valide).
- `get_current_user_optional` : utilisateur si jeton valide, sinon None.
- `require_admin` : réserve l'accès aux administrateurs (403 sinon).
- `resolve_org_scope(user, requested)` : organisation effective à filtrer —
  l'admin voit tout (ou l'org demandée), les autres sont restreints à la leur.
- `assert_org_access(user, org_id)` : 403 si l'utilisateur n'a pas accès à une
  ressource appartenant à `org_id`.
- `assert_can_write(user)` : 403 si le rôle est en lecture seule (auditeur).
"""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.auth_service import decode_access_token

_bearer = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)


def _user_from_token(token: str, db: Session) -> models.Utilisateur:
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("sub absent")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré.")

    user = db.query(models.Utilisateur).filter(models.Utilisateur.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Utilisateur:
    return _user_from_token(credentials.credentials, db)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
    db: Session = Depends(get_db),
) -> Optional[models.Utilisateur]:
    if not credentials:
        return None
    try:
        return _user_from_token(credentials.credentials, db)
    except HTTPException:
        return None


def require_admin(
    user: models.Utilisateur = Depends(get_current_user),
) -> models.Utilisateur:
    if user.role != models.RoleUtilisateur.admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    return user


def is_admin(user: models.Utilisateur) -> bool:
    return user.role == models.RoleUtilisateur.admin


def resolve_org_scope(
    user: models.Utilisateur, requested_org_id: Optional[str] = None
) -> Optional[str]:
    """
    Organisation à utiliser pour filtrer une liste :
    - admin : l'org demandée, ou None (toutes) ;
    - autre : sa propre organisation (403 si une autre est demandée, ou s'il
      n'est rattaché à aucune organisation).
    """
    if is_admin(user):
        return requested_org_id
    if not user.organisation_id:
        raise HTTPException(
            status_code=403,
            detail="Votre compte n'est rattaché à aucune organisation. Contactez un administrateur.",
        )
    own = str(user.organisation_id)
    if requested_org_id and str(requested_org_id) != own:
        raise HTTPException(status_code=403, detail="Accès refusé à cette organisation.")
    return own


def assert_org_access(user: models.Utilisateur, org_id) -> None:
    """403 si l'utilisateur ne peut pas accéder à une ressource de `org_id`."""
    if is_admin(user):
        return
    if not user.organisation_id or str(org_id) != str(user.organisation_id):
        raise HTTPException(status_code=403, detail="Accès refusé à cette ressource.")


def assert_can_write(user: models.Utilisateur) -> None:
    """Le rôle auditeur est en lecture seule."""
    if user.role == models.RoleUtilisateur.auditeur:
        raise HTTPException(
            status_code=403,
            detail="Votre rôle (auditeur) ne permet pas de modifier les données.",
        )
