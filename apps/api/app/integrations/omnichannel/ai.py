"""
AI context builder + draft generation for the Omnichannel Responder.

Deliberately self-contained (own httpx call, not a shared client) so this
add-on module has no code dependency on app/integrations/openai/client.py -
the only piece of existing infrastructure it reuses is
app.services.ai_settings_service.get_openai_credentials, the same
admin-configured OpenAI key already used by the Blog Writer/campaign wizard.

Knowledge base retrieval (hybrid full-text + embeddings) lives in
app/integrations/omnichannel/knowledge.py; this module only decides where the
retrieved blocks go in the prompt.
"""
import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import httpx
from sqlalchemy.orm import Session

from app.integrations.omnichannel import knowledge
from app.integrations.omnichannel.crm import tools as crm_tools
from app.integrations.omnichannel.exceptions import ConnectorError
from app.models.omnichannel import (
    OmniAIAgentConfig,
    OmniConversation,
    OmniKnowledgeDocument,
)

# Quanti giri "strumento -> risposta" concediamo al modello per una bozza. Due
# o tre bastano per "saldo + ultimo ordine"; il tetto evita che una domanda
# strana diventi una raffica di chiamate al CRM e a OpenAI.
MAX_TOOL_ROUNDS = 4

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


def build_system_prompt(agent_config: Optional[OmniAIAgentConfig], standing_instructions: Sequence[OmniKnowledgeDocument] = ()) -> str:
    """
    La parte STABILE del prompt: identica da un messaggio all'altro finche'
    non si cambiano le impostazioni. Sta in testa alla richiesta apposta:
    OpenAI mette in cache automaticamente i prefissi ripetuti oltre i 1024
    token e li fattura a meta' prezzo, quindi tutto cio' che varia (i blocchi
    della Knowledge Base) va in fondo, dopo la cronologia - vedi
    build_messages().
    """
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

    if standing_instructions:
        body = "\n\n".join(
            f"- {doc.title}{f' ({doc.company})' if doc.company else ''}: {(doc.content_text or '').strip()}"
            for doc in standing_instructions
        )
        lines.append(f"Istruzioni dell'azienda da seguire sempre:\n{body}")

    if not agent_config or agent_config.knowledge_base_enabled:
        lines.append(
            "Prima di ogni risposta puoi ricevere un messaggio con le informazioni pertinenti prese dalla Knowledge Base, "
            "ognuna con la sua provenienza tra parentesi quadre (azienda e documento). Usale come fonte principale. "
            "Se informazioni di aziende diverse sono in conflitto, usa quelle dell'azienda di cui il cliente sta parlando. "
            "Non inventare mai prezzi, disponibilita', tempi, condizioni o dati che non trovi li' o nella conversazione: "
            "se un'informazione manca, dillo con naturalezza e proponi che un collega ricontatti il cliente."
        )

    lines.append(
        "IMPORTANTE: scrivi solo il testo del messaggio pronto da inviare al cliente, "
        "senza premesse tipo 'Ecco una proposta di risposta'. Sii conciso: e' una chat, non un'email."
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


def build_messages(system_prompt: str, history: List[Dict[str, str]], kb_context: str, crm_context: str = "") -> List[Dict[str, Any]]:
    """
    Il contesto CRM (chi e' il cliente, cosa si puo' consultare) va in fondo con
    la Knowledge Base, non nel prompt di sistema: cambia da cliente a cliente e
    nel prefisso stabile romperebbe la cache di OpenAI.
    """
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}, *history]
    if kb_context:
        messages.append({"role": "system", "content": kb_context})
    if crm_context:
        messages.append({"role": "system", "content": crm_context})
    return messages


# Codici/tipi con cui OpenAI segnala "l'account non puo' pagare questa
# chiamata" invece di "stai andando troppo veloce". Entrambi tornano 429, ma
# il rimedio e' opposto: ricaricare contro aspettare.
_QUOTA_MARKERS = {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"}


def _describe_openai_error(response: httpx.Response) -> str:
    """
    Turns an OpenAI error response into something an operator can act on.

    The response body is safe to surface: OpenAI echoes back only its own
    error object ({"error": {"message", "type", "code"}}), never the request
    we sent - so no API key can leak through here. It's the request headers
    that must stay out of any error message, not the reply.

    Why this exists (2026-09-22): a 429 reached the operator as the bare
    "OpenAI ha risposto con errore (429)" and, since the key had been
    accepted by the Impostazioni page, it read as a broken integration. The
    account had simply run out of credit - a fact OpenAI states plainly in
    the body we were discarding. Same failure shape as the Maytapi
    setWebhook bug fixed the same day: the provider explains itself and we
    throw the explanation away.

    Note that validate_api_key() (integrations/openai/client.py) cannot
    catch this case at configuration time: it lists models, which costs no
    tokens and keeps working with an empty balance.
    """
    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}
    detail = str(error.get("message") or "").strip()
    # Both fields matter and they disagree: a real exhausted-balance 429 comes
    # back as type="insufficient_quota" WITH code="credit_balance_exhausted"
    # (payload observed in production on 2026-09-22), so reading `code or type`
    # and comparing to one value labels it a rate limit - the opposite remedy.
    markers = {str(error.get("code") or ""), str(error.get("type") or "")}

    if response.status_code == 429 and markers & _QUOTA_MARKERS:
        return (
            "Credito OpenAI esaurito: la chiave è valida ma l'account non ha credito residuo. "
            "Ricaricalo su platform.openai.com/settings/organization/billing, poi riprova."
        )
    if response.status_code == 429:
        return f"OpenAI ha applicato un limite di frequenza (429): {detail or 'riprova tra qualche secondo'}"
    if response.status_code == 401:
        return "Chiave OpenAI rifiutata (401): controlla la chiave in Impostazioni > AI."
    if detail:
        return f"OpenAI ha risposto con errore ({response.status_code}): {detail}"
    return f"OpenAI ha risposto con errore ({response.status_code})"


def retrieve_context(
    db: Session, api_key: Optional[str], agent_config: Optional[OmniAIAgentConfig], owner_id, customer_texts: Sequence[str],
    company_id=None,
) -> Tuple[List[knowledge.RetrievedChunk], Optional[str]]:
    if agent_config and not agent_config.knowledge_base_enabled:
        return [], None
    query = knowledge.build_search_query(customer_texts)
    return knowledge.search(db, owner_id, query, api_key, company_id=company_id)


ToolsProvider = Union[None, List[Dict[str, Any]], Callable[[], List[Dict[str, Any]]]]


def _post_chat(api_key: str, body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=45.0,
        )
    except httpx.RequestError as e:
        raise ConnectorError(f"Errore di rete verso OpenAI: {e!s}") from e

    if response.status_code != 200:
        raise ConnectorError(_describe_openai_error(response), status_code=response.status_code)
    return response.json()


def complete_chat(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    tools: ToolsProvider = None,
    tool_executor: Optional[Callable[[str, Dict[str, Any]], str]] = None,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
) -> Dict[str, Any]:
    """
    Una conversazione con il modello, con eventuali strumenti (function
    calling). Finche' il modello chiede strumenti, li eseguiamo con
    ``tool_executor`` e rimandiamo i risultati; ``tools`` puo' essere una
    funzione perche' l'elenco puo' cambiare tra un giro e l'altro (dopo
    confirm_identity_by_email compaiono gli strumenti del cliente). I token
    si sommano su tutti i giri: e' il costo vero della bozza.
    """
    conversation: List[Dict[str, Any]] = list(messages)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    tool_calls_made = 0

    for round_index in range(max_tool_rounds + 1):
        tool_list = tools() if callable(tools) else tools
        body: Dict[str, Any] = {"model": model, "messages": conversation, "temperature": temperature, "max_tokens": 600}
        # All'ultimo giro niente strumenti: il modello deve rispondere con
        # quello che ha, invece di chiedere un'altra ricerca che non eseguiremmo.
        if tool_list and tool_executor and round_index < max_tool_rounds:
            body["tools"] = tool_list
            body["tool_choice"] = "auto"

        data = _post_chat(api_key, body)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise ConnectorError(f"Risposta OpenAI non valida: {e!s}") from e

        usage = data.get("usage", {}) or {}
        totals["input_tokens"] += usage.get("prompt_tokens", 0) or 0
        totals["output_tokens"] += usage.get("completion_tokens", 0) or 0
        totals["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0

        tool_calls = message.get("tool_calls") or []
        if tool_calls and tool_executor and "tools" in body:
            conversation.append({"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls})
            for call in tool_calls:
                function = call.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                output = tool_executor(str(function.get("name") or ""), args)
                tool_calls_made += 1
                conversation.append({"role": "tool", "tool_call_id": call.get("id"), "content": output})
            continue

        text = (message.get("content") or "").strip()
        if not text:
            raise ConnectorError("Risposta OpenAI vuota")
        return {"text": text, "model": model, "tool_calls": tool_calls_made, **totals}

    raise ConnectorError("Il modello ha chiesto troppe ricerche nel CRM senza arrivare a una risposta")


def generate_ai_reply(
    db: Session,
    api_key: str,
    model: str,
    agent_config: Optional[OmniAIAgentConfig],
    conversation: OmniConversation,
    latest_customer_text: str,
) -> Dict[str, Any]:
    """
    Returns {"text", "model", "input_tokens", "output_tokens", "cached_tokens",
    "kb_sources", "kb_warning", "crm"}. Una chiamata al modello di chat per
    bozza, piu' una per ogni giro di strumenti CRM se il cliente chiede dati
    del suo account; la ricerca nella Knowledge Base costa al massimo un
    embedding. Callers are responsible for checking detect_sensitive_category()
    themselves before calling this (the draft is still generated for
    HUMAN_REVIEW_REQUIRED cases too - see app/services/omnichannel_service.py -
    it's just labeled and never auto-approved).
    """
    max_messages = agent_config.max_context_messages if agent_config else 20
    history = build_conversation_messages(conversation, max_messages)
    customer_texts = [m["content"] for m in history if m["role"] == "user"]
    if latest_customer_text and (not customer_texts or customer_texts[-1] != latest_customer_text):
        customer_texts.append(latest_customer_text)

    kb_chunks, kb_warning = retrieve_context(db, api_key, agent_config, conversation.owner_id, customer_texts)
    standing = knowledge.always_on_instructions(db, conversation.owner_id) if (not agent_config or agent_config.knowledge_base_enabled) else []

    # CRM: chi e' il cliente lo decide il canale (numero WhatsApp) o la scheda
    # compilata dall'operatore - vedi crm/tools.py. Il modello riceve solo
    # strumenti gia' legati a quel cliente.
    crm_client = crm_tools.client_for(agent_config)
    crm_ctx = crm_tools.prepare(crm_client, conversation.customer, conversation.channel_account.channel if conversation.channel_account else None)
    crm_section = crm_tools.system_prompt_section(crm_ctx) if crm_ctx else ""

    messages = build_messages(build_system_prompt(agent_config, standing), history, knowledge.format_context(kb_chunks), crm_section)
    temperature = agent_config.temperature if agent_config else 0.7

    result = complete_chat(
        api_key, model, messages, temperature,
        tools=(lambda: crm_tools.tool_definitions(crm_ctx)) if crm_ctx else None,
        tool_executor=(lambda name, args: crm_tools.execute_tool(crm_client, crm_ctx, name, args)) if crm_ctx else None,
    )
    result["kb_sources"] = [
        {"document_id": str(c.document_id), "title": c.document_title, "company": c.company} for c in kb_chunks
    ]
    result["kb_warning"] = kb_warning
    result["crm"] = crm_ctx.summary() if crm_ctx else None
    return result


def preview_reply(
    db: Session, api_key: str, model: str, agent_config: Optional[OmniAIAgentConfig], owner_id, question: str,
    company_id=None,
) -> Dict[str, Any]:
    """
    Come generate_ai_reply, ma su una domanda di prova senza conversazione: per
    la pagina Knowledge Base. Nessun cliente, quindi il CRM entra solo con il
    catalogo (prodotti, gift card): e' anche il modo di provare che la chiave
    funzioni senza toccare dati di nessuno.
    """
    kb_chunks, kb_warning = retrieve_context(db, api_key, agent_config, owner_id, [question], company_id)
    standing = knowledge.always_on_instructions(db, owner_id, company_id) if (not agent_config or agent_config.knowledge_base_enabled) else []
    crm_client = crm_tools.client_for(agent_config)
    crm_ctx = crm_tools.prepare(crm_client, None, None)
    messages = build_messages(
        build_system_prompt(agent_config, standing), [{"role": "user", "content": question}], knowledge.format_context(kb_chunks),
        crm_tools.system_prompt_section(crm_ctx) if crm_ctx else "",
    )
    result = complete_chat(
        api_key, model, messages, agent_config.temperature if agent_config else 0.7,
        tools=(lambda: crm_tools.tool_definitions(crm_ctx)) if crm_ctx else None,
        tool_executor=(lambda name, args: crm_tools.execute_tool(crm_client, crm_ctx, name, args)) if crm_ctx else None,
    )
    result["kb_chunks"] = kb_chunks
    result["kb_warning"] = kb_warning
    result["crm"] = crm_ctx.summary() if crm_ctx else None
    return result
