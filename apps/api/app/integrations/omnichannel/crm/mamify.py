"""
Client per le "API Mamify per il RAG" (CRM Mamify, sola lettura).

Documentazione di riferimento (2026-10-26):
  base URL  https://mamify.app/m/api/plugins/mamify/rag/
  auth      header X-Fw360-Key: <chiave>   (mai il token di un cliente)
  risposta  {"status":1,"data":{...}}  oppure  {"status":0,"error":"codice","message":"..."}
  429       limite della chiave, con Retry-After
  cliente   identificato da email | phone (ultime 10 cifre) | code | customer_id;
            piu' identificativi insieme devono indicare lo stesso cliente

Il client non decide niente sulla privacy: espone gli endpoint cosi' come
sono. Chi lo chiama (tools.py) e' responsabile di passare solo identificativi
fidati. Per questo i metodi customer_* prendono gli identificativi come
argomenti espliciti e non da un dizionario libero: un chiamante non puo'
"dimenticarsi" di controllare cosa ci finisce dentro.

La chiave non compare mai nei log ne' nei messaggi d'errore: MamifyError porta
solo codice e messaggio restituiti dal CRM.
"""
import re
from typing import Any, Dict, Optional

import httpx

DEFAULT_BASE_URL = "https://mamify.app/m/api/plugins/mamify/rag/"
_DEFAULT_TIMEOUT = 12.0

# Codici d'errore documentati che hanno un significato per noi.
ERR_WRONG_KEY = "wrong_api_key"
ERR_NO_PERMISSION = "insufficient_permissions"
ERR_IDENTIFIER_REQUIRED = "customer_identifier_required"
ERR_NOT_FOUND = "customer_not_found"
ERR_AMBIGUOUS = "customer_ambiguous"
ERR_RATE_LIMITED = "rate_limited"  # nostro: HTTP 429
ERR_UNAVAILABLE = "crm_unavailable"  # nostro: rete/timeout/risposta non JSON


class MamifyError(Exception):
    def __init__(self, code: str, message: str = "", status_code: Optional[int] = None, data: Optional[Dict[str, Any]] = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status_code = status_code
        # Per customer_ambiguous il CRM allega `candidates` (id, nome, email):
        # servono a contare, non vanno mai mostrati al cliente.
        self.data = data or {}


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """
    Da cio' che un canale ci da' (``+39 333 1234567``, ``393331234567@c.us``)
    alle sole cifre, come le vuole il CRM. None se non e' un numero personale:
    un JID di gruppo WhatsApp (``...@g.us``) non e' un cliente, e un numero
    sotto le 9 cifre non e' confrontabile (il CRM usa le ultime 10).
    """
    if not raw:
        return None
    value = raw.strip()
    if "@" in value:
        local, _, domain = value.partition("@")
        if domain.startswith("g.us") or domain.startswith("broadcast"):
            return None
        value = local
    digits = re.sub(r"\D", "", value)
    if len(digits) < 9:
        return None
    return digits


class MamifyRagClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: float = _DEFAULT_TIMEOUT):
        if not api_key:
            raise ValueError("Chiave API Mamify mancante")
        self._api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.timeout = timeout

    # ------------------------------------------------------------------ core
    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            response = httpx.get(
                self.base_url + endpoint,
                params=clean,
                headers={"X-Fw360-Key": self._api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise MamifyError(ERR_UNAVAILABLE, f"CRM non raggiungibile: {e.__class__.__name__}") from e

        if response.status_code == 429:
            retry = response.headers.get("Retry-After")
            raise MamifyError(ERR_RATE_LIMITED, f"Limite di richieste del CRM raggiunto (riprova tra {retry or 'qualche'} secondi)", 429)

        try:
            payload = response.json()
        except ValueError:
            raise MamifyError(ERR_UNAVAILABLE, f"Risposta del CRM non valida (HTTP {response.status_code})", response.status_code) from None

        if not isinstance(payload, dict):
            raise MamifyError(ERR_UNAVAILABLE, "Risposta del CRM non valida", response.status_code)

        if payload.get("status") == 1:
            data = payload.get("data")
            return data if isinstance(data, dict) else {"result": data}

        code = str(payload.get("error") or f"http_{response.status_code}")
        message = str(payload.get("message") or "")
        extra = {k: v for k, v in payload.items() if k not in ("status", "error", "message")}
        raise MamifyError(code, message, response.status_code, extra)

    @staticmethod
    def _ids(email: Optional[str], phone: Optional[str], code: Optional[str], customer_id: Optional[str]) -> Dict[str, Any]:
        ids = {"email": email, "phone": phone, "code": code, "customer_id": customer_id}
        ids = {k: v for k, v in ids.items() if v}
        if not ids:
            raise MamifyError(ERR_IDENTIFIER_REQUIRED, "Nessun identificativo del cliente")
        return ids

    # ----------------------------------------------------------- customer/*
    def find_customer(self, *, email: Optional[str] = None, phone: Optional[str] = None, code: Optional[str] = None, customer_id: Optional[str] = None) -> Dict[str, Any]:
        return self._get("customer/find", self._ids(email, phone, code, customer_id))

    def wallets(self, *, customer_id: str) -> Dict[str, Any]:
        return self._get("customer/wallets", {"customer_id": customer_id})

    def transactions(self, *, customer_id: str, wallet: str, app: Optional[str] = None, since: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._get("customer/transactions", {"customer_id": customer_id, "wallet": wallet, "app": app, "since": since, "page": page, "limit": limit})

    def orders(self, *, customer_id: str, order_id: Optional[str] = None, status: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._get("customer/orders", {"customer_id": customer_id, "order_id": order_id, "status": status, "page": page, "limit": limit})

    def network(self, *, customer_id: str, scope: Optional[str] = None, query: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._get("customer/network", {"customer_id": customer_id, "scope": scope, "query": query, "page": page, "limit": limit})

    # ------------------------------------------------------------ catalogo
    def search_products(self, *, query: Optional[str] = None, ids: Optional[str] = None, app: Optional[str] = None, type_: Optional[str] = None, only_available: Optional[bool] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._get("products/search", {
            "query": query, "id": ids, "app": app, "type": type_,
            "only_available": 1 if only_available else None, "page": page, "limit": limit,
        })

    def search_giftcards(self, *, app: Optional[str] = None, query: Optional[str] = None, ids: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        return self._get("giftcards/search", {"app": app, "query": query, "id": ids, "page": page, "limit": limit})

    # ------------------------------------------------------------- diagnosi
    def check_key(self) -> Dict[str, str]:
        """
        Verifica la chiave senza leggere dati di nessuno: ``customer/find``
        senza identificativi. Una chiave buona e abilitata risponde
        ``customer_identifier_required`` (ha superato autenticazione e
        permessi, si e' fermata sui parametri); ``wrong_api_key`` e
        ``insufficient_permissions`` dicono esattamente cosa sistemare.
        """
        try:
            self._get("customer/find", {})
        except MamifyError as e:
            if e.code == ERR_IDENTIFIER_REQUIRED:
                return {"status": "ok", "message": "Chiave valida e abilitata agli endpoint cliente."}
            if e.code == ERR_WRONG_KEY:
                return {"status": "invalid", "message": "Chiave rifiutata dal CRM: controlla di averla copiata per intero."}
            if e.code == ERR_NO_PERMISSION:
                return {"status": "no_permission", "message": "Chiave valida ma senza il permesso sugli endpoint 'customer': spunta il gruppo Plugins > Mamify > Rag sulla chiave."}
            if e.code in (ERR_RATE_LIMITED, ERR_UNAVAILABLE):
                return {"status": "unavailable", "message": e.message}
            return {"status": "error", "message": f"Il CRM ha risposto {e.code}: {e.message}".strip()}
        # Un 200 senza identificativi non e' previsto dalla documentazione, ma
        # vuol comunque dire che la chiave e' accettata.
        return {"status": "ok", "message": "Chiave accettata dal CRM."}
