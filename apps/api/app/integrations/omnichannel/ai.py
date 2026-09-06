"""
AI context builder + draft generation for the Omnichannel Responder.

Deliberately self-contained (own httpx call, not a shared client) so this
add-on module has no code dependency on app/integrations/openai/client.py -
the only piece of existing infrastructure it reuses is
app.services.ai_settings_service.get_openai_credentials, the same
admin-configured OpenAI key already used by the Blog Writer/campaign wizard.

Knowledge base retrieval is keyword-based (ILIKE + naive term overlap
ranking) over OmniKnowledgeChunk rows, not embeddings - see
OmniKnowledgeChunk's docstring in app/models/omnichannel.py. Swapping this
for real vector search later (pgvector) only touches search_knowledge_base()
below.
"""
import json
import re
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.integrations.omnichannel.exceptions import ConnectorError
from app.models.omnichannel import OmniAIAgentConfig, OmniConversation, OmniKnowledgeChunk, OmniMessage

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

# Fixed vocabulary from the product spec (section 16) - always available even
# if the agent config hasn't customized sensitive_categories_json yet.
DEFAULT_SENSITIVE_CATEGORIES: List[str] = [
    "refund", "legal", "medical", "complaint", "pricing_exception", "discount", "contract", "payment_problem",
]

# Heuristic IT/EN keyword sets used to flag a customer message as touching a
# sensitive category. Intentionally simple (substring match) - good enough to
# force human review on the obvious cases; not a substitute for a real
# classifier, which would be the natural next iteration.
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "refund": ["rimborso", "refund", "storno", "restituzione soldi"],
    "legal": ["avvocato", "legale", "denuncia", "causa", "tribunale", "lawsuit", "legal action"],
    "medical": ["medico", "salute", "sintomo", "farmaco", "diagnosi", "medical", "symptom"],
    "complaint": ["reclamo", "insoddisfatto", "pessimo servizio", "complaint", "terrible service"],
    "pricing_exception": ["sconto speciale", "prezzo speciale", "eccezione", "special price"],
    "discount": ["sconto", "discount", "coupon", "promo code"],
    "contract": ["contratto", "clausola", "contract", "termination"],
    "payment_problem": ["pagamento fallito", "addebito", "non riesco a pagare", "payment failed", "double charge"],
}


def detect_sensitive_category(text: Optional[str], enabled_categories: Optional[List[str]]) -> Optional[str]:
    if not text:
        return None
    categories = enabled_categories or DEFAULT_SENSITIVE_CATEGORIES
    lowered = text.lower()
    for category in categories:
        for keyword in _CATEGORY_KEYWORDS.get(category, []):
            if keyword in lowered:
                return category
    return None


def search_knowledge_base(db: Session, owner_id, query_text: str, limit: int = 3) -> List[OmniKnowledgeChunk]:
    """Naive keyword search: ranks chunks by how many distinct query terms (len > 3) they contain."""
    terms = [t for t in re.findall(r"\w+", query_text.lower()) if len(t) > 3]
    if not terms:
        return []

    conditions = [OmniKnowledgeChunk.content.ilike(f"%{term}%") for term in terms[:10]]
    candidates = (
        db.query(OmniKnowledgeChunk)
        .filter(OmniKnowledgeChunk.owner_id == owner_id, or_(*conditions))
        .limit(50)
        .all()
    )

    def score(chunk: OmniKnowledgeChunk) -> int:
        content_lower = chunk.content.lower()
        return sum(1 for term in terms if term in content_lower)

    return sorted(candidates, key=score, reverse=True)[:limit]


def build_system_prompt(agent_config: Optional[OmniAIAgentConfig], kb_chunks: List[OmniKnowledgeChunk]) -> str:
    if agent_config and agent_config.system_prompt:
        base = agent_config.system_prompt
    else:
        base = "Sei un assistente clienti professionale. Rispondi in modo cortese, chiaro e utile ai messaggi dei clienti."

    lines = [base]
    if agent_config:
        if agent_config.company_description:
            lines.append(f"Informazioni sull'azienda: {agent_config.company_description}")
        lines.append(f"Tono di voce da usare: {agent_config.tone}.")
        if agent_config.language and agent_config.language != "auto":
            lines.append(f"Rispondi sempre in lingua: {agent_config.language}.")
        elif agent_config.automatic_language_detection:
            lines.append("Rispondi sempre nella stessa lingua usata dal cliente nel suo ultimo messaggio.")
        if agent_config.allowed_topics_json:
            lines.append(f"Argomenti su cui puoi rispondere: {', '.join(agent_config.allowed_topics_json)}.")
        if agent_config.forbidden_topics_json:
            lines.append(f"Non affrontare mai questi argomenti, rimanda a un operatore umano: {', '.join(agent_config.forbidden_topics_json)}.")
        if agent_config.signature:
            lines.append(f"Se appropriato, chiudi il messaggio con: {agent_config.signature}")

    if kb_chunks:
        kb_text = "\n\n".join(f"- {chunk.content}" for chunk in kb_chunks)
        lines.append(f"Usa queste informazioni aziendali per rispondere quando pertinenti, senza inventare dettagli non presenti:\n{kb_text}")

    lines.append(
        "IMPORTANTE: questa è solo una BOZZA di risposta che un operatore umano revisionerà prima dell'invio. "
        "Scrivi il testo pronto da inviare al cliente, senza premesse tipo 'Ecco una proposta di risposta'."
    )
    return "\n\n".join(lines)


def build_conversation_messages(conversation: OmniConversation, max_messages: int) -> List[Dict[str, str]]:
    recent = conversation.messages[-max_messages:] if conversation.messages else []
    result: List[Dict[str, str]] = []
    for msg in recent:
        if not msg.text:
            continue
        role = "user" if msg.sender_type == "customer" else "assistant"
        result.append({"role": role, "content": msg.text})
    return result


def generate_ai_reply(
    db: Session,
    api_key: str,
    model: str,
    agent_config: Optional[OmniAIAgentConfig],
    conversation: OmniConversation,
    latest_customer_text: str,
) -> Dict[str, Any]:
    """
    Returns {"text": str, "model": str, "input_tokens": int, "output_tokens": int}.
    Callers are responsible for checking detect_sensitive_category() themselves
    before calling this (the draft is still generated for HUMAN_REVIEW_REQUIRED
    cases too - see app/services/omnichannel_service.py - it's just labeled and
    never auto-approved).
    """
    kb_chunks: List[OmniKnowledgeChunk] = []
    if not agent_config or agent_config.knowledge_base_enabled:
        kb_chunks = search_knowledge_base(db, conversation.owner_id, latest_customer_text)

    system_prompt = build_system_prompt(agent_config, kb_chunks)
    max_messages = agent_config.max_context_messages if agent_config else 20
    messages = [{"role": "system", "content": system_prompt}] + build_conversation_messages(conversation, max_messages)

    temperature = agent_config.temperature if agent_config else 0.7

    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 800,
            },
            timeout=45.0,
        )
    except httpx.RequestError as e:
        raise ConnectorError(f"Errore di rete verso OpenAI: {str(e)}")

    if response.status_code != 200:
        raise ConnectorError(f"OpenAI ha risposto con errore ({response.status_code})", status_code=response.status_code)

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise ConnectorError(f"Risposta OpenAI non valida: {str(e)}")

    usage = data.get("usage", {})
    return {
        "text": text,
        "model": model,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }
