# Omnichannel Responder

Modulo separato e indipendente: inbox unificata multicanale (Telegram, WhatsApp — Cloud API di Meta, numero personale via Maytapi, oppure numero personale sul gateway **myAGI** in casa —, Instagram, Facebook, Gmail) con proposte di risposta generate dall'AI. Per **default** ogni bozza resta "da approvare" finché un operatore non la invia manualmente; l'amministratore può attivare esplicitamente l'**autorisponditore automatico** (AUTO_REPLY, vedi §5) dalla pagina AI Agent — con un interruttore ben visibile e una conferma esplicita prima di accenderlo — nel qual caso l'AI invia le risposte da sola. In entrambi i casi, gli argomenti sensibili (rimborso, legale, medico...) richiedono **sempre** revisione umana esplicita, senza eccezioni: questa è l'unica regola che nessuna impostazione può disattivare. Non modifica né duplica alcuna tabella/funzionalità esistente: l'unico collegamento con il resto della piattaforma è `owner_id` (FK verso `administrators.id`, la stessa identità che fa login nella dashboard). Per lo schema dati generale vedi [DATABASE.md](./DATABASE.md); per il resto delle funzionalità della piattaforma vedi [FUNCTIONALITY.md](./FUNCTIONALITY.md).

Questo file è scritto per essere sufficiente, da solo, a ricostruire il modulo identico su un altro server (schema dati, endpoint, decisioni architetturali e i loro perché) senza dover rileggere il codice riga per riga.

---

## Indice

1. [Architettura in breve](#1-architettura-in-breve)
2. [Perché `owner_id` e non `tenant_id`](#2-perché-owner_id-e-non-tenant_id)
3. [Schema database](#3-schema-database)
4. [Connector layer](#4-connector-layer)
5. [Flusso messaggio → bozza AI → approvazione → invio](#5-flusso-messaggio--bozza-ai--approvazione--invio)
6. [Pipeline AI](#6-pipeline-ai)
6-bis. [CRM Mamify: dati del cliente nelle risposte](#6-bis-crm-mamify-dati-del-cliente-nelle-risposte)
7. [Sicurezza contro invii duplicati e fuori ordine](#7-sicurezza-contro-invii-duplicati-e-fuori-ordine)
8. [Webhook e strumento di simulazione](#8-webhook-e-strumento-di-simulazione)
9. [API REST](#9-api-rest)
10. [Frontend](#10-frontend)
11. [Configurazione e come collegare Telegram](#11-configurazione-e-come-collegare-telegram)
12. [Sicurezza](#12-sicurezza)
13. [Limiti noti di questa v1](#13-limiti-noti-di-questa-v1)

---

## 1. Architettura in breve

```
Dashboard: /omnichannel-responder                (inbox a 3 colonne: conversazioni | chat + bozza AI | scheda cliente)
           /omnichannel-responder/channels        (canali collegati, registrazione webhook, simulazione messaggi)
           /omnichannel-responder/settings         (configurazione AI Agent)
           /omnichannel-responder/knowledge-base    (documenti/FAQ usati dall'AI)

Backend:   /api/v1/omnichannel-responder/...       (CRUD + workflow, autenticato, vedi §9)
           /api/v1/omnichannel-responder/webhooks/telegram/{channel_account_id}  (pubblico, non autenticato)
           /api/v1/omnichannel-responder/dev/simulate-message  (autenticato, solo su canali 'mock')

Backend - moduli nuovi:
  app/models/omnichannel.py                        (15 tabelle, vedi §3)
  app/schemas/schemas.py                            (sezione "Omnichannel Responder" in fondo al file, non tocca le sezioni esistenti)
  app/integrations/omnichannel/connectors/          (interfaccia Connector + implementazioni, vedi §4)
  app/integrations/omnichannel/ai.py                 (context builder + generazione + loop function calling, vedi §6)
  app/integrations/omnichannel/crm/                   (CRM Mamify: client API + strumenti con regole di privacy, vedi §6-bis)
  app/integrations/myagi/                             (gateway WhatsApp in casa: client WAHA, vedi §4 MyAgiWhatsAppConnector e §11)
  app/api/v1/myagi.py                                 (pagina myAGI: sessioni, QR, stato - router /api/v1/myagi)
  app/services/omnichannel_service.py                (ingest messaggi, customer/conversation resolution, note/tag/notifiche)
  app/services/omnichannel_draft_service.py           (workflow bozza AI: genera/modifica/rigenera/approva-e-invia/scarta)
  app/tasks/omnichannel.py                            (task Celery: generazione bozza AI in background)
  app/api/v1/omnichannel.py                           (router principale, autenticato)
  app/api/v1/omnichannel_webhooks.py                  (router webhook, pubblico + dev tool)
  apps/api/alembic/versions/a1b2c3d4e5f6_...py         (unica migration che crea tutte le 15 tabelle)
```

File esistenti toccati, e solo in modo **additivo** (righe aggiunte, nessuna riga esistente modificata o rimossa):

| File | Aggiunta |
|---|---|
| `app/db/base.py` | import dei nuovi modelli, necessario perché Alembic li veda |
| `app/main.py` | due `app.include_router(...)` per i due nuovi router |
| `app/workers/celery_app.py` | `"app.tasks.omnichannel"` aggiunto a `celery.conf.imports` |
| `app/schemas/schemas.py` | nuova sezione in fondo al file (banner `# Omnichannel Responder`) |
| `apps/dashboard/lib/navigation.ts` | nuovo gruppo di voci menu "Omnichannel Responder" (era già presente un placeholder da una richiesta precedente, ora sostituito con le voci reali) |
| `apps/dashboard/components/navigation/app-sidebar.tsx` | rendering del nuovo gruppo |
| `apps/dashboard/components/shared/status-badge.tsx` | nuove voci nelle mappe di tono/etichetta per gli stati di conversazione (`new`, `ai_processing`, `waiting_approval`, `waiting_customer`, `resolved`, `spam`) — stesso pattern già usato da ogni altro modulo in questo file |
| `apps/dashboard/types/api.ts`, `lib/query/keys.ts` | nuove interfacce/query key, in fondo ai rispettivi file |

Un solo servizio Docker in più, e facoltativo: `myagi_wa` (gateway WhatsApp WAHA, §4/§11), con il suo volume `myagi_sessions_prod`. Per il resto il modulo riusa `db` (Postgres), `redis`, `worker`/`beat` (Celery) già esistenti — nessuna modifica a `docker-compose.yml` / `docker-compose.prod.yml` / `infrastructure/nginx/nginx.conf` necessaria (il webhook pubblico vive sotto `/api/v1/...`, già proxato interamente da Nginx verso `api:8000`).

---

## 2. Perché `owner_id` e non `tenant_id`

Il resto della piattaforma ha un solo tipo di identità che fa login: `Administrator` (vedi [DATABASE.md §3](./DATABASE.md#3-amministrazione)). La tabella `users` esistente rappresenta invece i **clienti gestiti** dall'amministratore (per le campagne social) — un concetto diverso da "un contatto che scrive su WhatsApp/Telegram", quindi non viene riusata qui.

Ogni singola tabella di questo modulo (comprese le tabelle ponte many-to-many) ha una colonna `owner_id` (FK → `administrators.id`, `ondelete="CASCADE"`, indicizzata) che identifica **l'amministratore proprietario di quel dato** — denormalizzata apposta su ogni riga, non solo raggiungibile tramite una join, così che:

- ogni query può filtrare `WHERE owner_id = :admin_id` direttamente, senza join;
- se in futuro questo sistema diventasse multi-amministratore (più persone che usano la stessa installazione, ognuna con i propri canali/conversazioni), l'isolamento dei dati è già garantito da questa singola colonna, ripetuta ovunque — non serve reingegnerizzare nulla.

Oggi, con un solo amministratore che fa login, `owner_id` coincide semplicemente con "l'admin loggato" su ogni endpoint (`admin.id` da `get_current_admin`, vedi [DATABASE.md §3](./DATABASE.md#3-amministrazione)).

---

## 3. Schema database

Migration iniziale: `a1b2c3d4e5f6_add_omnichannel_responder_module.py` (down_revision `f977e27daa7d`, l'ultima migration esistente al momento della creazione del modulo). Crea 15 tabelle, tutte prefissate `omni_`, nessuna modifica a tabelle esistenti. Le migration successive del modulo sono `b7e2d91c4a18` (Knowledge Base ibrida: `heading`, `embedding`, `embedding_model`, `embedded_at` e indici GIN full-text su `omni_knowledge_chunks`; `kind`, `always_on`, `file_name`, `chunk_count`, `error_message` su `omni_knowledge_documents`), `c5a83f0e9d21` (tabella `omni_knowledge_companies` e `omni_knowledge_documents.company_id`: oggi le tabelle `omni_*` sono 16), `e6b1d4f8a2c7`, `f2c7a9e3d4b1` e `a7d3c9e1f5b2` (CRM Mamify). Lo snapshot leggibile dell'intero schema è in [schema.sql](./schema.sql), rigenerato il 2026-10-31 alla revisione `a7d3c9e1f5b2`. Tutte le PK sono UUID (`uuid.uuid4()` lato Python), stesso stile di ogni altro modello del progetto.

### `omni_channel_accounts`
Un account/canale collegato (bot Telegram, futuro numero WhatsApp Business, pagina Instagram/Facebook...).

**Bug reale corretto il 2026-08-15**: `DELETE /channel-accounts/{id}` falliva con `500 Internal Server Error` ogni volta che il canale aveva almeno una conversazione collegata — funzionava solo dopo aver cancellato a mano tutte le conversazioni di quel canale. Causa: la relazione `OmniChannelAccount.conversations` (in `models/omnichannel.py`) non aveva `passive_deletes=True` — comportamento di default di SQLAlchemy quando cancelli il genitore: prova a impostare a `NULL` la colonna `channel_account_id` di ogni conversazione collegata *prima* di procedere, invece di lasciar fare al database. Ma quella colonna è `NOT NULL`, quindi l'operazione falliva con un `IntegrityError` mai gestito. Il vincolo `ON DELETE CASCADE` a livello di database (verificato via `pg_constraint`) c'era già ed era corretto — bastava dire a SQLAlchemy di fidarsene invece di gestire la cosa lui stesso in Python. Stesso bug latente corretto anche su `OmniCustomer.conversations` (mai riscontrato perché oggi non esiste un endpoint per cancellare un cliente, ma la stessa causa ci sarebbe stata). L'endpoint ha anche un backstop difensivo (`try/except IntegrityError` → `409` invece di `500`) per qualunque vincolo imprevisto futuro, ma non è quello il fix reale.

| Colonna | Tipo | Note |
|---|---|---|
| `channel` | string | `telegram`, `whatsapp`, `instagram`, `facebook`, `mock` |
| `status` | string | `pending`, `connected`, `error`, `disabled`. `disabled` non era mai impostato né controllato da nessuna parte fino al 2026-08-15 (valore "morto", documentato ma inutilizzato) — ora è il vero interruttore on/off della pagina Canali (`POST /channel-accounts/{id}/toggle`, `OmnichannelService.toggle_channel_account_status`): `omnichannel_webhooks.py` verifica sempre prima la firma/secret del webhook, e solo dopo, se `status == "disabled"`, riconosce la richiesta con `200 {"ok": true}` ma **non ingerisce nulla** — niente nuova conversazione, niente bozza AI. Il provider (Telegram/Meta) smette così di ritentare, ma il messaggio non viene mai salvato: se il canale resta spento per giorni, quei messaggi sono persi per sempre, non recuperabili alla riattivazione (Telegram/Meta non li ri-consegnano una volta accettato il webhook). L'handshake di verifica GET di Meta (`_meta_webhook_verify`, sottoscrizione one-time) non è invece condizionato da questo stato — è un'operazione di setup, non "ricezione messaggi" |
| `access_token_encrypted` | text, nullable | cifrato con lo stesso `EncryptionService` (Fernet) usato per i token Buffer — mai in chiaro, mai restituito dall'API. Per i canali Meta (Facebook/Instagram/WhatsApp) contiene un blob JSON cifrato `{"access_token", "app_secret"}` invece di una singola stringa, vedi §4. WhatsApp aggiunge anche il Phone Number ID, ma in `external_account_id` (non è un segreto) |
| `webhook_secret` | string(64) | generato random alla creazione (`uuid4().hex`); Telegram lo rimanda nell'header `X-Telegram-Bot-Api-Secret-Token` ad ogni richiesta webhook — è così che il webhook (pubblico, non autenticato) verifica che la richiesta venga davvero da Telegram, vedi §8 |
| `config_json` (colonna `config`) | JSONB, nullable | configurazione libera per canale |

### `omni_customers`
Il contatto che scrive (persona reale dietro un numero WhatsApp/username Telegram/ecc.) — **non** la tabella `users` esistente, vedi §2.

| Colonna | Tipo | Note |
|---|---|---|
| `name`, `first_name`, `last_name`, `phone`, `email`, `language`, `timezone`, `notes` | | tutti nullable, popolati progressivamente (dal canale al primo contatto, poi modificabili dall'operatore nella scheda cliente) |
| `is_blocked` | bool, default `false` | `POST /customers/{id}/block\|unblock` (scheda cliente, pulsante "Blocca"/"Sblocca"). Un cliente bloccato può ancora scrivere - il messaggio viene salvato normalmente - ma `ingest_message` marca subito la conversazione `SPAM` invece di `AI_PROCESSING`, e il chiamante (`_ingest_and_trigger`) non mette mai in coda `generate_ai_draft_task` per lui: nessuna bozza AI viene mai generata finché resta bloccato. Non impedisce all'operatore di scrivergli manualmente (`POST /conversations/{id}/messages`) |
| `last_contact_at` | timestamp, nullable | aggiornato ad ogni messaggio in arrivo |

### `omni_customer_identities`
L'identità di un cliente su un canale specifico — separata da `omni_customers` apposta per riconoscere in futuro la stessa persona su più canali (WhatsApp + Instagram + Telegram = un solo `omni_customers`, più identità).

| Colonna | Tipo | Note |
|---|---|---|
| `channel` | string | |
| `external_user_id` | string | ID/numero/username lato canale (es. `chat.id` di Telegram) |
| `display_name` | string, nullable | |

Vincolo unico `(owner_id, channel, external_user_id)`: la stessa persona sullo stesso canale non genera mai due identità duplicate.

### `omni_conversations`
Una conversazione tra un cliente (su un canale specifico) e l'amministratore.

| Colonna | Tipo | Note |
|---|---|---|
| `status` | string | `NEW`, `OPEN`, `AI_PROCESSING`, `WAITING_APPROVAL`, `WAITING_CUSTOMER`, `RESOLVED`, `ARCHIVED`, `SPAM` |
| `assigned_admin_id` | UUID, nullable (FK → administrators, `SET NULL`) | assegnazione manuale (nessun round-robin/team in questa v1, vedi §13) |
| `unread_count` | int | azzerato quando l'operatore apre la conversazione (`GET /conversations/{id}`) |
| `last_message_at` | timestamp, nullable | usato per ordinare la lista conversazioni |

Una conversazione **RESOLVED o ARCHIVED** non viene mai riaperta silenziosamente: un nuovo messaggio dello stesso cliente sullo stesso canale crea una **nuova** riga `omni_conversations` invece di riaprire la vecchia (vedi `OmnichannelService._find_or_create_conversation`).

### `omni_messages`
Ogni singolo messaggio, in entrata o in uscita.

| Colonna | Tipo | Note |
|---|---|---|
| `channel_account_id` | UUID (FK → omni_channel_accounts) | denormalizzato dalla conversazione apposta per l'indice di idempotenza sotto |
| `direction` | string | `inbound`, `outbound` |
| `sender_type` | string | `customer`, `operator`, `ai` (l'AI compare come mittente solo per un messaggio realmente inviato dopo approvazione, mai per una bozza) |
| `external_message_id` | string, nullable | ID del messaggio lato canale |
| `message_type` | string | `TEXT`, `IMAGE`, `VIDEO`, `AUDIO`, `VOICE`, `DOCUMENT`, `LOCATION`, `CONTACT`, `OTHER` |
| `attachments_json` (colonna `attachments`), `metadata_json` (colonna `metadata`) | JSONB, nullable | |
| `status` | string | `received`, `pending`, `sent`, `failed` |

Vincolo unico `(channel_account_id, external_message_id)`: **idempotenza dei webhook** — se Telegram (o qualunque canale) rinvia lo stesso evento due volte, il secondo viene scartato silenziosamente (vedi §8).

### `omni_ai_drafts`
La proposta di risposta generata dall'AI — il cuore del workflow "human-in-the-loop".

| Colonna | Tipo | Note |
|---|---|---|
| `source_message_id` | UUID, nullable (FK → omni_messages, `SET NULL`) | il messaggio del cliente che ha innescato la generazione |
| `original_ai_text` | text, nullable | **mai sovrascritto** da una modifica dell'operatore — conservato per un futuro confronto/analisi (spec "feedback loop") |
| `edited_text` | text, nullable | testo modificato dall'operatore, se diverso dall'originale |
| `status` | string | `GENERATING`, `PENDING_APPROVAL`, `EDITED`, `APPROVED`, `SENDING`, `SENT`, `REJECTED`, `FAILED`, `HUMAN_REVIEW_REQUIRED`, `SUPERSEDED`. **`SUPERSEDED`** (dal 2026-10-27): bozza archiviata perché il cliente ha scritto di nuovo (`OmnichannelService.ingest_message` → `OmnichannelDraftService.supersede_open_drafts`) o perché ne è nata una più recente (`generate_draft_for_message`). Vale per `PENDING_APPROVAL`/`EDITED`/`HUMAN_REVIEW_REQUIRED`/`FAILED`, non per `GENERATING` (il task la riscrive a fine lavoro) né per `SENT`/`REJECTED`. Non è approvabile, modificabile né rigenerabile; il motivo è in `failure_reason`; audit `AI_SUPERSEDED`. Prima una bozza di ieri restava "da approvare" e la chat la riproponeva al nuovo messaggio di oggi: sembrava che l'AI generasse da sola anche con `auto_generate_draft` spento (segnalazione reale, 2026-10-27). Il frontend (`chat-panel.tsx`) la esclude dalla bozza attiva, quindi il bottone "Genera risposta AI" torna disponibile. |
| `model`, `prompt_version` | string, nullable | |
| `confidence_score` | float, nullable | riservato per uso futuro, non popolato in questa v1 |
| `sensitive_category` | string, nullable | valorizzato se il messaggio del cliente tocca un argomento sensibile (rimborso, legale, medico...) — vedi §6 |
| `failure_reason` | text, nullable | motivo se `status = FAILED` (es. nessuna API key OpenAI configurata) o `SUPERSEDED` (perché è stata archiviata) |
| `approved_at`, `approved_by` (FK → administrators, `SET NULL`), `sent_at` | | |

**La AI non ha mai un percorso di codice che invia un messaggio.** Solo `OmnichannelDraftService.approve_and_send`, chiamato da un endpoint autenticato dopo un'azione esplicita dell'operatore, chiama `Connector.send_message`.

### `omni_ai_agent_configs`
Configurazione dell'assistente AI. Una riga per `owner_id` (vincolo unico), creata al primo accesso con valori di default se non esiste ancora.

| Colonna | Tipo | Note |
|---|---|---|
| `system_prompt`, `company_description`, `tone`, `language`, `signature` | | testo libero incorporato nel prompt di sistema ad ogni generazione, vedi §6 |
| `temperature` | float | default `0.7` |
| `allowed_topics_json`, `forbidden_topics_json` | JSONB, nullable | liste di argomenti, incorporate nel prompt |
| `max_context_messages` | int | quanti messaggi recenti della conversazione includere nel contesto (default 20) |
| `knowledge_base_enabled` | bool | se disattivato, la ricerca nella Knowledge Base viene saltata |
| `automatic_language_detection` | bool | |
| `auto_generate_draft` | bool, default `true` | **Ortogonale a `response_mode`** — controlla *quando* nasce una bozza, non cosa succede dopo. `true` (default, comportamento originale invariato): ogni messaggio in arrivo genera subito una bozza (`generate_ai_draft_task`). `false`: nessuna generazione automatica — la conversazione va in `OPEN` invece di `AI_PROCESSING`, l'operatore scrive a mano oppure preme "Genera risposta AI" (`POST /conversations/{id}/generate-draft`) quando vuole. Pensato per non consumare chiamate OpenAI su conversazioni gestite sempre manualmente. Una volta generata (automaticamente o a richiesta), la bozza segue **esattamente lo stesso percorso** — stessa `generate_draft_for_message`, stesso controllo argomenti sensibili, stesso rispetto di `response_mode` (compreso l'auto-invio se `AUTO_REPLY` è acceso) — non esiste un secondo percorso di codice per la generazione manuale |
| `response_mode` | string | `MANUAL`, `APPROVAL_REQUIRED` (default per ogni nuovo owner), `AUTO_REPLY`. Cambiato solo esplicitamente dalla pagina AI Agent (interruttore con conferma prima di accendere), mai di default. Ogni cambio produce un `OmniAuditLog` dedicato (`AI_RESPONSE_MODE_CHANGED`, con `from`/`to` in `metadata_json`). `MANUAL` è accettato dallo schema ma non ha ancora un comportamento distinto da `APPROVAL_REQUIRED` in questa v1 — per "niente AI a meno che non lo chieda io" usa `auto_generate_draft=false` sopra, che è il vero meccanismo per questo caso d'uso |
| `sensitive_categories_json` | JSONB, nullable | vedi §6 |
| `crm_enabled` | bool, default `false` | interruttore dell'integrazione CRM Mamify (§6-bis). Si accende solo dalla pagina AI Agent, con conferma, e solo se c'è una chiave; ogni cambio produce un audit `CRM_TOGGLED` |
| `crm_api_key_encrypted` | text, nullable | chiave `X-Fw360-Key` cifrata con `EncryptionService` (Fernet). **Mai restituita** dall'API: `OmniAIAgentConfigResponse` espone solo `crm_api_key_set` e `crm_api_key_source` (`config` \| `env`). Ripiego a livello di installazione: `MAMIFY_RAG_API_KEY` in `.env`. Ogni scrittura/rimozione → audit `CRM_KEY_CHANGED` (solo `set: true/false`, mai la chiave) |
| `crm_base_url` | string(255), nullable | per puntare a uno staging; vuoto = `https://mamify.app/m/api/plugins/mamify/rag/`. Solo `https://` |

### `omni_knowledge_companies` / `omni_knowledge_documents` / `omni_knowledge_chunks`
Knowledge Base dell'AI, codice in `app/integrations/omnichannel/knowledge.py` (il docstring in testa spiega le scelte).

- **Aziende** (`omni_knowledge_companies`, dal 2026-10-15): fanno da cartelle. Nome (unico per proprietario, senza badare alle maiuscole), descrizione, sito, email, telefono, indirizzo, note interne. I dati, **note escluse**, diventano una "scheda azienda": un documento nascosto con `kind="profile"`, rigenerato da `sync_company_profile()` a ogni modifica e cercabile come gli altri. Così "qual è il vostro numero?" trova il telefono senza aggiungere token alle altre risposte. La scheda non compare mai negli elenchi e non si modifica dalle rotte dei documenti.
Colonne (tipi come in [schema.sql](./schema.sql)):

| Tabella | Colonne | Note |
|---|---|---|
| `omni_knowledge_companies` | `id`, `owner_id` → `administrators` (CASCADE), `name` (255), `description`, `website` (500), `email` (255), `phone` (100), `address` (500), `notes`, `created_at`, `updated_at` | `UNIQUE (owner_id, name)`; `notes` non entra mai nella scheda azienda |
| `omni_knowledge_documents` | `id`, `owner_id`, `title` (255), `source_type` (20: `manual`, `pdf`, `docx`, `xlsx`, `csv`, `txt`, `md`), `content_text`, `source_url` (1000), `status` (20: `processing`, `ready`, `error`), `kind` (20, default `document`), `always_on` (default `false`), `file_name` (255), `chunk_count` (default 0), `error_message`, `company_id` → `omni_knowledge_companies` (SET NULL, nullable), `created_at`, `updated_at` | indici su `owner_id` e `company_id`; `error_message` tiene l'ultimo errore di embedding, l'elenco lo mostra come "indicizzazione ferma" |
| `omni_knowledge_chunks` | `id`, `owner_id`, `document_id` → `omni_knowledge_documents` (CASCADE), `chunk_index`, `heading` (600), `content`, `embedding` (`bytea`: 512 float32 = 2048 byte, `NULL` finché il worker non lo calcola), `embedding_model` (100), `embedded_at`, `created_at` | indici btree su `owner_id`/`document_id` e due GIN su `to_tsvector('italian'|'simple', coalesce(heading,'') || ' ' || content)`: sono quelli che usano `_fts_search()` e la ricerca avanzata |

- **Documenti** (`kind` = `document` | `instruction` | `profile`): `company_id` nullable, `NULL` = vale per tutte le aziende. Eliminando un'azienda i documenti si spostano fra quelli senza azienda (lo fa l'API, non il `SET NULL`, così cambia `updated_at` e la cache dei vettori se ne accorge), oppure si eliminano con `?delete_documents=true`.
- **Blocchi**: ~900 caratteri, con intestazione `Azienda: X | Documento: Y` che entra nell'embedding e nella ricerca. Rinominare un'azienda o spostare documenti rigenera i blocchi e rimette in coda gli embedding.
- **Ricerca ibrida**: full-text Postgres (`italian` + `simple`, indici GIN) + embedding `text-embedding-3-small` a 512 dimensioni in `bytea`, confrontati in numpy (niente pgvector), fusi con Reciprocal Rank Fusion e tagliati a un budget fisso di caratteri. `search(..., company_id=X)` limita ai documenti di X più quelli senza azienda: oggi lo usa solo "Prova il bot"; le bozze vere cercano in tutte le aziende.
- **Elenco** (`GET /knowledge-base?company=<id>|none&q=`): niente `content_text`, solo `preview` (300 caratteri), perché con centinaia di PDF l'elenco completo peserebbe megabyte. Il testo intero arriva da `GET /knowledge-base/{id}`.
- **Ricerca avanzata dall'elenco** (`GET /knowledge-base/find?q=&company=<id>|none&kind=`, dal 2026-10-31): risponde all'operatore "in quali file se ne parla", non al bot. `knowledge.find_documents()` usa lo stesso motore ibrido (`_hybrid_rank`, estratto da `search()`), ma con un bacino più largo (120 blocchi), raggruppa per documento (punteggio = blocco migliore + 25% degli altri) e restituisce fino a 3 passaggi per documento, tagliati attorno alla prima parola cercata. In più cerca nel **nome del file e nel titolo** (tutta la frase, oppure ogni parola): questi file valgono `1.0`, molto più di qualunque somma RRF (~1/60), quindi stanno sempre in cima con `matched_by=["nome", ...]`. Differenze volute rispetto a `search()`: dentro una cartella si vede **solo** quella cartella (niente documenti generali), le istruzioni sempre attive si trovano (per testo), le schede azienda no. Costa al massimo un embedding: per questo la dashboard la lancia con Invio, non a ogni tasto.

### `omni_tags` / `omni_conversation_tags`
Tag liberi (es. `VIP`, `RECLAMO`, `LEAD`) applicabili alle conversazioni. `omni_conversation_tags` è la tabella ponte many-to-many, con **PK composta** `(conversation_id, tag_id)` più la colonna `owner_id` (non-PK, `NOT NULL`).

> **Attenzione se estendi questo modulo**: `omni_conversation_tags` ha una colonna extra (`owner_id`) oltre alle due FK della relazione. Il meccanismo automatico di SQLAlchemy (`relationship(secondary=...)`) scrive **solo** le due colonne della relazione quando fai `conversation.tags.append(tag)` — non conosce `owner_id` e l'INSERT fallirebbe per violazione del vincolo NOT NULL. Per questo `add_conversation_tag` in `api/v1/omnichannel.py` usa un `insert()` SQLAlchemy Core esplicito con `owner_id` valorizzato, mai `.append()`. La rimozione (`DELETE`, che non deve popolare nulla) può invece restare sul meccanismo automatico — vedi il commento sopra alla definizione della tabella in `app/models/omnichannel.py`.

### `omni_internal_notes`
Note interne su una conversazione, mai visibili/inviate al cliente — renderizzate nella chat con uno stile visivamente distinto (bordo tratteggiato, sfondo diverso).

### `omni_audit_logs`
Log di audit **separato** da `audit_logs` esistente (questo modulo non scrive mai in quella tabella). Stesso spirito: `action`, `entity_type`, `entity_id`, `metadata_json`, `admin_id` (FK `SET NULL`). Azioni registrate: `AI_GENERATED`, `AI_GENERATION_FAILED`, `AI_EDITED`, `AI_REGENERATED`, `AI_SUPERSEDED`, `AI_APPROVED`, `AI_REJECTED`, `MESSAGE_SENT`, `MESSAGE_FAILED`, `ASSIGNMENT_CHANGED`, `CUSTOMER_UPDATED`, `SETTINGS_CHANGED`, e per il CRM (§6-bis) `CRM_KEY_CHANGED`, `CRM_TOGGLED`, `CRM_PROFILE_VIEWED`.

### `omni_notifications`
Notifiche in-app, lette via polling (`GET /notifications`, ogni 15s lato frontend). `admin_id` nullable = notifica broadcast a tutti gli amministratori di quell'`owner_id`.

### `omni_ai_usage`
Tracciamento consumo AI per conversazione/modello (token input/output, costo stimato con una tariffa approssimativa hardcoded) — base per un futuro sistema di billing/limiti, non applica ancora alcun limite.

---

## 4. Connector layer

Interfaccia comune (`app/integrations/omnichannel/connectors/base.py::Connector`, classe astratta) che ogni canale implementa, così che la logica di business non parli mai direttamente con l'API di un social network specifico:

```python
verify_webhook(headers, path_secret) -> bool     # la richiesta viene davvero dal canale?
parse_webhook(payload) -> List[NormalizedIncomingMessage]   # payload grezzo -> formato interno comune
send_message(external_user_id, text) -> SendResult          # invio reale, chiamato SOLO dopo approvazione umana
get_contact(external_user_id) -> dict | None                 # opzionale
download_attachment(attachment_ref) -> bytes | None           # opzionale, non implementato in questa v1 (vedi §13)
get_status() -> dict                                          # health check per la pagina Canali
```

`verify_webhook` accetta anche un parametro opzionale `body: bytes` (il corpo grezzo, non ancora parsato, della richiesta) — usato solo dai canali che firmano l'intero payload (Facebook, `X-Hub-Signature-256`) invece di un valore statico in un header (Telegram, secret token); la maggior parte delle implementazioni lo ignora.

Implementazioni:

- **`TelegramConnector`** (`connectors/telegram.py`) — canale reale. Chiama l'API Bot di Telegram (`api.telegram.org/bot<token>/...`) via `httpx` diretto, stesso stile di `app/integrations/openai/client.py` (nessun SDK di terze parti). `register_webhook()` (non parte dell'ABC, specifico Telegram) chiama `setWebhook` passando `secret_token` = `omni_channel_accounts.webhook_secret`.
- **`FacebookConnector`** (`connectors/facebook.py`) — canale reale, via Graph API (`graph.facebook.com/v19.0`, Send API + Messenger webhooks). A differenza di Telegram, Meta non offre una chiamata "registra webhook": l'amministratore incolla lui stesso URL e Verify Token nella Meta App Dashboard (Messenger → Impostazioni → Webhooks) — la pagina Canali mostra questi due valori già pronti da copiare (`MetaWebhookInfoDialog`, condiviso con Instagram/WhatsApp). Richiede **due** segreti distinti, non uno solo come Telegram: l'Access Token (per inviare) e l'App Secret (per verificare che i webhook in arrivo vengano davvero da Meta, header `X-Hub-Signature-256`, HMAC-SHA256 del body grezzo) — combinati in un unico blob JSON cifrato `{"access_token", "app_secret"}` dentro `access_token_encrypted` (`OmnichannelService.create_channel_account`), nessuna nuova colonna necessaria. `parse_webhook` scarta esplicitamente gli "echo" (`message.is_echo`, i nostri stessi messaggi in uscita rimandati indietro da Meta) e le ricevute di consegna/lettura — solo i messaggi realmente in arrivo dal cliente diventano un `NormalizedIncomingMessage`.
- **`InstagramConnector`** (`connectors/instagram.py`) — canale reale, **sottoclasse di `FacebookConnector` senza alcuna differenza di logica**: da quando Meta ha unificato Messenger e la messaggistica Instagram, un account Instagram professionale collegato a una Pagina Facebook usa esattamente la stessa infrastruttura (stesso formato webhook, stesso endpoint `/me/messages`, stessa firma) — quindi non c'è nulla da riscrivere, solo un'etichetta diversa (`channel_label = "Instagram"`) nei messaggi di errore/stato mostrati all'admin.
- **`WhatsAppConnector`** (`connectors/whatsapp.py`) — canale reale, ma una famiglia di API diversa: **WhatsApp Cloud API**, non il Send API di Messenger. Payload webhook (`entry[].changes[].value.messages[]`) e formato di invio (`POST /{phone_number_id}/messages`, `messaging_product: "whatsapp"`) sono strutturalmente diversi da Facebook/Instagram, anche se la verifica firma webhook (`X-Hub-Signature-256`) passa dalla stessa infrastruttura Meta. Il Phone Number ID (non un segreto) va nella colonna esistente `external_account_id`, non nel blob cifrato. **Limite non implementato**: fuori dalla finestra di 24 ore dall'ultimo messaggio del cliente, WhatsApp accetta solo messaggi-template pre-approvati, che questo modulo non gestisce — dato che ogni bozza qui nasce sempre in risposta a un messaggio del cliente appena ricevuto, in pratica non è quasi mai un problema, ma un'approvazione molto tardiva (oltre 24h) fallirà con un errore esplicito sulla bozza, non silenziosamente.
- **`MaytapiConnector`** (`connectors/maytapi.py`) — canale reale, **secondo modo di collegare WhatsApp**, aggiunto il 2026-09-19. Non sostituisce `WhatsAppConnector`: quello parla con la Cloud API ufficiale di Meta e richiede numero business dedicato, verifica aziendale, App Review e template approvati fuori dalla finestra di 24 ore; questo collega un **numero WhatsApp normale** — quello personale dell'amministratore — via QR code dalla console Maytapi, senza review e senza finestra dei template. Due canali distinti nel registro (`whatsapp` e `whatsapp_maytapi`), si sceglie per canale. Credenziali: `api_token` (unico segreto, cifrato in `access_token_encrypted`), `product_id` e `phone_id` in `config_json` (non sono segreti: indirizzano quale istanza/numero usare, come il Phone Number ID della Cloud API). **Verifica webhook**: Maytapi non firma il payload — né HMAC come Meta, né header con segreto come Telegram — quindi il segreto viaggia **nell'URL** (`/webhooks/maytapi/{id}/{webhook_secret}`), che è l'uso per cui `webhook_secret` era nato; confronto a tempo costante (`hmac.compare_digest`), più un controllo che `product_id`/`phone_id` del payload corrispondano a quelli configurati. **Il punto delicato**: Maytapi rimanda sul webhook anche i messaggi partiti dal telefono, comprese le risposte appena inviate da noi (`message.fromMe`), che vengono scartate — ingerirle significherebbe generare una bozza AI sulla propria risposta e, con l'autorisponditore acceso, rispondere a se stessi all'infinito. `send_message` non si fida del codice HTTP: Maytapi risponde `200` anche quando rifiuta, e l'esito sta in `success`. `register_webhook()` (non parte dell'ABC, come per Telegram) chiama `setWebhook`; attenzione, il webhook Maytapi vale per l'intero **prodotto**, non per singolo numero. **`setWebhook` non restituisce `success`**, a differenza di `/status` e `/sendMessage`: in caso di successo risponde `200` con la configurazione aggiornata del prodotto (`{"pid", "webhook", "ack_delivery", "phone_limit", ...}`) e basta — quindi si fallisce solo su HTTP >= 400 o su `success` esplicitamente `False`, mai sull'assenza del campo (il 2026-09-22 pretenderlo faceva fallire ogni registrazione riuscita: il webhook veniva registrato davvero e la dashboard diceva "errore sconosciuto"). L'URL memorizzato torna nella risposta e viene confrontato con quello inviato: se Maytapi ne ha tenuto un altro lo si dice subito, invece di scoprirlo dai messaggi che non arrivano.
- **`MyAgiWhatsAppConnector`** (`connectors/whatsapp_myagi.py`, canale `whatsapp_myagi`) — **terzo modo di collegare WhatsApp**, aggiunto il 2026-10-26: stesso meccanismo di Maytapi (numero normale collegato via QR come "dispositivo", nessuna review Meta) ma il client "WhatsApp Web" gira su un **nostro container** invece che dai server di Maytapi. Il gateway è [WAHA](https://github.com/devlikeapro/waha) (Apache-2.0, dalla 2026.6 tutto gratuito e senza limite di sessioni), immagine `devlikeapro/waha:noweb` (motore NOWEB, senza browser), servizio `myagi_wa` in `docker-compose.prod.yml`, non esposto fuori dalla rete Docker. Client in `app/integrations/myagi/waha.py` (verificato dal vivo contro WAHA 2026.9.2). **Nessuna credenziale per canale**: la chiave del gateway è dell'installazione (`MYAGI_WA_API_KEY`), e il legame canale ↔ sessione WAHA è il nome della sessione, derivato dall'id del canale (`agi_<uuid hex>`). **Verifica webhook, due prove**: il segreto nel path (`/webhooks/myagi/{id}/{webhook_secret}`, come Maytapi) **e**, se presente, la firma HMAC-SHA512 del corpo che WAHA mette in `X-Webhook-Hmac` quando la sessione è configurata con `hmac.key` = `webhook_secret` (lo fa `ensure_session`); una firma presente ma sbagliata è un 403 anche con il path giusto. Scartati come per Maytapi: `fromMe`, gruppi (`@g.us`), broadcast/status, eventi diversi da `message`, e messaggi di una sessione diversa da quella del canale. Media: `payload.media.url` punta a `http://myagi_wa:3000/api/files/...` (interno, richiede la chiave): salvato nell'allegato, non apribile dal browser in questa v1. `send_message` → `POST /api/sendText` con `chatId` `<cifre>@c.us`; un 422 "Session status is not as expected" viene riportato con lo stato (es. `SCAN_QR_CODE` = riscansiona il QR). **Attenzione**: `PUT /api/sessions/{name}` riavvia la sessione (verificato), quindi `ensure_session` lo chiama solo se URL o segreto del webhook sono cambiati davvero, mai a ogni "Avvia". Le sessioni WAHA vivono nel volume `myagi_sessions_prod:/app/.sessions`: senza volume ogni riavvio del container richiederebbe un nuovo QR. Rischio di blocco del numero da parte di WhatsApp: identico a Maytapi (stessa tecnica, è il comportamento del numero che conta), senza il canone; cambia che gli aggiornamenti del client, quando Meta cambia protocollo, toccano a noi (aggiornare l'immagine).
- **`MockConnector`** (`connectors/mock.py`) — nessuna chiamata esterna. Usato dallo strumento "Simula messaggio" per testare l'intera pipeline (ingest → bozza AI → approvazione → invio) senza credenziali reali.
- **`GmailConnector`** (`connectors/gmail.py`) — canale reale, ma l'unico che **non riceve via webhook**: usa IMAP (`imaplib`, stdlib) per leggere e SMTP (`smtplib`, stdlib) per inviare, autenticandosi con una **App Password** Gmail (Account Google → Sicurezza → Password per le app, richiede la verifica in due passaggi) invece di OAuth — scelta deliberata per evitare un progetto Google Cloud + un topic Pub/Sub solo per le notifiche push della vera Gmail API (`users.watch()`, che andrebbe comunque rinnovato ogni 7 giorni). `verify_webhook`/`parse_webhook` sollevano `NotImplementedError`: non c'è alcun percorso di codice che li chiami per questo canale, l'ingestione passa interamente da `fetch_new_messages()` (non parte dell'ABC), invocato dal poller Celery (§5). Nessuna colonna nuova: `external_account_id` contiene l'indirizzo Gmail stesso (username IMAP/SMTP), `access_token_encrypted` la App Password, `config_json.last_uid` il cursore IMAP per il fetch incrementale. La lettura usa `BODY.PEEK[]`, non `RFC822`, apposta per non marcare i messaggi come letti nella casella reale — un effetto collaterale che una casella di supporto condivisa non dovrebbe mai subire in modo invisibile. **Le risposte in uscita restano in copia sulla vera Gmail** e sono threadate correttamente: `Connector.send_message` accetta ora un parametro opzionale `reply_to` (metadata dell'ultimo messaggio in arrivo della conversazione, calcolato da `OmnichannelService.get_reply_context` e passato da ogni punto che invia — approvazione bozza, invio manuale, broadcast; ignorato dagli altri 5 canali), che Gmail usa per riprendere Subject/Message-ID originali come `Subject`/`In-Reply-To`/`References` (RFC 2822) — e siccome l'invio passa comunque da `smtp.gmail.com` con le credenziali dell'account stesso, Gmail salva automaticamente una copia in "Posta inviata" (comportamento nativo di Gmail via SMTP, non qualcosa che questo modulo deve replicare) — aprendo Gmail direttamente si ritrova quindi la stessa conversazione vista nell'Inbox di questa app, non due email scollegate.
- **`registry.py::get_connector(channel_account)`** è la unica factory: decripta il token (se presente) e istanzia la classe giusta in base a `channel_account.channel`. Tutti e 7 i canali (`mock`, `telegram`, `facebook`, `instagram`, `whatsapp`, `whatsapp_maytapi`, `gmail`) sono implementazioni reali — non esiste alcun connettore-stub in questo modulo.

---

## 5. Flusso messaggio → bozza AI → approvazione → invio

```
1. Webhook (Telegram/Meta), "Simula messaggio" (canale mock) o il poller
   IMAP (Gmail, ogni 2 minuti - vedi app/tasks/omnichannel.py::
   poll_gmail_channels_task, nessun webhook per questo canale) rileva un
   evento
2. Connector.verify_webhook()  → 403 se non valido (saltato per Gmail: non
   applicabile, la connessione IMAP è già autenticata)
3. Connector.parse_webhook() → NormalizedIncomingMessage (per Gmail:
   Connector.fetch_new_messages(), che combina fetch IMAP + parsing)
4. OmnichannelService.ingest_messages_and_trigger_ai() per ogni messaggio
   normalizzato → OmnichannelService.ingest_message():
     - se external_message_id già visto per questo channel_account → no-op (idempotenza, §7)
     - trova o crea omni_customers + omni_customer_identities
     - trova o crea omni_conversations (mai riapre una RESOLVED/ARCHIVED, vedi §3)
     - salva omni_messages (direction=inbound, sender_type=customer)
     - conversation.status = AI_PROCESSING SE OmniAIAgentConfig.auto_generate_draft, altrimenti OPEN
5. SE auto_generate_draft: generate_ai_draft_task.delay(message.id)   → in coda Celery, la richiesta HTTP del webhook NON aspetta l'AI
   ALTRIMENTI: si ferma qui - l'operatore scrive a mano o preme "Genera risposta AI"
   (POST /conversations/{id}/generate-draft, sincrono, stessa generate_draft_for_message
   del passo 6 sotto - nessun percorso di codice separato/semplificato)
6. (worker Celery) OmnichannelDraftService.generate_draft_for_message():
     - crea subito una riga omni_ai_drafts con status GENERATING (la UI può mostrare "L'AI sta generando...")
     - risolve la chiave OpenAI (ai_settings_service.get_openai_credentials, STESSA chiave configurata in Impostazioni)
     - se manca la chiave → status FAILED, conversation torna OPEN
     - integrations/omnichannel/ai.py::detect_sensitive_category() sul testo del cliente
     - integrations/omnichannel/ai.py::generate_ai_reply() → chiamata OpenAI (chat/completions, testo puro)
     - status = HUMAN_REVIEW_REQUIRED (se categoria sensibile) altrimenti PENDING_APPROVAL
     - conversation.status = WAITING_APPROVAL

     SE OmniAIAgentConfig.response_mode == "AUTO_REPLY" E la bozza NON è HUMAN_REVIEW_REQUIRED:
     6b. OmnichannelDraftService.approve_and_send(db, draft.id, admin=None) viene chiamato
         subito, dallo stesso task Celery, con lo STESSO percorso di codice (stesso row-lock
         anti-doppio-invio, stesso stato SENDING→SENT) che userebbe un click umano - non
         esiste un secondo percorso di invio parallelo. `admin=None` produce un audit log
         "AI_AUTO_SENT" invece di "AI_APPROVED" e nessuna notifica "Bozza AI pronta" (sostituita
         da una notifica "L'AI ha risposto automaticamente", informativa, non un'azione da fare).
         Se l'invio fallisce (es. token canale scaduto), la bozza torna comunque "FAILED" e
         resta visibile/rigenerabile in Inbox come nel percorso manuale - non sparisce silenziosamente.

     ALTRIMENTI (default, response_mode = APPROVAL_REQUIRED): crea una omni_notifications
     ("Bozza AI pronta") e si ferma qui, in attesa di un operatore.
7. Operatore apre la conversazione (se non già inviata automaticamente al passo 6b), vede la bozza, può:
     PATCH /drafts/{id}          → modifica il testo (status → EDITED)
     POST /drafts/{id}/regenerate → richiama generate_ai_reply da zero (anche da stato FAILED)
     POST /drafts/{id}/reject     → status REJECTED, conversation torna OPEN
     POST /drafts/{id}/approve    → SOLO qui (o al passo 6b) può partire un invio reale, vedi §7
8. Approvazione riuscita (manuale o automatica):
     - Connector.send_message() con il testo finale (edited_text se presente, altrimenti original_ai_text)
     - nuovo omni_messages (direction=outbound, sender_type=ai o operator se il testo era stato modificato)
     - draft.status = SENT, conversation.status = WAITING_CUSTOMER
```

L'operatore può anche scrivere un messaggio libero, bypassando completamente il workflow AI (`POST /conversations/{id}/messages`) — utile per rispondere subito senza aspettare/usare l'AI, indipendentemente da `response_mode`.

**Messaggio multiplo (broadcast)** — `POST /broadcast` invia lo stesso testo a molte conversazioni esistenti in una volta sola ("scrivi a tutti quelli che mi hanno contattato"). Non esiste un concetto di "rubrica" separato: l'Inbox stessa è l'elenco contatti, ogni `omni_conversations` collega già cliente + canale + identità, quindi `conversation_ids` (o vuoto = tutte le conversazioni non `ARCHIVED`/`SPAM`) è sufficiente. I clienti bloccati sono **sempre** esclusi, anche se selezionati esplicitamente — controllo non aggirabile da questa azione. Girato **sincrono** con un tetto rigido di 50 destinatari per singolo invio (`_MAX_BROADCAST_RECIPIENTS`, `api/v1/omnichannel.py`) invece di un task Celery in background: è un'azione manuale e occasionale dell'amministratore, non uno strumento di marketing massivo, e un tetto basso permette di dare un riepilogo immediato (chi è andato a buon fine, chi no e perché) senza dover implementare polling. Ogni invio riuscito crea un normale `omni_messages` in uscita (`sender_type="operator"`) e aggiorna la conversazione esattamente come un invio manuale singolo; un solo `omni_audit_logs` riassuntivo (`BROADCAST_SENT`) invece di uno per destinatario.

**Limite reale da conoscere**: per i canali Meta (Facebook/Instagram/WhatsApp), Meta accetta messaggi liberi solo entro 24 ore dall'ultimo messaggio del contatto (vedi §4) — un broadcast verso contatti "vecchi" su quei canali fallirà per la maggior parte dei destinatari, mostrato chiaramente nel riepilogo finale (`OmniBroadcastResult.failures`), non un fallimento silenzioso. Su Telegram non c'è questo limite.

---

## 6. Pipeline AI

`app/integrations/omnichannel/ai.py`, deliberatamente **senza dipendenza di codice** da `app/integrations/openai/client.py` (chiamata `httpx` propria) — l'unico pezzo di infrastruttura esistente riusato è `app.services.ai_settings_service.get_openai_credentials`, la stessa chiave OpenAI già configurabile dalla pagina Impostazioni e già usata da Blog Writer AI e dal wizard campagne.

**Context builder** (`build_system_prompt` + `build_conversation_messages`): il prompt di sistema è composto da `system_prompt` dell'agente + descrizione azienda + tono + lingua (fissa o rilevata automaticamente) + argomenti consentiti/vietati + firma + eventuali blocchi di Knowledge Base pertinenti; la cronologia è limitata a `max_context_messages` messaggi più recenti **letti freschi dal database ad ogni generazione** (mai una cronologia in cache), così una bozza generata durante una raffica di messaggi quasi simultanei vede sempre lo stato più aggiornato possibile.

**`system_prompt` è un'istruzione per il modello, non uno script letterale**: un `system_prompt` come `"Saluta sempre con 'Buongiorno dal Team X...'"` viene rispettato nello *stile*, ma il modello può parafrasare invece di ripetere la frase parola per parola — comportamento normale di un LLM, non un bug che ignora l'impostazione (verificato: il prompt salvato in `omni_ai_agent_configs.system_prompt` è sempre incluso per intero in ogni chiamata). Due leve per un output più fedele/ripetibile: (1) scrivere il prompt in modo esplicitamente imperativo, tra virgolette, es. *"rispondi SEMPRE e SOLO con questo testo esatto: '...'"*; (2) abbassare `temperature` (slider "Creatività" nella pagina AI Agent, 0-1.5, default 0.7) — più bassa = risposte più letterali e ripetibili. Nota anche che `build_conversation_messages` include lo storico della conversazione: una risposta AI precedente già presente nello storico (magari generata prima di cambiare il prompt) influenza il tono delle risposte successive nella stessa conversazione, anche dopo aver aggiornato il prompt.

**Knowledge Base**: `knowledge.search()` è un RAG **ibrido** (dettagli in §3): full-text Postgres sugli indici GIN (`italian` + `simple`, OR fra i termini, stopword italiane scartate, codici prodotto cercati come sottostringa) più ricerca semantica con `text-embedding-3-small` a 512 dimensioni, confrontata in numpy su una matrice in cache per proprietario (niente `pgvector`), fuse con Reciprocal Rank Fusion e tagliate a un budget di 4.500 caratteri. La domanda da cercare è costruita da `build_search_query()` con gli ultimi messaggi del cliente, senza chiamate al modello. Se l'embedding fallisce (chiave assente, credito finito) resta la ricerca testuale e la bozza parte comunque, con `kb_warning` valorizzato. La stessa classifica (`_hybrid_rank`) serve alla ricerca avanzata della dashboard (`find_documents`, §3), che però raggruppa per documento invece di preparare blocchi per il modello.

**Categorie sensibili** (`detect_sensitive_category`): lista fissa `refund`, `legal`, `medical`, `complaint`, `pricing_exception`, `discount`, `contract`, `payment_problem` (personalizzabile per agente in `sensitive_categories_json`), rilevate con un dizionario di parole chiave IT/EN (`_CATEGORY_KEYWORDS`) — un controllo euristico volutamente semplice, non un classificatore vero: sufficiente a forzare `HUMAN_REVIEW_REQUIRED` sui casi più ovvi, non un sostituto di un vero controllo prima di configurare l'agente su un caso d'uso sensibile davvero.

**Errori di OpenAI, e perché arrivano fino allo schermo** (`_describe_openai_error`): il corpo della risposta di errore di OpenAI (`{"error": {"message", "type", "code"}}`) viene letto e riportato nel messaggio. È sicuro: OpenAI rimanda solo il proprio oggetto errore, mai la richiesta che abbiamo inviato — a dover restare fuori da un messaggio d'errore sono gli header della richiesta, non la risposta. Due casi distinti hanno lo stesso `429` ma rimedi opposti e vengono separati: `insufficient_quota` (credito dell'account esaurito → ricaricare) e un vero limite di frequenza (→ aspettare). **Attenzione**: la pagina Impostazioni **non** può accorgersi del credito esaurito quando salvi la chiave — `validate_api_key()` elenca i modelli, cosa che non costa token e funziona a saldo zero, quindi una chiave senza credito viene accettata e fallisce solo alla prima generazione. Il 2026-09-22 questo è costato una diagnosi sbagliata: il 429 usciva come `500 Internal Server Error` e sembrava l'integrazione rotta.

**Chi cattura l'errore**: la prima generazione lo registra sulla bozza stessa (`generate_draft_for_message` → `status = FAILED` + `failure_reason`, mostrato nell'Inbox), mentre `POST /drafts/{id}/regenerate` ha una bozza già esistente da preservare e lascia uscire il `ConnectorError` — l'endpoint lo mappa a **502** con il messaggio (`api/v1/omnichannel.py`), come già fa `register-webhook`. Senza quella `except` era un 500 anonimo.

**Costo**: ogni generazione salva una riga `omni_ai_usage` con token input/output e un costo stimato (tariffa forfettaria approssimata nel codice, non collegata a un vero listino OpenAI aggiornato automaticamente).

---

## 6-bis. CRM Mamify: dati del cliente nelle risposte

Dal 2026-10-26 l'AI può rispondere con i **dati dell'account del cliente che scrive** (saldi Mamix/MamiCash, movimenti, ordini, rete di invitati) e con il **catalogo** (prodotti, gift card), letti al momento dalle "API Mamify per il RAG" del CRM (`https://mamify.app/m/api/plugins/mamify/rag/`, sola lettura, autenticate con header `X-Fw360-Key`). Codice in `app/integrations/omnichannel/crm/`: `mamify.py` è il client HTTP (un metodo per endpoint, errori del CRM → `MamifyError(code, message)`, 429 → `rate_limited`, rete/non-JSON → `crm_unavailable`, la chiave non compare mai in log o eccezioni); `tools.py` decide chi è il cliente, quali strumenti il modello può usare e li esegue.

### La regola di privacy, e dove vive

**Un cliente può chiedere solo di sé stesso, e "sé stesso" lo stabilisce il backend, non il cliente e non il modello.** Non è un'istruzione nel prompt (quella c'è, ma è una cortesia): è la forma degli strumenti.

1. **Identità fidata** (`trusted_identity_for_customer`). Nell'ordine: il numero del mittente su un canale WhatsApp (`whatsapp`: `external_user_id` è il numero; `whatsapp_maytapi`: è il JID `39333...@c.us`, i gruppi `@g.us` sono scartati); altrimenti telefono/email che **l'operatore** ha scritto nella scheda cliente (`omni_customers.phone/email`), perché un umano ha verificato chi è — è l'unico modo per far funzionare il CRM su Telegram/Instagram/Facebook/Gmail, dove il canale non dà un numero. **Mai** un dato scritto dal cliente nel messaggio.
2. **Risoluzione prima della generazione** (`resolve_customer`): una `customer/find` con i soli identificativi fidati. Esiti (`CrmContext.status`): `identified` (un solo cliente → `customer_id`), `ambiguous` (`customer_ambiguous`: stesso numero su più account), `not_found`, `unverified` (nessuna identità fidata), `unavailable` (CRM giù o chiave rifiutata: si risponde senza CRM, la bozza non fallisce).
3. **Strumenti senza identificativi** (`tool_definitions`/`execute_tool`): `get_my_wallets`, `get_my_transactions(wallet, app, since, limit)`, `get_my_orders(order_id, status, limit)`, `get_my_network(scope, query, limit)` esistono **solo** a stato `identified` e non hanno parametri per scegliere il cliente: il backend inietta il `customer_id` risolto e **scarta** `email`/`phone`/`code`/`customer_id`/`id` che il modello provasse a passare (test: `test_il_modello_non_puo_scegliere_il_cliente`). "Dammi il saldo di mario.rossi@…" produce quindi, al massimo, il saldo di chi sta scrivendo. `search_products` e `search_giftcards` sono catalogo pubblico e ci sono sempre.
4. **Caso ambiguo**: compare il solo `confirm_identity_by_email(email)`, che passa l'email detta dal cliente **insieme** al telefono fidato: il CRM accetta solo se indicano la stessa anagrafica (regola documentata delle API), quindi l'email restringe e non sostituisce. Senza telefono fidato lo strumento non esiste (`not_applicable`). Riuscita la conferma, il contesto passa a `identified` e al giro successivo compaiono gli strumenti del cliente: per questo `complete_chat` ricalcola l'elenco strumenti a ogni giro.
5. **Minimizzazione**: `limit` è tappato (10 movimenti, 5 ordini, 15 persone, 5 prodotti), l'output di ogni strumento è troncato a 4000 caratteri, e da `get_my_network` vengono tolti email/telefono delle persone invitate (sono di terzi: il cliente li vede nell'app, ma una chat WhatsApp non è l'app). Il prompt chiede inoltre di non ripetere identificativi completi nel messaggio.
6. **Audit senza dati**: ogni strumento eseguito finisce in `CrmContext.lookups` (`{"tool", "ok", "error"}`) e da lì in `metadata_json.crm` dell'audit `AI_GENERATED`/`AI_REGENERATED` insieme a `status`, `identity_source`, `customer_id` CRM. Nessun saldo, nome o contatto viene scritto nell'audit (test: `test_il_riepilogo_per_l_audit_non_contiene_dati_personali`).

### Come entra nel prompt

`generate_ai_reply` (ai.py) chiama `crm_tools.client_for(agent_config)` (None se spento o senza chiave → tutto come prima), poi `prepare()` → `CrmContext`, e passa a `complete_chat` due callable: `tools` (ricalcolato a ogni giro) e `tool_executor`. Il paragrafo su chi è il cliente e cosa può/non può consultare (`system_prompt_section`) va in fondo ai messaggi insieme ai blocchi della Knowledge Base, **non** nel prompt di sistema stabile: cambia da cliente a cliente e nel prefisso romperebbe la cache di OpenAI. `complete_chat` ora è un loop di function calling (`MAX_TOOL_ROUNDS = 4`): finché il modello chiede strumenti li eseguiamo e rimandiamo i risultati; all'ultimo giro gli strumenti vengono tolti così deve rispondere con quel che ha; i token di tutti i giri si sommano in `omni_ai_usage` (è il costo vero della bozza). Un errore del CRM dentro uno strumento **non** alza: torna al modello come `{"error", "message"}` con l'indicazione di dirlo al cliente e proporre che un collega verifichi. "Prova il bot" (`preview_reply`) non ha un cliente, quindi usa il CRM solo per il catalogo: è anche il modo di provare la chiave senza toccare dati di nessuno.

### Configurazione (pagina AI Agent → "CRM Mamify")

- Chiave dal pannello Mamify (*Sviluppatori › API › Chiavi API*, spuntando nel gruppo *Plugins › Mamify › Rag* gli endpoint che servono: tutti i `customer/*` più `products/search` e `giftcards/search`). `PUT /ai-agent` con `crm_api_key` (stringa vuota = rimuovi), `crm_base_url`, `crm_enabled` (400 se si accende senza chiave). **Non** va mai usato il token di un cliente (`X-Fw360-Customertoken`): queste API rispondono solo alla chiave.
- `POST /ai-agent/crm/check` prova la chiave **senza leggere dati di nessuno**: `customer/find` senza identificativi — `customer_identifier_required` = chiave valida e abilitata (`ok`), `wrong_api_key` = `invalid`, `insufficient_permissions` = `no_permission` (endpoint non spuntati sulla chiave). Se il server risponde HTTP 200 con la lista `["status","wrong_endpoint"]` (il dispatcher `/m/api/` di Mamify quando il plugin RAG non e' pubblicato a quell'URL) il check restituisce `error` con un messaggio esplicito: la chiave non viene nemmeno controllata, va chiesto a Mamify di attivare il plugin o l'URL corretto (verificato il 2026-10-26: tutto `https://mamify.app/m/api/...` rispondeva cosi', anche senza chiave).
- **Scheda cliente nell'Inbox** (`customer-crm-card.tsx` → `GET /customers/{id}/crm-profile?channel=`): a richiesta ("Consulta"), mostra la stessa identificazione che vede l'AI (identificato / più account / non in anagrafica / identità non verificabile / CRM non disponibile / integrazione spenta), nome, email, codice invito, saldi Mamix e MamiCash e conteggi della rete. Ogni apertura è una chiamata al CRM e un audit `CRM_PROFILE_VIEWED`; per questo non parte da sola. È il posto dove si capisce perché una bozza dice "non posso fornire dati di account" — e dove, scrivendo telefono o email nella scheda, si collega al CRM un cliente arrivato da Telegram.
- Limiti di frequenza: quelli della chiave (header `X-RateLimit-*`); un 429 arriva al modello come "CRM non disponibile al momento".

### Cosa dire al cliente, per stato

| Stato | L'AI… |
|---|---|
| `identified` | usa gli strumenti quando la domanda lo richiede; per la rete cita nomi e conteggi, mai contatti |
| `ambiguous` | spiega che risultano più profili con il suo numero, chiede l'email di registrazione, poi `confirm_identity_by_email` |
| `not_found` | spiega che il numero non è collegato a un profilo, invita a verificare il numero nell'app; risponde comunque su prodotti e gift card |
| `unverified` | non fornisce dati di account anche se il cliente dà email/telefono; invita a scrivere su WhatsApp dal numero registrato |
| `unavailable` | dice che non può verificare ora e propone che un collega ricontatti |

Test: `tests/integrations/test_omnichannel_crm.py` (normalizzazione numeri, identità fidata, iniezione del `customer_id`, conferma via email con telefono, minimizzazione rete, client HTTP con `httpx.MockTransport`, loop function calling) e `tests/api/test_omnichannel_crm_api.py` (chiave cifrata e mai restituita, check, scheda CRM e isolamento per owner). Migration: `a7d3c9e1f5b2`.

---

## 7. Sicurezza contro invii duplicati e fuori ordine

- **Idempotenza webhook**: vincolo unico `(channel_account_id, external_message_id)` su `omni_messages` (§3) — un evento ricevuto due volte dal canale non crea due messaggi né due generazioni AI.
- **Doppio click su "Approva e invia"**: `OmnichannelDraftService.approve_and_send` fa `SELECT ... FOR UPDATE` sulla riga `omni_ai_drafts`, verifica che lo stato sia ancora approvabile (`PENDING_APPROVAL`/`EDITED`/`HUMAN_REVIEW_REQUIRED`), lo porta subito a `SENDING` e **committa prima** di chiamare l'API esterna (mai un lock DB tenuto aperto durante una chiamata di rete). Una seconda richiesta concorrente legge `SENDING`/`SENT` e viene rifiutata con `409 Conflict` — nessun messaggio può partire due volte da un doppio click.
- **Nessun lock a livello di conversazione** per l'ordine dei messaggi in arrivo quasi simultanei: mitigato dal fatto che il context builder legge sempre lo stato più recente dal database ad ogni generazione (vedi §6) — un limite noto, non un vero lock distribuito, vedi §13.

---

## 8. Webhook e strumento di simulazione

`app/api/v1/omnichannel_webhooks.py`, **router separato** da `omnichannel.py` perché ha un modello di autenticazione diverso:

- `POST /api/v1/omnichannel-responder/webhooks/telegram/{channel_account_id}` — **non autenticato** (Telegram non può inviare il JWT admin). Verificato invece tramite l'header `X-Telegram-Bot-Api-Secret-Token`, confrontato con `omni_channel_accounts.webhook_secret` (vedi §3, §4). Un `channel_account_id` inesistente o di un canale diverso da `telegram` risponde `404` identico in entrambi i casi (mai confermare/negare l'esistenza di un ID a un chiamante non autenticato). Non processa nulla di lento inline: normalizza, salva, e mette in coda `generate_ai_draft_task` — la richiesta HTTP a Telegram torna subito.
- `POST /api/v1/omnichannel-responder/webhooks/maytapi/{channel_account_id}/{webhook_secret}` — **non autenticato**, ed è l'unico webhook di questo file con il segreto **nel path** invece che in un header o in una firma del body. Non è una scorciatoia: Maytapi non firma i payload e il suo `setWebhook` accetta un URL e basta, quindi l'URL è l'unico posto dove un segreto può viaggiare (vedi §4). Stesso trattamento degli altri per il resto: `404` identico per canale inesistente o di tipo diverso, canale disattivo → `200` senza ingestione ma **solo dopo** aver verificato il segreto, e niente lavoro lento inline.
- `POST /api/v1/omnichannel-responder/webhooks/myagi/{channel_account_id}/{webhook_secret}` — **non autenticato**, chiamato dal container `myagi_wa` sull'URL interno `http://api:8000/...` (`MYAGI_WEBHOOK_BASE_URL`), mai da fuori. Segreto nel path come Maytapi, più la firma `X-Webhook-Hmac` (HMAC-SHA512 del corpo grezzo, letto prima del JSON) quando presente. Stesso 404 indistinguibile, stesso `200` senza ingestione a canale disattivo.
- **Pagina myAGI** (`/api/v1/myagi`, autenticata, `app/api/v1/myagi.py`): `GET /status` (gateway configurato/raggiungibile, versione, motore), `GET /sessions` (i canali `whatsapp_myagi` dell'owner con lo stato letto ora dal gateway — `WORKING`, `SCAN_QR_CODE`, `STARTING`, `STOPPED`, `FAILED`, più `MISSING` se mai avviata e `UNAVAILABLE` se il gateway è giù — e lo stato del canale allineato di conseguenza: `connected`/`pending`/`error`, mai toccando `disabled`), `POST /sessions` (crea il canale **e** avvia la sessione con il webhook già configurato), `POST /sessions/{id}/start` (idempotente), `/restart`, `/logout` (scollega il telefono, la sessione resta e torna a chiedere il QR: è il modo per cambiare numero senza perdere le conversazioni), `GET /sessions/{id}/qr` (PNG base64, solo in `SCAN_QR_CODE`; il QR si rinnova ogni ~20 s, la pagina lo richiede ogni 10). Eliminare il canale (`DELETE /channel-accounts/{id}`) elimina anche la sessione sul gateway, best effort. Audit: `MYAGI_SESSION_CREATED`, `MYAGI_SESSION_STARTED`, `MYAGI_SESSION_LOGOUT`.

- `POST /api/v1/omnichannel-responder/dev/simulate-message` — **autenticato** (richiede login admin), ma funziona **solo** su un `omni_channel_accounts` con `channel = "mock"`. Scelta diversa dalla spec originale (che suggeriva un gate su `ENVIRONMENT=development`): questa installazione ha un solo ambiente (produzione), quindi un gate sull'environment renderebbe lo strumento permanentemente inutilizzabile; il gate sul tipo di canale ottiene lo stesso obiettivo di sicurezza (non si può mai iniettare un messaggio falso su un canale reale) restando utilizzabile per testare il flusso end-to-end in qualunque momento.

---

## 9. API REST

Tutti gli endpoint sotto `/api/v1/omnichannel-responder/` (eccetto il webhook Telegram) richiedono `Administrator` autenticato (`Depends(get_current_admin)`) e filtrano sempre per `owner_id = admin.id`.

| Area | Endpoint principali |
|---|---|
| Canali | `GET/POST /channel-accounts` (ogni account annotato con `conversation_count`, `pending_count` — WAITING_APPROVAL o non lette, stessa definizione di `pending-count` — e `unread_count`: una sola query aggregata `GROUP BY channel_account_id`, non una `COUNT` per riga; li usa l'`AccountSwitcher` dell'Inbox, §10), `GET /channel-accounts/supported`, `PUT /channel-accounts/{id}` (aggiorna/completa credenziali dopo la creazione, vedi sotto), `GET /channel-accounts/{id}/status`, `POST /channel-accounts/{id}/register-webhook`, `DELETE /channel-accounts/{id}` |
| Conversazioni | `GET /conversations` (filtri: `status`, `channel`, `channel_account_id`, `assigned_admin_id`, `tag_id`, `search`), `GET /conversations/pending-count` (conteggio per la lucina di notifica in sidebar, vedi §10), `GET /conversations/{id}`, `POST /conversations/{id}/assign\|resolve\|archive`, `DELETE /conversations/{id}` (eliminazione **definitiva**, cascata su messaggi/bozze/note, vedi §3), `POST\|DELETE /conversations/{id}/tags/{tag_id}`, `POST /conversations/{id}/notes`, `POST /conversations/{id}/messages` (invio manuale, bypassa l'AI), `POST /conversations/{id}/generate-draft` (genera bozza a richiesta se `auto_generate_draft=false`, idempotente su click doppi, vedi §3/§5), `POST /broadcast` (messaggio multiplo, max 50 destinatari, vedi §5) |
| Clienti | `GET\|PATCH /customers/{id}`, `POST /customers/{id}/block\|unblock` |
| Tag | `GET\|POST /tags` |
| Bozze AI | `PATCH /drafts/{id}`, `POST /drafts/{id}/approve\|regenerate\|reject` |
| AI Agent | `GET\|PUT /ai-agent` (`PUT` valida `response_mode` contro i 3 valori ammessi e registra un `AI_RESPONSE_MODE_CHANGED` ad ogni cambio, vedi §3) |
| Knowledge Base | `GET\|POST /knowledge-base`, `GET /knowledge-base/find` (ricerca avanzata, §3), `GET\|PUT\|DELETE /knowledge-base/{id}`, `POST /knowledge-base/upload\|move\|search\|reindex`, `GET\|POST /knowledge-base/companies`, `PUT\|DELETE /knowledge-base/companies/{id}` |
| Notifiche | `GET /notifications`, `POST /notifications/{id}/read` |
| Analytics | `GET /analytics` — conteggi + `ai_acceptance_rate`/`ai_edit_rate`/`ai_rejection_rate` (bozze approvate senza modifiche / modificate / scartate, sul totale delle bozze arrivate a uno stato finale) |
| Webhook/dev | `POST /webhooks/telegram/{channel_account_id}` (pubblico), `POST /webhooks/maytapi/{channel_account_id}/{webhook_secret}` (pubblico, segreto nel path — vedi §8), `GET\|POST /webhooks/{facebook\|instagram\|whatsapp}/{channel_account_id}` (pubblico — `GET` è l'handshake di verifica di Meta, `POST` riceve i messaggi, stessa logica condivisa per tutti e tre via `_meta_webhook_verify`/`_meta_webhook_receive`), `POST /dev/simulate-message` (vedi §8) |

Schema Pydantic completo in fondo a `app/schemas/schemas.py` (sezione `# Omnichannel Responder`).

---

## 10. Frontend

`app/(dashboard)/omnichannel-responder/`:

- **`page.tsx`** — layout dell'inbox: `InboxToolbar` a tutta larghezza sopra, poi una griglia a 3 colonne sotto (`_components/conversation-list.tsx`, `chat-panel.tsx`, `customer-panel.tsx`, `ai-draft-card.tsx`). Lo stato dei filtri (ricerca, stato conversazione) e la query `useConversations` vivono qui, non dentro `conversation-list.tsx`; il filtro per account collegato (`channel_account_id`) invece vive **nell'URL** come `?account=<id>` (dal 2026-10-26, `useSearchParams` dentro un `<Suspense>`), cosi' la pagina myAGI (bottone "Inbox" su ogni numero) e qualunque altro punto possono aprire "l'Inbox di questo numero soltanto" con un semplice link. L'ultimo account scelto e' ricordato in `localStorage` (`omni.inbox.account`) e ripristinato alla prossima apertura senza parametro: e' una comodita' per browser, l'URL vince sempre. Cambiare account chiude la conversazione aperta, perche' potrebbe appartenere a un altro numero — sia la toolbar che la lista renderizzano a partire dagli stessi dati, passati come props (ristrutturato il 2026-08-15: prima erano tutti dentro la colonna lista, stipati in 300px di larghezza).
- **`inbox-toolbar.tsx`** — barra strumenti sopra la griglia (non più dentro la colonna lista, per darle spazio orizzontale vero): titolo "Inbox" + contatore, campo ricerca, filtro stato, bottone aggiorna, icona 📣 broadcast, e come primo elemento della riga l'**`AccountSwitcher`** (`_components/account-switcher.tsx`, dal 2026-10-26 al posto della vecchia riga di pillole, che non reggeva molti numeri): un bottone che mostra sempre su quale account si sta lavorando (nome, numero di telefono o id esterno, quante conversazioni da gestire) e apre una tendina con "Tutti i canali" piu' **un elemento per ogni account collegato** (non per tipo: due bot Telegram o due numeri WhatsApp sarebbero altrimenti indistinguibili, si filtra per `channel_account_id`, non per `channel`). Ogni riga ha `ChannelIcon`, nome, numero/etichetta, totale conversazioni e un badge ambra con `pending_count` (bozze da approvare + non lette, stessa definizione del pallino in sidebar, vedi `GET /channel-accounts`), cosi' si vede dove c'e' lavoro prima di cambiare filtro. Una "X" accanto al bottone torna a "Tutti"; con il filtro attivo appare sotto la riga una frase che ricorda che le altre conversazioni sono nascoste e che le risposte partono da quel numero. Se l'URL punta a un account che non esiste piu', il bottone lo dice ("Canale non trovato") invece di mostrare una lista vuota senza spiegazione. Per i numeri WhatsApp il sottotitolo e' il telefono formattato da `external_account_id`: per myAGI lo scrive `api/v1/myagi.py::_to_response` appena il gateway riporta la sessione `WORKING`. Icona 📣 apre `BroadcastDialog` — composizione del testo, poi scelta tra "Tutti in Inbox" o selezione manuale da una lista con checkbox, poi un riepilogo con l'elenco di eventuali destinatari falliti e il motivo (utile soprattutto per capire chi è fuori dalla finestra 24h di WhatsApp/Meta, vedi §5). **Attenzione se tocchi questo componente**: ogni bottone che chiude il dialog (X nativa, "Annulla", "Chiudi" sul riepilogo finale) deve passare da un'unica funzione `handleClose()` che chiama sia `onOpenChange(false)` sia il reset dello stato interno — un bottone che chiamasse `onOpenChange(false)` direttamente (bypassando `handleClose`) chiuderebbe il dialog senza resettarlo, mostrando il riepilogo del giro precedente alla riapertura successiva (bug reale riscontrato e corretto).
- **`conversation-list.tsx`** — solo presentazione, riceve `conversations`/`isLoading`/`selectedId`/`onSelect` come props da `page.tsx` (nessuna query o stato filtri propri). Ogni riga mostra lo `StatusBadge` dello stato (`NEW`/`OPEN`/`AI_PROCESSING`/`WAITING_APPROVAL`/`WAITING_CUSTOMER`/`RESOLVED`/`ARCHIVED`/`SPAM`) su una riga propria, ben visibile, non solo aprendo la conversazione — così si vede a colpo d'occhio quali richiedono un'azione (`WAITING_APPROVAL`) senza doverle aprire una per una. Mostra anche `channel_account_name` (non solo l'icona del tipo canale) accanto all'anteprima dell'ultimo messaggio — stesso principio della toolbar sopra, per distinguere due account dello stesso tipo canale. L'header della chat aperta (`chat-panel.tsx`) mostra `channelLabel(channel)` **e** `channel_account_name` insieme (es. "Telegram · Bot Assistenza Prodotto A") — `OmniConversationDetailResponse.channel_account_name`, aggiunto apposta perché in precedenza il dettaglio conversazione aveva solo `channel_account_id` (un UUID, inutile in UI) e non il nome leggibile già presente invece in `OmniConversationListItem`. La bozza AI attiva (se presente) appare inline nella chat con i pulsanti Approva e invia / Copia / Rigenera / Scarta, textarea modificabile.
- **`channels/page.tsx`** — lista canali, dialog di creazione (campi diversi per canale: Telegram un token, i tre canali Meta due segreti + Phone Number ID solo per WhatsApp, Gmail indirizzo + App Password), registrazione webhook automatica per Telegram, dialog "Info webhook" condiviso per Facebook/Instagram/WhatsApp (`MetaWebhookInfoDialog`), strumento "Simula messaggio" sui canali mock. Ogni campo credenziale (Bot Token, Access Token, App Secret, App Password) usa `components/ui/password-input.tsx` (`PasswordInput`) invece del semplice `Input type="password"` — un wrapper con un'iconetta 👁️ che alterna in chiaro/nascosto ciò che si sta digitando, per evitare di salvare un token con un errore di battitura senza accorgersene. Nuovo componente condiviso, riusabile da qualunque altro campo password del progetto in futuro (oggi usato solo qui). Le credenziali dei canali Meta (Access Token/App Secret/Phone Number ID) sono **opzionali alla creazione**, non solo nello schema ma anche nella validazione del form: un canale WhatsApp/Facebook/Instagram può essere creato con il solo nome, per ottenere subito `webhook_secret` (serve per la schermata Webhooks di Meta) prima ancora di avere le credenziali reali — Meta stessa richiede di passare dalla propria API Setup per ottenerle, un passaggio indipendente e non sequenziale rispetto al webhook. Gmail non ha questo problema di bootstrap (nessun webhook da registrare, vedi §4/§11) quindi indirizzo e App Password sono **richiesti subito**, validati lato form prima di inviare la richiesta. Le credenziali si completano/ruotano dopo con l'icona 🔑 "Modifica credenziali" (`edit-credentials-dialog.tsx` → `PUT /channel-accounts/{id}`, vedi tabella endpoint sopra) — campi lasciati vuoti non sovrascrivono quelli già salvati (stessa convenzione di `AISettingsUpdateRequest`), e cambiare solo l'App Secret non richiede di reinserire l'Access Token: `OmnichannelService.update_channel_account` decifra il blob esistente e aggiorna solo la chiave cambiata.
- **`settings/page.tsx`** — configurazione AI Agent (prompt, tono, lingua, argomenti, categorie sensibili a chip cliccabili, slider "Creatività" per `temperature`, interruttore "Generazione automatica della bozza AI" per `auto_generate_draft` — normale, parte del salvataggio batch col pulsante "Salva", non serve conferma: a differenza dell'invio automatico, disattivarla non fa mai partire un messaggio da sola). In cima alla pagina, un riquadro ben visibile (bordo/sfondo colorato quando acceso, icona diversa) con l'interruttore per l'**autorisponditore automatico** (`response_mode`): a differenza degli altri campi si salva **subito** al click (non con il pulsante "Salva" generico, per non lasciarlo in uno stato "modificato ma non salvato" ambiguo su un'impostazione così delicata), e accenderlo richiede una conferma esplicita in un dialog dedicato — spegnerlo invece è immediato, senza conferma.
- **`chat-panel.tsx`** — all'apertura di una conversazione il thread parte già scrollato in fondo, sull'ultimo messaggio del cliente e sulla bozza AI (ref `threadRef` + `useEffect` che imposta `scrollTop = scrollHeight`); lo stesso scroll scatta quando cambia l'ultimo messaggio, la bozza attiva o il numero di note, cioè quando arriva davvero qualcosa di nuovo. Il polling ogni 4s non modifica queste dipendenze se nulla è cambiato, quindi non riporta in fondo l'operatore che sta rileggendo messaggi vecchi. Prima (fino al 2026-10-25) il thread si apriva in cima alla cronologia e bisognava scorrere a mano con la barra ad ogni conversazione aperta.
- **`chat-panel.tsx`** — quando non c'è una bozza attiva e l'ultimo messaggio è del cliente (nessuna bozza generata automaticamente, `auto_generate_draft=false`), mostra un pulsante "Genera risposta AI" al posto di `AIDraftCard` — la stessa `POST /conversations/{id}/generate-draft` sincrona di §9, con feedback immediato in UI. Accanto al testo "Nessuna bozza AI generata automaticamente..." c'è anche un link diretto a `settings/page.tsx` che spiega come accendere `auto_generate_draft` in modo permanente, con l'avviso esplicito di premere "Salva" dopo — aggiunto perché non era ovvio che questa specifica impostazione richiede il salvataggio a differenza di `response_mode` sopra, che si salva da solo al click.
- **`knowledge-base/page.tsx`** — aziende come cartelle, caricamento file, istruzioni, "Prova il bot". La casella di ricerca ha due modi: **Rapida** filtra l'elenco mentre si scrive (`?q=`, ILIKE su titolo/file/testo); **Avanzata** parte con Invio o "Cerca" e chiama `GET /knowledge-base/find`: i risultati prendono il posto dell'elenco nella scheda Documenti e in quella Istruzioni, ogni riga è la solita `DocumentRow` (quindi selezione, sposta, modifica, elimina funzionano anche lì) con sotto il motivo ("nome del file", "parole nel testo", "significato (AI)") e i passaggi trovati, con le parole cercate evidenziate (`Highlight`). La ricerca è una `useQuery` sotto la chiave della Knowledge Base, così caricare o spostare un documento la aggiorna come l'elenco.

**Nessun WebSocket/SSE**: l'intero progetto non ha alcuna infrastruttura realtime preesistente (verificato prima di iniziare). L'inbox si aggiorna via **polling** con TanStack Query (`refetchInterval`: 8s per la lista conversazioni, 4s per la conversazione aperta, 15s per le notifiche) — coerente con il resto della dashboard, nessuna nuova infrastruttura introdotta per questo modulo. Se in futuro serve un aggiornamento realtime, andrebbe introdotto come una scelta architetturale a parte, non implicita in questo modulo.

Nuovi file: `services/omnichannel.ts` (chiamate fetch), `hooks/use-omnichannel.ts` (React Query), entrambi seguono esattamente lo stesso pattern di `services/channels.ts` / `hooks/use-channels.ts` già esistenti.

**Lucina di notifica nel menu**: la voce "Inbox" nella sidebar (presente su ogni pagina della dashboard, non solo quelle di questo modulo) mostra un puntino rosso sull'icona quando `GET /conversations/pending-count` (owner-scoped, una singola query `COUNT`) è maggiore di zero — conta le conversazioni con bozza da approvare (`WAITING_APPROVAL`) **o** messaggi non letti (`unread_count > 0`, incluse conversazioni "vecchie" già gestite in cui il cliente ha scritto di nuovo). `components/navigation/app-sidebar.tsx::usePendingCount()` interroga ogni 20s, indipendentemente dal fatto che l'Inbox sia aperta — è per questo che serve un endpoint dedicato leggero (solo un numero) invece di riusare `GET /conversations` per intero. Il tooltip al passaggio del mouse mostra anche il numero esatto ("Inbox (3 da gestire)").

Un pulsante di refresh manuale (icona ⟳) è disponibile accanto alla ricerca conversazioni, giusto per rassicurazione visiva — non necessario funzionalmente (il polling a 8s è già sufficiente), e comunque **impossibile da estendere a un vero "scarica cronologia"**: l'API Bot di Telegram non ha alcun endpoint per recuperare messaggi passati, riceve solo gli eventi arrivati dopo la registrazione del webhook.

**Attenzione per ogni futura colonna scrollabile aggiunta a questo modulo**: le tre colonne dell'inbox (`conversation-list.tsx`, `chat-panel.tsx`, `customer-panel.tsx`) sono celle di una griglia CSS. Dal 2026-08-15 l'altezza fissa (`h-[calc(100vh-4rem)]` + `overflow-hidden`) è sul wrapper più esterno di `page.tsx`, che contiene `InboxToolbar` (altezza naturale) e sotto la griglia a 3 colonne (`min-h-0 flex-1`, non più l'elemento con l'altezza fissa diretta — quella ora è sul wrapper). Sia i figli flex (`flex-1`) sia le celle di griglia hanno di default `min-height: auto`, cioè **non si restringono mai sotto l'altezza del loro contenuto** anche con `overflow-y-auto` impostato — con molti messaggi/conversazioni/note, il contenitore cresce oltre l'area visibile invece di scorrere al suo interno, e la parte sotto (bozza AI, pulsanti di approvazione, composer) finisce fuori schermo e irraggiungibile (bug reale riscontrato e corretto). La correzione è `min-h-0` su ogni contenitore flex/griglia che deve restare vincolato all'altezza del genitore, dalla griglia stessa fino al root `flex h-full ...` di ogni colonna e al div interno `flex-1 overflow-y-auto` — senza `min-h-0` a ogni livello, `overflow-y-auto` da solo non basta.

**Attenzione per ogni futuro `<Select>` aggiunto a questo modulo**: il componente `Select` di questo progetto (`components/ui/select.tsx`, base-ui) mostra il **valore grezzo** nel trigger invece dell'etichetta se non gli viene passata esplicitamente la prop `items` (una mappa `{value, label}[]`) — comportamento già documentato nel commento di `components/shared/filter-bar.tsx::FilterSelect`, ma inizialmente dimenticato in 4 punti di questo modulo (filtro stato conversazioni, tono/lingua nell'AI Agent, tipo canale nella creazione, selettore tag — corretto). Per un filtro con opzione "Tutti", riusa `FilterSelect`; per un `<Select>` normale, passa sempre `items={OPTIONS}` insieme a `value`/`onValueChange`.

---

## 11. Configurazione e come collegare Telegram / Facebook / Instagram / WhatsApp / Maytapi / myAGI / Gmail

**Nessuna nuova variabile `.env` obbligatoria** (fa eccezione il gateway myAGI, facoltativo: `MYAGI_WA_URL`, `MYAGI_WA_API_KEY`, `MYAGI_WEBHOOK_BASE_URL`, vedi sotto). Il modulo riusa `OPENAI_API_KEY`/`OPENAI_MODEL` (o la chiave configurata dalla pagina Impostazioni, stessa precedenza di [DATABASE.md §9](./DATABASE.md#9-impostazioni-ai)) e il `DATABASE_URL`/`REDIS_URL` già esistenti.

Per collegare un bot Telegram:

1. Crea un bot con [@BotFather](https://t.me/BotFather) su Telegram, copia il token (`123456:ABC-DEF...`).
2. Dashboard → Omnichannel Responder → Canali → "Nuovo canale" → tipo `Telegram`, incolla il token.
3. Sulla riga del canale appena creato, icona 🔗 "Registra webhook" → incolla l'URL pubblico HTTPS di **questa API** (es. `https://api.46-225-185-149.sslip.io`, lo stesso vhost `api.*` di [DEPLOYMENT.md §9](./DEPLOYMENT.md#9-dominio-e-https-consigliato-richiesto-per-pubblicare-fotovideo-su-buffer)). Il backend chiama `setWebhook` verso Telegram con l'URL `<public_base_url>/api/v1/omnichannel-responder/webhooks/telegram/<channel_account_id>`.
4. Scrivi al bot da Telegram: il messaggio deve comparire nell'Inbox entro pochi secondi, seguito dalla bozza AI (se una chiave OpenAI è configurata).

Per testare senza un bot reale: crea un canale di tipo `Test (mock)`, poi usa l'icona ▶ "Simula messaggio" sulla sua riga.

Per collegare il **proprio numero WhatsApp** (Maytapi) — la strada più corta, nessuna approvazione di Meta:

1. Su [console.maytapi.com](https://console.maytapi.com) crea un'istanza e collega il numero scansionando il **QR code** dal telefono, come si fa con WhatsApp Web. Il telefono deve restare acceso e connesso: è quello che tiene viva la sessione.
2. Sempre dalla console, Settings → Token: copia **Product ID**, **Phone ID** e **API Token**.
3. Dashboard → Omnichannel Responder → Canali → "Nuovo canale" → tipo `WhatsApp — numero personale (Maytapi)`, incolla i tre valori. A differenza dei canali Meta si chiedono subito: stanno tutti sulla stessa pagina della console, non c'è il problema di dover creare il canale prima per ottenere il `webhook_secret`.
4. Sulla riga del canale, icona 🔗 "Registra webhook" → incolla l'URL pubblico HTTPS di questa **API** (il vhost `api.*`, lo stesso usato da Telegram). **Non il dominio della dashboard**: `agipostapp.mamify.ai` proxa solo verso il container `dashboard`, sotto non c'è l'API, e un webhook puntato lì riceve 404 su ogni messaggio. Il backend chiama `setWebhook` verso Maytapi con `<public_base_url>/api/v1/omnichannel-responder/webhooks/maytapi/<channel_account_id>/<webhook_secret>`. **Il webhook è per prodotto**: registrandolo sostituisci quello di tutti i numeri dello stesso Product ID.
5. Scrivi al numero da un altro telefono: il messaggio deve comparire nell'Inbox in pochi secondi, seguito dalla bozza AI.

Da lì in poi il flusso è identico a ogni altro canale — bozza AI, approvazione umana obbligatoria per default, argomenti sensibili sempre a revisione manuale (§5). L'icona 🔄 "Verifica connessione" sulla riga del canale interroga `/status` di Maytapi e dice se il telefono è ancora appaiato: una sessione collegata via QR cade da sola (telefono spento a lungo, logout dall'app), e senza quel controllo la prima avvisaglia sarebbe una risposta che non parte.

Per collegare il **proprio numero WhatsApp sul gateway myAGI** (stesso risultato di Maytapi, senza canone, 2026-10-26):

1. In `.env`: `MYAGI_WA_URL=http://myagi_wa:3000`, `MYAGI_WA_API_KEY=<stringa casuale lunga>`, `MYAGI_WEBHOOK_BASE_URL=http://api:8000`. Poi `docker compose -f docker-compose.prod.yml up -d myagi_wa` e ricrea `api`/`worker` perché leggano le variabili. Il container non pubblica porte: ci parla solo l'API.
2. Dashboard → **myAGI** (voce nel gruppo Omnichannel Responder). Il riquadro in alto dice se il gateway è raggiungibile e con quale versione.
3. "Nuovo numero" → un nome (es. "Assistenza clienti") → "Crea e mostra QR". Nasce un canale `WhatsApp (myAGI)` in Canali e una sessione sul gateway; dopo pochi secondi compare il QR.
4. Sul telefono: WhatsApp → Impostazioni → Dispositivi collegati → Collega un dispositivo → inquadra. Lo stato passa a **Collegato** con numero e nome profilo. Nessun webhook da registrare: la sessione nasce già puntata all'API.
5. Scrivi al numero da un altro telefono: il messaggio compare nell'Inbox con l'etichetta "WhatsApp (myAGI)" e segue il flusso di ogni altro canale.

"Scollega" toglie il telefono dai dispositivi collegati e riporta la sessione al QR (per cambiare numero senza perdere le conversazioni); "Riavvia" per una sessione in errore; il cestino elimina canale e sessione. Usa un **numero dedicato**, non quello del titolare: è un client non ufficiale e WhatsApp può limitare il numero, esattamente come con Maytapi. Il telefono deve collegarsi a internet almeno ogni due settimane, come per WhatsApp Web. Quando Meta cambia protocollo e i messaggi smettono di arrivare, aggiornare l'immagine (`docker compose pull myagi_wa && docker compose up -d myagi_wa`) è il primo rimedio.

Per collegare una Pagina Facebook (Messenger) — più passaggi di Telegram, alcuni richiedono l'approvazione di Meta:

1. Su [developers.facebook.com](https://developers.facebook.com) crea un'app (tipo "Business"), aggiungi il prodotto **Messenger**.
2. Collega la tua Pagina Facebook all'app e genera un **Page Access Token** (Messenger → Impostazioni Messenger → Generate Token, sotto "Access Tokens").
3. Copia l'**App Secret** da App Dashboard → Impostazioni → Basic.
4. Dashboard → Omnichannel Responder → Canali → "Nuovo canale" → tipo `Facebook Messenger`, incolla Page Access Token e App Secret.
5. Sulla riga del canale appena creato, icona ℹ️ "Info webhook" → incolla l'URL pubblico HTTPS di questa API → copia l'**URL di callback** e il **Verify Token** mostrati.
6. Su Meta: Messenger → Impostazioni → Webhooks → "Aggiungi URL callback", incolla i due valori, poi **iscrivi la Pagina all'evento `messages`** nella stessa schermata (passaggio facile da dimenticare — senza, il webhook risulta verificato ma non arriva mai nulla).
7. **Prima di poter rispondere a clienti reali** (chiunque non sia un Tester/Admin dell'app), l'app deve superare l'**App Review** di Meta per il permesso `pages_messaging` — richiede Business Verification, può richiedere giorni. Finché l'app è in modalità sviluppo, puoi comunque testare scrivendo alla Pagina da un account aggiunto come Tester/Admin nell'app Meta.

Per collegare Instagram Direct — **stessa app Meta di Facebook**, non serve crearne una seconda:

1. Nell'app Meta già creata per Facebook, collega un account Instagram **professionale** (Business/Creator) alla stessa Pagina Facebook (Impostazioni Pagina → Account collegati, lato Instagram) e assicurati che il prodotto **Messenger** dell'app abbia il permesso Instagram abilitato.
2. Dashboard → Canali → "Nuovo canale" → tipo `Instagram Direct` → stessi due valori di Facebook (Access Token, App Secret) — può essere lo stesso Page Access Token se la Pagina è la stessa.
3. Icona ℹ️ "Info webhook" → questa volta l'URL punta a `.../webhooks/instagram/<id>` invece di `.../webhooks/facebook/<id>` — usa quello, non riusare l'URL di Facebook.
4. Stessa App Review di Meta richiesta (permesso `instagram_manage_messages`) prima di rispondere a clienti reali.

Per collegare un numero WhatsApp Business — configurazione a parte, API diversa (Cloud API, non Send API):

1. Nella stessa app Meta, aggiungi il prodotto **WhatsApp**, collega o crea un numero da [WhatsApp Manager](https://business.facebook.com/wa/manage).
2. Genera un **access token** permanente (System User con permesso `whatsapp_business_messaging`, da Meta Business Suite → Impostazioni Business → Utenti di sistema — un token temporaneo di test scade in 24h ed è utile solo per una prova rapida).
3. Copia il **Phone Number ID** (non il numero di telefono stesso) da WhatsApp Manager → il tuo numero → API Setup.
4. Dashboard → Canali → "Nuovo canale" → tipo `WhatsApp Business`, incolla Access Token, Phone Number ID e App Secret.
5. Icona ℹ️ "Info webhook" → URL `.../webhooks/whatsapp/<id>` → incollalo in Meta App Dashboard → WhatsApp → Configuration → Webhook, iscrivendo il campo `messages`.
6. **Limite non implementato**: risposte libere solo entro 24h dall'ultimo messaggio del cliente (vedi §4) — nessun messaggio-template pre-approvato gestito da questo modulo.
7. Stessa App Review di Meta richiesta (`whatsapp_business_messaging`) prima di poter scrivere a numeri reali fuori dalla lista dei numeri di test.

Per collegare Gmail — nessuna app/progetto Google Cloud richiesto, solo una App Password (vedi §4 per il perché di questa scelta invece della vera Gmail API):

1. Sull'account Gmail da collegare, attiva la **verifica in due passaggi** (Account Google → Sicurezza), se non è già attiva.
2. Genera una **App Password** (Account Google → Sicurezza → Password per le app) — non è la password normale dell'account, è una stringa di 16 caratteri dedicata.
3. Dashboard → Omnichannel Responder → Canali → "Nuovo canale" → tipo `Gmail`, inserisci l'indirizzo Gmail e incolla la App Password. Entrambi sono richiesti subito alla creazione (a differenza dei canali Meta, qui non c'è alcuna schermata webhook da compilare in un secondo momento).
4. Nessun passaggio di registrazione webhook: il canale viene letto da `poll_gmail_channels_task` (Celery beat, ogni 2 minuti) fin dalla creazione. Il primo giro legge solo la posta **non letta** al momento del collegamento (non fa backfill dell'intera casella); da lì in poi tiene traccia della propria posizione con un cursore IMAP (`config_json.last_uid`), indipendente dal flag "letto/non letto" reale della casella.
5. Scrivi all'indirizzo Gmail collegato: il messaggio deve comparire nell'Inbox entro ~2 minuti, seguito dalla bozza AI (se una chiave OpenAI è configurata).

---

## 12. Sicurezza

- **Isolamento dati**: ogni query filtra per `owner_id`, vedi §2. Nessun endpoint accetta un `owner_id` dal client — è sempre derivato dall'admin autenticato.
- **Token canale cifrati a riposo**: stesso `EncryptionService` (Fernet) usato per i token Buffer, mai restituiti da nessun endpoint.
- **Webhook Telegram non autenticato ma verificato**: header secret-token confrontato con un valore casuale per-canale (§8), non un segreto condiviso globale.
- **Un solo percorso di invio**: nessun percorso di codice chiama `Connector.send_message` se non `OmnichannelDraftService.approve_and_send` — sia che parta da un click umano (`admin` valorizzato) sia che parta dall'autorisponditore automatico (`admin=None`, vedi §5), è la stessa funzione, con lo stesso row-lock anti-doppio-invio.
- **`AUTO_REPLY` è opt-in, mai il default**: ogni nuovo `OmniAIAgentConfig` nasce con `response_mode="APPROVAL_REQUIRED"` (§3); passare ad `AUTO_REPLY` richiede un'azione esplicita dell'amministratore dalla pagina AI Agent, con una conferma dedicata prima di attivarlo, ed è sempre reversibile con un click. Ogni cambio produce un audit log dedicato (`AI_RESPONSE_MODE_CHANGED`).
- **Categorie sensibili sempre più forti di `AUTO_REPLY`**: una bozza `HUMAN_REVIEW_REQUIRED` non viene mai auto-inviata, indipendentemente da `response_mode` — il controllo è esplicito nel codice (`generate_draft_for_message`), non delegato a un'impostazione che potrebbe essere disattivata per errore.
- **Eliminazione conversazione irreversibile**: `DELETE /conversations/{id}` è un hard delete reale (nessun soft-delete/cestino per questo modulo, a differenza di Blog Writer AI) — confermato lato frontend con un dialog esplicito che elenca cosa verrà perso, e registrato in `omni_audit_logs` (`CONVERSATION_DELETED`) *prima* della cancellazione, perché dopo la riga non esiste più da interrogare.
- **Blocco cliente non nasconde nulla**: un cliente bloccato può ancora scrivere e il messaggio resta salvato — si blocca solo la generazione automatica di bozze AI, non la ricezione. Un operatore può sempre vedere/rispondere manualmente a un cliente bloccato.

---

## 13. Limiti noti di questa v1

- **Tutti e 6 i canali (Telegram, Facebook, Instagram, WhatsApp, Gmail, mock) sono implementazioni reali** — non esiste più alcun connettore-stub in questo modulo (§4). Per i tre canali Meta, prima di poter rispondere a clienti reali (non solo Tester/Admin dell'app), serve comunque l'**App Review** di Meta per il permesso corrispondente (`pages_messaging`, `instagram_manage_messages`, `whatsapp_business_messaging`, vedi §11) — il codice è pronto e verificato, ma l'approvazione di Meta è un passaggio esterno che l'amministratore deve completare per conto proprio, può richiedere giorni.
- **WhatsApp: nessun messaggio-template per fuori dalla finestra di 24h** (§4, §11) — solo risposte libere entro 24 ore dall'ultimo messaggio del cliente, come previsto dalla WhatsApp Cloud API.
- **Gmail: ricezione a polling, non push** (§4, §5) — fino a ~2 minuti di ritardo tra l'arrivo di una mail e la sua comparsa in Inbox, contro i pochi secondi degli altri canali basati su webhook. Nessun limite di invio applicato lato codice: Gmail stesso limita un account personale a 500 invii/giorno (2000/giorno su Google Workspace) — non rilevante per un inbox di supporto con risposte 1:1, ma da tenere presente.
- **Knowledge Base: le bozze vere cercano in tutte le aziende** (§3, §6) — il filtro per azienda del RAG esiste ma lo usano solo "Prova il bot" e la ricerca avanzata; non c'è ancora un collegamento canale/cliente → azienda che lo applichi alle conversazioni in arrivo. Gli embedding stanno in `bytea` confrontati in numpy: va bene fino a qualche decina di migliaia di blocchi per proprietario, oltre servirebbe `pgvector`.
- **Nessun WebSocket/SSE**: aggiornamento via polling (§10), coerente col resto della piattaforma ma non istantaneo (fino a qualche secondo di ritardo).
- **Nessun lock a livello di conversazione** per messaggi in arrivo quasi simultanei (§7) — mitigato ma non eliminato dal fatto che il contesto è sempre letto fresco dal database.
- **`response_mode: MANUAL` non ha ancora un comportamento distinto** da `APPROVAL_REQUIRED` — la bozza AI viene sempre generata ad ogni messaggio in arrivo; `MANUAL` (nessuna generazione AI, solo risposta manuale) non è ancora implementato, solo accettato dallo schema.
- **Nessuna eccezione di orario/giorno per l'autorisponditore**: acceso o spento, `AUTO_REPLY` vale sempre, 24 ore su 24 - non esiste ancora una fascia oraria configurabile (es. "autorisponditore solo fuori orario ufficio").
- **Download allegati non implementato**: `Connector.download_attachment()` esiste nell'interfaccia ma nessuna implementazione la usa ancora — un messaggio con foto/video/audio viene salvato con `message_type` corretto e il riferimento file Telegram in `metadata_json`, ma il file non viene scaricato/servito.
- **Nessun round-robin/team di assegnazione**: solo assegnazione manuale (`assigned_admin_id`), niente logica di smistamento automatico per reparto/lingua/canale.
- **Nessun merge contatti**: se un cliente scrive la prima volta con dati diversi (es. nome cambiato), non viene proposto automaticamente alcun merge tra `omni_customers` esistenti.
- **Nessun test pytest automatico aggiunto**: stesso stato del resto del progetto (vedi [BLOG_WRITER.md §9](./BLOG_WRITER.md#9-limiti-noti-di-questa-v1)) — verificato manualmente end-to-end contro il database di produzione (import Python, generazione schema OpenAPI, migration applicata, container ricostruiti e verificati via `curl` attraverso Nginx).
