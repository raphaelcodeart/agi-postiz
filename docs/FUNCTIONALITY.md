# Funzionalità del sistema

Cosa fa **davvero**, oggi, questo software — non un elenco di intenzioni, ma il comportamento effettivo del codice in `apps/api` e `apps/dashboard`. Utile per capire il sistema senza doverlo rileggere da zero, e per chiunque (persona o Claude Code) debba ricostruirlo identico su un nuovo server dopo aver applicato le migration ([DATABASE.md](./DATABASE.md)) e completato il deploy ([DEPLOYMENT.md](./DEPLOYMENT.md)).

Se modifichi il comportamento descritto qui, aggiorna questo file nello stesso commit (AGENTS.md, regola 20).

Il modulo **Blog Writer AI** (generazione articoli, siti WordPress, pubblicazione) è documentato separatamente in [BLOG_WRITER.md](./BLOG_WRITER.md) essendo un modulo isolato con proprie tabelle/endpoint/pagine — questo file copre solo la piattaforma campagne/Buffer preesistente.

Il modulo **Omnichannel Responder** (inbox AI multicanale con approvazione umana obbligatoria) è documentato separatamente in [OMNICHANNEL_RESPONDER.md](./OMNICHANNEL_RESPONDER.md), anch'esso un modulo isolato con proprie tabelle/endpoint/pagine, collegato al resto della piattaforma solo tramite `owner_id`.

Il modulo **Statistiche** (dashboard persistita delle metriche Buffer per promoter/canale/campagna) è documentato separatamente in [STATISTICS.md](./STATISTICS.md), anch'esso isolato con proprie tabelle, collegato al resto della piattaforma solo tramite foreign key in sola lettura.

---

## Indice

1. [Architettura in breve](#1-architettura-in-breve)
2. [Autenticazione amministratori](#2-autenticazione-amministratori)
3. [Utenti, gruppi e canali](#3-utenti-gruppi-e-canali)
4. [Integrazione Buffer: mock vs production](#4-integrazione-buffer-mock-vs-production)
5. [Campagne: targeting e testo](#5-campagne-targeting-e-testo)
6. [Ciclo di vita di una pubblicazione](#6-ciclo-di-vita-di-una-pubblicazione)
7. [Rate limiting verso Buffer](#7-rate-limiting-verso-buffer)
8. [Task in background (Celery)](#8-task-in-background-celery)
9. [Endpoint API](#9-endpoint-api)
10. [Metriche](#10-metriche)
    - 10.1 [Bacheca (feed pubblico delle pubblicazioni)](#101-bacheca-feed-pubblico-delle-pubblicazioni)
    - 10.2 [Modulo Statistiche (dati persistiti)](#102-modulo-statistiche-dati-persistiti)
11. [Media](#11-media)
12. [Impostazioni runtime](#12-impostazioni-runtime)
13. [Cose note come non finite o legacy](#13-cose-note-come-non-finite-o-legacy)

---

## 1. Architettura in breve

```
Next.js dashboard (apps/dashboard)
   → proxy BFF same-origin (app/api/backend/[...path])
      → FastAPI (apps/api), Postgres (fonte di verità), Redis (rate limit + broker Celery)
         → Celery worker (esegue i task) + Celery beat (pianifica i task periodici)
            → Buffer (mock in sviluppo, reale in produzione)
```

Per i dettagli di deploy/infrastruttura vedi [DEPLOYMENT.md](./DEPLOYMENT.md); per lo schema dati vedi [DATABASE.md](./DATABASE.md). Questo file copre solo il *comportamento*.

---

## 2. Autenticazione amministratori

- `POST /api/v1/auth/login` — email + password, verificata con Argon2 (`SecurityService`), ritorna un JWT HS256 valido `ACCESS_TOKEN_EXPIRE_MINUTES` (default 7 giorni).
- `GET /api/v1/auth/me` — ritorna l'amministratore autenticato.
- Ogni altro endpoint richiede il JWT (dependency `get_current_admin`).
- La dashboard verifica lo stesso JWT lato server nelle sue route BFF (`SECRET_KEY` deve essere identica tra `apps/api` e `apps/dashboard`).
- Gli **utenti** (`users`) non fanno mai login: sono gestiti dagli amministratori, non un ruolo applicativo.

---

## 3. Utenti, gruppi e canali

- Un `User` è un cliente/amico i cui canali social vengono pubblicati tramite il **suo** account Buffer personale.
- `status` di un utente (`active`/`inactive`/`suspended`) e `deleted_at` (soft delete) determinano se è targetabile: solo utenti `active` e non cancellati entrano nella risoluzione di una campagna.
- I `UserGroup` sono raggruppamenti arbitrari (many-to-many) usati solo per il targeting, non per permessi.
- Un `SocialChannel` è **un singolo profilo social** connesso a Buffer (una pagina FB, un profilo IG, un canale YouTube...). `is_active` e `publication_mode` (`automatic`/`notification`/`approval`/`disabled`) determinano se una campagna può davvero pubblicarci sopra — `disabled` lo esclude sempre dal targeting, a prescindere dagli altri criteri.
- `SocialChannel.external_link` è l'URL pubblico reale del profilo/pagina sul social network (`Channel.externalLink` di Buffer), popolato dal sync — non un URL Buffer. Può essere `null` se Buffer non lo espone per quella piattaforma. La pagina "Canali" della dashboard lo usa per aprire il profilo in una nuova scheda.

---

## 4. Integrazione Buffer: mock vs production

Buffer non offre più OAuth funzionante per app di terze parti (verificato luglio 2026): l'unico meccanismo di collegamento è che ogni utente generi una **chiave API personale** dal proprio account Buffer (Settings → API) e la incolli nella dashboard. Non esiste alcuna credenziale a livello di piattaforma (niente client id/secret condiviso).

Punto di switch: `get_buffer_client()` in `apps/api/app/integrations/buffer/service.py`, controllato dalla variabile `BUFFER_INTEGRATION_MODE`:

| Modalità | Classe | Comportamento |
|---|---|---|
| `mock` (default) | `MockBufferClient` | Interamente in memoria: nessuna chiamata di rete reale. Organizzazioni/canali fissi restituiti per test. `create_post` supporta stringhe magiche nel testo per simulare errori (`simulate-fail-temp-429` → rate limit, `simulate-fail-temp-500` → errore server, `simulate-fail-perm` → errore permanente). `get_post_metrics` genera metriche pseudo-casuali deterministiche (seed = id del post). |
| `production` | `ProductionBufferClient` | Chiama davvero `https://api.buffer.com` (GraphQL), header `Authorization: Bearer <chiave utente>`. Mappa 401→errore auth, 429→rate limit, 5xx→errore server. |

**Non è mai permesso** che `mock` sia attivo in produzione con dati reali (AGENTS.md, regola 16) — è una responsabilità operativa: verificare `BUFFER_INTEGRATION_MODE=production` nel `.env` di produzione, il codice non lo forza automaticamente in base ad `ENVIRONMENT`.

Ogni implementazione rispetta la stessa interfaccia astratta `BaseBufferClient` (`client.py`): `get_user_info`, `sync_organizations`, `sync_channels`, `create_post`, `get_post_status`, `get_post_metrics`.

Cose specifiche del client production, da non "correggere" per errore:
- YouTube richiede metadati strutturati separati (`metadata.youtube.title`/`categoryId`), non il solo testo del post.
- Instagram richiede `metadata.instagram.type`/`shouldShareToFeed`; `type` è `"post"` di default ma diventa `"reel"` per video oltre 60s (vedi §5 sotto per il perché).
- Facebook richiede `metadata.facebook.type` (`post`/`story`/`reel`) e `metadata.facebook.annotations` (lista, inviata vuota perché il progetto non calcola menzioni/link annotati) — senza questi campi Buffer rifiuta il post con "Facebook posts require a type (post, story, or reel)".
- Le miniature video personalizzate **non vengono mai inviate a Buffer**: l'API reale rifiuta `VideoAssetInput.thumbnailUrl`. Le miniature generate da questo progetto (via ffmpeg) servono solo per l'anteprima interna nella dashboard.

---

## 5. Campagne: targeting e testo

### Modalità di targeting (`Campaign.targeting_mode`)

Risolte da `CampaignResolver.resolve_targets` (`apps/api/app/services/campaign_resolver.py`). La query di base **richiede sempre**, per ogni riga candidata: utente `active` e non cancellato, `BufferConnection.status == "connected"`, canale `is_active`, `publication_mode != "disabled"`. Un utente con connessione Buffer scaduta/non connessa (`expired`, `error`, `disconnected`, `pending`) è **sempre escluso**, qualunque sia il targeting scelto — non è un bug, è la garanzia di non pubblicare con un token non valido.

| Modalità | Chi include |
|---|---|
| `all_active_channels` | Tutti i canali attivi di tutti gli utenti attivi con connessione valida |
| `selected_users` | Solo i canali degli utenti scelti esplicitamente (`user_ids`) |
| `selected_groups` | Solo i canali degli utenti appartenenti ai gruppi scelti (`group_ids`) |
| `selected_channels` | Esattamente i canali scelti (`channel_ids`) — nessun altro filtro applicato sopra |
| `selected_platforms` | Tutti i canali di tutti gli utenti validi che corrispondono alle piattaforme scelte (`platform_names`) |

**Filtro piattaforma secondario** (`platform_names`): applicabile solo sopra a `all_active_channels`, `selected_users`, `selected_groups` — non su `selected_channels` (già esplicito) né su `selected_platforms` (che *è* già il filtro). È un `WHERE platform IN (...)` per singolo canale, **non** un "deve avere tutte queste piattaforme": se scegli Instagram+YouTube e un utente ha solo YouTube, quell'utente contribuisce comunque con il suo canale YouTube, e viene escluso silenziosamente solo su Instagram — nessun errore, nessuna pubblicazione persa, nessun invio sulla piattaforma sbagliata. Se il totale risolto per **l'intera campagna** è zero (es. l'unico utente selezionato non ha connessione valida), `launch_campaign` blocca il lancio con un errore esplicito e imposta `Campaign.status = "failed"`, senza creare nessuna `Publication`.

### Testo per canale

`CampaignResolver.resolve_text_for_channel`, in ordine di priorità:
1. Override specifico del singolo canale (se impostato in fase di lancio)
2. Testo specifico per piattaforma (`instagram_text`, `facebook_text`, `linkedin_text`, `tiktok_text`, `x_text`, `threads_text`)
3. `default_text`

YouTube è un caso a parte: `youtube_title` e `youtube_description` sono campi strutturati separati, risolti indipendentemente dal testo generico (Buffer richiede un titolo per i video YouTube, non solo una didascalia).

**Link referral personale (opzionale)**: dopo i tre passi sopra, se `Campaign.include_referral_link=true` (checkbox nello step 2 del wizard, spento di default), `resolve_text_for_channel` aggiunge in fondo al testo `"\n\nISCRIVITI QUI: {referral_link}"`, dove `referral_link` è quello dell'**utente proprietario del canale che si sta risolvendo in quel momento** — mai quello di un altro utente targetizzato dalla stessa campagna: `launch_campaign` carica `chan.buffer_organization.buffer_connection.user` per ogni canale dentro lo stesso ciclo che crea i target, quindi ogni canale riceve sempre e solo il link del proprio proprietario. Un utente senza `referral_link` configurato (pagina Utenti, icona 🔗 "Configura referral") non viene escluso e non genera errore: il suo testo resta invariato, esattamente come con l'opzione spenta — nessun placeholder vuoto, nessun fallimento. Deliberatamente l'**ultimo** passo della risoluzione: il testo con link incluso passa comunque per il controllo `PLATFORM_TEXT_LIMITS` descritto subito sotto, quindi un link che fa superare 280 caratteri su X/Twitter fa fallire solo quel target, come già succede oggi per un testo troppo lungo senza link.

Lato dashboard (`step-text.tsx`, `lib/validation/campaigns.ts`), quando il checkbox è acceso i box con un limite reale (X 280, Threads 500 — `PLATFORM_HARD_LIMITS`) si riducono di `REFERRAL_LINK_RESERVED_CHARS` (60, spazio per l'etichetta `"\n\nISCRIVITI QUI: "` + un'assunzione sulla lunghezza del link — un link referral reale è quasi sempre un URL corto, non serve riservare più di così) sia nel tetto dell'input sia nella validazione Zod, per scoraggiare in scrittura un testo che sforerebbe una volta aggiunto il link. È una guardia **lato UI, non garantita**: se il `referral_link` reale di un utente supera l'assunzione riservata, resta comunque il backstop server-side sopra a escludere quel singolo target — non è mai possibile che l'intera campagna fallisca per questo. Il valore era inizialmente 170 (assunzione più prudente, fino a 150 caratteri di link) ma bloccava testi del tutto normali (es. 168 caratteri per X) non appena il checkbox veniva acceso — corretto il 2026-08-15.

Se il "Avanti" del wizard non avanza dopo aver acceso il checkbox, non fallisce in silenzio: `goNext` (`campaigns/new/page.tsx`) mostra un toast con il messaggio di validazione esatto (es. "Con il link referral attivo restano N caratteri disponibili..."), e accendere il checkbox stesso con un testo X/Threads già troppo lungo mostra subito un avviso, senza aspettare il click su "Avanti".

**Contatti personali (opzionale)**: stessa identica meccanica del link referral appena descritto, ma per un secondo campo utente, `User.personal_contacts` — un blocco di testo libero (firma: nome, telefono, email...) invece di un singolo URL, configurabile dalla pagina Utenti (icona 🪪 "Contatti personali", stesso pattern del bottone 🔗 "Configura referral"). Un secondo checkbox nello step 2 del wizard, "Includi contatti personali" (`Campaign.include_personal_contacts`, spento di default, indipendente dal checkbox del link referral), controlla se `resolve_text_for_channel` lo aggiunge in fondo al testo. L'ordine è deliberato e fisso: se **entrambi** i checkbox sono accesi, il testo finale è `{testo}\n\nISCRIVITI QUI: {link}\n\n{contatti}` — il link referral viene sempre prima, i contatti personali subito dopo, mai il contrario, indipendentemente dall'ordine in cui l'admin accende i due checkbox. Un utente senza `personal_contacts` configurato non viene escluso e non genera errore, esattamente come per il link referral. Stesso backstop server-side (`PLATFORM_TEXT_LIMITS`): un blocco contatti che fa sforare il limite di un canale fa fallire solo quel target.

Lato dashboard, stessa logica di riduzione dei box con un limite reale (X, Threads): quando il checkbox è acceso, si riducono di altri `PERSONAL_CONTACTS_RESERVED_CHARS` (100, stesso principio di `REFERRAL_LINK_RESERVED_CHARS` ma per un blocco firma anziché un URL). Se **entrambi** i checkbox sono accesi, le due riduzioni si sommano (fino a 160 caratteri in meno su X, ad es.) — sia nel tetto dell'input sia nella validazione Zod (`lib/validation/campaigns.ts`), stessa guardia lato UI, non garantita, con lo stesso backstop server-side descritto sopra.

**Limite caratteri per piattaforma**: se non è impostato un testo specifico per una piattaforma, il fallback è `default_text` (fino a 5000 caratteri) — ma X/Twitter e Threads hanno limiti reali molto più bassi (280 e 500). `launch_campaign` (`campaign_resolver.py`, `PLATFORM_TEXT_LIMITS`) verifica la lunghezza del testo **risolto** per questi due casi *prima* di contattare Buffer: se supera il limite, quel target/`Publication` viene creato direttamente in stato `failed` con `error_category="validation_failed"` e un messaggio esplicativo, senza sprecare una chiamata reale e senza consumare un tentativo. Gli altri canali della stessa campagna non sono influenzati (ogni destinazione resta indipendente, regola 1 di AGENTS.md).

**Limite di durata video per piattaforma**: stesso principio del limite di testo, ma solo per X/Twitter, che ha un vincolo stabile e documentato da Buffer stesso (support.buffer.com/article/616: tra 0.5 e 140 secondi). `launch_campaign` (`campaign_resolver.py`, `PLATFORM_VIDEO_MAX_DURATION_SECONDS` + `compute_video_duration_validation_error`) confronta `MediaFile.duration_seconds` (estratto via ffprobe al momento dell'upload, `inspect_media` in background) con quel limite *prima* di contattare Buffer: se il video supera 140s, solo il target X viene creato in `failed`/`validation_failed`, senza toccare gli altri canali. Se la durata non è ancora nota (media ancora in elaborazione), il controllo è **fail-open**: non blocca, lascia che sia l'eventuale rifiuto live di Buffer a intervenire.

**Instagram**: nessun numero pubblicato da Buffer per la durata massima di un "post" video, ma un errore reale osservato in produzione (lancio campagna, 2026-08-14) lo rende esplicito: *"Video must be no longer than 1 minute for Instagram Posts"*. `prod_client.create_post()` gestisce questo in modo proattivo, non con un controllo bloccante in `campaign_resolver.py` come per X/Twitter: se `media_type == "video"` e `MediaFile.duration_seconds` supera `INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS` (60s, costante nello stesso file), `metadata.instagram.type` viene impostato a `"reel"` invece di `"post"` — un Reel non ha questo limite. Video più corti, immagini, o durata ancora sconosciuta (media in elaborazione) continuano ad andare come `"post"` normale, comportamento invariato. Se in futuro serve dare all'amministratore la scelta esplicita del tipo (es. per la spinta algoritmica dei Reel anche sotto i 60s), va aggiunta come impostazione per-campagna consapevole — oggi la scelta è automatica e trasparente, unico obiettivo è che la pubblicazione vada a buon fine.

**Facebook**: nessun controllo di durata, proattivo o reattivo — pubblica sempre e solo come `"post"` (`prod_client.py`, `metadata.facebook.type` hardcoded a `"post"`). Non essendoci ancora stato un errore reale osservato in produzione per Facebook (a differenza di Instagram sopra), non è stato aggiunto alcun limite o fallback: per AGENTS.md regola 8 non si inventa un comportamento Buffer non verificato. Se in futuro un video Facebook fallisce per un motivo simile, va replicata la stessa indagine fatta per Instagram (verificare il messaggio di errore reale restituito da Buffer) prima di implementare un fix.

**Canali Instagram personali (non Professional/Business)**: stesso principio dei due controlli sopra. `SocialChannel.channel_type` (valore riportato direttamente da Buffer via `sync_buffer_connection`, es. `"page"`, `"group"`, `"profile"`) vale `"profile"` per un profilo Instagram personale — un account di questo tipo **non può mai pubblicare via API**, è una limitazione strutturale di Instagram/Meta (solo gli account Professional/Business, collegati a una Pagina Facebook, hanno il permesso "Content Publishing"), confermata dal vero errore Buffer osservato in produzione: *"Instagram personal profile channels require notification scheduling. Use notification scheduling instead."* `launch_campaign` (`campaign_resolver.py`, `CHANNEL_TYPES_REQUIRING_NOTIFICATION_SCHEDULING` + `compute_channel_type_validation_error`) intercetta questo caso *prima* di contattare Buffer: il target/`Publication` viene creato subito in `failed`/`validation_failed` con un messaggio esplicativo, senza sprecare i 5 tentativi di retry (fino a ~6 ore di backoff ciascuno) su una chiamata che fallirebbe sempre allo stesso modo. **Non rende il canale pubblicabile**: l'unico modo reale di pubblicare su quell'account è convertirlo in Professional/Business dall'app Instagram e ricollegarlo su Buffer — `SocialChannel.publication_mode="notification"` esiste come campo ma oggi è puramente descrittivo (vedi `api/v1/buffer.py`), non collegato a una vera chiamata Buffer di tipo "notification scheduling".

**Generazione testo con AI (opzionale)**: nello step 2 del wizard, il pulsante "Genera con AI" apre un dialog dove l'admin descrive un argomento in linguaggio naturale; `POST /api/v1/ai/generate-campaign-text` (`app/integrations/openai/client.py`) chiama l'API di OpenAI chiedendo un JSON con tutti e 9 i campi testo, rispettando target di lunghezza realistici per piattaforma nel prompt, un tetto di `max_tokens=1500` per contenere il costo per chiamata, e un **troncamento server-side di sicurezza** (`HARD_LIMITS`) allineato agli stessi vincoli già validati da `CampaignCreateRequest` (x=280, threads=500, youtube_title=100, altri=5000) — non può mai generare un testo che fallisca la creazione della campagna. Il risultato compila i campi del form ma **non salva né lancia nulla**: è solo una bozza di partenza, modificabile liberamente come se fosse scritta a mano. Genera solo testo — nessuna chiamata a endpoint immagine/video di OpenAI esiste in questa integrazione.

**Consapevole del link referral e dei contatti personali**: il dialog passa anche lo stato corrente di entrambi i checkbox, "Includi link referral" e "Includi contatti personali" (`AIGenerateTextRequest.include_referral_link` / `include_personal_contacts`). Per ciascuno che è acceso, `generate_campaign_text` riduce il target chiesto al modello e `HARD_LIMITS` per `x_text`/`threads_text` della relativa costante (`REFERRAL_LINK_RESERVED_CHARS`=60, `PERSONAL_CONTACTS_RESERVED_CHARS`=100 — stessi valori del lato dashboard, tenuti manualmente in sync) e aggiunge un'istruzione esplicita nel system prompt di non scrivere da sé quel contenuto — così il testo generato lascia già spazio per entrambi se entrambi sono attivi, invece di scoprire il problema solo dopo aver acceso i checkbox su un testo già generato alla lunghezza piena.

Credenziali: la chiave API OpenAI è **configurabile dalla pagina Impostazioni** della dashboard (tabella `ai_settings`, cifrata a riposo come le chiavi Buffer — vedi [DATABASE.md §9](./DATABASE.md#9-impostazioni-ai)), non solo dal `.env`. `GET/PUT/DELETE /api/v1/settings/ai` gestiscono lettura (solo `configured`+`model`, mai la chiave), scrittura (valida la chiave contro `GET /v1/models` di OpenAI prima di salvarla, stesso principio del collegamento Buffer) e rimozione. `app/services/ai_settings_service.get_openai_credentials` decide quale chiave usare ad ogni generazione: quella in `ai_settings` se presente, altrimenti `OPENAI_API_KEY` da `.env` come fallback di primo avvio. Se nessuna delle due è configurata, l'endpoint di generazione risponde 503 — ma lato frontend il pulsante "Genera con AI" lo anticipa già: `hooks/use-ai-gate.ts` controlla `GET /settings/ai` e, se non configurata, apre un dialog esplicativo ("configura prima l'API ChatGPT nelle Impostazioni") invece di tentare la chiamata, senza mai bloccare in modo nativo il pulsante (resta cliccabile per mostrare il dialog). Stesso hook riusato identicamente da tutte le azioni AI del modulo Blog Writer (vedi [BLOG_WRITER.md §3](./BLOG_WRITER.md)). Il resto del wizard funziona identico comunque.

### Modalità di pubblicazione (`Campaign.publishing_mode`)

`immediate` (lancia subito), `scheduled` (aspetta `scheduled_at`, poi il task periodico `poll_and_queue_scheduled_publications` lancia la campagna), `buffer_queue`, `draft` (non lanciata, salvata per dopo), `approval`.

### Stato campagna (`Campaign.status`)

`draft → preparing → queued → running → (paused) → partially_completed | completed | failed | cancelled`. Ricalcolato automaticamente ad ogni cambio di stato di una sua `Publication` (`_recalculate_campaign_status` in `tasks/publication.py`): se *tutti* i target sono terminali e almeno uno è riuscito ma non tutti → `partially_completed`; se tutti riusciti → `completed`; se tutti falliti → `failed`.

### Pausa / ripresa / annullamento / cancellazione

- **Pausa**: congela le pubblicazioni `pending`/`queued` in `retry_wait` per 24h (non le annulla).
- **Ripresa**: le rimette `pending` e ridà la sveglia al task di poll.
- **Annullamento**: cancella la campagna e ogni pubblicazione non ancora terminale — irreversibile.
- **Eliminazione** (`DELETE /campaigns/{id}`): cancella *tutto* in cascata (target, pubblicazioni, tentativi), scrive prima un audit log, funziona anche se la campagna è già stata pubblicata su alcuni canali. Il media allegato **non** viene eliminato (può essere riusato da altre campagne).

---

## 6. Ciclo di vita di una pubblicazione

Ogni coppia `(campagna, canale)` risolta al lancio produce **un** `CampaignTarget` e **una** `Publication` — mai una pubblicazione unica "cumulativa" per la campagna (AGENTS.md, regola 1). La chiave di idempotenza è deterministica: `"{campaign_id}:{social_channel_id}"` — rilanciare la stessa campagna non duplica mai un invio già fatto (AGENTS.md, regola 7).

`Publication.status`:

```
pending → queued → processing → submitted → published
                              ↘ scheduled (se Buffer accoda per dopo)
                 ↘ retry_wait (errore temporaneo, backoff con jitter) → pending (quando matura)
                 ↘ failed (errore permanente, o retry esauriti)
pending/queued/retry_wait → cancelled (azione admin)
qualunque stato non terminale → skipped (azione admin, non verrà più ritentato)
```

Eseguito da `process_publication_task` (`apps/api/app/tasks/publication.py`): prende un lock di riga (`SELECT ... FOR UPDATE SKIP LOCKED`) per evitare doppie esecuzioni concorrenti dello stesso target, controlla il rate limiter, chiama `create_post` sul client Buffer attivo, registra **sempre** un `PublicationAttempt` (successo o fallimento — AGENTS.md, regola 6), poi aggiorna lo stato.

Backoff dei retry (`RETRY_BACKOFF_SEQUENCE_SECONDS`, default `60,300,900,3600,21600`): 1 min, 5 min, 15 min, 1h, 6h — con jitter per evitare thundering herd. Numero massimo di tentativi: `MAX_PUBLICATION_ATTEMPTS` (default 5); il retry manuale da dashboard estende il limite di 3 tentativi in più se già esaurito.

Nessuna pubblicazione **riuscita** viene mai ritentata (AGENTS.md, regola 2): gli endpoint di retry operano solo su `failed`/`cancelled`/`retry_wait`.

**`published` vs `scheduled` sono entrambi esiti di successo**, non uno "in attesa" dell'altro: `scheduled` significa che Buffer ha accettato ed accodato il post per la data futura richiesta (`Campaign.publishing_mode == "scheduled"`), `published` che è già stato pubblicato live. La distinzione immediato/programmato è un dettaglio di *quando*, non un esito diverso — per l'amministratore conta solo che Buffer l'abbia accettato. Il backend li tratta già come equivalenti nel calcolo di `Campaign.status`/`progress_percentage` (`_recalculate_campaign_status`, `campaigns.py`); qualunque contatore lato dashboard che mostri "quante pubblicazioni sono andate a buon fine" deve sommare entrambi in un unico numero ("Riuscite"), altrimenti una campagna programmata risulta erroneamente "a zero successi" pur avendo funzionato — vedi `campaign-progress.tsx` e la lista campagne.

Se un worker crash lascia una pubblicazione bloccata in `processing` per più di 15 minuti, il task periodico `recover_stale_publications` la rimette in `retry_wait` o `failed` a seconda dei tentativi già fatti. Lo stesso task recupera anche pubblicazioni bloccate in `queued` da più di 15 minuti (job Celery perso, mai eseguito) rimettendole in `pending`. Un admin può anche forzare subito un retry manuale su una riga `queued` bloccata da dashboard/endpoint, senza aspettare i 15 minuti.

**Il dashboard tiene aggiornati i contatori dopo un retry manuale** (bug reale corretto il 2026-08-17): `POST /publications/{id}/retry` imposta lo stato a `pending` **in modo sincrono**, ma la pubblicazione vera e propria avviene dopo, in modo asincrono, dentro `process_publication_task`. Le mutation di retry (`useRetryPublication`/`useRetrySelectedPublications`/`useCancelPublication`/`useSkipPublication`, `hooks/use-publications.ts`) invalidano subito la cache React Query — un solo refetch immediato, che quindi può catturare lo stato transitorio (`pending`) invece dell'esito finale. Senza un meccanismo che continui a controllare, i contatori "riuscite/fallite" restano bloccati su quello stato transitorio finché non si ricarica manualmente la pagina. Corretto con il polling già esistente per la pagina di dettaglio campagna, ora esteso e reso più robusto (`lib/campaign-stats.ts::hasUnresolvedPublications`/`isUnresolvedPublicationStatus`, condiviso):
- lista **Campagne** (`DestinationsCell`) e dettaglio campagna: `useCampaignDetail(..., { refetchInterval })` continua a interrogare ogni 5s finché `stats` ha almeno una pubblicazione in `pending`/`queued`/`processing`/`submitted`/`retry_wait` — prima il dettaglio campagna si basava sullo `status` testuale della campagna (`completed`/`cancelled`/`failed`), che non copriva mai `partially_completed` e non rifletteva lo stato reale delle singole pubblicazioni;
- dettaglio singola pubblicazione (`usePublicationDetail`): stesso polling basato sul suo `status`, prima assente del tutto;
- `invalidatePublications` ora invalida anche la query di dettaglio della/e pubblicazione/i toccata/e (`queryKeys.publications.detail(id)`), non solo le liste — prima una pubblicazione aperta nella propria scheda di dettaglio non veniva mai reinterrogata dopo un retry cliccato lì.

---

## 7. Rate limiting verso Buffer

`RateLimiter` (`apps/api/app/services/rate_limiter.py`), backed da chiavi Redis:

- `buffer:paused:{connection_id}` — pausa forzata dopo un 429 da quella specifica connessione Buffer.
- `buffer:active:conn:{connection_id}` — concorrenza massima per singola connessione (`CONCURRENT_JOBS_PER_CONNECTION`, default 1).
- `buffer:active:global` — concorrenza massima aggregata su tutte le connessioni (`GLOBAL_CONCURRENCY_LIMIT`, default 5).
- `buffer:last_req:{connection_id}` — intervallo minimo tra due richieste sulla stessa connessione (`PAUSE_BETWEEN_REQUESTS_SECONDS`, default 10s).

Questi limiti sono **modificabili a caldo** senza riavviare i worker: vedi [§12](#12-impostazioni-runtime).

---

## 8. Task in background (Celery)

| Task | Trigger | Cosa fa |
|---|---|---|
| `process_publication` | on-demand (lancio/retry campagna, o dal task di poll) | Esegue una singola pubblicazione verso Buffer (vedi §6) |
| `poll_and_queue_scheduled_publications` | periodico, ogni 30s | Lancia le campagne `draft` il cui `scheduled_at` è passato; accoda le pubblicazioni `pending` o `retry_wait` mature |
| `sync_buffer_connection` | on-demand (collegamento/ricollegamento, sync manuale) + periodico (via `sync_all_buffer_connections`) | Sincronizza organizzazioni e canali Buffer per una connessione; disattiva i canali non più presenti, aggiorna `channel_type`/`is_active` |
| `sync_all_buffer_connections` | periodico, ogni 4 ore | Dispatcha `sync_buffer_connection` per ogni connessione `connected`/`expired`/`error` (esclude `disconnected`/`revoked`/`pending`, vedi docstring). Aggiunto per evitare che `is_active`/`channel_type` restino non aggiornati per settimane tra un collegamento manuale e l'altro — così `resolve_targets` (§5) esclude i canali diventati non validi *prima* del lancio di una campagna, senza aggiungere alcuna chiamata Buffer in più al momento dell'invio |
| `refresh_expired_tokens` | periodico, ogni ora | **Codice legacy inattivo**, vedi [§13](#13-cose-note-come-non-finite-o-legacy) |
| `inspect_media` | on-demand (dopo ogni upload media) | ffprobe + generazione miniatura |
| `recover_stale_publications` | periodico, ogni 5 minuti | Recupera pubblicazioni bloccate in `processing` (worker crashato) o in `queued` (job Celery perso) da più di 15 minuti |
| `media_retention_cleanup` | periodico, giornaliero alle 02:00 UTC | Cancella fisicamente file/miniature dei media soft-eliminati |

---

## 9. Endpoint API

Prefisso comune `/api/v1`. Elenco completo per router — per i dettagli di request/response vedi lo Swagger generato automaticamente su `/docs` (FastAPI) di ogni ambiente.

- **`/auth`**: `POST /login`, `GET /me`
- **`/buffer`**: `GET /connections`, `POST /connections` (collega/ricollega), `POST /connections/{id}/sync`, `GET /channels`, `PUT /channels/{id}/publication-mode`, `DELETE /connections/{id}`
- **`/campaigns`**: `GET /`, `GET /summary` (conteggi per le stat card sopra la tabella, vedi nota sotto), `POST /`, `POST /preview-targets`, `POST /{id}/launch`, `GET /{id}`, `GET /{id}/metrics`, `POST /{id}/pause`, `POST /{id}/resume`, `POST /{id}/cancel`, `DELETE /{id}`
- **`/publications`**: `GET /`, `GET /summary` (idem, vedi nota sotto), `GET /feed` (vedi §10.1), `GET /{id}`, `GET /{id}/metrics`, `POST /{id}/retry`, `POST /retry-selected`, `POST /retry-campaign-failures/{campaign_id}`, `POST /{id}/cancel`, `POST /{id}/skip`
- **`/media`**: `GET /`, `POST /upload`, `GET /{id}`, `PATCH /{id}` (rinomina solo `original_filename`, non tocca il file fisico), `DELETE /{id}`
- **`/users`**: `GET /`, `GET /summary` (totale + conteggio per status, per le stat card sopra la tabella Utenti), `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` (soft delete), `GET /groups/list` (ogni gruppo annotato con `user_count`, i membri non soft-eliminati - conteggio transitorio calcolato in `list_groups`, non una colonna reale su `UserGroup`), `POST /groups`, `PUT /groups/{id}`, `GET /groups/{id}/users` (elenco membri, usato dal popup "Vedi utenti" nella pagina Gruppi)

**Stat card riassuntive sopra le liste** (aggiunte 2026-08-27): le pagine Utenti, Campagne e Pubblicazioni mostrano una fila di `StatCard` (stesso componente del modulo Statistiche) sopra la tabella/filtri, alimentate da un endpoint `GET .../summary` dedicato — nessuna delle liste paginate (`GET /`) espone un conteggio totale (limitate a `skip`/`limit`, niente `X-Total-Count`), quindi senza un endpoint a parte non ci sarebbe modo di mostrare "quanti ce ne sono in totale" senza scaricare tutte le pagine. `/users/summary` risponde con campi diretti (`total`/`active`/`inactive`/`suspended`, i soli 3 valori possibili di `UserStatus`); `/campaigns/summary` e `/publications/summary` rispondono invece con `{total, by_status}` grezzo (troppi status individuali - 9 e 11 rispettivamente - per una card ciascuno) e il frontend li raggruppa in poche card leggibili (`lib/status-buckets.ts`: Bozze/In corso/Completate/Fallite per le campagne, Pubblicate/In corso/Fallite/Annullate per le pubblicazioni) — un raggruppamento impreciso non romperebbe nulla, sono card informative, non un totale da far quadrare esattamente. Ogni mutazione che cambia lo status di una campagna/pubblicazione (lancio, pausa, ripresa, annullamento, retry, eliminazione) invalida anche la relativa query di summary, cosi' le card restano coerenti con la tabella sotto senza un refresh manuale.
- **`/settings`**: `GET /`, `PUT /`, `GET /health`, `GET /ai`, `PUT /ai`, `DELETE /ai` (credenziali OpenAI, vedi §5)
- **`/ai`**: `POST /generate-campaign-text` (bozza testi campagna via OpenAI, richiede una chiave configurata — vedi `/settings/ai` sopra)

---

## 10. Metriche

`GET /campaigns/{id}/metrics` chiama Buffer **on-demand** (non salvato periodicamente) per ogni pubblicazione `published` **o** `scheduled` della campagna con un `external_post_id` valorizzato (stessa equivalenza pubblicato/programmato del §6 — un `scheduled` il cui orario è già passato è quasi certamente già live sulla piattaforma reale anche se la nostra label interna non lo riflette), tramite `get_post_metrics`. Le metriche di tipo "tasso" (es. `engagementRate`, unica percentuale 0-100 secondo la documentazione Buffer) vengono **mediate**, tutte le altre (like, visualizzazioni, commenti, ecc.) vengono **sommate** — non si sommano mai metriche di tipo diverso tra loro nella dashboard (es. visualizzazioni + impression + copertura restano tile separate, perché misurano cose diverse).

**Link al post pubblicato** (`Publication.external_post_url`): quasi sempre `null` subito dopo `create_post` — `Post.externalLink` (developers.buffer.com/types/Post.html, "The external URL of the post at the destination service", verificato anche con una query reale contro l'API Buffer il 2026-08-15) resta vuoto finché Buffer non ha *davvero* consegnato il post alla piattaforma di destinazione: lo stato interno di Buffer per un post resta `"scheduled"` anche per pubblicazioni che per noi sono già `"published"`, quindi il link arriva solo più tardi. `get_post_metrics` richiede lo stesso campo e sia `GET /campaigns/{id}/metrics` sia `GET /publications/{id}/metrics` fanno **backfill** automatico su `Publication.external_post_url` la prima volta che lo trovano valorizzato (nessun job di polling dedicato: si aggiorna quando l'admin controlla le statistiche). Finché non è disponibile, la scheda pubblicazione mostra come alternativa il link al **profilo del canale** (`SocialChannel.external_link`, popolato dal sync Buffer) invece di non mostrare nulla — stesso principio anche nella colonna azioni della lista pubblicazioni.

`GET /publications/{id}/metrics` è lo stesso meccanismo ma scoped a **una singola pubblicazione** (mostrato nella scheda di dettaglio pubblicazione, sotto "Cronologia tentativi"): stessa chiamata `get_post_metrics`, stesso schema di risposta (`ChannelMetrics`), nessuna aggregazione essendo un solo canale. Risponde 400 se la pubblicazione non è `published`/`scheduled` o non ha ancora un `external_post_id`.

**Anteprima media nella scheda dettaglio**: `GET /publications/{id}` (`PublicationDetailResponse`) include ora anche `media` (`pub.campaign.media_file`, `Optional[MediaResponse]`) — la card "Testo risolto" mostra l'anteprima (foto con lightbox al click, video con controlli nativi) sopra il testo, riusando lo stesso componente `components/shared/media-lightbox.tsx` (`MediaLightbox`) della card Bacheca (§10.1), non duplicato.

**URL nel testo cliccabili**: `resolved_text` (qui e in Bacheca, §10.1) è testo semplice lato backend — anche il link referral `"ISCRIVITI QUI: {url}"` (§5) è solo una stringa, mai HTML — quindi un browser non lo rende mai cliccabile da solo. `components/shared/linkified-text.tsx` (`LinkifiedText`, componente condiviso tra questa pagina e la Bacheca) individua ogni URL `http(s)://` nel testo via regex e lo trasforma in un vero `<a target="_blank">`, staccando la punteggiatura finale di fine frase (es. il punto dopo `.../abc123.`) perché non faccia parte del link.

### 10.1 Bacheca (feed pubblico delle pubblicazioni)

`GET /publications/feed` (dashboard: voce **Bacheca**, in cima alla sidebar, sopra anche "Dashboard") — un feed in stile social network di ogni `Publication` con `status = "published"`, ordinato per `published_at` decrescente (più recente in cima), paginato (`skip`/`limit`, default 30, max 100). Dichiarato **prima** di `/{pub_id}` nel router (`publications.py`) apposta, altrimenti FastAPI proverebbe a interpretare `"feed"` come un UUID del path param e fallirebbe.

A differenza di `GET /publications/` (righe grezze di `Publication`, usate dalla vista a tabella "Pubblicazioni"), questo endpoint fa un **join** con `CampaignTarget` (per il testo realmente risolto per quel canale, `resolved_text` — non `Campaign.default_text`, che non riflette override piattaforma/referral link), `Campaign` (per `media_file_id`), `SocialChannel` (id/piattaforma/nome/avatar) e `User` (`Publication.user_id` → `User.name`, il cliente proprietario di quel canale), più una singola query aggiuntiva a `MediaFile` per tutti i media coinvolti nella pagina (batch, non N+1 per riga). Risposta: `PublicationFeedItem` (id, campaign_id, published_at, text, external_post_url, social_channel_id, platform, channel_name, channel_avatar_url, user_name, media). `social_channel_id` esiste solo per il filtro canale del frontend (sotto) — `channel_name` da solo non è garantito univoco (due canali potrebbero avere lo stesso nome, anche di clienti diversi).

**Link al post originale non sempre presente**: come spiegato sopra, `external_post_url` spesso è `null` finché l'admin non controlla le metriche di quella pubblicazione (nessun backfill automatico in background) — la card in Bacheca semplicemente non mostra il link "Vedi post originale" finché non è valorizzato, non è un bug.

Il frontend (`app/(dashboard)/board/page.tsx`) mostra ogni pubblicazione come una card centrata in singola colonna (larghezza `max-w-3xl`, la stessa del selettore canale sotto — un'unica costante `FEED_WIDTH` condivisa da card, tendina e skeleton di caricamento, così restano sempre allineati se cambia ancora): media in cima (immagine `<img>` o video `<video controls>`, riproducibile direttamente in pagina — niente autoplay), poi avatar/nome canale, badge piattaforma (`components/shared/platform-badge.tsx`, stessa mappa colori/etichette platform usata altrove), testo, ed eventuale link al post.

**Lightbox immagine** (`components/shared/media-lightbox.tsx::MediaLightbox`, componente condiviso — usato anche dalla scheda dettaglio pubblicazione, vedi §10): le foto (non i video, che hanno già i propri controlli nativi per il fullscreen) sono racchiuse in un `<button>` — click per aprire un `Dialog` (`components/ui/dialog.tsx`) a schermo intero con l'immagine ingrandita (`object-contain`, mai tagliata) e un pulsante di chiusura sempre visibile (sfondo scuro semi-opaco fisso, indipendente da quanto è chiara l'immagine sotto). Un'icona di lente d'ingrandimento appare al passaggio del mouse sulla card come indizio visivo. Nota tecnica: avvolgere l'immagine in un `<button>` rompe il rilevamento automatico di `Card` (`has-[>img:first-child]:pt-0` in `components/ui/card.tsx`, che si aspetta l'`<img>` come figlio diretto) — il padding superiore viene quindi rimosso esplicitamente via classe quando il media è un'immagine, per mantenere l'aspetto "a filo" con gli angoli arrotondati della card.

**Nome canale cliccabile**: apre `channel_external_link` (`SocialChannel.external_link`, aggiunto a `PublicationFeedItem`) in una nuova scheda — stesso identico pattern della colonna "Canale" nella tabella "Canali social" (`app/(dashboard)/channels/page.tsx`): link con icona `ExternalLinkIcon` se il link esiste, altrimenti solo testo statico (non tutte le piattaforme lo espongono, vedi §5). Nessuna richiesta in più: il valore arriva già dentro la stessa riga joinata di `GET /publications/feed`.

**Bottone Statistiche**: ogni card ha un pulsante piccolo "Statistiche" (`BarChart3Icon`) che porta a `/publications/{item.id}` — la stessa scheda di dettaglio pubblicazione già esistente della vista a tabella "Pubblicazioni" (§9), non una pagina nuova. Le metriche vere e proprie (like, visualizzazioni, ecc.) non vengono caricate qui in Bacheca: restano un caricamento **on-demand** sulla scheda di dettaglio, tramite il pulsante "Carica/Aggiorna statistiche" già descritto sopra (`GET /publications/{id}/metrics`) — coerente con la scelta di non salvarle periodicamente.

**Filtro canale**: un selettore grande e centrato sotto l'intestazione (non un piccolo controllo nell'header — pensato per essere il modo primario di navigare il feed) elenca solo i canali effettivamente presenti nella pagina di feed caricata (derivata client-side da `PublicationFeedItem.social_channel_id`, nessuna chiamata separata per l'elenco canali), ordinati per **piattaforma** (alfabetico — tutti i canali Facebook insieme, poi Instagram, ecc. — a parità di piattaforma, per nome canale), più un'opzione "Tutti i canali" in cima alla lista. Ogni voce mostra `"{channel_name} ({user_name}) - {piattaforma}"` (es. "Algarve Beach Resort (Mario Rossi) - Instagram") — nome canale e cliente insieme, altrimenti due canali con nome simile o la stessa piattaforma sarebbero indistinguibili nella tendina. **Vista di default**: il primo canale della lista ordinata, non tutto mescolato — calcolato al render (non con un `useEffect` + `setState`, per evitare un render a cascata) come fallback quando l'admin non ha ancora scelto esplicitamente, così una sua scelta manuale non viene mai sovrascritta da un refetch successivo. Il fetch usa `limit=100` (il massimo dell'endpoint) invece del default 30 delle altre viste, per dare al filtro abbastanza dati anche su un canale meno attivo.

### 10.2 Modulo Statistiche (dati persistiti)

Tutto quanto descritto sopra in questo §10 è **live**: chiamato al volo, mai salvato. Il modulo **Statistiche** (voce sidebar dedicata, tra "Pubblicazioni" e "Centro errori") aggiunge un secondo livello sopra queste stesse chiamate a Buffer, salvando il risultato in tabelle proprie (`stat_*`) così da poterlo navigare per utente → canale → campagna senza richiamare Buffer ogni volta, con 3 bottoni di sincronizzazione manuale (utente/campagna/tutti) ed export Excel. Documentazione completa, schema dati e motore di sync in **[STATISTICS.md](./STATISTICS.md)**.

---

## 11. Media

- Upload validato e salvato da `MediaService`; poi `inspect_media` gira ffprobe per estrarre durata/risoluzione/codec (solo video) e genera una miniatura.
- `public_url` deve essere raggiungibile via **HTTPS pubblico**: Buffer scarica il file da lì al momento della pubblicazione. Senza HTTPS configurato, il task di pubblicazione rifiuta esplicitamente (categoria errore `configuration_error`) prima di provare a chiamare Buffer.
- Cancellazione: rifiutata se il media è ancora referenziato da una campagna attiva; altrimenti soft-delete, poi pulizia fisica giornaliera via `media_retention_cleanup`.
- Limite dimensione upload: `UPLOAD_MAX_SIZE_BYTES` (default 100MB) — attenzione a mantenere allineato anche `client_max_body_size` in Nginx (vedi problema noto #6 in DEPLOYMENT.md).
- Rinomina (`PATCH /media/{id}`): modifica solo `original_filename`, cioè il nome mostrato in dashboard — non tocca mai `stored_filename`/`storage_key`/`public_url`, quindi non può mai rompere un media già referenziato da una campagna o già inviato a Buffer.
- **Miniatura nella lista "Campagne"**: `CampaignResponse` include ora anche `media_file` (`Optional[MediaResponse]`, stesso nome dell'attributo/relazione SQLAlchemy `Campaign.media_file` — Pydantic lo risolve da solo grazie a `from_attributes`), non solo il vecchio `media_file_id`. `GET /campaigns/` (`list_campaigns`) carica la relazione con `joinedload(Campaign.media_file)` per evitare una query in più per riga. Il frontend (`app/(dashboard)/campaigns/page.tsx`) mostra la miniatura (`components/shared/media-preview.tsx::MediaPreview`, la stessa già usata nella pagina Media) affiancata al titolo nella prima colonna della tabella, solo quando la campagna ha un media allegato.

---

## 12. Impostazioni runtime

`GET/PUT /api/v1/settings` legge/scrive in Redis i limiti di concorrenza, retry e upload — sovrascrivono i default di `apps/api/app/core/config.py` **senza richiedere il riavvio dei worker**, perché ogni task li rilegge da Redis ad ogni esecuzione invece che una sola volta all'avvio. `GET /settings/health` verifica DB (`SELECT 1`), Redis (`ping`) e che almeno un worker Celery risponda (`inspector.ping()`) — usato dal passo 8 di DEPLOYMENT.md.

---

## 13. Cose note come non finite o legacy

- **`get_post_status`** in `ProductionBufferClient` non è implementato (`NotImplementedError`, marcato `BUFFER_API_TODO` nel codice): non è mai stato verificato contro l'API reale di Buffer. Non inventare un comportamento per questo metodo (AGENTS.md, regola 8) — se serve, va prima verificato manualmente contro Buffer e poi implementato.
- **`refresh_expired_tokens`** (task periodico orario in `tasks/sync.py`) presuppone semantiche OAuth (token/refresh token in scadenza) che non si applicano più al modello attuale a chiave API personale (`authentication_type="personal_api_key"`, nessun refresh token). Il task gira ancora ogni ora ma di fatto non ha più righe valide su cui agire nel modello dati corrente — codice legacy rimasto dalla vecchia integrazione OAuth, non rimosso per prudenza. Se lo tocchi, verifica prima con l'utente se va rimosso o riadattato.
- Le colonne `refresh_token_encrypted`, `token_expires_at`, `scopes` su `buffer_connections` esistono ancora nello schema (stessa ragione: retaggio OAuth) ma non sono più popolate dal flusso a chiave API personale — restano `NULL`. Non è un bug, ma non affidarti al loro valore.
