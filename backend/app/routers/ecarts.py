"""
Analyse des écarts de conformité APDP + plan d'action — Bloc 2.

- Un référentiel d'exigences APDP prédéfini (commun) + des exigences
  personnalisées par organisation.
- Une évaluation par exigence, au niveau de l'organisation (traitement_id
  NULL) ou d'un traitement précis.
- Un plan d'action : des actions correctives rattachées à chaque écart.

Ce module ne mélange jamais le « taux de complétude » du registre
(scoring.py) avec la « conformité évaluée » calculée ici (exigences +
preuves + validation humaine).
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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

router = APIRouter(prefix="/analyse-ecarts", tags=["analyse des écarts"])

REFERENTIEL_PATH = Path(__file__).resolve().parent.parent / "referentiel_exigences_apdp_v1.json"


# ------------------------------------------------------------
# Référentiel
# ------------------------------------------------------------

def _ensure_referentiel(db: Session) -> None:
    """Charge le référentiel prédéfini (exigences globales) s'il est absent."""
    existe = (
        db.query(models.ExigenceReferentiel)
        .filter(models.ExigenceReferentiel.organisation_id.is_(None))
        .first()
    )
    if existe:
        return

    with open(REFERENTIEL_PATH, encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", "v1")
    for ordre, ex in enumerate(data.get("exigences", [])):
        db.add(
            models.ExigenceReferentiel(
                organisation_id=None,
                code=ex["code"],
                domaine=ex["domaine"],
                intitule=ex["intitule"],
                description=ex.get("description"),
                reference_reglementaire=ex.get("reference_reglementaire"),
                version_referentiel=version,
                personnalisee=False,
                ordre=ordre,
            )
        )
    db.commit()


def _exigences_applicables(db: Session, organisation_id: str):
    """Exigences actives applicables à une organisation : globales + propres."""
    _ensure_referentiel(db)
    return (
        db.query(models.ExigenceReferentiel)
        .filter(
            models.ExigenceReferentiel.active.is_(True),
            (models.ExigenceReferentiel.organisation_id.is_(None))
            | (models.ExigenceReferentiel.organisation_id == organisation_id),
        )
        .order_by(models.ExigenceReferentiel.ordre.asc().nullslast(),
                  models.ExigenceReferentiel.code.asc())
        .all()
    )


@router.get("/referentiel", response_model=list[schemas.ExigenceReferentielOut])
def lister_referentiel(
    organisation_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    _ensure_referentiel(db)
    org_filter = resolve_org_scope(utilisateur, organisation_id)
    q = db.query(models.ExigenceReferentiel).filter(
        models.ExigenceReferentiel.active.is_(True)
    )
    if org_filter:
        q = q.filter(
            (models.ExigenceReferentiel.organisation_id.is_(None))
            | (models.ExigenceReferentiel.organisation_id == org_filter)
        )
    else:
        # Admin sans filtre : exigences globales + toutes les exigences personnalisées.
        pass
    return q.order_by(
        models.ExigenceReferentiel.ordre.asc().nullslast(),
        models.ExigenceReferentiel.code.asc(),
    ).all()


@router.post("/referentiel", response_model=schemas.ExigenceReferentielOut, status_code=201)
def ajouter_exigence(
    data: schemas.ExigenceReferentielCreate,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    if not data.organisation_id:
        raise HTTPException(
            status_code=422,
            detail="Une exigence personnalisée doit être rattachée à une organisation.",
        )
    # L'exigence est forcément rattachée à l'organisation de l'utilisateur
    # (ou à celle demandée si admin).
    org_id = resolve_org_scope(utilisateur, data.organisation_id)
    exigence = models.ExigenceReferentiel(
        organisation_id=org_id,
        code=data.code,
        domaine=data.domaine,
        intitule=data.intitule,
        description=data.description,
        reference_reglementaire=data.reference_reglementaire,
        personnalisee=True,
    )
    db.add(exigence)
    db.commit()
    db.refresh(exigence)
    return exigence


# ------------------------------------------------------------
# Évaluations (grille d'écarts)
# ------------------------------------------------------------

def _get_org_ou_404(organisation_id: str, db: Session) -> models.Organisation:
    org = db.get(models.Organisation, organisation_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation introuvable")
    return org


def _materialiser_grille(db: Session, organisation_id: str, traitement_id: str | None):
    """Crée une évaluation « non évaluée » pour chaque exigence sans évaluation à cette portée."""
    exigences = _exigences_applicables(db, organisation_id)

    existantes = (
        db.query(models.EvaluationEcart.exigence_id)
        .filter(
            models.EvaluationEcart.organisation_id == organisation_id,
            (models.EvaluationEcart.traitement_id == traitement_id)
            if traitement_id
            else models.EvaluationEcart.traitement_id.is_(None),
        )
        .all()
    )
    deja = {e[0] for e in existantes}

    cree = False
    for ex in exigences:
        if ex.id not in deja:
            db.add(
                models.EvaluationEcart(
                    organisation_id=organisation_id,
                    traitement_id=traitement_id,
                    exigence_id=ex.id,
                    statut=models.StatutConformite.non_evalue,
                )
            )
            cree = True
    if cree:
        db.commit()


@router.get("", response_model=list[schemas.EvaluationEcartOut])
def lister_ecarts(
    organisation_id: str = Query(...),
    traitement_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    resolve_org_scope(utilisateur, organisation_id)  # 403 si l'org n'est pas la sienne
    _get_org_ou_404(organisation_id, db)
    if traitement_id and not db.get(models.Traitement, traitement_id):
        raise HTTPException(status_code=404, detail="Traitement introuvable")

    _materialiser_grille(db, organisation_id, traitement_id)

    q = db.query(models.EvaluationEcart).filter(
        models.EvaluationEcart.organisation_id == organisation_id,
        (models.EvaluationEcart.traitement_id == traitement_id)
        if traitement_id
        else models.EvaluationEcart.traitement_id.is_(None),
    )
    evaluations = q.all()
    # tri par code d'exigence
    evaluations.sort(key=lambda e: (e.exigence.ordre if e.exigence.ordre is not None else 999, e.exigence.code))
    return evaluations


@router.patch("/evaluations/{evaluation_id}", response_model=schemas.EvaluationEcartOut)
def modifier_evaluation(
    evaluation_id: str,
    data: schemas.EvaluationEcartUpdate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    ev = db.get(models.EvaluationEcart, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Évaluation introuvable")
    assert_org_access(utilisateur, ev.organisation_id)

    modifs = data.model_dump(exclude_unset=True)
    for champ, valeur in modifs.items():
        setattr(ev, champ, valeur)
    ev.date_evaluation = datetime.utcnow()

    code = ev.exigence.code if ev.exigence else evaluation_id
    descr = f"Écart {code}"
    if "statut" in modifs:
        st = getattr(modifs["statut"], "value", modifs["statut"])
        descr += f" — statut : {str(st).replace('_', ' ')}"
    journaliser_audit(
        db, "modification", "ecart", evaluation_id, descr,
        utilisateur=utilisateur, request=request, details=modifs,
    )
    db.commit()
    db.refresh(ev)
    return ev


# ------------------------------------------------------------
# Plan d'action
# ------------------------------------------------------------

@router.post(
    "/evaluations/{evaluation_id}/actions",
    response_model=schemas.ActionCorrectiveOut,
    status_code=201,
)
def ajouter_action(
    evaluation_id: str,
    data: schemas.ActionCorrectiveCreate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    ev = db.get(models.EvaluationEcart, evaluation_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Évaluation introuvable")
    assert_org_access(utilisateur, ev.organisation_id)
    action = models.ActionCorrective(
        evaluation_ecart_id=evaluation_id,
        **data.model_dump(),
    )
    db.add(action)
    journaliser_audit(
        db, "creation", "action", evaluation_id,
        f"Action corrective : {data.action[:80]}",
        utilisateur=utilisateur, request=request,
    )
    db.commit()
    db.refresh(action)
    return action


@router.patch("/actions/{action_id}", response_model=schemas.ActionCorrectiveOut)
def modifier_action(
    action_id: str,
    data: schemas.ActionCorrectiveUpdate,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    action = db.get(models.ActionCorrective, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action introuvable")
    if action.evaluation:
        assert_org_access(utilisateur, action.evaluation.organisation_id)
    modifs = data.model_dump(exclude_unset=True)
    for champ, valeur in modifs.items():
        setattr(action, champ, valeur)
    journaliser_audit(
        db, "modification", "action", action_id,
        "Action corrective mise à jour",
        utilisateur=utilisateur, request=request, details=modifs,
    )
    db.commit()
    db.refresh(action)
    return action


@router.delete("/actions/{action_id}", status_code=204)
def supprimer_action(
    action_id: str,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    assert_can_write(utilisateur)
    action = db.get(models.ActionCorrective, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action introuvable")
    if action.evaluation:
        assert_org_access(utilisateur, action.evaluation.organisation_id)
    journaliser_audit(
        db, "suppression", "action", action_id,
        "Action corrective supprimée",
        utilisateur=utilisateur, request=request,
    )
    db.delete(action)
    db.commit()


# ------------------------------------------------------------
# Synthèse
# ------------------------------------------------------------

@router.get("/synthese", response_model=schemas.SyntheseEcarts)
def synthese(
    organisation_id: str = Query(...),
    traitement_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(get_current_user),
):
    resolve_org_scope(utilisateur, organisation_id)  # 403 si l'org n'est pas la sienne
    _get_org_ou_404(organisation_id, db)
    _materialiser_grille(db, organisation_id, traitement_id)

    evaluations = (
        db.query(models.EvaluationEcart)
        .filter(
            models.EvaluationEcart.organisation_id == organisation_id,
            (models.EvaluationEcart.traitement_id == traitement_id)
            if traitement_id
            else models.EvaluationEcart.traitement_id.is_(None),
        )
        .all()
    )

    par_statut = {s.value: 0 for s in models.StatutConformite}
    for ev in evaluations:
        par_statut[ev.statut.value] += 1

    conforme = par_statut["conforme"]
    partiel = par_statut["partiellement_conforme"]
    non_conforme = par_statut["non_conforme"]
    base = conforme + partiel + non_conforme
    taux = round((conforme + 0.5 * partiel) / base * 100, 1) if base else 0.0
    evaluees = sum(1 for ev in evaluations if ev.statut != models.StatutConformite.non_evalue)

    ids = [ev.id for ev in evaluations]
    actions = (
        db.query(models.ActionCorrective)
        .filter(models.ActionCorrective.evaluation_ecart_id.in_(ids))
        .all()
        if ids
        else []
    )
    now = datetime.utcnow()
    en_retard = sum(
        1
        for a in actions
        if a.echeance
        and a.echeance < now
        and a.statut not in (models.StatutAction.realisee, models.StatutAction.validee)
    )

    return schemas.SyntheseEcarts(
        total=len(evaluations),
        par_statut=par_statut,
        taux_conformite=taux,
        exigences_evaluees=evaluees,
        actions_total=len(actions),
        actions_en_retard=en_retard,
    )
