"""
Proposte di campagna dal lato dell'amministratore: leggerle, rifiutarle con un
motivo, o trasformarle in campagne.

**L'approvazione non e' qui.** Non esiste un `POST /{id}/approve`: approvare
significa creare la campagna, e quella la crea `POST /campaigns/` passando
`proposal_id` (vedi app/api/v1/campaigns.py). E' una scelta, non una mancanza -
un endpoint di approvazione separato potrebbe lasciare una proposta approvata
senza campagna dietro, o una campagna la cui proposta risulta ancora in attesa;
facendo coincidere i due fatti in una sola transazione quello stato non esiste.
Nella pratica: l'amministratore apre il wizard di creazione gia' compilato col
contenuto proposto, sceglie destinatari e date come per qualunque altra
campagna, e quando la crea la proposta risulta approvata.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_admin
from app.db.session import get_db
from app.models.administrator import Administrator
from app.models.campaign_proposal import CampaignProposal
from app.schemas.schemas import (
    CampaignProposalResponse,
    CampaignProposalReviewRequest,
    StatusCountsSummaryResponse,
)
from app.services import campaign_proposal_service as proposals

router = APIRouter()

# Le bozze non compaiono mai qui. Sono appunti che il promoter sta ancora
# scrivendo e che non ha consegnato: mostrarle vorrebbe dire far leggere
# all'amministratore qualcosa che nessuno gli ha mandato.
VISIBLE_STATUSES = (
    CampaignProposal.STATUS_SUBMITTED,
    CampaignProposal.STATUS_APPROVED,
    CampaignProposal.STATUS_REJECTED,
)


def _visible_proposal(db: Session, proposal_id: uuid.UUID) -> CampaignProposal:
    proposal = (
        db.query(CampaignProposal)
        .filter(CampaignProposal.id == proposal_id, CampaignProposal.status.in_(VISIBLE_STATUSES))
        .first()
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    return proposal


@router.get("/", response_model=List[CampaignProposalResponse])
def list_proposals(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    query = db.query(CampaignProposal).filter(CampaignProposal.status.in_(VISIBLE_STATUSES))
    if status_filter:
        if status_filter not in VISIBLE_STATUSES:
            raise HTTPException(status_code=400, detail="Stato non valido")
        query = query.filter(CampaignProposal.status == status_filter)

    # Le consegnate per prime, poi le piu' recenti: cio' che aspetta una
    # decisione va in cima, non in ordine cronologico in mezzo al resto.
    rows = query.order_by(
        (CampaignProposal.status == CampaignProposal.STATUS_SUBMITTED).desc(),
        CampaignProposal.submitted_at.desc().nullslast(),
        CampaignProposal.created_at.desc(),
    ).all()
    return [proposals.serialize(p) for p in rows]


@router.get("/summary", response_model=StatusCountsSummaryResponse)
def get_proposals_summary(db: Session = Depends(get_db), admin: Administrator = Depends(get_current_admin)):
    """Alimenta il contatore accanto alla voce di menu "Proposte" - stesso
    schema gia' usato da campagne e pubblicazioni."""
    rows = (
        db.query(CampaignProposal.status)
        .filter(CampaignProposal.status.in_(VISIBLE_STATUSES))
        .all()
    )
    by_status: dict[str, int] = {}
    for (proposal_status,) in rows:
        by_status[proposal_status] = by_status.get(proposal_status, 0) + 1
    return StatusCountsSummaryResponse(total=len(rows), by_status=by_status)


@router.get("/{proposal_id}", response_model=CampaignProposalResponse)
def get_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    return proposals.serialize(_visible_proposal(db, proposal_id))


@router.post("/{proposal_id}/reject", response_model=CampaignProposalResponse)
def reject_proposal(
    proposal_id: uuid.UUID,
    payload: CampaignProposalReviewRequest,
    db: Session = Depends(get_db),
    admin: Administrator = Depends(get_current_admin),
):
    """
    Rifiuta con un motivo, che il promoter legge cosi' com'e'. La proposta torna
    modificabile: puo' correggerla e ripresentarla, altrimenti un rifiuto
    sarebbe un vicolo cieco invece di una risposta.
    """
    proposal = _visible_proposal(db, proposal_id)
    if proposal.status == CampaignProposal.STATUS_APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Questa proposta è già diventata una campagna: annulla la campagna, non la proposta.",
        )
    return proposals.serialize(proposals.reject(db, proposal, admin.id, payload.review_notes))
