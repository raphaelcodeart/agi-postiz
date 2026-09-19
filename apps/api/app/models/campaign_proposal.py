"""
Proposte di campagna: il contenuto che un promoter suggerisce
all'amministratore.

Tabella separata da `campaigns`, non uno stato in piu' su quella. La differenza
non e' organizzativa, e' di sicurezza: `campaigns` e' la tabella che leggono il
resolver dei destinatari, il task di lancio e il poller di beat
(`poll_and_queue_scheduled_publications`). Una riga li' dentro che "non va mai
lanciata" obbligherebbe ognuno di quei percorsi a imparare a saltarla, e un solo
filtro dimenticato pubblicherebbe su tutti i canali la bozza non ancora
esaminata di un promoter. Una tabella diversa non e' lanciabile per costruzione:
non esiste codice che parta da qui e arrivi a una pubblicazione.

Il passaggio da proposta a campagna e' quindi una **creazione**, non un cambio
di stato: l'amministratore apre il wizard di creazione gia' compilato col
contenuto proposto, sceglie destinatari e date come per qualunque altra campagna
e la crea. Da quel momento in poi il meccanismo e' identico a sempre - palinsesto,
finestra di rinuncia, lancio - e resta quello che AGENTS.md ss2-3 proteggono.
`campaign_id` qui sotto tiene il filo fra le due cose.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CampaignProposal(Base):
    __tablename__ = "campaign_proposals"

    # Ancora modificabile e cancellabile da chi l'ha scritta; l'amministratore
    # non la vede nemmeno.
    STATUS_DRAFT = "draft"
    # Consegnata: da qui in poi e' in sola lettura per il promoter, perche' e'
    # cio' che l'amministratore sta guardando.
    STATUS_SUBMITTED = "submitted"
    # Ne e' nata una campagna vera (`campaign_id`).
    STATUS_APPROVED = "approved"
    # Rifiutata con un motivo. Torna modificabile: un rifiuto che non lascia
    # correggere e ripresentare e' un vicolo cieco, non una risposta.
    STATUS_REJECTED = "rejected"

    EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_REJECTED)

    # I social che un promoter puo' indicare come destinazione desiderata. Sono
    # gli stessi nomi di SocialChannel.platform, cosi' il wizard li puo' passare
    # tali e quali a targeting_params.platform_names.
    PLATFORMS = ("instagram", "facebook", "tiktok", "youtube", "linkedin", "twitter", "threads")

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Il testo del post proposto. Un solo testo, non le dieci varianti per
    # piattaforma di Campaign: il promoter propone un contenuto, le rifiniture
    # per Instagram/YouTube/X le fa l'amministratore nel wizard, dove quei campi
    # gia' esistono. Chiedergliele qui vorrebbe dire duplicare meta' del modello
    # Campaign in una tabella che non pubblica niente.
    default_text: Mapped[str] = mapped_column(String(5000), nullable=False)
    # Nota per l'amministratore: perche' questa campagna, a chi si rivolge,
    # cosa c'e' nel video. Non finisce mai nel testo pubblicato.
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Richiesta di un video su misura: il promoter che non sa (o non puo')
    # girarlo descrive qui cosa vorrebbe che AGI Post realizzasse. Facoltativa;
    # come `notes` e' rivolta all'amministratore e non viene mai pubblicata.
    video_request: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    # Su quali social il promoter vorrebbe vederla uscire. Indicazione, non
    # vincolo: il wizard la usa per precompilare il filtro per piattaforma,
    # e l'amministratore resta libero di cambiarlo.
    target_platforms: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), default=list, server_default="{}", nullable=False
    )

    media_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    # Data suggerita dal promoter. Deliberatamente NON vincolante e tenuta
    # separata da Campaign.scheduled_at: e' un'indicazione ("sarebbe bello
    # uscisse prima di Natale"), e chi decide quando si pubblica resta
    # l'amministratore.
    suggested_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default=STATUS_DRAFT, nullable=False)

    # Motivo del rifiuto, o nota dell'amministratore all'approvazione. Mostrato
    # al promoter cosi' com'e': un "no" senza motivo non gli dice cosa cambiare.
    review_notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # La campagna nata da questa proposta. Unico collegamento fra le due
    # tabelle, e in una direzione sola: da qui verso `campaigns`, mai il
    # contrario - nessun percorso di pubblicazione deve poter risalire a una
    # proposta, ne' avere motivo di farlo.
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Sola lettura, per mostrare nome del promoter e anteprima del media senza
    # una seconda query. Nessuna relationship inversa viene aggiunta su User,
    # MediaFile o Campaign: il collegamento resta unidirezionale, come per il
    # modulo Statistiche.
    user: Mapped["User"] = relationship("User", lazy="joined")
    media_file: Mapped[Optional["MediaFile"]] = relationship("MediaFile", lazy="joined")

    __table_args__ = (
        Index("idx_campaign_proposals_status", "status"),
        Index("idx_campaign_proposals_user_status", "user_id", "status"),
    )
