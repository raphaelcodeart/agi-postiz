import json
from typing import Any, Dict, List, Optional
import httpx
from app.integrations.openai.exceptions import OpenAIApiError

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


def validate_api_key(api_key: str) -> bool:
    """
    Cheaply verifies a key actually works before persisting it, mirroring the
    Buffer connection UX precedent (POST /connections calls get_user_info
    synchronously). Listing models costs no tokens.
    """
    try:
        response = httpx.get(
            OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )
    except httpx.RequestError:
        return False
    return response.status_code == 200

# Per-platform character targets given to the model, and the hard ceiling this
# module enforces server-side afterward regardless of what the model returns.
# x_text/threads_text/youtube_title match real, strict platform limits (X=280,
# Threads=500, YouTube title=100) already enforced elsewhere in this codebase
# (campaign_resolver.PLATFORM_TEXT_LIMITS, schemas.CampaignCreateRequest). The
# others (instagram/facebook/linkedin/tiktok) use widely-documented practical
# caption limits, not a database constraint - this app's own storage columns
# allow up to 5000 chars for those, so the model's target is the real guardrail,
# with the DB max_length as a final backstop.
FIELD_TARGETS: Dict[str, int] = {
    "default_text": 2000,
    "instagram_text": 2200,
    "facebook_text": 2000,
    "linkedin_text": 3000,
    "tiktok_text": 2200,
    "x_text": 280,
    "threads_text": 500,
    "youtube_title": 100,
    "youtube_description": 1000,
}

# Absolute ceilings - never exceeded even if the model ignores the target above.
# Matches this app's own column limits (models/campaign.py, schemas.py) so a
# generated text can never fail campaign creation validation downstream.
HARD_LIMITS: Dict[str, int] = {
    "default_text": 5000,
    "instagram_text": 5000,
    "facebook_text": 5000,
    "linkedin_text": 5000,
    "tiktok_text": 5000,
    "x_text": 280,
    "threads_text": 500,
    "youtube_title": 100,
    "youtube_description": 5000,
}

# Mirrors REFERRAL_LINK_RESERVED_CHARS in apps/dashboard/lib/validation/campaigns.ts
# - keep both in sync if either changes. Space for the fixed "\n\nISCRIVITI QUI: "
# label (17 chars, see campaign_resolver.py resolve_text_for_channel) plus a
# modest assumption for the link itself. When the campaign wizard's "Includi
# link referral" is already on at generation time, x_text/threads_text targets
# are reduced by this before asking the model, so the generated text already
# leaves room instead of the admin discovering it's too long only after
# toggling the option on (real incident, 2026-08-15: an ordinary 168-char
# generated X/Twitter text blocked the wizard the moment referral was enabled).
REFERRAL_LINK_RESERVED_CHARS = 60

# Same idea as REFERRAL_LINK_RESERVED_CHARS above, but for the "Includi contatti
# personali" checkbox and User.personal_contacts (a short signature block - name,
# phone, etc. - not a single URL). Mirrors PERSONAL_CONTACTS_RESERVED_CHARS in
# apps/dashboard/lib/validation/campaigns.ts - keep both in sync if either
# changes. Deliberately modest, same rationale as the referral link constant:
# a soft UI/generation-time guardrail, not the real safety check (that remains
# campaign_resolver.py's PLATFORM_TEXT_LIMITS check on the resolved text).
PERSONAL_CONTACTS_RESERVED_CHARS = 100

SYSTEM_PROMPT = """Sei un social media copywriter. Dato un argomento in italiano, scrivi contenuti pronti per essere pubblicati su più piattaforme social, nella stessa lingua della richiesta dell'utente.

Rispondi SOLO con un oggetto JSON con esattamente queste chiavi, tutte stringhe:
- default_text: testo generico di base (per piattaforme senza versione dedicata)
- instagram_text: caption per Instagram, con hashtag pertinenti
- facebook_text: post per Facebook, tono colloquiale
- linkedin_text: post per LinkedIn, tono professionale, senza emoji eccessive
- tiktok_text: didascalia breve e diretta per TikTok, con hashtag
- x_text: post per X/Twitter, ENTRO 280 caratteri totali inclusi eventuali hashtag - è un limite rigido, non superarlo mai
- threads_text: post per Threads, entro 500 caratteri
- youtube_title: titolo per un video YouTube, ENTRO 100 caratteri, senza hashtag
- youtube_description: descrizione per un video YouTube, con hashtag pertinenti

Rispetta questi target di lunghezza (caratteri) per ogni campo: {targets}

Scrivi contenuti concreti e specifici sull'argomento richiesto, non placeholder. Includi hashtag pertinenti dove indicato, senza esagerare (max 5-8)."""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    # Cut at the last whitespace before the limit rather than mid-word, when
    # there's a reasonable one to cut at; otherwise a hard slice.
    truncated = text[:limit]
    last_space = truncated.rfind(" ")
    if last_space > limit * 0.6:
        truncated = truncated[:last_space]
    return truncated.rstrip()


def generate_campaign_text(
    api_key: str,
    model: str,
    topic: str,
    include_referral_link: bool = False,
    include_personal_contacts: bool = False,
) -> Dict[str, str]:
    """
    Calls OpenAI's Chat Completions API to draft campaign copy for every
    platform-specific text field from a single topic description. Returns a
    dict with exactly the keys in FIELD_TARGETS, each truncated to HARD_LIMITS
    as a safety net regardless of what the model returned.

    include_referral_link / include_personal_contacts: pass the wizard's
    current checkbox state (not whether a link/contacts block exists on any
    specific user - the caller can't know which recipients will get one yet
    at generation time). When on, x_text/threads_text targets and hard limits
    shrink by the matching *_RESERVED_CHARS constant so the generated text
    already leaves room for it.
    """
    field_targets = dict(FIELD_TARGETS)
    hard_limits = dict(HARD_LIMITS)
    reserved_chars = 0
    if include_referral_link:
        reserved_chars += REFERRAL_LINK_RESERVED_CHARS
    if include_personal_contacts:
        reserved_chars += PERSONAL_CONTACTS_RESERVED_CHARS
    if reserved_chars:
        for field in ("x_text", "threads_text"):
            field_targets[field] = max(1, FIELD_TARGETS[field] - reserved_chars)
            hard_limits[field] = max(1, HARD_LIMITS[field] - reserved_chars)

    system_prompt = SYSTEM_PROMPT.format(
        targets=", ".join(f"{k}={v}" for k, v in field_targets.items())
    )
    if include_referral_link:
        system_prompt += (
            "\n\nA ogni testo generato verrà aggiunto automaticamente, dopo la tua risposta, un link "
            "personale in fondo (circa 60 caratteri in più) - i target sopra per x_text e threads_text "
            "sono già ridotti per lasciare spazio a questo link: non aggiungerlo tu stesso nel testo."
        )
    if include_personal_contacts:
        system_prompt += (
            "\n\nA ogni testo generato verrà anche aggiunto automaticamente, in fondo (dopo l'eventuale "
            "link sopra), un blocco di contatti personali (circa 100 caratteri in più) - i target sopra "
            "per x_text e threads_text sono già ridotti per lasciare spazio anche a questo: non "
            "aggiungerlo tu stesso nel testo."
        )

    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": topic},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.8,
                # Backstop against runaway output cost: the 9 fields combined rarely
                # exceed ~1000-1200 tokens even at their max length targets. This is
                # a pure text-completion call (chat/completions) - no image/video
                # generation endpoint is ever used by this integration.
                "max_tokens": 1500,
            },
            timeout=45.0,
        )
    except httpx.RequestError as e:
        raise OpenAIApiError(f"Errore di rete verso OpenAI: {str(e)}")

    if response.status_code != 200:
        # Never include the request body/headers in the error (would leak the key).
        raise OpenAIApiError(
            f"OpenAI ha risposto con errore ({response.status_code})",
            status_code=response.status_code,
        )

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise OpenAIApiError(f"Risposta OpenAI non valida: {str(e)}")

    result: Dict[str, str] = {}
    for field, limit in hard_limits.items():
        value = parsed.get(field)
        result[field] = _truncate(str(value).strip(), limit) if value else ""

    return result


# ==============================================================================
# Blog Writer AI - article generation and per-platform social adaptation
# ==============================================================================

def _chat_completion_json(api_key: str, model: str, system_prompt: str, user_content: str, max_tokens: int, temperature: float = 0.7) -> Dict[str, Any]:
    """Shared JSON-mode chat completion call used only by the Blog Writer functions below."""
    try:
        response = httpx.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=90.0,
        )
    except httpx.RequestError as e:
        raise OpenAIApiError(f"Errore di rete verso OpenAI: {str(e)}")

    if response.status_code != 200:
        raise OpenAIApiError(f"OpenAI ha risposto con errore ({response.status_code})", status_code=response.status_code)

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise OpenAIApiError(f"Risposta OpenAI non valida: {str(e)}")


# Approximate output budget per requested length - a full HTML article with
# headings/paragraphs/lists runs noticeably more tokens than the short social
# captions above, this is unavoidable given the ask (a real article, not a
# caption) but still capped so a single generation has a predictable cost.
ARTICLE_LENGTH_MAX_TOKENS: Dict[str, int] = {
    "short": 1800,     # ~400-600 words
    "medium": 3000,    # ~800-1200 words
    "long": 4500,       # ~1500-2000 words
}

BLOG_ARTICLE_SYSTEM_PROMPT = """Sei un copywriter professionista specializzato in articoli di blog SEO-friendly, naturali e leggibili - non un generatore di contenuti robotico.

Scrivi nella lingua richiesta dall'utente. Il contenuto deve essere concreto e specifico sull'argomento, mai generico o con informazioni inventate presentate come certe.

Struttura, quando appropriato: titolo efficace, introduzione, paragrafi ben organizzati con titoli H2 ed eventuali H3, elenchi puntati SOLO quando realmente utili (non abusarne), esempi/approfondimenti, conclusione, call to action finale, hashtag pertinenti in fondo.

Evita: testi ripetitivi, frasi generiche, keyword stuffing, titoli artificiali/clickbait, tono eccessivamente robotico, introduzioni inutilmente lunghe, uso eccessivo di elenchi puntati.

Rispondi SOLO con un oggetto JSON con esattamente queste chiavi:
- title: string, titolo efficace dell'articolo
- slug: string, slug URL-friendly (minuscolo, trattini, senza accenti/caratteri speciali)
- excerpt: string, riassunto breve (1-2 frasi)
- content: string, il corpo completo dell'articolo in HTML semantico (usa <h2>, <h3>, <p>, <ul>/<li> solo quando utile, <strong> per enfasi) - NON includere <html>/<body>/<title>, solo il markup del corpo
- hashtags: array di string, hashtag pertinenti (senza il simbolo #)
- keywords: array di string, parole chiave rilevanti individuate nel testo (oltre a quelle eventualmente fornite)
- meta_title: string, titolo SEO (max ~60 caratteri)
- meta_description: string, descrizione SEO (max ~155 caratteri)
- language: string, codice lingua usato (es. "it", "en")
- tone: string, il tono di voce effettivamente utilizzato"""


def generate_blog_article(api_key: str, model: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Drafts a full blog article as structured JSON from the "Nuovo articolo" form
    params (topic is the only required field, everything else has sensible
    defaults applied by the caller before this is invoked). Returns a dict with
    the 10 fields documented in BLOG_ARTICLE_SYSTEM_PROMPT - the caller is
    responsible for persisting it as a draft (this function never saves anything).
    """
    length = params.get("length", "medium")
    max_tokens = ARTICLE_LENGTH_MAX_TOKENS.get(length, ARTICLE_LENGTH_MAX_TOKENS["medium"])

    user_lines = [f"Argomento: {params['topic']}"]
    if params.get("description"):
        user_lines.append(f"Descrizione: {params['description']}")
    if params.get("goal"):
        user_lines.append(f"Obiettivo dell'articolo: {params['goal']}")
    if params.get("target_audience"):
        user_lines.append(f"Pubblico di riferimento: {params['target_audience']}")
    user_lines.append(f"Lingua: {params.get('language', 'it')}")
    user_lines.append(f"Tono di voce: {params.get('tone', 'professionale e naturale')}")
    user_lines.append(f"Lunghezza desiderata: {length}")
    if params.get("primary_keyword"):
        user_lines.append(f"Parola chiave principale: {params['primary_keyword']}")
    if params.get("secondary_keywords"):
        user_lines.append(f"Parole chiave secondarie: {', '.join(params['secondary_keywords'])}")
    if params.get("must_include"):
        user_lines.append(f"Informazioni da includere obbligatoriamente: {params['must_include']}")
    if params.get("must_avoid"):
        user_lines.append(f"Informazioni/argomenti da evitare: {params['must_avoid']}")
    if params.get("call_to_action"):
        user_lines.append(f"Call to action finale da usare: {params['call_to_action']}")
    hashtag_count = params.get("hashtag_count", 5)
    user_lines.append(f"Numero indicativo di hashtag: {hashtag_count}")

    parsed = _chat_completion_json(
        api_key, model, BLOG_ARTICLE_SYSTEM_PROMPT, "\n".join(user_lines), max_tokens, temperature=0.75
    )

    return {
        "title": str(parsed.get("title", "")).strip()[:255],
        "slug": str(parsed.get("slug", "")).strip()[:255],
        "excerpt": str(parsed.get("excerpt", "")).strip()[:1000],
        "content": str(parsed.get("content", "")).strip(),
        "hashtags": [str(h).strip() for h in parsed.get("hashtags", []) if str(h).strip()][:20],
        "keywords": [str(k).strip() for k in parsed.get("keywords", []) if str(k).strip()][:20],
        "meta_title": str(parsed.get("meta_title", "")).strip()[:255],
        "meta_description": str(parsed.get("meta_description", "")).strip()[:500],
        "language": str(parsed.get("language", params.get("language", "it"))).strip()[:10],
        "tone": str(parsed.get("tone", "")).strip()[:100],
    }


SOCIAL_ADAPTATION_SYSTEM_PROMPT = """Sei un social media copywriter. Ti viene fornito un articolo di blog (titolo, riassunto, testo) e un link pubblico all'articolo completo. Crea versioni sintetiche adatte a diverse piattaforme social che promuovono l'articolo, includendo sempre il link e una call to action tipo "Leggi l'articolo completo".

Non usare lo stesso testo identico per tutte le piattaforme: adatta tono e lunghezza.
- instagram_text: tono più emozionale, testo sintetico, invito a leggere l'articolo, hashtag pertinenti
- facebook_text: tono diretto e coinvolgente, riassunto leggibile, domanda o call to action, link
- linkedin_text: tono professionale, introduzione chiara, breve approfondimento, call to action, link, hashtag pertinenti
- x_text: testo breve, messaggio principale, link, pochi hashtag, ENTRO 280 caratteri totali - limite rigido
- threads_text: entro 500 caratteri
- default_text: versione generica per piattaforme senza testo dedicato

Rispondi SOLO con un oggetto JSON con queste chiavi, tutte stringhe: default_text, instagram_text, facebook_text, linkedin_text, x_text, threads_text."""


def adapt_article_for_platforms(api_key: str, model: str, title: str, excerpt: str, article_url: str) -> Dict[str, str]:
    """
    Turns a published article into per-platform social summaries for the
    "Usa per campagna social" flow - same HARD_LIMITS truncation backstop as
    generate_campaign_text (x=280/threads=500/others=5000), so the result can
    never fail campaign creation validation downstream.
    """
    user_content = f"Titolo: {title}\nRiassunto: {excerpt}\nLink articolo: {article_url}"
    parsed = _chat_completion_json(api_key, model, SOCIAL_ADAPTATION_SYSTEM_PROMPT, user_content, max_tokens=800, temperature=0.8)

    fields = ["default_text", "instagram_text", "facebook_text", "linkedin_text", "x_text", "threads_text"]
    result: Dict[str, str] = {}
    for field in fields:
        value = parsed.get(field)
        result[field] = _truncate(str(value).strip(), HARD_LIMITS.get(field, 5000)) if value else ""
    return result
