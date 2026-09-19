# Modulo Statistiche

Modulo separato e indipendente: dashboard **persistita** (non on-demand) del valore reale che ogni promoter/canale social porta alle campagne marketing — views, reazioni, commenti, nuovi iscritti — navigabile per **utente → canale → campagna/post**, con storico salvato nel database invece che ricalcolato ogni volta da Buffer. Lo leggono in due: l'amministratore, su tutta la piattaforma (§5-§9), e ogni promoter sui propri dati dal suo portale (§11) — stesse funzioni di aggregazione, filtrate sull'utente del token. Non modifica né duplica alcuna tabella/funzionalità esistente: l'unico collegamento con il resto della piattaforma sono foreign key in sola lettura verso `publications`/`campaigns`/`users`/`social_channels`/`buffer_connections`/`administrators` — stesso principio di isolamento già usato per l'Omnichannel Responder (vedi [OMNICHANNEL_RESPONDER.md](./OMNICHANNEL_RESPONDER.md)). Per lo schema generale vedi [DATABASE.md](./DATABASE.md); per le metriche **live** (non salvate, già esistenti prima di questo modulo) vedi [FUNCTIONALITY.md §10](./FUNCTIONALITY.md#10-metriche).

Questo file è scritto per essere sufficiente, da solo, a ricostruire il modulo identico su un altro server (schema dati, motore di sync, endpoint, decisioni architetturali e i loro perché) senza dover rileggere il codice riga per riga.

---

## Indice

1. [Perché un modulo persistito, separato dalle metriche live](#1-perché-un-modulo-persistito-separato-dalle-metriche-live)
2. [Schema database](#2-schema-database)
3. [Motore di sincronizzazione](#3-motore-di-sincronizzazione)
4. [Guardia anti-spreco e rate limiting](#4-guardia-anti-spreco-e-rate-limiting)
5. [Endpoint API](#5-endpoint-api)
6. [Frontend](#6-frontend)
7. [I 3 livelli di sincronizzazione](#7-i-3-livelli-di-sincronizzazione)
8. [Export Excel](#8-export-excel)
9. [Grafici di andamento (mensile/annuale)](#9-grafici-di-andamento-mensileannuale)
10. [Limiti noti di questa v1](#10-limiti-noti-di-questa-v1)
11. [Le statistiche nel portale del promoter](#11-le-statistiche-nel-portale-del-promoter)

---

## 1. Perché un modulo persistito, separato dalle metriche live

Prima di questo modulo, le uniche metriche disponibili erano quelle **live** descritte in [FUNCTIONALITY.md §10](./FUNCTIONALITY.md#10-metriche): `GET /campaigns/{id}/metrics` e `GET /publications/{id}/metrics` chiamano Buffer al volo, senza salvare nulla — utili per un controllo puntuale, ma senza storico, senza vista aggregata per utente/canale, e con un costo in richieste Buffer ogni volta che qualcuno apre la pagina.

Questo modulo aggiunge un secondo livello **sopra** quello esistente, senza toccarlo: un motore di sincronizzazione scarica le metriche una volta e le salva in tabelle proprie (`stat_*`); il resto del modulo (dashboard, drill-down utente/canale/post, export Excel) è puro **sola lettura** su quei dati salvati — navigabile senza generare nuove chiamate a Buffer. Il bottone "Sincronizza e salva in Statistiche" aggiunto alla scheda campagna esistente (`campaigns/[id]`) è l'unico punto di contatto tra i due sistemi, ed è puramente additivo: le metriche live esistenti restano invariate.

## 2. Schema database

Tre tabelle nuove, prefisso `stat_`, migration Alembic `9c1f3a7e2b6d_add_statistics_module.py` (modello SQLAlchemy: `app/models/statistics.py`):

### `stat_sync_runs`
Una riga per ogni sincronizzazione lanciata (bottone "Sincronizza" a uno dei 3 livelli, §7). Alimenta sia la barra di progresso mentre gira, sia l'etichetta "Ultima sincronizzazione" mostrata a ogni livello della dashboard.

| Colonna | Tipo | Note |
|---|---|---|
| `scope` | string | `global` \| `user` \| `campaign` |
| `scope_user_id` / `scope_campaign_id` | UUID nullable, FK `users.id`/`campaigns.id` (SET NULL) | valorizzato solo per lo scope corrispondente |
| `triggered_by` | UUID nullable, FK `administrators.id` (SET NULL) | chi ha premuto il bottone |
| `status` | string | `queued` → `running` → `completed` \| `completed_with_errors` \| `failed` |
| `total_posts` / `synced_posts` / `failed_posts` / `skipped_posts` | int | contatori di avanzamento, aggiornati man mano che ogni post viene processato |
| `started_at` / `finished_at` | timestamp | |

### `stat_post_metrics`
Ultimo snapshot noto delle metriche Buffer per una pubblicazione — **1:1 con `Publication`** (`UNIQUE(publication_id)`). `campaign_id`/`user_id`/`social_channel_id`/`buffer_connection_id` sono denormalizzati da `Publication` apposta: le aggregazioni per utente/canale/campagna diventano `GROUP BY` diretti, senza dover attraversare `campaign_targets`/`publications` ogni volta.

Le metriche più comuni hanno una colonna dedicata (`reactions`, `likes`, `views`, `impressions`, `reach`, `follows`, `clicks`, `comments`, `shares`, `engagement_rate`) per permettere `SUM`/`ORDER BY` via SQL — nullable, perché non tutte le piattaforme riportano ogni tipo. Il payload completo così com'è arrivato da Buffer resta comunque in `metrics_raw` (JSONB), per non perdere tipi di metrica futuri non ancora mappati su una colonna propria. `metrics_updated_at` è il timestamp **di Buffer** (quando *loro* hanno calcolato quei valori); `last_synced_at` è quando **noi** li abbiamo scaricati — possono differire.

### `stat_metric_history`
Append-only: una riga per ogni sync riuscito di un post (oltre all'ultimo snapshot in `stat_post_metrics`). Costo trascurabile per riga, scritta ad ogni sync riuscito ma **non ancora usata dalla UI v1** — pensata per abilitare in futuro grafici dell'andamento di un singolo post nel tempo (crescita tra un sync e l'altro) senza dover ridisegnare lo schema. I grafici mensili/annuali del §10 non usano questa tabella: bucketizzano invece l'ultimo snapshot noto (`stat_post_metrics`) per data di *pubblicazione* — un caso d'uso diverso ("quanto ha reso il contenuto pubblicato in agosto"), non "come è cresciuto questo singolo post".

**Stesse identiche colonne metriche di `stat_post_metrics` sopra** (bug reale corretto il 2026-08-26, migration `e5f6a7b8c9d0`): mancavano `likes`/`impressions`/`reach`, cioè 3 delle 9 colonne di `ALL_METRIC_COLUMNS`. `_apply_metrics` (`app/tasks/statistics.py`) scrive entrambe le tabelle dallo stesso dizionario `**{c: columns.get(c) for c in ALL_METRIC_COLUMNS}` — la disallineamento faceva sollevare un `TypeError` non gestito ad ogni singolo sync (bottone "aggiorna" per riga → 500, sync di scope ampio → ogni post finiva con `last_sync_error` valorizzato), **pur avendo già scritto correttamente le metriche su `stat_post_metrics` un attimo prima** nella stessa chiamata. Il fix aggiunge un test (`test_statistics_metric_history_columns.py`) che verifica esplicitamente che entrambi i modelli accettino ogni colonna di `ALL_METRIC_COLUMNS` come kwarg — così un futuro nuovo tipo di metrica aggiunto a uno solo dei due modelli fallisce a un test, non in produzione.

Nessuna relationship viene aggiunta sui modelli esistenti (`User`, `Campaign`, `Publication`, `SocialChannel`) — le FK sono unidirezionali, dal modulo Statistiche verso il resto della piattaforma, mai il contrario.

## 3. Motore di sincronizzazione

`app/services/statistics_service.py` contiene la logica pura (query di eleggibilità, guardia anti-spreco, aggregazioni di lettura); `app/tasks/statistics.py` contiene l'orchestrazione Celery e le vere chiamate a Buffer.

Un post è **eleggibile** per il sync se `status` è `published` o `scheduled` **e** ha un `external_post_id` valorizzato — stesso identico filtro già usato dalle metriche live in `campaigns.py`/`publications.py`.

Il worker Celery è condiviso con la pubblicazione delle campagne e l'Omnichannel Responder, a concorrenza diversa tra ambienti (`docker-compose.prod.yml`: `celery worker -c 4`; `docker-compose.yml`, sviluppo: `-c 1`). Un singolo task che scorresse centinaia di post con `time.sleep()` per rispettare il rate limit bloccherebbe tutto il resto (nuove pubblicazioni, messaggi in arrivo) per l'intera durata del sync, indipendentemente dalla concorrenza. Per questo la sincronizzazione di uno scope (utente/campagna/tutti) **non esegue un loop bloccante**: `sync_user_statistics_task`/`sync_campaign_statistics_task`/`sync_all_statistics_task` risolvono la lista di post eleggibili e dispatchano un task Celery indipendente (`sync_publication_metrics_task`) per ciascuno, con un **countdown scaglionato per connessione Buffer** (`PAUSE_BETWEEN_REQUESTS_SECONDS` tra due post della stessa connessione/cliente; nessuna attesa tra post di clienti diversi, dato che usano API key diverse). Il worker resta quindi libero di processare nel frattempo una pubblicazione in coda o un messaggio omnichannel in arrivo, invece di restare fermo ad aspettare — il ritardo è nello *scheduling*, non in un blocco del processo.

`sync_publication_metrics_task` (l'unità atomica) usa lo stesso `RateLimiter` Redis (`app/services/rate_limiter.py`) e lo stesso idioma acquire/release-lock già usato da `app/tasks/publication.py::process_publication_task`, così il sync non compete mai con una campagna in corso di pubblicazione sulla stessa connessione Buffer. Con concorrenza reale > 1 in produzione, più task dello stesso run possono incrementare i contatori su `stat_sync_runs` davvero in parallelo: l'incremento usa quindi un `UPDATE ... SET synced_posts = synced_posts + 1` SQL atomico (Postgres serializza gli UPDATE concorrenti sulla stessa riga via row lock), non un `+= 1` in ORM che sotto concorrenza reale perderebbe incrementi.

## 4. Guardia anti-spreco e rate limiting

Requisito esplicito: ogni cliente ha la propria API key Buffer, quindi il sync deve consumare il meno possibile.

- **Guardia di staleness** (`statistics_service.needs_sync`): un post già sincronizzato nelle ultime **20 ore** non viene ri-scaricato da un sync di scope ampio (utente/campagna/tutti) — Buffer stesso aggiorna le metriche una volta al giorno (vedi `app/integrations/buffer/client.py`), quindi ri-chiedere più spesso non produrrebbe dati diversi. Un secondo click su "Sincronizza" subito dopo il primo costa **zero** chiamate se non è passato abbastanza tempo (`StatSyncRun` si chiude subito con tutti i post `skipped`). **Eccezione**: un post il cui ultimo tentativo ha lasciato un `last_sync_error` valorizzato è sempre eleggibile, a prescindere da quanto sia recente `last_synced_at` — altrimenti un post fallito per un motivo nel frattempo risolto (es. il bug di `stat_metric_history` sopra, o una chiave API rinnovata) resterebbe bloccato in errore fino allo scadere delle 20 ore anche premendo di nuovo "Sincronizza tutto".
- Il **refresh del singolo post** (bottone "aggiorna" per riga nel drill-down canale, `POST /statistics/posts/{id}/sync`) bypassa la guardia perché è un'azione esplicita dell'amministratore su un solo post, non uno scope ampio.
- **Pacing per connessione**: countdown scaglionato descritto sopra (§3) — mai più di una richiesta ogni `PAUSE_BETWEEN_REQUESTS_SECONDS` verso la stessa API key cliente.
- **Nessuna chiamata batch inventata**: il client Buffer di questo progetto espone solo `get_post_metrics` per singolo post (`app/integrations/buffer/prod_client.py`) — nessuna ipotesi su endpoint multi-post non documentati (AGENTS.md, regola 14).
- **Nessun job automatico in background**: la sincronizzazione è **solo manuale**, sui 3 bottoni descritti al §7. Nessuno scheduling periodico (niente voce in `celery.conf.beat_schedule`) che consumerebbe API key dei clienti anche se nessuno guarda la dashboard.

## 5. Endpoint API

Router `app/api/v1/statistics.py`, prefisso `/api/v1/statistics`, tutti autenticati (`get_current_admin`):

| Endpoint | Uso |
|---|---|
| `GET /dashboard` | Totali globali, classifica utenti, distribuzione per piattaforma, ultimo sync |
| `GET /users/{user_id}` | Totali utente + canali con mini-totali |
| `GET /users/{user_id}/channels/{channel_id}` | Totali canale + elenco campagne/post partecipati |
| `POST /sync/users/{user_id}` | Dispatch sync utente (202, ritorna `sync_run_id`) |
| `POST /sync/campaigns/{campaign_id}` | Dispatch sync campagna (202) |
| `POST /sync/all` | Dispatch sync generale (202) |
| `GET /sync/{sync_run_id}` | Stato/progresso di un run (per il polling del bottone) |
| `POST /posts/{publication_id}/sync` | Refresh sincrono di un solo post (bypassa la guardia, vedi §4) |
| `GET /export/dashboard.xlsx` | Export Excel generale |
| `GET /export/users/{user_id}.xlsx` | Export Excel utente (per canale) |
| `GET /export/users/{user_id}/channels/{channel_id}.xlsx` | Export Excel canale (per post) |

Router separato, **senza autenticazione**, prefisso `/api/v1/public/stats` (`app/api/v1/public_stats.py`): un solo `GET`, pensato per un eventuale sito pubblico di vetrina (oggi non ne esiste uno: l'allow-list degli origin è vuota, va popolata quando il sito ci sarà). Espone solo `statistics_service.build_public_summary` — totali generali, conteggio post/campagne/canali/utenti attivi (`active_user_count`, mostrato sul sito come "Influencer attivi") e un breakdown per piattaforma (`_platform_breakdown`), mai un id o nome di utente/canale. CORS gestito a mano nell'endpoint (allow-list fissa di origin, nessuna credenziale) invece che tramite il `CORSMiddleware` globale di `main.py`, che resta con `allow_credentials=True` per gli origin autenticati dell'app — questo endpoint non deve mai transitare su quella configurazione.

## 6. Frontend

Voce sidebar **"Statistiche"** (`lib/navigation.ts`, `BarChart3Icon`) - dal 2026-08-26 in `BUFFER_NAV_ITEMS`, tra "Pubblicazioni" e "Centro errori" (spostata su richiesta esplicita da sotto "Media": legge dati di pubblicazione, quindi si accompagna meglio a quel gruppo che a quello di configurazione connessioni/canali sopra).

- `app/(dashboard)/statistics/page.tsx` — dashboard generale: tile metriche, distribuzione piattaforme (`PlatformDistributionChart`, riusato da campaigns), grafico di andamento (§9), classifica utenti cliccabile (con mini-tile di views/mi piace/commenti/condivisioni accanto a ognuno, visibili dal breakpoint `lg` in su), bottone "Sincronizza tutto", export Excel.
- `app/(dashboard)/statistics/users/[id]/page.tsx` — totali utente, grafico di andamento (§9), elenco canali cliccabili (stesse 4 mini-tile accanto a ognuno, visibili dal breakpoint `lg` in su, senza dover aprire il canale), bottone "Sincronizza utente", export Excel.
- `app/(dashboard)/statistics/users/[id]/channels/[channelId]/page.tsx` — totali canale, grafico di andamento (§9), tabella campagne/post (link a `/campaigns/[id]` e `/publications/[id]` esistenti), bottone "aggiorna" per singolo post, export Excel.

**Mini-tile riassuntive per riga** (2026-08-27): sia la classifica promoter (dashboard generale) sia l'elenco canali (pagina utente) mostrano, accanto a ogni riga, le stesse 4 metriche - `ROW_SUMMARY_METRIC_KEYS` in `lib/metric-config.ts` (`views`, `reactions`, `comments`, `shares`) - come `MetricMiniStat`, lette da `StatUserSummary.totals`/`StatChannelSummary.totals` (già presenti nella risposta, nessuna nuova chiamata). Inizialmente l'elenco canali ne mostrava solo 3 (mancavano le condivisioni) con un array locale duplicato in quella pagina; ora entrambe le pagine condividono la stessa costante e lo stesso helper `shortLabelForMetric`, cosi' aggiungere/togliere una metrica da questa vista si fa in un solo punto.

**Mini-tile per ogni metrica, nella tabella post e nell'elenco canali** (2026-08-26, iterata lo stesso giorno): ogni valore di `StatPostRow.metrics`/`StatChannelSummary.totals` diverso da `null` è una piccola tile compatta — etichetta abbreviata in maiuscolo sopra, valore in grassetto sotto (`components/shared/metric-mini-stat.tsx`, `MetricMiniStat`) — invece di un elenco di testo con "valore etichetta, valore etichetta..." affiancati. Le tile sono disposte in una riga che va a capo (`flex flex-wrap`), un'unica colonna "Statistiche" nella tabella post (non più colonne separate per singola metrica: prima versione dello stesso giorno, sostituita perché duplicava l'etichetta già nell'intestazione di colonna). L'indicatore di errore di sincronizzazione (tooltip rosso, "Errore di sincronizzazione") sostituisce l'intera cella al posto delle tile quando `last_sync_error` è valorizzato.

Le etichette sono quelle **abbreviate** di `METRIC_TILE_CONFIG` (`lib/metric-config.ts`, campo `shortLabel`, distinto da `label` — quest'ultimo resta quello esteso usato nelle StatCard in cima a ogni pagina, dove lo spazio non manca): `reactions`→"Mi piace", `likes`→"Like FB", `views`→"Views", `impressions`→"Impression", `reach`→"Copertura", `follows`→"Iscritti", `clicks`→"Clic", `engagementRate`→"Coinvolgimento", `comments`→"Commenti", `shares`→"Condivisioni".

**Pulsanti "torna indietro" più evidenti** (stesso giorno): sulle pagine utente e canale, il link di ritorno ("Torna alla classifica generale" / "Torna a {nome utente}") è ora un `Button variant="outline"` invece di un semplice testo piccolo — più facile da notare e da premere, non solo leggibile.

`components/shared/sync-button.tsx` + `hooks/use-statistics.ts::useSyncFlow` è il componente/hook condiviso dai 3 bottoni "Sincronizza": dispatcha, fa polling di `GET /sync/{id}` ogni 2s finché lo stato non è definitivo, mostra il progresso (`sincronizzati/falliti/saltati` su `totale`), notifica l'esito con un toast e invalida tutte le query del modulo (`queryKey: ["statistics"]`) così la pagina mostra i nuovi totali senza bisogno di un refresh manuale. L'etichetta "Ultima sincronizzazione" è sempre visibile accanto al bottone (tranne quando il chiamante non ha un timestamp aggregato pertinente, es. il bottone sulla scheda di una singola campagna).

## 7. I 3 livelli di sincronizzazione

Esattamente i 3 richiesti, nessuno automatico:

1. **Singolo utente** — bottone nella pagina utente (`/statistics/users/{id}`) e sulla dashboard generale (via drill-down). Sincronizza tutti i post di tutti i canali di quell'utente.
2. **Singola campagna** — bottone "Sincronizza e salva in Statistiche" aggiunto alla scheda campagna esistente (`/campaigns/{id}`, card "Statistiche"), accanto — non al posto — del bottone "Carica/Aggiorna statistiche" già esistente (quello resta live/non salvato). Sincronizza tutte le destinazioni di quella campagna.
3. **Generale (tutti)** — bottone "Sincronizza tutto" sulla dashboard Statistiche. Sincronizza ogni post eleggibile su tutta la piattaforma, un cliente/connessione alla volta secondo il pacing del §3.

## 8. Export Excel

`app/services/xlsx_export.py::build_xlsx` genera il file **in memoria** (`openpyxl`, nessun file temporaneo su disco) e lo streamma via `StreamingResponse`. Sul frontend non serve gestione blob via JS: gli export sono semplici link `<a href="/api/backend/statistics/export/...">` — stesso dominio del proxy BFF (`app/api/backend/[...path]/route.ts`), che inoltra già l'header `content-disposition`, quindi il cookie di sessione httpOnly viaggia automaticamente con la normale navigazione del browser e il download parte come un link qualsiasi.

## 9. Grafici di andamento (mensile/annuale)

Aggiunti il 2026-08-26 ai 3 livelli esistenti (dashboard generale, utente, canale) - `MetricTrendChart` (`app/(dashboard)/statistics/_components/metric-trend-chart.tsx`), un unico componente riusato da tutte e 3 le pagine.

- **Calcolo lato backend, zero query aggiuntive**: `statistics_service.timeseries(rows, granularity)` raggruppa le righe `StatPostMetric` **già caricate** da `build_dashboard`/`build_user_detail`/`build_channel_detail` per `published_at` troncato a mese (`"YYYY-MM"`) o anno (`"YYYY"`), riusando `_totals_dict` per l'aggregazione di ogni bucket (stessa regola somma-vs-media-per-`engagement_rate` di ogni altro totale in questo modulo). Un post senza `published_at` noto (ancora in coda/programmato senza data ferma) è escluso dal bucket, non forzato a uno finto. Ogni risposta (`StatDashboardResponse`/`StatUserDetailResponse`/`StatChannelDetailResponse`) espone sia `timeseries_monthly` sia `timeseries_yearly` - il frontend sceglie quale mostrare senza una seconda chiamata di rete.
- **Bucketizzato per data di *pubblicazione*, non di sincronizzazione**: risponde a "quanto ha reso il contenuto pubblicato ad agosto", non "quando abbiamo scaricato l'ultima metrica" - le due date sono spesso diverse (un sync può avvenire giorni dopo la pubblicazione).
- **Una metrica alla volta, mai due assi**: il selettore nel componente lascia scegliere quale delle 10 metriche mostrare (le 9 di `ALL_METRIC_COLUMNS` più la pseudo-metrica "Post pubblicati", sempre disponibile anche prima di qualunque sincronizzazione Buffer) - mai una combinazione, per non introdurre un secondo asse con scala diversa nello stesso grafico.
- **Colore**: singola serie, sempre `--chart-1` (nessuna legenda necessaria - titolo/selettore già dicono cosa mostra). I 5 token `--chart-1..5` in tema scuro sono stati corretti nella stessa modifica (`app/globals.css`): i valori originali (`oklch L 0.70-0.80`) erano sopra la banda categorica per superfici scure (~0.48-0.67), troppo pallidi per leggersi come marcatori di dati affidabili - validato con lo script `validate_palette.js` del skill dataviz (tutti e 5 i controlli passano ora su sfondo scuro). Stesso hue/chroma, solo luminosità abbassata; nessun altro utilizzo esistente di quei token (icone accento in `page.tsx`/`groups/page.tsx`) ne risente in modo negativo.
- **Interazione**: tooltip al passaggio del mouse/focus su ogni barra (componente `Tooltip` condiviso, stesso usato altrove nell'app) con periodo, valore esatto e numero di post in quel bucket; l'ultima barra porta anche un'etichetta diretta sempre visibile (valore all'apice) - le altre restano leggibili solo via tooltip/asse, per non affollare il grafico di numeri.
- **Vista mensile limitata agli ultimi 12 bucket** (il backend restituisce tutta la storia disponibile, il frontend mostra solo la coda più recente) - la vista annuale mostra sempre tutti gli anni disponibili, tipicamente pochi.

### Lo snapshot giusto: bug corretto il 2026-09-14

bundle.social **non** restituisce un solo valore di metriche per post: restituisce **tutti gli
snapshot** che ha mai preso (uno al giorno circa, più quello scritto pochi secondi dopo la
pubblicazione), e li elenca **dal più recente al più vecchio**. `prod_client.get_post_metrics`
leggeva `items[-1]` con il commento "the API appends a row per refresh" — assunzione sbagliata:
`items[-1]` è lo snapshot **più vecchio**, cioè quello scattato appena il post è andato online,
quando per definizione ogni contatore è ancora 0.

Effetto: la dashboard mostrava praticamente ogni post a 0 su tutte le metriche, il sync riportava
"completato" senza errori, e niente da nessuna parte diceva perché — esattamente il modo di
fallire contro cui mettono in guardia i commenti di questo modulo. I pochi post con un numero
diverso da zero erano fermi alla loro cifra del primo giorno (un post reale a 69 visualizzazioni
risultava 65, il valore del 9 settembre, e non si muoveva più).

La correzione **non** si limita a invertire l'indice: sceglie lo snapshot con il timestamp più
recente (`max` su `updatedAt`/`createdAt`), così se un domani il provider cambiasse l'ordine di
elencazione il bug non tornerebbe in silenzio. Due test di regressione in
`tests/integrations/test_bundle_social_client.py` coprono entrambi gli ordinamenti.

**Da qui discende una cosa importante sull'uso**: le metriche di un post appena pubblicato sono
**sempre 0**, e restano 0 finché bundle.social non fa il suo giro di aggiornamento (~24h). Non è un
malfunzionamento: sincronizzare subito dopo una campagna non può produrre numeri.

### `likes` e non `reactions` (2026-09-14)

`reactions` è una metrica dell'era Buffer: bundle.social riporta `likes` per **tutte** le
piattaforme (Instagram, TikTok, LinkedIn, YouTube, Facebook), mai `reactions`. Le mini-tile per
riga (`ROW_SUMMARY_METRIC_KEYS`, §6) chiedevano però `reactions`, quindi la tile "Mi piace" accanto
a ogni promoter e a ogni canale era **permanentemente vuota** su tutte le connessioni di questa
piattaforma — che oggi sono la totalità (31 su 31, provider `bundle_social`, nessuna Buffer
residua). Ora chiedono `likes`. Di conseguenza l'etichetta di `likes` non è più "Like FB" (che su
Buffer voleva davvero dire Facebook) ma "Mi piace"; `reactions` resta in `METRIC_TILE_CONFIG` come
"Reazioni (storico Buffer)" perché le righe storiche continuino a mostrarsi.

### Errori di sincronizzazione che NON sono bug

Alcuni post falliscono il sync con un messaggio già esplicito, e la causa è di configurazione lato
bundle.social, non di codice:

- *"Il canale X non risulta più collegato"* (`Team does not have a X account`): quell'account social
  è stato scollegato dal team bundle.social del cliente. Va ricollegato dal portale.
- *"Il post non risulta pubblicato su X"* (`Post doesn't have external ID for that platform`): il
  provider ha accettato il post ma quella piattaforma non l'ha mai pubblicato davvero.

## 10. Limiti noti di questa v1

- `stat_metric_history` viene scritta ad ogni sync ma resta priva di una UI propria - i grafici del §9 usano `stat_post_metrics`, non lo storico multi-sync per singolo post (vedi nota in §2).
- Nessun export Excel a livello di singola campagna (solo generale/utente/canale) — i dati sono comunque consultabili nella scheda campagna esistente.
- Il refresh del singolo post non ha un indicatore di "in coda" persistito (è sincrono, un'unica richiesta HTTP) — se la connessione è occupata risponde 429 e l'admin riprova.

---

## 11. Le statistiche nel portale del promoter

Aggiunte il 2026-09-19. Il promoter ha nel suo portale (`/portal/statistics`) la
stessa sezione Statistiche dell'amministratore, ristretta a sé: i propri totali,
il grafico di andamento, l'elenco dei propri canali e, dentro ognuno, i singoli
post con le loro metriche.

**Niente aggregazioni nuove.** `app/api/v1/portal_statistics.py` non ricalcola
nulla: chiama gli stessi `statistics_service.build_user_detail` /
`build_channel_detail` che alimentano le pagine admin, passando
`current_user.id`. È la proprietà che conta: i numeri che il promoter vede e
quelli che l'amministratore vede per lui non possono divergere, perché sono la
stessa funzione sulle stesse righe `stat_post_metrics`. Le risposte riusano
`StatUserDetailResponse`/`StatChannelDetailResponse` — nessuno schema parallelo,
e sul frontend i tipi si importano da `types/api.ts` invece di essere
ridichiarati in `lib/portal/server.ts`.

**Scoping.** Vale la regola di tutto il portale (vedi il docstring di
`portal.py`): l'id utente viene dal token validato, mai da un path o da un body
— qui non esiste nemmeno un endpoint che accetti uno `user_id`. L'unico
parametro manipolabile è l'id del canale nell'URL, e `build_channel_detail` lo
verifica già contro la connessione dell'utente (join canale → organizzazione →
connessione → utente), quindi il canale di un altro promoter risponde 404 come
uno inesistente. Idem per un `sync_run_id` altrui, filtrato su `scope_user_id`.

| Endpoint | Uso |
|---|---|
| `GET /portal/statistics` | Totali propri + canali con mini-totali + timeseries |
| `GET /portal/statistics/channels/{id}` | Totali canale + elenco post |
| `POST /portal/statistics/sync` | Sincronizza i propri post (202) |
| `GET /portal/statistics/sync/{id}` | Stato/progresso, per il polling del bottone |
| `GET /portal/statistics/export.xlsx` | Export Excel per canale |
| `GET /portal/statistics/channels/{id}/export.xlsx` | Export Excel per post |

### Cosa il promoter **non** ha, e perché

- **La classifica dei promoter** (la dashboard generale del §5) non esiste nel
  portale: mostra chi rende più di chi, cioè esattamente l'unica cosa di questo
  modulo che un promoter non deve poter vedere degli altri.
- **Il bottone "aggiorna" per singolo post** (§4) non c'è. Quello
  dell'amministratore scavalca la guardia anti-spreco di proposito, perché è
  un'azione singola e consapevole; moltiplicato per ogni promoter e per ogni riga
  diventerebbe il modo più facile di bruciare la quota API del cliente.
  L'aggiornamento nel portale è uno solo, di scope utente, che rispetta la
  guardia.

### Il sync self-service

`POST /portal/statistics/sync` crea uno `StatSyncRun` con `scope="user"` sul
proprio id e dispatcha lo **stesso** `sync_user_statistics_task` del bottone
admin — eredita quindi senza aggiungere nulla le due protezioni che rendono
sostenibile metterlo in mano a ogni promoter (§4): la guardia di staleness (un
post già scaricato nelle ultime 20 ore viene saltato, quindi due click di fila
costano zero chiamate) e il `RateLimiter` Redis per connessione (il sync non
compete mai con una campagna in corso di pubblicazione sulla stessa API key).

Due aggiunte rispetto al bottone admin:

- **Run già in volo riusato**: se esiste un run dell'utente in stato
  `queued`/`running`, viene restituito quello invece di crearne un secondo. Un
  amministratore preme il suo bottone una volta e guarda la barra; una pagina
  aperta su un telefono viene ricaricata e il bottone ripremuto, e senza questo
  ogni click lascerebbe dietro di sé un run in più da seguire in polling.
- **`stat_sync_runs.triggered_by_user_id`** (migration `c7a2e9f14b30`): colonna
  nuova, FK a `users` con `ondelete SET NULL`. `triggered_by` punta ad
  `administrators`, quindi da sola non potrebbe registrare chi ha chiesto il
  sync, e un run self-service resterebbe indistinguibile da uno di un
  amministratore poi cancellato — la sua FK è già `SET NULL`.

### Frontend

- `app/portal/(app)/statistics/page.tsx` — totali, grafico di andamento, elenco
  canali cliccabili con le stesse 4 mini-tile per riga delle liste admin
  (`ROW_SUMMARY_METRIC_KEYS`), bottone "Aggiorna statistiche", export Excel.
- `app/portal/(app)/statistics/channels/[channelId]/page.tsx` — totali canale,
  grafico, i post uno per scheda.
- `MetricTrendChart` si è spostato da `app/(dashboard)/statistics/_components/`
  a `components/shared/`: ora lo usano due aree del prodotto, ed è interamente
  pilotato dalle props, quindi non sa di chi sono i dati che disegna.
- **Schede e non tabella** per i post: la `DataTable` admin vive su uno schermo
  largo, questa pagina si apre soprattutto dal telefono (il portale ha la barra
  di navigazione in basso proprio per quello), e cinque colonne lì si leggono
  solo scorrendo di lato.
- `SyncStatsButton` (`sync-stats-button.tsx`) non riusa
  `components/shared/sync-button.tsx`: quello è costruito su react-query e
  `useSyncFlow`, che nel portale non esistono — le pagine del portale sono
  Server Components che leggono e basta. A fine sincronizzazione qui basta
  `router.refresh()`.
- **Homepage arricchita**: `PortalStatsResponse` espone ora anche
  `total_follows`, `total_clicks` ed `engagement_rate` (quest'ultima *mediata*,
  mai sommata, e `null` — non `0` — quando nessun post la riporta). Le tile
  corrispondenti compaiono solo se hanno un valore: una tile a zero direbbe
  "nessun nuovo iscritto" dove la verità è "questa piattaforma non lo riporta".
  La `StatTile` del portale è passata da `page.tsx` a
  `app/portal/_shared/stat-tile.tsx`, condivisa fra homepage e sezione
  Statistiche.
- Voce di navigazione **"Statistiche"** in `portal-nav.tsx`, subito dopo
  "Palinsesto": la home mostra già le cifre di sintesi, questa è dove si va
  avendo deciso di guardare sul serio.

### Nota sull'export

L'intestazione della colonna `likes` negli export Excel era rimasta
"Mi piace (Facebook)", etichetta dell'era Buffer, mentre l'interfaccia l'aveva
già corretta in "Mi piace" (§9). Ora è "Mi piace" in entrambi. Le intestazioni
vivono in `app/services/xlsx_export.py` (`METRIC_HEADERS`, `metric_values`,
`xlsx_response`) e non più dentro il router admin, perché ora due router le
usano — lasciandole in uno dei due, l'altro avrebbe finito per tenerne una copia.
