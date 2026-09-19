"""
Proposte di campagna dal lato del promoter.

Un promoter scrive testo, note e allega un video, e lo manda all'amministratore.
Non lancia niente e non puo' lanciare niente: questi endpoint scrivono soltanto
su `campaign_proposals`, una tabella che nessun percorso di pubblicazione legge
(vedi il docstring di app/models/campaign_proposal.py). La campagna vera nasce
solo quando l'amministratore la crea, dal suo wizard, con i suoi destinatari e
le sue date.

Vale la regola invariante del portale (docstring di portal.py): l'id utente
viene dal token, mai da un parametro. Ogni query qui sotto filtra su
`user_id == current_user.id`, quindi la proposta di un altro promoter risponde
404 come una inesistente.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.portal import get_current_portal_user
from app.db.session import get_db
from app.models.campaign_proposal import CampaignProposal
from app.models.media import MediaFile
from app.models.user import User
from app.schemas.schemas import (
    CampaignProposalCreate,
    CampaignProposalResponse,
    CampaignProposalUpdate,
    MediaResponse,
)
from app.services import campaign_proposal_service as proposals
from app.services.media_service import MediaService
from app.tasks.media import inspect_media_task

router = APIRouter()


def _owned_proposal(db: Session, user: User, proposal_id: uuid.UUID) -> CampaignProposal:
    proposal = (
        db.query(CampaignProposal)
        .filter(CampaignProposal.id == proposal_id, CampaignProposal.user_id == user.id)
        .first()
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    return proposal


def _require_editable(proposal: CampaignProposal) -> None:
    if not proposals.is_editable(proposal):
        raise HTTPException(
            status_code=409,
            detail=(
                "Questa proposta è già stata inviata all'amministratore e non è più modificabile."
                if proposal.status == CampaignProposal.STATUS_SUBMITTED
                else "Questa proposta è già diventata una campagna e non è più modificabile."
            ),
        )


def _validate_media(db: Session, user: User, media_file_id: uuid.UUID | None) -> None:
    """Il media allegato dev'essere uno caricato da questo promoter.

    La libreria media e' condivisa con l'amministratore, quindi senza questo
    controllo un promoter potrebbe allegare alla propria proposta un id qualsiasi
    e vedersi restituire, nella risposta, l'URL di un file dell'amministratore -
    una lettura di materiale non suo ottenuta indovinando un UUID.
    """
    if media_file_id is None:
        return
    media = (
        db.query(MediaFile)
        .filter(
            MediaFile.id == media_file_id,
            MediaFile.deleted_at.is_(None),
            MediaFile.uploaded_by_user_id == user.id,
        )
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="File non trovato fra quelli che hai caricato")


# ==============================================================================
# Media del promoter
# ==============================================================================
@router.post("/proposals/media", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
def upload_proposal_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Carica il video o l'immagine da allegare a una proposta.

    Riusa `MediaService.validate_and_save_upload` - stessa validazione di
    tipo/dimensione e stessa ispezione FFprobe in background dell'upload
    dell'amministratore, nessuna seconda strada per far entrare un file nel
    sistema. L'unica differenza e' `uploaded_by_user_id`, che marca la riga come
    caricata da un promoter: e' cio' su cui poggia il controllo di
    `_validate_media` qui sopra.
    """
    media_file = MediaService.validate_and_save_upload(db, file)
    media_file.uploaded_by_user_id = current_user.id
    db.commit()
    db.refresh(media_file)

    inspect_media_task.delay(str(media_file.id))
    return media_file


# ==============================================================================
# Proposte
# ==============================================================================
@router.get("/proposals", response_model=List[CampaignProposalResponse])
def list_my_proposals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    rows = (
        db.query(CampaignProposal)
        .filter(CampaignProposal.user_id == current_user.id)
        .order_by(CampaignProposal.created_at.desc())
        .all()
    )
    return [proposals.serialize(p) for p in rows]


@router.post("/proposals", response_model=CampaignProposalResponse, status_code=status.HTTP_201_CREATED)
def create_my_proposal(
    payload: CampaignProposalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    _validate_media(db, current_user, payload.media_file_id)

    proposal = CampaignProposal(
        user_id=current_user.id,
        title=payload.title.strip(),
        default_text=payload.default_text,
        notes=payload.notes,
        video_request=payload.video_request,
        target_platforms=payload.target_platforms,
        media_file_id=payload.media_file_id,
        suggested_scheduled_at=payload.suggested_scheduled_at,
        status=CampaignProposal.STATUS_DRAFT,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    if payload.submit:
        proposals.submit(db, proposal)
    return proposals.serialize(proposal)


@router.get("/proposals/{proposal_id}", response_model=CampaignProposalResponse)
def get_my_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    return proposals.serialize(_owned_proposal(db, current_user, proposal_id))


@router.patch("/proposals/{proposal_id}", response_model=CampaignProposalResponse)
def update_my_proposal(
    proposal_id: uuid.UUID,
    payload: CampaignProposalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    proposal = _owned_proposal(db, current_user, proposal_id)
    _require_editable(proposal)

    # `exclude_unset`: un campo non mandato resta com'e'. Senza, salvare solo il
    # titolo svuoterebbe le note e staccherebbe il video.
    data = payload.model_dump(exclude_unset=True)
    if "media_file_id" in data:
        _validate_media(db, current_user, data["media_file_id"])
    # "Nessun social" si manda come null o come lista vuota: la colonna vuole
    # sempre una lista.
    if "target_platforms" in data and data["target_platforms"] is None:
        data["target_platforms"] = []
    for field, value in data.items():
        setattr(proposal, field, value)

    db.commit()
    db.refresh(proposal)
    return proposals.serialize(proposal)


@router.post("/proposals/{proposal_id}/submit", response_model=CampaignProposalResponse)
def submit_my_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    proposal = _owned_proposal(db, current_user, proposal_id)
    _require_editable(proposal)
    return proposals.serialize(proposals.submit(db, proposal))


@router.delete("/proposals/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_portal_user),
):
    """
    Si cancella solo cio' che e' ancora in mano al promoter: una bozza o una
    proposta rifiutata. Una consegnata no - sparirebbe dalla lista mentre
    l'amministratore la sta leggendo - e una approvata nemmeno: e' il documento
    che dice da dove viene una campagna che ormai esiste.
    """
    proposal = _owned_proposal(db, current_user, proposal_id)
    _require_editable(proposal)
    db.delete(proposal)
    db.commit()
    return
