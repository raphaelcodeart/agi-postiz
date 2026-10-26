"""
Token monouso spediti per email: conferma dell'indirizzo e reset della password.

Una tabella e non due colonne su ``users``. Le colonne renderebbero impossibile
avere due richieste vive insieme (conferma + reset), non lascerebbero traccia di
quelle consumate o scadute, e obbligherebbero a una migrazione per ogni nuovo
tipo di link. Qui il tipo e' un dato, e la storia resta leggibile: chi ha chiesto
cosa, quando, e se e' stato usato.

Due scelte di sicurezza, entrambe deliberate:

1. Il database conserva solo lo SHA-256 del token, mai il token. Un backup o un
   dump letto da terzi non contiene quindi nulla di spendibile: il segreto
   esiste in chiaro solo nell'email dell'utente. Lo SHA-256 nudo basta perche' -
   a differenza di una password - il valore e' generato da ``secrets`` con
   256 bit di entropia: non c'e' dizionario da provare, e un hash lento qui
   servirebbe solo a rallentare ogni verifica.
2. Un token e' monouso (``used_at``). Un link di reset che resta valido dopo
   essere stato usato e' una password di riserva permanente nella casella di
   posta di qualcuno.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# Tipi di token. Costanti e non enum del database: aggiungerne uno non deve
# richiedere una migrazione, e il confronto avviene sempre con questi nomi.
PURPOSE_EMAIL_VERIFICATION = "email_verification"
PURPOSE_PASSWORD_RESET = "password_reset"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserAuthToken(Base):
    __tablename__ = "user_auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 esadecimale del token spedito - 64 caratteri. Unico: e' la chiave
    # con cui un link in arrivo viene risolto.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="auth_tokens")  # noqa: F821

    __table_args__ = (
        # Le due domande che il servizio fa sempre: "questo utente ha token vivi
        # di questo tipo?" (invalidazione) e "quanti ne ha chiesti nell'ultima
        # ora?" (limite di frequenza).
        Index("ix_user_auth_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_user_auth_tokens_purpose_created", "purpose", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        # Mai il token, nemmeno il suo hash (AGENTS.md regola 10).
        return f"<UserAuthToken {self.purpose} user={self.user_id} used={bool(self.used_at)}>"
