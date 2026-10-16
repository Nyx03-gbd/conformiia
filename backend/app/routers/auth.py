import logging
import re
from datetime import datetime

# Jetons émis par secrets.token_urlsafe : base64url strict.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,400}$")

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings, admin_email_set
from app.database import get_db
from app.models import Utilisateur, RoleUtilisateur, JournalSecurite, JournalAudit, Organisation
from app.schemas import JournalAuditItem
from app.services.email_service import send_verification_email, send_reset_email


def _lien_verification(token: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/auth/verify-email?token={token}"


def _lien_reset(token: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/auth/reset-password-page?token={token}"


def _page_html(titre: str, corps: str, succes: bool = True) -> str:
    couleur = "#067647" if succes else "#b42318"
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ConformiIA</title></head>"
        "<body style='margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f2f4f7;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;'>"
        "<div style='background:#fff;max-width:440px;width:92%;padding:32px 28px;border-radius:16px;"
        "box-shadow:0 10px 40px rgba(16,24,40,.08);text-align:center;'>"
        "<div style='font-weight:800;font-size:22px;letter-spacing:.04em;color:#101828;'>CONFORMIIA</div>"
        f"<h2 style='color:{couleur};font-size:19px;margin:18px 0 8px;'>{titre}</h2>"
        f"<div style='color:#475467;font-size:14px;line-height:1.5;'>{corps}</div>"
        f"<p style='margin-top:22px;'><a href='{settings.app_base_url}' "
        "style='background:#2563eb;color:#fff;text-decoration:none;padding:11px 22px;"
        "border-radius:8px;font-size:14px;display:inline-block;'>Aller à la connexion</a></p>"
        "</div></body></html>"
    )
from app.schemas_auth import (
    AdminUserItem,
    AdminUserUpdate,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SecurityLogItem,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    reset_expiration,
    verification_expiration,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["authentification"],
)

logger = logging.getLogger("conformiia.auth")

security = HTTPBearer()

# Implémentation unique des dépendances d'auth (security.py).
from app.services.security import (  # noqa: E402
    get_current_user,
    get_current_user_optional,
    require_admin,
)


def enregistrer_evenement_securite(
    db: Session,
    evenement: str,
    description: str,
    utilisateur_id=None,
    request=None,
):
    """
    Enregistre un événement de sécurité sans stocker
    de mot de passe, JWT ou token sensible.
    """

    adresse_ip = None
    user_agent = None

    if request is not None:
        adresse_ip = (
            request.client.host
            if request.client
            else None
        )

        user_agent = request.headers.get(
            "user-agent"
        )

    evenement_securite = JournalSecurite(
        utilisateur_id=utilisateur_id,
        evenement=evenement,
        description=description,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
    )

    db.add(evenement_securite)
    db.commit()


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    email = data.email.lower().strip()

    existing = (
        db.query(Utilisateur)
        .filter(Utilisateur.email == email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Cette adresse e-mail est déjà utilisée.",
        )

    verification_token = generate_token()

    try:
        password_hash = hash_password(
            data.mot_de_passe
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # Rattachement à une organisation : si l'inscription n'en fournit pas et
    # qu'une seule organisation existe (déploiement mono-organisation), on y
    # rattache l'utilisateur automatiquement. Un admin peut réaffecter ensuite.
    organisation_id = data.organisation_id
    if not organisation_id:
        orgs = db.query(Organisation).limit(2).all()
        if len(orgs) == 1:
            organisation_id = str(orgs[0].id)

    # Sécurité : on ne skippe JAMAIS la vérification pour une adresse admin.
    # Le compte est créé non vérifié, avec un jeton ; le rôle admin n'est
    # octroyé qu'APRÈS vérification de l'adresse (voir verify_email), ce qui
    # exige la preuve de possession de la boîte e-mail.
    user = Utilisateur(
        nom=data.nom.strip(),
        prenoms=(
            data.prenoms.strip()
            if data.prenoms
            else None
        ),
        email=email,
        fonction=(
            data.fonction.strip()
            if data.fonction
            else None
        ),
        organisation_id=organisation_id,
        role=RoleUtilisateur.metier,
        mot_de_passe_hash=password_hash,
        email_verifie=False,
        token_verification_hash=hash_token(verification_token),
        token_verification_expire_at=verification_expiration(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("Compte créé pour %s.", email)

    envoye = send_verification_email(email, _lien_verification(verification_token))
    if not envoye:
        # SMTP non configuré : on journalise le lien (mode développement).
        logger.warning(
            "LIEN DE VERIFICATION DEV - email=%s %s",
            email,
            _lien_verification(verification_token),
        )

    return MessageResponse(
        message=(
            "Compte créé. "
            "Vérifiez votre adresse e-mail "
            "pour activer votre compte."
        )
    )


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(
    token: str,
    db: Session = Depends(get_db),
):
    token_hash = hash_token(token)

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.token_verification_hash == token_hash)
        .first()
    )

    if not user:
        return HTMLResponse(
            _page_html(
                "Lien invalide",
                "Ce lien de vérification est invalide ou a déjà été utilisé.",
                succes=False,
            ),
            status_code=400,
        )

    if user.email_verifie:
        return HTMLResponse(
            _page_html(
                "Adresse déjà vérifiée",
                "Votre adresse e-mail est déjà vérifiée. Vous pouvez vous connecter.",
            )
        )

    if (
        not user.token_verification_expire_at
        or user.token_verification_expire_at < datetime.utcnow()
    ):
        return HTMLResponse(
            _page_html(
                "Lien expiré",
                "Ce lien de vérification a expiré. Connectez-vous pour en demander un nouveau.",
                succes=False,
            ),
            status_code=400,
        )

    user.email_verifie = True
    user.token_verification_hash = None
    user.token_verification_expire_at = None

    # Le rôle admin n'est octroyé qu'ici, une fois la possession de
    # l'adresse e-mail prouvée (et seulement si elle est déclarée dans
    # ADMIN_EMAILS côté serveur).
    promu_admin = user.email.lower() in admin_email_set()
    if promu_admin:
        user.role = RoleUtilisateur.admin

    enregistrer_evenement_securite(
        db=db,
        evenement="EMAIL_VERIFIE",
        description=(
            "Adresse e-mail vérifiée - rôle administrateur octroyé."
            if promu_admin
            else "Adresse e-mail vérifiée avec succès."
        ),
        utilisateur_id=user.id,
    )

    db.commit()

    return HTMLResponse(
        _page_html(
            "Adresse e-mail vérifiée",
            "Votre compte est activé. Vous pouvez maintenant vous connecter.",
        )
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
)
def resend_verification(
    email: str,
    db: Session = Depends(get_db),
):
    email = email.lower().strip()

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.email == email)
        .first()
    )

    # Ne pas révéler si l'adresse existe.
    if not user:
        return MessageResponse(
            message=(
                "Si ce compte existe, "
                "un nouveau lien de vérification "
                "sera généré."
            )
        )

    if user.email_verifie:
        return MessageResponse(
            message="Cette adresse e-mail est déjà vérifiée."
        )

    verification_token = generate_token()

    user.token_verification_hash = hash_token(
        verification_token
    )
    user.token_verification_expire_at = (
        verification_expiration()
    )

    db.commit()

    envoye = send_verification_email(email, _lien_verification(verification_token))
    if not envoye:
        logger.warning(
            "LIEN DE VERIFICATION DEV - email=%s %s",
            email,
            _lien_verification(verification_token),
        )

    return MessageResponse(
        message=(
            "Un nouveau lien de vérification "
            "a été généré."
        )
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = data.email.lower().strip()

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.email == email)
        .first()
    )

    if (
        not user
        or not verify_password(
            data.mot_de_passe,
            user.mot_de_passe_hash,
        )
    ):
        enregistrer_evenement_securite(
            db=db,
            evenement="ECHEC_CONNEXION",
            description="Tentative de connexion échouée.",
            utilisateur_id=(
                user.id
                if user
                else None
            ),
            request=request,
        )

        raise HTTPException(
            status_code=401,
            detail="Adresse e-mail ou mot de passe incorrect.",
        )

    if not user.email_verifie:
        raise HTTPException(
            status_code=403,
            detail=(
                "Votre adresse e-mail n'est pas encore "
                "vérifiée."
            ),
        )

    token = create_access_token(
        str(user.id)
    )

    enregistrer_evenement_securite(
        db=db,
        evenement="CONNEXION_REUSSIE",
        description="Connexion réussie au compte.",
        utilisateur_id=user.id,
        request=request,
    )

    return TokenResponse(
        access_token=token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def current_user(
    credentials: HTTPAuthorizationCredentials =
        Depends(security),
    db: Session = Depends(get_db),
):
    try:

        payload = decode_access_token(
            credentials.credentials
        )

        user_id = payload.get("sub")

        if not user_id:
            raise ValueError("sub absent")

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token invalide ou expiré.",
        )

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.id == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Utilisateur introuvable.",
        )

    return UserResponse(
        id=str(user.id),
        nom=user.nom,
        prenoms=user.prenoms,
        email=user.email,
        fonction=user.fonction,
        role=user.role.value,
        organisation_id=(
            str(user.organisation_id)
            if user.organisation_id
            else None
        ),
        email_verifie=user.email_verifie,
    )


@router.post(
    "/change-password",
    response_model=MessageResponse,
)
def change_password(
    data: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials =
        Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_access_token(
            credentials.credentials
        )
        user_id = payload.get("sub")

        if not user_id:
            raise ValueError("sub absent")

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token invalide ou expiré.",
        )

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.id == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Utilisateur introuvable.",
        )

    if not verify_password(
        data.ancien_mot_de_passe,
        user.mot_de_passe_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="L'ancien mot de passe est incorrect.",
        )

    if data.ancien_mot_de_passe == data.nouveau_mot_de_passe:
        raise HTTPException(
            status_code=400,
            detail=(
                "Le nouveau mot de passe doit être "
                "différent de l'ancien."
            ),
        )

    try:
        nouveau_hash = hash_password(
            data.nouveau_mot_de_passe
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    user.mot_de_passe_hash = nouveau_hash

    enregistrer_evenement_securite(
        db=db,
        evenement="CHANGEMENT_MOT_DE_PASSE",
        description="Mot de passe modifié avec succès.",
        utilisateur_id=user.id,
    )

    db.commit()

    return MessageResponse(
        message="Mot de passe modifié avec succès."
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
)
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    email = data.email.lower().strip()

    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.email == email)
        .first()
    )

    if not user:
        return MessageResponse(
            message=(
                "Si cette adresse existe, "
                "un lien de réinitialisation "
                "sera généré."
            )
        )

    reset_token = generate_token()

    user.token_reset_hash = hash_token(
        reset_token
    )
    user.token_reset_expire_at = (
        reset_expiration()
    )

    enregistrer_evenement_securite(
        db=db,
        evenement="DEMANDE_RESET_MOT_DE_PASSE",
        description="Demande de réinitialisation du mot de passe.",
        utilisateur_id=user.id,
    )

    db.commit()

    envoye = send_reset_email(email, _lien_reset(reset_token))
    if not envoye:
        logger.warning(
            "LIEN RESET DEV - email=%s %s",
            email,
            _lien_reset(reset_token),
        )

    return MessageResponse(
        message=(
            "Si cette adresse existe, "
            "un lien de réinitialisation "
            "a été généré."
        )
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
)
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    token_hash = hash_token(data.token)

    user = (
        db.query(Utilisateur)
        .filter(
            Utilisateur.token_reset_hash ==
            token_hash
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Token de réinitialisation invalide.",
        )

    if (
        not user.token_reset_expire_at
        or user.token_reset_expire_at
        < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Le token de réinitialisation "
                "a expiré."
            ),
        )

    try:
        nouveau_hash = hash_password(
            data.nouveau_mot_de_passe
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    user.mot_de_passe_hash = nouveau_hash

    user.token_reset_hash = None
    user.token_reset_expire_at = None

    enregistrer_evenement_securite(
        db=db,
        evenement="RESET_MOT_DE_PASSE",
        description="Mot de passe réinitialisé avec succès.",
        utilisateur_id=user.id,
    )

    db.commit()

    return MessageResponse(
        message="Mot de passe réinitialisé avec succès.",
    )


@router.get(
    "/security-log",
    response_model=list[SecurityLogItem],
)
def security_log(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    claims = decode_access_token(
        credentials.credentials
    )

    if not claims or not claims.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Session invalide ou expirée.",
        )

    user_id = claims["sub"]

    evenements = (
        db.query(JournalSecurite)
        .filter(
            JournalSecurite.utilisateur_id == user_id
        )
        .order_by(
            JournalSecurite.date_evenement.desc()
        )
        .limit(50)
        .all()
    )

    return [
        SecurityLogItem(
            id=str(event.id),
            evenement=event.evenement,
            description=event.description,
            adresse_ip=event.adresse_ip,
            user_agent=event.user_agent,
            date_evenement=event.date_evenement,
        )
        for event in evenements
    ]


@router.post(
    "/logout",
    response_model=MessageResponse,
)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None,
    db: Session = Depends(get_db),
):
    claims = decode_access_token(
        credentials.credentials
    )

    if not claims or not claims.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Session invalide ou expirée.",
        )

    user_id = claims["sub"]

    enregistrer_evenement_securite(
        db=db,
        evenement="DECONNEXION",
        description="Déconnexion du compte.",
        utilisateur_id=user_id,
        request=request,
    )

    return MessageResponse(
        message="Déconnexion enregistrée."
    )


@router.get(
    "/utilisateurs",
    response_model=list[AdminUserItem],
    tags=["administration"],
)
def lister_utilisateurs(
    admin: Utilisateur = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Liste de tous les comptes - réservée aux administrateurs (qui utilise la plateforme)."""
    utilisateurs = (
        db.query(Utilisateur)
        .order_by(Utilisateur.date_creation.desc())
        .all()
    )
    return [
        AdminUserItem(
            id=str(u.id),
            nom=u.nom,
            prenoms=u.prenoms,
            email=u.email,
            fonction=u.fonction,
            role=u.role.value,
            organisation_id=str(u.organisation_id) if u.organisation_id else None,
            email_verifie=u.email_verifie,
            date_creation=u.date_creation,
        )
        for u in utilisateurs
    ]


@router.get("/reset-password-page", response_class=HTMLResponse)
def reset_password_page(token: str):
    """Page (ouverte depuis le lien e-mail) pour choisir un nouveau mot de passe."""
    if not _TOKEN_RE.fullmatch(token or ""):
        return HTMLResponse(
            _page_html(
                "Lien invalide",
                "Ce lien de réinitialisation est invalide ou a expiré.",
                succes=False,
            ),
            status_code=400,
        )
    safe = token  # jeton validé : uniquement [A-Za-z0-9_-], aucune injection possible
    champ = (
        "width:100%;padding:11px 13px;border:1px solid #d0d5dd;border-radius:9px;"
        "box-sizing:border-box;font-size:14px;margin-top:6px;"
    )
    html = (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ConformiIA - Nouveau mot de passe</title></head>"
        "<body style='margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f2f4f7;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;'>"
        "<form id='f' style='background:#fff;max-width:420px;width:92%;padding:30px 26px;"
        "border-radius:16px;box-shadow:0 10px 40px rgba(16,24,40,.08);'>"
        "<div style='font-weight:800;font-size:20px;letter-spacing:.04em;color:#101828;text-align:center;'>CONFORMIIA</div>"
        "<h2 style='font-size:17px;color:#101828;margin:16px 0 4px;'>Nouveau mot de passe</h2>"
        "<p style='font-size:13px;color:#667085;margin:0 0 10px;'>Au moins 8 caractères, une lettre, un chiffre et un caractère spécial.</p>"
        f"<input id='p1' type='password' placeholder='Nouveau mot de passe' style='{champ}'>"
        f"<input id='p2' type='password' placeholder='Confirmez le mot de passe' style='{champ}'>"
        "<div id='msg' style='font-size:13px;margin-top:10px;color:#b42318;'></div>"
        "<button type='submit' style='width:100%;margin-top:14px;padding:11px;border:0;border-radius:9px;"
        "background:#2563eb;color:#fff;font-size:14px;cursor:pointer;'>Réinitialiser</button></form>"
        "<script>"
        f"var TOKEN='{safe}';"
        "var f=document.getElementById('f'),msg=document.getElementById('msg');"
        "f.addEventListener('submit',async function(e){e.preventDefault();"
        "var p1=document.getElementById('p1').value,p2=document.getElementById('p2').value;"
        "if(p1!==p2){msg.style.color='#b42318';msg.textContent='Les mots de passe ne correspondent pas.';return;}"
        "msg.style.color='#667085';msg.textContent='Enregistrement…';"
        "try{var r=await fetch('/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({token:TOKEN,nouveau_mot_de_passe:p1})});var j=await r.json();"
        "if(!r.ok){throw new Error(typeof j.detail==='string'?j.detail:'Erreur');}"
        "msg.style.color='#067647';msg.textContent='Mot de passe réinitialisé. Vous pouvez vous connecter.';"
        "f.querySelector('button').disabled=true;}"
        "catch(err){msg.style.color='#b42318';msg.textContent=err.message;}});"
        "</script></body></html>"
    )
    return HTMLResponse(html)


@router.get(
    "/audit",
    response_model=list[JournalAuditItem],
    tags=["administration"],
)
def journal_audit(
    entite: str | None = None,
    limite: int = 200,
    admin: Utilisateur = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Journal d'audit métier (qui a fait quoi, quand) - réservé aux administrateurs."""
    query = db.query(JournalAudit)
    if entite:
        query = query.filter(JournalAudit.entite == entite)
    return (
        query.order_by(JournalAudit.date_action.desc())
        .limit(max(1, min(limite, 1000)))
        .all()
    )


@router.patch(
    "/utilisateurs/{utilisateur_id}",
    response_model=AdminUserItem,
    tags=["administration"],
)
def modifier_utilisateur(
    utilisateur_id: str,
    data: AdminUserUpdate,
    admin: Utilisateur = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Réaffecte l'organisation et/ou le rôle d'un compte - réservé aux administrateurs."""
    cible = db.query(Utilisateur).filter(Utilisateur.id == utilisateur_id).first()
    if not cible:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    modifs = data.model_dump(exclude_unset=True)

    if "organisation_id" in modifs:
        org_id = modifs["organisation_id"]
        if org_id:
            if not db.get(Organisation, org_id):
                raise HTTPException(status_code=404, detail="Organisation introuvable.")
        cible.organisation_id = org_id or None

    if "role" in modifs and modifs["role"]:
        try:
            cible.role = RoleUtilisateur(modifs["role"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Rôle invalide.")

    enregistrer_evenement_securite(
        db=db,
        evenement="COMPTE_MODIFIE_ADMIN",
        description=f"Compte {cible.email} modifié par l'administrateur {admin.email}.",
        utilisateur_id=cible.id,
    )
    db.commit()
    db.refresh(cible)

    return AdminUserItem(
        id=str(cible.id),
        nom=cible.nom,
        prenoms=cible.prenoms,
        email=cible.email,
        fonction=cible.fonction,
        role=cible.role.value,
        organisation_id=str(cible.organisation_id) if cible.organisation_id else None,
        email_verifie=cible.email_verifie,
        date_creation=cible.date_creation,
    )
