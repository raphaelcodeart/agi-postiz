"""
Ciclo di vita dei token monouso spediti per email.

Un solo posto che sa come si crea, come si verifica e quando smette di valere un
link mandato a un indirizzo: se questa logica si sparpagliasse fra gli endpoint,
prima o poi uno dei due dimenticherebbe un controllo, e il controllo dimenticato
qui e' un accesso all'account di qualcun altro.

Le regole, tutte insieme:

- il token in chiaro esiste solo nell'email; il database ne tiene lo SHA-256
  (vedi models/auth_token.py per il perche' SHA-256 nudo qui basti);
- emetterne uno nuovo annulla quelli ancora vivi dello stesso tipo, cosi' non
  restano piu' link validi in giro per la casella;
- e' monouso e scade;
- c'e' un limite di frequenza per utente, altrimenti la casella di chiunque
  diventa bersaglio di una valanga di email a costo zero per chi la lancia.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.auth_token import (
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    UserAuthToken,
)
from app.models.user import User

logger = logging.getLogger(__name__)

# 32 byte da secrets -> 43 caratteri URL-safe. Entropia sufficiente perche'
# indovinarlo sia fuori discussione, e il link resta incollabile senza che il
# client email lo spezzi.
TOKEN_BYTES = 32

# Quante richieste dello stesso tipo accettiamo per utente nella finestra.
# Cinque copre abbondantemente "non mi e' arrivata, riprova" e taglia l'uso
# dell'endpoint come mitragliatrice contro una casella.
MAX_REQUESTS_PER_WINDOW = 5
RATE_WINDOW = timedelta(hours=1)


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def rate_limited(db: Session, user: User, purpose: str) -> bool:
    """Vero se l'utente ha gia' esaurito le richieste di questo tipo nell'ultima ora."""
    since = datetime.now(timezone.utc) - RATE_WINDOW
    count = (
        db.query(UserAuthToken)
        .filter(
            UserAuthToken.user_id == user.id,
            UserAuthToken.purpose == purpose,
            UserAuthToken.created_at >= since,
        )
        .count()
    )
    return count >= MAX_REQUESTS_PER_WINDOW


def issue(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    """
    Crea un token, ne salva l'impronta e restituisce il valore in chiaro.

    Il valore restituito e' l'unica copia leggibile che esistera' mai: va usato
    subito per comporre il link e poi dimenticato, mai registrato nei log.

    Non fa commit: chi chiama sta gia' scrivendo altro nella stessa transazione
    (l'utente appena registrato, per esempio) e le due cose devono vivere o
    morire insieme.
    """
    now = datetime.now(timezone.utc)

    # I link precedenti dello stesso tipo smettono di valere. ``used_at`` copre
    # sia "consumato" sia "superato da uno nuovo": in entrambi i casi il link
    # non deve piu' aprire niente, e distinguere i due stati non servirebbe a
    # nessuna decisione.
    (
        db.query(UserAuthToken)
        .filter(
            UserAuthToken.user_id == user.id,
            UserAuthToken.purpose == purpose,
            UserAuthToken.used_at.is_(None),
        )
        .update({UserAuthToken.used_at: now}, synchronize_session=False)
    )

    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(
        UserAuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_hash(raw_token),
            expires_at=now + ttl,
        )
    )
    db.flush()
    return raw_token


def consume(db: Session, raw_token: str, purpose: str) -> Optional[User]:
    """
    Convalida un token e lo brucia. Restituisce l'utente, o None.

    Un solo None per tutti i motivi di fallimento - inesistente, scaduto, gia'
    usato, tipo sbagliato - di proposito: distinguere i casi nella risposta
    direbbe a chi prova link a caso quali stanno andando vicino.

    Anche qui nessun commit: il chiamante deve poter scrivere l'effetto del
    token (indirizzo confermato, password cambiata) nella stessa transazione in
    cui il token viene bruciato. Bruciarlo a parte vorrebbe dire poter perdere
    l'effetto tenendosi il consumo.
    """
    if not raw_token:
        return None

    row = (
        db.query(UserAuthToken)
        .filter(
            UserAuthToken.token_hash == _hash(raw_token),
            UserAuthToken.purpose == purpose,
        )
        .first()
    )

    if row is None or row.used_at is not None:
        return None

    # Le date arrivano da PostgreSQL con fuso; il confronto e' sempre in UTC
    # (AGENTS.md regola 12). Il ramo senza fuso copre SQLite nei test.
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None

    user = db.query(User).filter(User.id == row.user_id, User.deleted_at.is_(None)).first()
    if user is None:
        return None

    row.used_at = datetime.now(timezone.utc)
    return user


def verification_sent(db: Session, user: User) -> bool:
    """
    Vero se a questo utente e' gia' partita almeno un'email di conferma.

    Serve solo alla finestra di attesa, per scegliere fra "ti abbiamo scritto" e
    "ti mandiamo un'email": un iscritto di prima della conferma non ha ancora
    ricevuto niente, e dirgli di controllare la posta lo manderebbe a cercare un
    messaggio che non esiste. Dopo ``purge_expired`` la risposta torna falsa, e
    va bene cosi': il testo che ne segue - "ti mandiamo un'email" - resta vero.
    """
    return (
        db.query(UserAuthToken.id)
        .filter(
            UserAuthToken.user_id == user.id,
            UserAuthToken.purpose == PURPOSE_EMAIL_VERIFICATION,
        )
        .first()
        is not None
    )


def invalidate_pending(db: Session, user: User, purpose: Optional[str] = None) -> int:
    """
    Spegne i link ancora vivi di un utente. Restituisce quanti ne ha spenti.

    Serve dopo un cambio di password: da quel momento ogni altro link valido su
    quell'account e' solo un'altra porta aperta su di esso, e chi ha appena
    ripreso il controllo delle proprie credenziali si aspetta che le porte siano
    tutte chiuse. Senza ``purpose`` vale per ogni tipo.

    Come in ``issue``, nessun commit: appartiene alla transazione del chiamante.
    """
    query = db.query(UserAuthToken).filter(
        UserAuthToken.user_id == user.id,
        UserAuthToken.used_at.is_(None),
    )
    if purpose is not None:
        query = query.filter(UserAuthToken.purpose == purpose)
    return query.update(
        {UserAuthToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False
    )


def purge_expired(db: Session, older_than: timedelta = timedelta(days=30)) -> int:
    """
    Elimina i token spenti da un pezzo. Restituisce quanti ne ha tolti.

    La tabella cresce di una riga per ogni registrazione e per ogni password
    dimenticata, e una riga scaduta non risponde piu' a nessuna domanda utile.
    Si tiene un mese perche' e' la finestra in cui puo' ancora servire capire
    cos'e' successo a un accesso andato storto.
    """
    cutoff = datetime.now(timezone.utc) - older_than
    removed = (
        db.query(UserAuthToken)
        .filter(UserAuthToken.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if removed:
        logger.info("Rimossi %s token di autenticazione scaduti", removed)
    return removed


__all__ = [
    "PURPOSE_EMAIL_VERIFICATION",
    "PURPOSE_PASSWORD_RESET",
    "consume",
    "invalidate_pending",
    "issue",
    "purge_expired",
    "rate_limited",
    "verification_sent",
]
