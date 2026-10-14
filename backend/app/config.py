from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://conformiia:CHANGE_ME@db:5432/conformiia"
    secret_key: str
    environment: str = "development"

    # --- URLs publiques (pour les liens dans les e-mails) ---
    app_base_url: str = "https://conformiia.localhost"
    api_base_url: str = "https://api.conformiia.localhost"

    # --- Envoi d'e-mails (SMTP) — facultatif ---
    # Renseignez ces valeurs dans .env pour activer l'envoi réel des e-mails.
    # Exemple Gmail : SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_TLS=true,
    # SMTP_USER=<adresse>, SMTP_PASSWORD=<mot de passe d'application>.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True

    # --- Comptes administrateurs/dév (séparés par des virgules) ---
    # Ces adresses reçoivent le rôle « admin » et sont vérifiées
    # automatiquement à l'inscription.
    admin_emails: str = ""

    class Config:
        env_file = ".env"


settings = Settings()


def admin_email_set() -> set[str]:
    return {
        e.strip().lower()
        for e in (settings.admin_emails or "").split(",")
        if e.strip()
    }


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)
