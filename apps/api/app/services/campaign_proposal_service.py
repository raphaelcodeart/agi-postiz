"""
Regole delle proposte di campagna, in un posto solo.

Due router le usano - il portale del promoter (app/api/v1/portal_proposals.py) e
la dashboard dell'amministratore (app/api/v1/campaign_proposals.py) - e le due
parti devono concordare su cosa e' modificabile, cosa e' consegnato e cosa
diventa una campagna. Le transizioni stanno qui e non nei router perche' una
regola scritta due volte e' una regola che prima o poi dice due cose diverse.

Vedi app/models/campaign_proposal.py per il perche' questa non e' una campagna.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign_proposal import CampaignProposal

# Cio' che l'amministratore deve esaminare. E' l'unico stato che conta per il
# contatore sul bottone "Proposte": una bozza non ancora consegnata non e'
# lavoro che lo aspetta, e una gia' decisa non lo e' piu'.
PENDING_STATUS = CampaignProposal.STATUS_SUBMITTED


def utc_now() -> datetime:
    return datetime.now(UTC)


def serialize(proposal: CampaignProposal) -> dict[str, Any]:
    """Forma di CampaignProposalResponse, identica per portale e dashboard.

    Il nome del promoter e l'URL del media sono appiattiti qui: chi legge una
    proposta vuole sempre sapere chi l'ha scritta e vedere il video, e farlo
    risolvere a ognuno dei due router porterebbe alla stessa join scritta due
    volte (le relationship sono `lazy="joined"`, quindi non costano una query in
    piu').
    """
    media = proposal.media_file
    return {
        "id": proposal.id,
        "user_id": proposal.user_id,
        "user_name": proposal.user.name if proposal.user else None,
        "title": proposal.title,
        "default_text": proposal.default_text,
        "notes": proposal.notes,
        "video_request": proposal.video_request,
        "target_platforms": list(proposal.target_platforms or []),
        "media_file_id": proposal.media_file_id,
        "media_url": media.public_url if media else None,
        "media_mime_type": media.mime_type if media else None,
        "suggested_scheduled_at": proposal.suggested_scheduled_at,
        "status": proposal.status,
        "review_notes": proposal.review_notes,
        "reviewed_at": proposal.reviewed_at,
        "submitted_at": proposal.submitted_at,
        "campaign_id": proposal.campaign_id,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }


def is_editable(proposal: CampaignProposal) -> bool:
    return proposal.status in CampaignProposal.EDITABLE_STATUSES


def submit(db: Session, proposal: CampaignProposal) -> CampaignProposal:
    """Consegna la proposta all'amministratore.

    Ripresentare una proposta rifiutata azzera la decisione precedente
    (`review_notes`/`reviewed_at`/`reviewed_by`): lasciare li' il motivo del
    vecchio rifiuto accanto a un testo nel frattempo cambiato farebbe leggere
    all'amministratore una critica che non riguarda piu' quello che ha davanti.
    """
    proposal.status = CampaignProposal.STATUS_SUBMITTED
    proposal.submitted_at = utc_now()
    proposal.review_notes = None
    proposal.reviewed_at = None
    proposal.reviewed_by = None
    db.commit()
    db.refresh(proposal)
    return proposal


def reject(db: Session, proposal: CampaignProposal, admin_id: uuid.UUID, review_notes: str) -> CampaignProposal:
    """Rifiuta con un motivo e riapre la proposta alle modifiche del promoter."""
    proposal.status = CampaignProposal.STATUS_REJECTED
    proposal.review_notes = review_notes
    proposal.reviewed_by = admin_id
    proposal.reviewed_at = utc_now()
    db.commit()
    db.refresh(proposal)
    return proposal


def mark_approved(proposal: CampaignProposal, admin_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
    """Segna la proposta come diventata una campagna.

    Non fa commit: e' chiamata da create_campaign (app/api/v1/campaigns.py)
    dentro la **stessa** transazione che crea la campagna. Separare le due cose
    lascerebbe aperta la finestra in cui una proposta risulta approvata senza
    che nessuna campagna sia nata, o una campagna esiste mentre la proposta
    risulta ancora in attesa.
    """
    proposal.status = CampaignProposal.STATUS_APPROVED
    proposal.reviewed_by = admin_id
    proposal.reviewed_at = utc_now()
    proposal.campaign_id = campaign_id


def pending_count(db: Session) -> int:
    return db.query(CampaignProposal).filter(CampaignProposal.status == PENDING_STATUS).count()
