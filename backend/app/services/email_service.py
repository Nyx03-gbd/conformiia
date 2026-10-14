"""
Envoi d'e-mails — vérification de compte et réinitialisation de mot de passe.

Si SMTP n'est pas configuré (voir app/config.py), aucun e-mail n'est envoyé :
le lien est simplement journalisé (mode développement). Dès que les variables
SMTP_* sont renseignées dans .env, l'envoi réel est automatique.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings, smtp_configured

logger = logging.getLogger("conformiia.email")


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Envoie un e-mail. Retourne True si réellement envoyé, False sinon."""
    if not smtp_configured():
        logger.warning(
            "E-MAIL NON ENVOYÉ (SMTP non configuré) — destinataire=%s sujet=%r",
            to,
            subject,
        )
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        if settings.smtp_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.starttls(context=context)
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=20, context=context
            ) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
        logger.info("E-mail envoyé à %s (%s).", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Échec de l'envoi de l'e-mail à %s : %s", to, exc)
        return False


def _page(titre: str, intro: str, bouton: str, lien: str, pied: str) -> str:
    return (
        f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;'>"
        f"<h2 style='color:#101828;'>ConformiIA</h2>"
        f"<p style='color:#344054;font-size:15px;'>{titre}</p>"
        f"<p style='color:#344054;font-size:14px;'>{intro}</p>"
        f"<p style='margin:22px 0;'><a href='{lien}' "
        f"style='background:#2563eb;color:#fff;text-decoration:none;padding:11px 20px;"
        f"border-radius:8px;font-size:14px;'>{bouton}</a></p>"
        f"<p style='color:#667085;font-size:12px;'>Ou copiez ce lien dans votre navigateur :<br>"
        f"<a href='{lien}'>{lien}</a></p>"
        f"<p style='color:#98a2b3;font-size:12px;'>{pied}</p></div>"
    )


def send_verification_email(to: str, lien: str) -> bool:
    return send_email(
        to,
        "ConformiIA — Vérifiez votre adresse e-mail",
        f"Bienvenue sur ConformiIA.\n\nActivez votre compte : {lien}\n\n"
        "Ce lien expire dans 24 heures.",
        _page(
            "Bienvenue sur ConformiIA.",
            "Pour activer votre compte, confirmez votre adresse e-mail.",
            "Activer mon compte",
            lien,
            "Ce lien expire dans 24 heures. Si vous n'êtes pas à l'origine de cette inscription, ignorez cet e-mail.",
        ),
    )


def send_reset_email(to: str, lien: str) -> bool:
    return send_email(
        to,
        "ConformiIA — Réinitialisation du mot de passe",
        f"Vous avez demandé la réinitialisation de votre mot de passe.\n\n{lien}\n\n"
        "Ce lien expire dans 30 minutes.",
        _page(
            "Réinitialisation du mot de passe",
            "Vous avez demandé à réinitialiser votre mot de passe.",
            "Choisir un nouveau mot de passe",
            lien,
            "Ce lien expire dans 30 minutes. Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.",
        ),
    )
