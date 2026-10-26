import uuid
from celery.utils.log import get_task_logger
from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.services.omnichannel_draft_service import OmnichannelDraftService
from app.services.omnichannel_service import OmnichannelService
from app.models.omnichannel import OmniChannelAccount
from app.integrations.omnichannel.connectors.registry import get_connector
from app.integrations.omnichannel.exceptions import ConnectorError

logger = get_task_logger(__name__)

@celery.task(name="app.tasks.omnichannel.generate_ai_draft_task")
def generate_ai_draft_task(message_id_str: str) -> None:
    """
    Background task triggered right after a new inbound message is ingested
    (see app/api/v1/omnichannel_webhooks.py). Generates the AI draft reply and
    leaves it as PENDING_APPROVAL/HUMAN_REVIEW_REQUIRED - never sends anything.
    """
    logger.info(f"Generating AI draft for omnichannel message {message_id_str}")
    message_id = uuid.UUID(message_id_str)

    db = SessionLocal()
    try:
        OmnichannelDraftService.generate_draft_for_message(db, message_id)
        logger.info(f"Completed AI draft generation for message {message_id_str}")
    except Exception as e:
        logger.error(f"Error generating AI draft for message {message_id_str}: {str(e)}")
    finally:
        db.close()


@celery.task(name="app.tasks.omnichannel.poll_gmail_channels_task")
def poll_gmail_channels_task() -> None:
    """
    Runs on a fixed interval (see celery.conf.beat_schedule in
    app/workers/celery_app.py). Gmail has no inbound webhook - see
    connectors/gmail.py module docstring - so this is the only ingestion path
    for channel == "gmail", playing the same role the Telegram/Meta webhook
    handlers (app/api/v1/omnichannel_webhooks.py) play for those channels,
    just pull instead of push. Each channel account's own failure is isolated
    (one broken App Password shouldn't stop polling every other Gmail/other
    channel account) and self-heals: status flips back to "connected" the
    first successful run after an "error".
    """
    db = SessionLocal()
    try:
        accounts = (
            db.query(OmniChannelAccount)
            .filter(OmniChannelAccount.channel == "gmail", OmniChannelAccount.status != "disabled")
            .all()
        )
        for account in accounts:
            try:
                connector = get_connector(account)
                since_uid = (account.config_json or {}).get("last_uid")
                messages, new_last_uid = connector.fetch_new_messages(since_uid)
                if messages:
                    OmnichannelService.ingest_messages_and_trigger_ai(db, account, messages)
                if new_last_uid is not None:
                    account.config_json = {**(account.config_json or {}), "last_uid": new_last_uid}
                account.status = "connected"
                db.commit()
            except ConnectorError as e:
                logger.error(f"Errore polling Gmail per canale {account.id}: {e.message}")
                account.status = "error"
                db.commit()
            except Exception as e:
                logger.error(f"Errore inatteso polling Gmail per canale {account.id}: {str(e)}")
                db.rollback()
    finally:
        db.close()


@celery.task(name="app.tasks.omnichannel.embed_knowledge_document_task")
def embed_knowledge_document_task(document_id_str: str) -> None:
    """
    Embedding dei blocchi di un documento appena salvato (vedi
    api/v1/omnichannel.py::_save_document). Se OpenAI rifiuta (credito finito,
    chiave assente) il documento resta "ready" e cercabile per testo: il motivo
    finisce in error_message, e il task periodico qui sotto riprova da solo.
    """
    from app.integrations.omnichannel import knowledge
    from app.models.omnichannel import OmniKnowledgeDocument
    from app.services.ai_settings_service import get_openai_credentials

    document_id = uuid.UUID(document_id_str)
    db = SessionLocal()
    try:
        document = db.query(OmniKnowledgeDocument).filter(OmniKnowledgeDocument.id == document_id).first()
        if not document:
            return
        api_key, _ = get_openai_credentials(db)
        if not api_key:
            document.error_message = "Ricerca semantica non attiva: nessuna API key OpenAI configurata. Il documento e' comunque cercabile per parole."
            db.commit()
            return
        try:
            done = knowledge.embed_pending_chunks(db, api_key, document_id=document_id)
            document.error_message = None
            db.commit()
            logger.info(f"Knowledge document {document_id_str}: {done} chunk embedded")
        except ConnectorError as e:
            db.rollback()
            document = db.query(OmniKnowledgeDocument).filter(OmniKnowledgeDocument.id == document_id).first()
            if document:
                document.error_message = f"Ricerca semantica non ancora attiva ({e.message}). Il documento e' comunque cercabile per parole; si riprova da solo."
                db.commit()
    except Exception as e:
        logger.error(f"Error embedding knowledge document {document_id_str}: {str(e)}")
        db.rollback()
    finally:
        db.close()


@celery.task(name="app.tasks.omnichannel.embed_pending_knowledge_task")
def embed_pending_knowledge_task() -> None:
    """
    Recupera i blocchi rimasti senza embedding: documenti caricati mentre il
    credito OpenAI era esaurito, task perso a un riavvio, documenti esistenti
    prima della migrazione b7e2d91c4a18. Non fa niente (nessuna chiamata) se
    non c'e' nulla da calcolare.
    """
    from sqlalchemy import update
    from app.integrations.omnichannel import knowledge
    from app.models.omnichannel import OmniKnowledgeChunk, OmniKnowledgeDocument
    from app.services.ai_settings_service import get_openai_credentials

    db = SessionLocal()
    try:
        if not db.query(OmniKnowledgeChunk.id).filter(OmniKnowledgeChunk.embedding.is_(None)).first():
            return
        api_key, _ = get_openai_credentials(db)
        if not api_key:
            return
        try:
            done = knowledge.embed_pending_chunks(db, api_key)
        except ConnectorError as e:
            logger.warning(f"Knowledge base embedding backlog not processed: {e.message}")
            db.rollback()
            return
        pending_docs = db.query(OmniKnowledgeChunk.document_id).filter(OmniKnowledgeChunk.embedding.is_(None)).distinct()
        db.execute(
            update(OmniKnowledgeDocument)
            .where(OmniKnowledgeDocument.error_message.isnot(None), OmniKnowledgeDocument.id.not_in(pending_docs))
            .values(error_message=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        logger.info(f"Knowledge base backlog: {done} chunk embedded")
    except Exception as e:
        logger.error(f"Error processing knowledge base embedding backlog: {str(e)}")
        db.rollback()
    finally:
        db.close()
