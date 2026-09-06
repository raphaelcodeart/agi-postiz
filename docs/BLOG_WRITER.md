# Blog Writer AI

Modulo separato e disattivabile per generare articoli di blog con AI, pubblicarli su uno o più siti WordPress, e riusare il contenuto per creare campagne social nel wizard già esistente. Non modifica né duplica il sistema di campagne/Buffer esistente — lo riusa. Per lo schema dati generale vedi [DATABASE.md](./DATABASE.md); per il resto delle funzionalità della piattaforma vedi [FUNCTIONALITY.md](./FUNCTIONALITY.md).

---

## 1. Architettura in breve

```
Dashboard: /blog-writer, /blog-writer/new, /blog-writer/drafts,
           /blog-writer/articles, /blog-writer/[id], /blog-writer/sites

Backend:   /api/v1/blog-writer/sites/...      (CRUD siti WordPress)
           /api/v1/blog-writer/articles/...   (generazione, editor, pubblicazione)

Integrazioni: app/integrations/openai/client.py (esteso: generate_blog_article,
              adapt_article_for_platforms - stessa chiave OpenAI di Impostazioni,
              vedi FUNCTIONALITY.md §5)
              app/integrations/wordpress/client.py (nuovo: REST API WordPress)
```

Nessun sistema multi-tenant/permessi esiste in questo progetto (un solo ruolo `Administrator`, login unico — vedi FUNCTIONALITY.md §2). I siti WordPress e gli articoli si possono collegare opzionalmente a uno `User` esistente (stesso schema di `buffer_connections.user_id`), ma **qualunque amministratore loggato vede e gestisce tutto** — non è stata introdotta alcuna nuova restrizione di accesso, per coerenza con il resto della piattaforma.

---

## 2. Schema database

Tre tabelle nuove (migration `f4deed527dc6`), nessuna tabella esistente modificata a parte una colonna additiva su `campaigns`.

### `blog_writer_wordpress_sites`
Un sito WordPress collegabile. `encrypted_application_password` è cifrata con lo stesso `EncryptionService` (Fernet) usato per i token Buffer — mai in chiaro nel database, mai restituita dall'API. `user_id` è opzionale (nullable, `SET NULL` alla cancellazione dell'utente).

| Colonna | Note |
|---|---|
| `api_url` | Root REST API WordPress, es. `https://tuosito.com/wp-json` |
| `encrypted_application_password` | Cifrata, mai esposta |
| `connection_status` | `untested`, `connected`, `error` |
| `default_status` | `publish`, `draft`, `pending`, `private` — stato WordPress predefinito per un nuovo post |

### `blog_writer_articles`
Un articolo generato/modificabile. `generation_prompt` (JSONB) conserva tutti i parametri del form di generazione, usato da "Rigenera" — resta `NULL` per gli articoli creati a mano, che quindi non sono rigenerabili (errore esplicito, non un bug). `content` è HTML (non Markdown), scritto direttamente dal modello con tag limitati (`h2`/`h3`/`p`/`ul`/`li`/`strong`) oppure incollato/scritto dall'admin. `media_file_id` (FK nullable → `media_files.id`, `SET NULL`) è un media **caricato manualmente** nella libreria Media esistente e allegato all'articolo dall'editor — mai generato/cercato dall'AI (vedi §3, §4).

`status`: `generating`, `draft`, `ready`, `publishing`, `partially_published`, `published`, `failed`, `archived`. Un articolo `archived` non appare più in Bozze/Pubblicati ma resta recuperabile dal **Cestino** (`/blog-writer/trash`, `POST /{id}/restore` lo rimanda a `draft`) finché non viene eliminato definitivamente — l'eliminazione (`DELETE /{id}`) resta bloccata se l'articolo è già pubblicato su almeno un sito, in entrambi i casi.

### `blog_writer_publications`
Una riga per ogni coppia `(articolo, sito WordPress)` — stesso principio di "ogni destinazione è indipendente" già applicato a `Publication`/`CampaignTarget` (AGENTS.md regola 1). Vincolo unico `(article_id, wordpress_site_id)` per idempotenza: non è possibile creare due pubblicazioni per la stessa coppia, un rilancio aggiorna la riga esistente invece di duplicarla.

`publication_status`: `pending`, `publishing`, `published`, `failed`, `retrying`, `removed`, `updated`.

### `campaigns.article_id`
Colonna nullable aggiunta a `campaigns` (FK → `blog_writer_articles.id`, `SET NULL`), popolata solo quando una campagna viene creata tramite "Usa per campagna social". Puramente informativa, nessun comportamento della pubblicazione dipende da questo campo.

---

## 3. Generazione contenuti — solo testo, AI opzionale

La pagina "Nuovo articolo" offre **due modalità indipendenti**, scelte dall'admin ogni volta:

- **Genera con AI** — `POST /blog-writer/articles/generate`: `generate_blog_article` (in `app/integrations/openai/client.py`) chiama esclusivamente l'endpoint di puro testo di OpenAI (`chat/completions`), mai un endpoint immagine/video. Restituisce titolo, slug, excerpt, contenuto HTML, hashtag, keyword, meta title/description, lingua e tono.
- **Scrivi a mano** — `POST /blog-writer/articles/`: crea la bozza direttamente dal testo fornito dall'admin (scritto o incollato), **senza mai interpellare OpenAI**. Utile quando l'articolo esiste già altrove e va solo caricato. Lo slug è generato automaticamente dal titolo se non specificato. `generation_prompt` resta `NULL` per questi articoli (non c'è nulla da "rigenerare": il pulsante "Rigenera" nella pagina Bozze risponde con un errore chiaro se usato su un articolo scritto a mano).

In entrambi i casi il risultato è salvato immediatamente come bozza (mai lasciato solo in memoria) e da quel momento in poi è indistinguibile per il resto del modulo (editor, pubblicazione, "usa per campagna social").

Budget di token per lunghezza richiesta nella modalità AI (contenimento costi): breve ~1800 token, media ~3000, lunga ~4500. La modalità manuale non consuma alcun token.

`adapt_article_for_platforms` genera le versioni social (Instagram/Facebook/LinkedIn/X/Threads/generica) a partire da titolo+excerpt+URL pubblico, con lo stesso troncamento di sicurezza (`HARD_LIMITS`) già usato per la generazione testi campagna — x_text non supera mai 280 caratteri, threads_text mai 500.

**Blocco lato frontend se l'AI non è configurata**: ogni pulsante che consuma AI in tutta la dashboard (generazione testi campagna, generazione/rigenerazione articolo, "usa per campagna social") usa lo stesso hook condiviso `hooks/use-ai-gate.ts` (letto da `GET /settings/ai`, vedi FUNCTIONALITY.md §5): il pulsante resta visivamente attenuato (non `disabled` nativo, resta cliccabile) e al click, se non è configurata alcuna chiave, apre `<AIRequiredDialog>` invece di procedere, con un link diretto a Impostazioni — mai una chiamata AI silenziosamente fallita con un errore 503 poco chiaro.

---

## 4. Pubblicazione WordPress

`app/integrations/wordpress/client.py` implementa l'autenticazione **Application Passwords** di WordPress (Basic Auth su HTTPS — developer.wordpress.org/rest-api/using-the-rest-api/authentication/#application-passwords), non OAuth. Ogni admin WordPress genera la propria Application Password da wp-admin → Utenti → Profilo → Application Passwords.

Endpoint REST usati (verificati su developer.wordpress.org, non inventati): `GET /wp/v2/users/me` (test connessione), `GET /wp/v2/categories|users|tags` (opzioni), `POST /wp/v2/posts` (crea), `POST /wp/v2/posts/{id}` (aggiorna).

**Pubblicazione multi-sito**: `POST /blog-writer/articles/{id}/publish` crea/aggiorna una `BlogPublication` `pending` per ogni sito selezionato e lancia un task Celery per-sito (`publish_article_to_wordpress_task`, stesso pattern `SELECT...FOR UPDATE SKIP LOCKED` di `process_publication_task` — vedi FUNCTIONALITY.md §6). Un sito che fallisce non blocca gli altri: ogni pubblicazione è indipendente, tracciata con il proprio stato ed errore.

**Retry**: `POST /blog-writer/articles/{id}/publications/{pub_id}/retry`, solo su pubblicazioni `failed`.

**Media allegato**: se l'articolo ha un `media_file_id`, `blog_writer_publication_service._content_with_media` antepone un `<img src="{public_url}" alt="{titolo}" />` al contenuto prima di inviarlo a WordPress — il campo `content` dell'API REST accetta HTML arbitrario, verificato, non è un comportamento inventato. **Non** è una "immagine in evidenza" (featured image) nativa di WordPress: quella richiederebbe ricaricare il file nella libreria media del sito di destinazione (`POST /wp/v2/media`) prima di referenziarlo — fuori scope per ora (vedi §8). Il media va caricato manualmente nella sezione Media esistente prima di poterlo allegare: nessuna generazione o ricerca immagini via AI.

---

## 5. "Usa per campagna social" — riuso del wizard esistente

Nessun secondo sistema di pubblicazione: il pulsante genera solo un'anteprima testuale (`POST /blog-writer/articles/{id}/social-preview`, richiede l'articolo pubblicato su almeno un sito) e la passa al wizard campagne **già esistente** (`/campaigns/new`).

Meccanismo (in `lib/blog-writer-prefill.ts`, usato sia da `blog-writer/[id]/page.tsx` che da `campaigns/new/page.tsx`): il testo generato viene salvato in `sessionStorage` (troppo lungo per una query string) e il wizard viene aperto con `?prefillArticle=1`, che lo legge una volta sola — stesso idioma già usato dal prefill `?duplicate=<id>` per "Duplica campagna", non un meccanismo nuovo. La campagna creata parte sempre in modalità **bozza** (`publishing_mode: "draft"`): non viene mai lanciata automaticamente, l'admin sceglie destinatari/piattaforme/programmazione e conferma manualmente come per qualunque altra campagna.

---

## 6. Sicurezza

- **SSRF**: `validate_public_url` (in `integrations/wordpress/client.py`) blocca ogni URL non-HTTPS e ogni host il cui IP risolto sia loopback/privato/link-local/riservato/multicast — verificato prima di **ogni** chiamata (non solo al salvataggio, per resistere a DNS rebinding). Testato dal vivo contro `localhost`, `127.0.0.1`, `192.168.1.5`, `169.254.169.254` (metadata cloud) — tutti bloccati; un sito HTTPS pubblico reale viene accettato.
- **Credenziali**: Application Password cifrata (stesso `EncryptionService` di Buffer), mai restituita da nessun endpoint, mai loggata.
- **Idempotenza**: vincolo unico `(article_id, wordpress_site_id)` impedisce duplicazioni accidentali.
- **Eliminazione sicura**: `DELETE /blog-writer/articles/{id}` rifiuta se l'articolo è già pubblicato su almeno un sito (suggerisce di archiviare invece).

---

## 7. Configurazione

Nessuna nuova variabile `.env` obbligatoria: il modulo riusa `OPENAI_API_KEY`/`OPENAI_MODEL` già documentate in [DEPLOYMENT.md](./DEPLOYMENT.md) (configurabili anche dalla pagina Impostazioni, vedi FUNCTIONALITY.md §5). I siti WordPress si collegano interamente da UI (`/blog-writer/sites`), nessuna configurazione file necessaria.

Per collegare un sito WordPress: sul sito stesso, wp-admin → Utenti → il tuo profilo → sezione "Application Passwords" in fondo alla pagina → genera una nuova password con un nome descrittivo (es. "Blog Writer AI") → incollala nel dialog "Connetti sito web" della dashboard insieme a `https://tuosito.com/wp-json` come URL API.

---

## 8. Interfaccia: conferme e selezione media

**Etichetta "Dashboard BWA"**: la sidebar principale ha già una voce "Dashboard" (la home Buffer/campagne, `/`); la dashboard del modulo (`/blog-writer`) è etichettata **"Dashboard BWA"** sia nella sidebar (`lib/navigation.ts`) sia nel subnav in-pagina (`blog-writer/_components/blog-writer-subnav.tsx`) per evitare ambiguità tra le due.

**Azioni di riga con conferma**: Duplica/Rigenera/Archivia/Elimina nella pagina Bozze (e Testa/Modifica/Scollega in Siti WordPress) usano il componente condiviso `components/shared/icon-action-button.tsx` — icona + etichetta piccola sotto, non un glifo nudo senza testo. Ogni azione che elimina o archivia (Archivia, Elimina, Scollega) apre sempre un `<ConfirmDialog>` prima di eseguire la mutation — mai un'azione irreversibile al primo click, stesso pattern già usato altrove nella dashboard (es. eliminazione campagna). "Duplica" e "Testa connessione" restano invece immediate: non distruttive, nulla da confermare.

**Selezione media (editor articolo e wizard campagna)**: sia il selettore "Media allegato" in `blog-writer/[id]/page.tsx` sia lo step media di `campaigns/new/_components/step-media.tsx` condividono `components/shared/media-type-filter.tsx` — un filtro **Tutti / Immagini / Video** (`filterMediaByType`, basato sul prefisso di `mime_type`) per trovare rapidamente il file giusto in librerie numerose. Ogni miniatura mostra il nome file per intero sotto l'anteprima, non solo al passaggio del mouse. `components/shared/media-preview.tsx` mostra il primo frame reale del video (`<video preload="metadata" muted>`, scarica solo i metadati, non l'intero file) invece di una semplice icona generica — l'anteprima immagine (`<img>`) resta invariata, l'audio resta un'icona (non esiste un frame da mostrare).

---

## 9. Limiti noti di questa v1

- **Pubblicazione WordPress non testata contro un sito reale** in questa sessione (deliberatamente, per non pubblicare contenuti di test su siti veri) — verificati invece, dal vivo e con successo: generazione articolo reale via OpenAI, adattamento social, CRUD completo (crea/modifica/duplica/elimina), protezione SSRF, tutti gli endpoint via richieste HTTP reali contro il database di produzione. Il primo utilizzo reale di "Pubblica sui blog" andrebbe verificato contro un sito WordPress di prova prima di un uso massiccio.
- **Nessuna generazione/ricerca immagini via AI** (esplicitamente fuori scope, vedi richiesta originale) — è però possibile allegare un media **già caricato manualmente** nella sezione Media esistente (§2/§4): viene incluso nel post come `<img>` in testa al contenuto, non come vera "featured image" WordPress (richiederebbe un upload separato nella libreria media di ogni sito di destinazione, non implementato).
- **Nessun mock client WordPress dedicato**: il client parla sempre con l'API REST reale del sito configurato; la sicurezza per i test è strutturale (nessun sito reale pre-configurato, "Testa connessione" è sempre in sola lettura).
- **Editor contenuto**: textarea HTML grezzo + anteprima renderizzata, non un editor WYSIWYG — coerente con l'assenza di qualunque libreria di rich-text editing nel resto della dashboard.
- **Nessuna pubblicazione WordPress programmata** (data futura): la pubblicazione è sempre immediata o come bozza WordPress; la spec la elencava come "se disponibile", quindi opzionale.
- **Conferma di uscita con modifiche non salvate**: implementata solo per chiusura/refresh del browser (`beforeunload`), non per la navigazione interna tra le pagine della dashboard (Next.js App Router non offre un'API stabile per intercettarla senza una libreria aggiuntiva).
- **Nessun test pytest automatico aggiunto**: il progetto non aveva alcun test pytest preesistente (framework configurato ma zero file `test_*.py` in tutto `apps/api`); la verifica di questo modulo ha seguito lo stesso metodo manuale/live già usato per ogni altra funzionalità di questo progetto.
