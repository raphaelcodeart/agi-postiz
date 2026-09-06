# Modulo Statistiche

Modulo separato e indipendente: dashboard **persistita** (non on-demand) del valore reale che ogni promoter/canale social porta alle campagne marketing — views, reazioni, commenti, nuovi iscritti — navigabile per **utente → canale → campagna/post**, con storico salvato nel database invece che ricalcolato ogni volta da Buffer. Non modifica né duplica alcuna tabella/funzionalità esistente: l'unico collegamento con il resto della piattaforma sono foreign key in sola lettura verso `publications`/`campaigns`/`users`/`social_channels`/`buffer_connections`/`administrators` — stesso principio di isolamento già usato per l'Omnichannel Responder (vedi [OMNICHANNEL_RESPONDER.md](./OMNICHANNEL_RESPONDER.md)). Per lo schema generale vedi [DATABASE.md](./DATABASE.md); per le metriche **live** (non salvate, già esistenti prima di questo modulo) vedi [FUNCTIONALITY.md §10](./FUNCTIONALITY.md#10-metriche).

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

Router separato, **senza autenticazione**, prefisso `/api/v1/public/stats` (`app/api/v1/public_stats.py`): un solo `GET`, per il sito pubblico `agimarketing.app`. Espone solo `statistics_service.build_public_summary` — totali generali, conteggio post/campagne/canali/utenti attivi (`active_user_count`, mostrato sul sito come "Influencer attivi") e un breakdown per piattaforma (`_platform_breakdown`), mai un id o nome di utente/canale. CORS gestito a mano nell'endpoint (allow-list fissa di origin, nessuna credenziale) invece che tramite il `CORSMiddleware` globale di `main.py`, che resta con `allow_credentials=True` per gli origin autenticati dell'app — questo endpoint non deve mai transitare su quella configurazione.

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

## 10. Limiti noti di questa v1

- `stat_metric_history` viene scritta ad ogni sync ma resta priva di una UI propria - i grafici del §9 usano `stat_post_metrics`, non lo storico multi-sync per singolo post (vedi nota in §2).
- Nessun export Excel a livello di singola campagna (solo generale/utente/canale) — i dati sono comunque consultabili nella scheda campagna esistente.
- Il refresh del singolo post non ha un indicatore di "in coda" persistito (è sincrono, un'unica richiesta HTTP) — se la connessione è occupata risponde 429 e l'admin riprova.
