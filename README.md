# ConformiIA

Plateforme GRC-as-Code : registre des traitements APDP, génération des formulaires APDP (PDF), scoring de conformité et de risque, analyse des écarts, suivi des incidents (notification de violation sous 72 h).

Auteur : Nyx

## Fonctionnalités

- Registre des traitements + organisations multi-tenant (rôles : admin, métier, auditeur).
- 14 formulaires APDP générés par superposition sur les PDF officiels (jamais modifiés) : formulaire unique (10 pages), annexes 1 à 4, capteurs, site web, engagement de conformité, engagement DPO, signalement, consentement électronique, registres, outil de vérification.
- Scoring de conformité / risque, analyse des écarts + plan d'action, journal d'audit et de sécurité.
- Vérification e-mail + SMTP réel (STARTTLS 587 ou SMTPS 465).

## Architecture

Interface web (HTML/CSS/JS) -> proxy HTTPS (Caddy) -> API FastAPI (`127.0.0.1:8001`) -> base PostgreSQL (`127.0.0.1:5433`). API et base tournent dans des conteneurs Docker.

## Prérequis

Linux, Docker et Docker Compose, Caddy, Git.

## Installation

1. Cloner le dépôt : `git clone https://github.com/Nyx03-gbd/conformiia.git && cd conformiia-repo`
2. Créer la configuration : `cp .env.example .env`, puis remplacer les valeurs `CHANGE_ME` (même mot de passe dans `POSTGRES_PASSWORD` et dans `DATABASE_URL` ; générer `SECRET_KEY` avec `openssl rand -hex 32`).
3. Lancer l'API et la base : `docker compose up -d --build`
4. Créer les tables : `docker compose exec api alembic upgrade head`
   (alternative : `docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/schema.sql`)
5. Déclarer les noms locaux : `echo "127.0.0.1 conformiia api.conformiia conformiia.test api.conformiia.test" | sudo tee -a /etc/hosts`
6. Lancer le serveur HTTPS depuis la racine du dépôt : `caddy run --config Caddyfile` (ou `caddy reload --config Caddyfile` si Caddy tourne déjà), puis accepter le certificat : `sudo /usr/local/bin/caddy trust` (ou accepter l'avertissement dans le navigateur pour `conformiia` **et** `api.conformiia`).
7. Ouvrir https://conformiia et créer un compte depuis l'écran de connexion.

La documentation de l'API est disponible sur https://api.conformiia/docs (santé : https://api.conformiia/health).

## Premier administrateur et organisation

1. Renseigner `ADMIN_EMAILS` dans `.env` avec l'e-mail du compte admin avant son inscription (le rôle est octroyé à la vérification de l'adresse).
2. Sans SMTP configuré, le lien de vérification s'affiche dans les logs : `docker compose logs api | grep "LIEN DE VERIFICATION"`.
3. Créer l'organisation (page Organisation, rôle admin requis), puis y rattacher les comptes.

## Variables `.env`

| Variable | Exemple | Rôle |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `conformiia` / `CHANGE_ME` / `conformiia` | Base PostgreSQL |
| `DATABASE_URL` | `postgresql+psycopg2://conformiia:CHANGE_ME@db:5432/conformiia` | Accès API à la base |
| `SECRET_KEY` | sortie de `openssl rand -hex 32` | Jetons d'authentification |
| `APP_BASE_URL` / `API_BASE_URL` | `https://conformiia` / `https://api.conformiia` | Liens dans les pages et e-mails |
| `ADMIN_EMAILS` | `admin@example.com` | Adresses promues admin |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_TLS` | `smtp.gmail.com` / `465` / `false` (SMTPS) ou `587` / `true` (STARTTLS) | Envoi réel des e-mails |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | adresse + mot de passe d'application | Compte d'envoi |

## Structure

- `backend/` : API FastAPI, moteur de génération PDF (`services/apdp_*`), modèles, migrations (`alembic/`), formulaires APDP (`templates/`)
- `frontend/` : interface web
- `database/schema.sql` : schéma de la base
- `docker-compose.yml`, `Caddyfile`, `.env.example` : configuration

Notes : `.env` n'est jamais commité ; les PDF générés (`backend/generated/`) sont exclus du dépôt ; les PDF sources APDP sont les documents officiels et ne sont jamais modifiés (génération par superposition uniquement).

## Sources et licences

Les formulaires APDP sont les documents officiels de l'APDP du Bénin. Les dépendances open source sont listées dans `backend/requirements.txt`. Code applicatif : équipe Nyx.
