"""
Avvisi di servizio inviati a un utente dall'amministrazione.

Nasce con un solo tipo di avviso - "hai meno canali social di quanti il
progetto ne richieda" - ma la tabella e' volutamente generica (``kind``): la
prossima comunicazione di servizio ai promoter avra' bisogno delle stesse tre
cose, chi l'ha ricevuta, quando e perche', e non merita una tabella nuova.

Perche' una riga per invio e non una colonna ``last_notified_at`` su ``users``:
la domanda dell'amministratore non e' solo "quando l'ho avvisato l'ultima
volta" ma anche "quante volte gliel'ho gia' detto" - un promoter avvisato tre
volte in un mese e' un caso diverso da uno avvisato ieri per la prima volta, e
la pagina lo mostra. Il ``metadata`` tiene la fotografia del momento (quanti
canali aveva), cosi' si capisce dopo se l'avviso ha avuto effetto.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# L'unico tipo esistente oggi. Un valore stringa e non un Enum SQL: aggiungerne
# uno non deve richiedere una migration.
KIND_CHANNEL_REQUIREMENT = "channel_requirement"


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    # Chi ha premuto il pulsante. SET NULL e non CASCADE: cancellare un
    # amministratore non deve cancellare la storia degli avvisi inviati.
    sent_by_administrator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True
    )
    # Indirizzo al momento dell'invio: se l'utente poi lo cambia, qui resta
    # scritto dove e' andato davvero il messaggio.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="notifications")

    __table_args__ = (
        # La pagina chiede sempre "ultimo avviso di questo tipo per questo
        # utente": e' esattamente questo indice.
        Index("idx_user_notifications_user_kind_sent", "user_id", "kind", "sent_at"),
    )
