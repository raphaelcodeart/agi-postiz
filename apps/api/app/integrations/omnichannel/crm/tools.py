"""
Il CRM Mamify come strumenti dell'AI, con la privacy decisa qui e non dal modello.

Regola unica: **il cliente puo' chiedere solo di se stesso**, e "se stesso" lo
stabiliamo noi, non lui. L'AI riceve strumenti (function calling OpenAI) che
non accettano alcun identificativo del cliente: il backend inietta il
``customer_id`` risolto prima della generazione, e scarta qualunque email,
telefono, codice o id che il modello provi a passare. Cosi' "dammi il saldo di
mario.rossi@..." scritto in chat non puo' diventare una ricerca su Mario Rossi:
lo strumento cerca comunque, e soltanto, il cliente che sta scrivendo.

Da dove viene l'identita' fidata (``trusted_identity``), in ordine:
1. il numero del mittente su un canale WhatsApp (Cloud API: ``external_user_id``
   e' il numero; Maytapi: e' il JID ``39333...@c.us``). E' il canale a
   garantirlo, non il cliente;
2. telefono o email scritti dall'operatore nella scheda cliente
   (``omni_customers.phone/email``): e' un umano che ha verificato chi e' -
   e' l'unico modo per far funzionare il CRM su Telegram/Instagram/Facebook,
   dove il canale non ci da' un numero.
Mai, in nessun caso, un dato scritto dal cliente nel messaggio.

Caso ambiguo (stesso numero su due account): il modello puo' chiedere l'email
e usare ``confirm_identity_by_email``, che la passa al CRM **insieme** al
telefono fidato. Il CRM accetta solo se entrambi indicano lo stesso cliente:
l'email restringe, non sostituisce. Senza telefono fidato lo strumento non
esiste.

Cliente non trovato o canale senza identita': niente strumenti ``customer/*``.
Restano prodotti e gift card, che sono catalogo pubblico e non dicono niente
di nessuno.

Ogni chiamata eseguita finisce in ``CrmContext.lookups`` (nome, esito, nessun
dato) e da li' nell'audit della bozza: si puo' sempre ricostruire cosa l'AI
ha consultato per rispondere.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.integrations.omnichannel.crm.mamify import (
    ERR_AMBIGUOUS,
    ERR_NO_PERMISSION,
    ERR_NOT_FOUND,
    ERR_RATE_LIMITED,
    ERR_UNAVAILABLE,
    ERR_WRONG_KEY,
    MamifyError,
    MamifyRagClient,
    normalize_phone,
)

# Canali in cui external_user_id e' il numero di telefono del mittente.
PHONE_CHANNELS = ("whatsapp", "whatsapp_maytapi")

# Il modello non deve poter chiedere pagine intere di storico: bastano gli
# ultimi movimenti/ordini per rispondere in chat, e il resto costa token.
_MAX_TRANSACTIONS = 10
_MAX_ORDERS = 5
_MAX_NETWORK = 15
_MAX_CATALOG = 5
# Oltre questa misura il risultato viene troncato: una risposta WhatsApp non
# ha bisogno di piu', e un ordine con lo storico completo puo' essere lungo.
_MAX_TOOL_OUTPUT_CHARS = 4000

# Identificativi che il modello potrebbe provare a passare: vengono sempre
# ignorati, il cliente e' quello risolto dal backend.
_FORBIDDEN_ARGS = {"email", "phone", "code", "customer_id", "id", "customer"}


@dataclass
class TrustedIdentity:
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str = "channel"  # channel | operator

    def as_params(self) -> Dict[str, str]:
        params = {}
        if self.phone:
            params["phone"] = self.phone
        if self.email:
            params["email"] = self.email
        return params


@dataclass
class CrmContext:
    """
    status:
      identified  - un solo cliente CRM: strumenti customer/* attivi
      ambiguous   - piu' clienti con quel numero: solo confirm_identity_by_email
      not_found   - identita' fidata ma nessuna anagrafica
      unverified  - nessuna identita' fidata su questo canale
      unavailable - CRM non raggiungibile / chiave rifiutata (si risponde senza)
    """
    status: str
    identity: Optional[TrustedIdentity] = None
    customer_id: Optional[str] = None
    customer: Optional[Dict[str, Any]] = None
    candidates_count: int = 0
    error: Optional[str] = None
    lookups: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def customer_tools_enabled(self) -> bool:
        return self.status == "identified" and bool(self.customer_id)

    def summary(self) -> Dict[str, Any]:
        """Per l'audit della bozza: cosa sapevamo e cosa abbiamo consultato, nessun dato personale."""
        return {
            "status": self.status,
            "identity_source": self.identity.source if self.identity else None,
            "customer_id": self.customer_id,
            "candidates": self.candidates_count or None,
            "error": self.error,
            "lookups": self.lookups,
        }


# ------------------------------------------------------------------ identita'
def trusted_identity_for_customer(customer, preferred_channel: Optional[str] = None) -> Optional[TrustedIdentity]:
    """
    L'identita' fidata di un omni_customer. ``preferred_channel`` e' il canale
    della conversazione in corso: se e' WhatsApp si usa quel numero; altrimenti
    va bene un'altra identita' WhatsApp della stessa persona, e in ultimo cio'
    che l'operatore ha scritto nella scheda.
    """
    identities = list(getattr(customer, "identities", None) or [])
    ordered = sorted(identities, key=lambda i: 0 if i.channel == preferred_channel else 1)
    for identity in ordered:
        if identity.channel in PHONE_CHANNELS:
            phone = normalize_phone(identity.external_user_id)
            if phone:
                return TrustedIdentity(phone=phone, source="channel")

    phone = normalize_phone(getattr(customer, "phone", None))
    email = (getattr(customer, "email", None) or "").strip().lower() or None
    if phone or email:
        return TrustedIdentity(phone=phone, email=email, source="operator")
    return None


def _compact_customer(data: Dict[str, Any]) -> Dict[str, Any]:
    """Il blocco `customer` di customer/find, con i soli campi utili al prompt."""
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else data
    keep = {}
    for key in ("id", "customer_id", "first_name", "last_name", "name", "email", "phone", "code", "invite_code", "registered_at", "created_at", "last_login", "last_access", "login_enabled", "access_enabled"):
        if key in customer:
            keep[key] = customer[key]
    network = data.get("network")
    if isinstance(network, dict):
        keep["network"] = {k: network.get(k) for k in ("direct", "total") if k in network}
    sponsor = data.get("sponsor")
    if isinstance(sponsor, dict):
        keep["sponsor"] = {k: sponsor.get(k) for k in ("first_name", "last_name", "name") if k in sponsor}
    return keep


def _customer_id_from(data: Dict[str, Any]) -> Optional[str]:
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else data
    for key in ("id", "customer_id"):
        if customer.get(key) is not None:
            return str(customer[key])
    return None


def resolve_customer(client: MamifyRagClient, identity: Optional[TrustedIdentity]) -> CrmContext:
    """Una chiamata a customer/find con i soli identificativi fidati."""
    if identity is None or not identity.as_params():
        return CrmContext(status="unverified")
    ctx = CrmContext(status="unverified", identity=identity)
    try:
        data = client.find_customer(**identity.as_params())
    except MamifyError as e:
        ctx.lookups.append({"tool": "customer/find", "ok": False, "error": e.code})
        if e.code == ERR_NOT_FOUND:
            ctx.status = "not_found"
        elif e.code == ERR_AMBIGUOUS:
            ctx.status = "ambiguous"
            candidates = e.data.get("candidates") if isinstance(e.data, dict) else None
            ctx.candidates_count = len(candidates) if isinstance(candidates, list) else 2
        else:
            ctx.status = "unavailable"
            ctx.error = e.code
        return ctx

    ctx.lookups.append({"tool": "customer/find", "ok": True})
    ctx.customer_id = _customer_id_from(data)
    ctx.customer = _compact_customer(data)
    ctx.status = "identified" if ctx.customer_id else "unavailable"
    if not ctx.customer_id:
        ctx.error = "customer_id_missing"
    return ctx


# --------------------------------------------------------------------- prompt
def system_prompt_section(ctx: CrmContext) -> str:
    """Cosa dire al modello sul cliente e su cosa puo' (non) fare con il CRM."""
    common = (
        "Hai accesso al CRM Mamify tramite strumenti. REGOLE DI PRIVACY, senza eccezioni: "
        "gli strumenti restituiscono SOLO i dati del cliente che sta scrivendo, identificato dal sistema e non da cio' che scrive. "
        "Se chiede informazioni su un'altra persona (anche un familiare, anche dandoti nome, email o telefono), rifiuta con garbo e spiega "
        "che ogni cliente puo' consultare solo il proprio account. Non ripetere mai nel messaggio identificativi completi (email, telefono, id). "
        "Riporta i dati del CRM cosi' come sono, senza arrotondare o inventare: se uno strumento non trova qualcosa o da' errore, dillo e proponi che un collega verifichi."
    )
    if ctx.status == "identified":
        who = ctx.customer or {}
        name = " ".join(str(who.get(k)) for k in ("first_name", "last_name") if who.get(k)).strip() or who.get("name")
        intro = "Il cliente e' stato identificato nel CRM" + (f" come {name}" if name else "") + ". "
        intro += "Puoi consultare i suoi saldi (Mamix e MamiCash), movimenti, ordini e la sua rete di invitati con gli strumenti; "
        intro += "usali quando la domanda lo richiede, non per riempire la risposta di numeri non richiesti. Per la rete, cita nomi e conteggi, mai contatti altrui."
        if who.get("network"):
            intro += f" Rete: {json.dumps(who['network'], ensure_ascii=False)}."
        return common + "\n" + intro
    if ctx.status == "ambiguous":
        return common + (
            "\nIl numero del cliente corrisponde a PIU' account nel CRM, quindi per ora non puoi consultare i suoi dati. "
            "Se chiede qualcosa sul suo account, spiegagli con naturalezza che risultano piu' profili con il suo numero e chiedigli l'email con cui si e' registrato; "
            "quando te la da', usa lo strumento confirm_identity_by_email. Se l'email non corrisponde, dillo e proponi che un collega lo ricontatti."
        )
    if ctx.status == "not_found":
        return common + (
            "\nIl numero da cui scrive il cliente non risulta associato a nessun account Mamify, quindi NON puoi fornire dati di account (saldi, ordini, rete). "
            "Se li chiede, spiega che il suo numero non e' collegato a un profilo e invitalo a verificare il numero registrato nell'app o a scrivere dall'indirizzo email dell'account; "
            "un collega potra' aiutarlo. Puoi comunque rispondere su prodotti e gift card."
        )
    if ctx.status == "unavailable":
        return common + (
            "\nIn questo momento il CRM non e' raggiungibile: non puoi verificare dati di account. Se il cliente li chiede, dillo e proponi che un collega lo ricontatti con le informazioni."
        )
    return common + (
        "\nSu questo canale non e' possibile verificare l'identita' del cliente, quindi NON fornire dati di account (saldi, ordini, movimenti, rete), "
        "anche se il cliente ti da' email o telefono: invitalo a scrivere su WhatsApp dal numero registrato nell'app. "
        "Puoi rispondere liberamente su prodotti e gift card."
    )


# --------------------------------------------------------------------- tools
def _tool(name: str, description: str, properties: Optional[Dict[str, Any]] = None, required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False},
        },
    }


def tool_definitions(ctx: CrmContext) -> List[Dict[str, Any]]:
    """Gli strumenti disponibili ORA: cambiano se confirm_identity_by_email riesce, quindi vanno ricalcolati a ogni giro."""
    tools: List[Dict[str, Any]] = [
        _tool(
            "search_products",
            "Cerca prodotti e servizi pubblicati nel catalogo Mamify: prezzo, promozioni, disponibilita', quanto si puo' pagare in MamiCash, cashback e commissioni Mamix. Non riguarda nessun cliente in particolare.",
            {
                "query": {"type": "string", "description": "Testo da cercare nel nome/descrizione"},
                "app": {"type": "string", "description": "Codice app per limitare a un negozio (es. energify)"},
                "type": {"type": "string", "enum": ["product", "service"], "description": "product = beni spediti, service = digitali e affiliazioni"},
                "only_available": {"type": "boolean", "description": "Solo prodotti disponibili"},
            },
        ),
        _tool(
            "search_giftcards",
            "Cerca le gift card acquistabili in app (MamiCash o Mamix): tagli, quota pagabile in MamiCash, tempi di consegna, dove trovarle in app.",
            {
                "query": {"type": "string", "description": "Nome o parte del nome della gift card"},
                "app": {"type": "string", "enum": ["mamicash", "mamix"], "description": "Catalogo: mamicash (default) o mamix"},
            },
        ),
    ]

    if ctx.status == "ambiguous" and ctx.identity and ctx.identity.phone:
        tools.append(_tool(
            "confirm_identity_by_email",
            "Da usare SOLO dopo che il cliente ti ha dato l'email con cui e' registrato: la confronta con il numero da cui scrive per capire quale dei suoi account intende. Non cerca altre persone.",
            {"email": {"type": "string", "description": "L'email che il cliente ha scritto"}},
            ["email"],
        ))

    if ctx.customer_tools_enabled:
        tools.extend([
            _tool(
                "get_my_wallets",
                "Saldi attuali del cliente che sta scrivendo: Mamix e MamiCash (con MamiCash diviso in personale e aziendale).",
            ),
            _tool(
                "get_my_transactions",
                "Ultimi movimenti del cliente che sta scrivendo su un portafoglio, dal piu' recente.",
                {
                    "wallet": {"type": "string", "enum": ["mamix", "mamicash"], "description": "Portafoglio"},
                    "app": {"type": "string", "description": "Codice app per filtrare (es. energify)"},
                    "since": {"type": "string", "description": "Solo movimenti da questa data, formato YYYY-MM-DD"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_TRANSACTIONS, "description": f"Quanti movimenti (max {_MAX_TRANSACTIONS})"},
                },
                ["wallet"],
            ),
            _tool(
                "get_my_orders",
                "Ordini del cliente che sta scrivendo: stato con data, totale, prodotti, pagamento, storico degli stati; per le gift card anche emissione e consegna prevista. Per i prodotti fisici non esiste una data di consegna prevista: comunica lo stato con la sua data.",
                {
                    "order_id": {"type": "string", "description": "Un ordine preciso, se il cliente ne cita il numero"},
                    "status": {"type": "string", "enum": ["open", "paid", "unpaid"], "description": "open = non ancora chiusi; omesso = tutti"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_ORDERS, "description": f"Quanti ordini (max {_MAX_ORDERS})"},
                },
            ),
            _tool(
                "get_my_network",
                "Le persone invitate dal cliente che sta scrivendo (la sua rete, come in 'La tua rete' nell'app): nomi, data di iscrizione, livello e quanti ne hanno invitati a loro volta. Non restituisce contatti altrui.",
                {
                    "scope": {"type": "string", "enum": ["direct", "all"], "description": "direct = solo invitati diretti (default), all = tutta la rete"},
                    "query": {"type": "string", "description": "Cerca un nome specifico nella rete"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_NETWORK, "description": f"Quante persone (max {_MAX_NETWORK})"},
                },
            ),
        ])
    return tools


def _clamp(value: Any, maximum: int) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(number, maximum))


def _strip_contacts(data: Any) -> Any:
    """Toglie email/telefono dalle persone della rete: sono di terzi, e una chat non e' l'app."""
    if isinstance(data, list):
        return [_strip_contacts(item) for item in data]
    if isinstance(data, dict):
        return {k: _strip_contacts(v) for k, v in data.items() if k not in ("email", "phone", "mobile", "telephone")}
    return data


def _serialize(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > _MAX_TOOL_OUTPUT_CHARS:
        text = text[:_MAX_TOOL_OUTPUT_CHARS] + '... [risultato troncato: chiedi al cliente di restringere la richiesta]'
    return text


def execute_tool(client: MamifyRagClient, ctx: CrmContext, name: str, args: Optional[Dict[str, Any]]) -> str:
    """
    Esegue uno strumento e torna una stringa per il modello. Non alza mai:
    un errore del CRM e' un'informazione da dare al modello ("non trovato",
    "non disponibile"), non un motivo per far fallire la bozza.
    """
    record: Dict[str, Any] = {"tool": name, "ok": False}
    ctx.lookups.append(record)
    # L'unico strumento a cui e' concesso un identificativo e' la conferma via
    # email, e solo perche' lo passa al CRM insieme al telefono fidato.
    if name == "confirm_identity_by_email":
        return _confirm_identity(client, ctx, (args or {}).get("email"), record)
    args = {k: v for k, v in (args or {}).items() if k not in _FORBIDDEN_ARGS}

    try:
        if name == "search_products":
            data = client.search_products(
                query=args.get("query"), app=args.get("app"), type_=args.get("type"),
                only_available=bool(args.get("only_available")), limit=_MAX_CATALOG,
            )
        elif name == "search_giftcards":
            data = client.search_giftcards(query=args.get("query"), app=args.get("app"), limit=_MAX_CATALOG)
        elif not ctx.customer_tools_enabled:
            record["error"] = "not_identified"
            return json.dumps({"error": "not_identified", "message": "Il cliente non e' identificato: non puoi consultare dati di account."})
        elif name == "get_my_wallets":
            data = client.wallets(customer_id=ctx.customer_id)
        elif name == "get_my_transactions":
            wallet = args.get("wallet")
            if wallet not in ("mamix", "mamicash"):
                record["error"] = "invalid_wallet"
                return json.dumps({"error": "invalid_wallet", "message": "wallet deve essere mamix o mamicash"})
            data = client.transactions(
                customer_id=ctx.customer_id, wallet=wallet, app=args.get("app"), since=args.get("since"),
                limit=_clamp(args.get("limit"), _MAX_TRANSACTIONS) or _MAX_TRANSACTIONS,
            )
        elif name == "get_my_orders":
            status = args.get("status")
            data = client.orders(
                customer_id=ctx.customer_id, order_id=args.get("order_id"),
                status=status if status in ("open", "paid", "unpaid") else None,
                limit=_clamp(args.get("limit"), _MAX_ORDERS) or _MAX_ORDERS,
            )
        elif name == "get_my_network":
            scope = args.get("scope")
            data = _strip_contacts(client.network(
                customer_id=ctx.customer_id, scope=scope if scope in ("direct", "all") else None,
                query=args.get("query"), limit=_clamp(args.get("limit"), _MAX_NETWORK) or _MAX_NETWORK,
            ))
        else:
            record["error"] = "unknown_tool"
            return json.dumps({"error": "unknown_tool", "message": f"Strumento sconosciuto: {name}"})
    except MamifyError as e:
        record["error"] = e.code
        return json.dumps({"error": e.code, "message": _message_for_model(e)}, ensure_ascii=False)

    record["ok"] = True
    return _serialize(data)


def _message_for_model(e: MamifyError) -> str:
    if e.code in (ERR_RATE_LIMITED, ERR_UNAVAILABLE):
        return "Il CRM non e' disponibile al momento: di' al cliente che un collega verifichera' e lo ricontattera'."
    if e.code in (ERR_WRONG_KEY, ERR_NO_PERMISSION):
        return "Accesso al CRM non autorizzato per questa operazione: non puoi fornire questo dato, proponi che un collega verifichi."
    if e.code == "order_not_found":
        return "Nessun ordine con quel numero risulta su questo account."
    return e.message or e.code


def _confirm_identity(client: MamifyRagClient, ctx: CrmContext, email: Optional[str], record: Dict[str, Any]) -> str:
    phone = ctx.identity.phone if ctx.identity else None
    if ctx.status != "ambiguous" or not phone:
        record["error"] = "not_applicable"
        return json.dumps({"error": "not_applicable", "message": "La conferma via email non e' prevista in questa situazione."})
    email = (email or "").strip().lower()
    if "@" not in email:
        record["error"] = "invalid_email"
        return json.dumps({"error": "invalid_email", "message": "Serve un indirizzo email valido scritto dal cliente."})
    try:
        # Telefono fidato + email del cliente: il CRM accetta solo se indicano
        # la stessa anagrafica, quindi l'email non puo' aprire l'account di
        # un'altra persona.
        data = client.find_customer(phone=phone, email=email)
    except MamifyError as e:
        record["error"] = e.code
        if e.code in (ERR_NOT_FOUND, ERR_AMBIGUOUS):
            return json.dumps({"error": e.code, "message": "L'email indicata non corrisponde a un account con il numero da cui scrive il cliente."})
        return json.dumps({"error": e.code, "message": _message_for_model(e)}, ensure_ascii=False)

    customer_id = _customer_id_from(data)
    if not customer_id:
        record["error"] = "customer_id_missing"
        return json.dumps({"error": "customer_id_missing", "message": "Il CRM non ha restituito un identificativo utilizzabile."})
    ctx.customer_id = customer_id
    ctx.customer = _compact_customer(data)
    ctx.status = "identified"
    record["ok"] = True
    who = ctx.customer
    name = " ".join(str(who.get(k)) for k in ("first_name", "last_name") if who.get(k)).strip() or who.get("name") or "il cliente"
    return json.dumps({"ok": True, "message": f"Identita' confermata: {name}. Ora puoi usare gli strumenti get_my_*."}, ensure_ascii=False)


# ------------------------------------------------------------------ factory
ToolExecutor = Callable[[str, Dict[str, Any]], str]


def resolve_api_key(agent_config) -> Optional[str]:
    """La chiave salvata dalla pagina AI Agent, oppure MAMIFY_RAG_API_KEY dell'ambiente."""
    from app.core.config import settings
    from app.core.security import EncryptionService

    encrypted = getattr(agent_config, "crm_api_key_encrypted", None) if agent_config else None
    if encrypted:
        try:
            key = EncryptionService.decrypt(encrypted)
        except Exception:  # chiave di cifratura cambiata: come se non ci fosse
            key = None
        if key:
            return key
    return settings.MAMIFY_RAG_API_KEY or None


def client_for(agent_config) -> Optional[MamifyRagClient]:
    """Il client CRM per questo agente, o None se l'integrazione e' spenta o senza chiave."""
    if not agent_config or not getattr(agent_config, "crm_enabled", False):
        return None
    api_key = resolve_api_key(agent_config)
    if not api_key:
        return None
    return MamifyRagClient(api_key, getattr(agent_config, "crm_base_url", None) or None)


def prepare(client: Optional[MamifyRagClient], customer, channel: Optional[str]) -> Optional[CrmContext]:
    """Identita' fidata + customer/find. None se l'integrazione non e' configurata."""
    if client is None:
        return None
    identity = trusted_identity_for_customer(customer, channel) if customer is not None else None
    return resolve_customer(client, identity)
