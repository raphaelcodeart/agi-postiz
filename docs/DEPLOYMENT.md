# Guida al deploy su server Linux

Guida pratica per portare questo progetto (backend FastAPI + worker/scheduler Celery + frontend Next.js + Postgres + Redis + Nginx, tutto in Docker — stack tecnologico completo in [sezione 1](#1-cosa-serve-prima-di-iniziare)) su un server Linux, creare il database, e avviare tutto. Scritta per essere seguita passo passo da una persona, oppure eseguita direttamente da Claude Code se gli viene chiesto "fai il deploy seguendo docs/DEPLOYMENT.md". Per lo schema dati vedi [DATABASE.md](./DATABASE.md); per il comportamento reale del sistema una volta avviato vedi [FUNCTIONALITY.md](./FUNCTIONALITY.md); per il modulo Blog Writer AI (generazione articoli + pubblicazione WordPress) vedi [BLOG_WRITER.md](./BLOG_WRITER.md). Per l'hostname temporaneo su cui gira oggi la piattaforma, in attesa di un dominio, vedi [sezione 9](#9-dominio-e-https-consigliato-richiesto-per-pubblicare-fotovideo-su-buffer).

Se sei Claude Code e stai leggendo questo file per eseguire un deploy: vai alla sezione **[13. Istruzioni per Claude Code](#13-istruzioni-per-claude-code)** in fondo prima di iniziare.

---

## 0. Due scenari diversi: leggi qui prima di iniziare

Questa guida serve per **due obiettivi diversi**, che richiedono passi diversi — capire subito quale ti serve evita di saltare (o fare inutilmente) un passo importante.

**Scenario A — Installazione nuova, vuota** (es. offrire lo stesso prodotto a un altro cliente da zero, un ambiente di test/staging): vuoi solo la **struttura** — stesso software, stesso schema database, nessun dato/utente/campagna esistente. Ti bastano `git clone` di questo repository e le sezioni **1 → 9** di questa guida, nell'ordine. Non serve nessun dump di dati: le migration Alembic (sezione 5) ricreano lo schema da sole, partendo da un database vuoto. Se lo chiedi a Claude Code, basta: *"clona questo repo su un nuovo server e fai il deploy seguendo docs/DEPLOYMENT.md"*.

**Scenario B — Migrazione/duplicazione di *questo* server con tutto il contenuto attuale** (utenti, connessioni Buffer già collegate, campagne, cronologia pubblicazioni, media caricati): lo scenario A da solo **non basta**, perché `git clone` porta solo codice e schema, non i dati reali. Serve in aggiunta:
1. Tutti i passi dello scenario A (1 → 9) sul server nuovo, **fermandoti prima di creare l'amministratore** (sezione 6) — verrà ripristinato dal backup insieme al resto.
2. Un backup dei dati dal server **di origine**: `./scripts/backup-db.sh` (sezione 10).
3. Copiare quel file `.sql` (non solo la struttura: contiene i dati veri) sul server nuovo e ripristinarlo con `./scripts/restore-db.sh <file>` (sezione 10) — a questo punto utenti, campagne e cronologia esistono già, l'account amministratore incluso, non va ricreato a mano.
4. Copiare a parte anche i **file media** (foto/video caricati): vivono in un volume Docker (`media_storage`), non sono né in git né nel dump database — vedi "problemi noti" punto 5 nella sezione 12.
5. Le **connessioni Buffer** viaggiano già cifrate dentro il dump (punto 2-3 sopra), quindi non serve che gli utenti ricolleghino nulla — a differenza dello scenario A, dove ogni utente riparte da zero e deve incollare di nuovo la propria chiave API Buffer.
6. Dominio/HTTPS (sezione 9) va comunque rifatto per il nuovo IP/hostname, in entrambi gli scenari — non è mai portabile automaticamente da un server all'altro.

Se lo chiedi a Claude Code, specifica esplicitamente lo scenario B, ad esempio: *"clona questo repo sul nuovo server, fai il deploy seguendo docs/DEPLOYMENT.md, poi ripristina anche l'ultimo backup con restore-db.sh e copia la cartella media dal vecchio server"* — senza questa precisazione, Claude Code segue lo scenario A (installazione vuota) per default, come descritto nella sezione 13.

`docs/schema.sql` (dump di sola struttura, senza dati) non serve per **nessuno** dei due scenari: è solo una lettura di riferimento rapida, vedi [DATABASE.md](./DATABASE.md).

---

## Indice

0. [Due scenari diversi: leggi qui prima di iniziare](#0-due-scenari-diversi-leggi-qui-prima-di-iniziare)
1. [Cosa serve prima di iniziare](#1-cosa-serve-prima-di-iniziare)
2. [Installare Docker sul server](#2-installare-docker-sul-server)
3. [Portare i file del progetto sul server](#3-portare-i-file-del-progetto-sul-server)
4. [Configurare il file .env](#4-configurare-il-file-env)
5. [Creare il database e le tabelle](#5-creare-il-database-e-le-tabelle)
6. [Creare l'utente amministratore](#6-creare-lutente-amministratore)
7. [Avviare backend e frontend](#7-avviare-backend-e-frontend)
8. [Verificare che tutto funzioni](#8-verificare-che-tutto-funzioni)
9. [Dominio e HTTPS (consigliato, richiesto per pubblicare foto/video su Buffer)](#9-dominio-e-https-consigliato-richiesto-per-pubblicare-fotovideo-su-buffer)
10. [Backup e ripristino del database (il "dump")](#10-backup-e-ripristino-del-database-il-dump)
11. [Aggiornare il progetto in futuro](#11-aggiornare-il-progetto-in-futuro)
12. [Problemi noti e cose da sistemare](#12-problemi-noti-e-cose-da-sistemare)
13. [Istruzioni per Claude Code](#13-istruzioni-per-claude-code)
14. [Comandi di uso quotidiano (riepilogo)](#14-comandi-di-uso-quotidiano-riepilogo)

---

## 1. Cosa serve prima di iniziare

- Un server Linux (consigliato **Ubuntu 22.04 o 24.04 LTS**), con almeno 2 GB di RAM.
- Un utente con permessi `sudo` e accesso SSH (es. `ssh utente@IP_DEL_SERVER`).
- Nessuna conoscenza di Docker richiesta: i comandi sono già pronti qui sotto, basta copiarli.
- Facoltativo ma consigliato: un nome a dominio che punti all'IP del server (serve solo per il passo 9, HTTPS).

Tutto il progetto gira dentro **container Docker**: non devi installare Python, Node.js o Postgres direttamente sul server, solo Docker.

### Stack tecnologico (per orientarti, versioni già pinnate nel codice)

Nessuna di queste va installata a mano: sono già fissate nei Dockerfile/compose e Docker le scarica da sola al primo `build`.

| Componente | Tecnologia | Dove è pinnata |
|---|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy + Alembic | `apps/api/Dockerfile` |
| Task in background | Celery (worker + beat), Redis come broker | `apps/api/Dockerfile`, `docker-compose*.yml` |
| Frontend | Next.js su Node.js 22, gestito con pnpm (via Corepack) | `apps/dashboard/Dockerfile`, `package.json` (`packageManager`) |
| Database | PostgreSQL 16 | `docker-compose*.yml` (immagine `postgres:16-alpine`) |
| Cache / broker | Redis 7 | `docker-compose*.yml` (immagine `redis:7-alpine`) |
| Reverse proxy + HTTPS | Nginx 1.25 + Certbot (Let's Encrypt) | `infrastructure/nginx/nginx.conf`, `docker-compose.prod.yml` |
| Elaborazione media | FFmpeg (durata video, thumbnail) | `apps/api/Dockerfile` |
| Orchestrazione | Docker Compose — due file: `docker-compose.yml` (dev) e `docker-compose.prod.yml` (produzione, con Nginx/HTTPS) | radice del progetto |

---

## 2. Installare Docker sul server

Collegati al server via SSH, poi esegui:

```bash
# Aggiorna il sistema
sudo apt update && sudo apt upgrade -y

# Installa Docker (script ufficiale)
curl -fsSL https://get.docker.com | sudo sh

# Permetti al tuo utente di usare docker senza scrivere "sudo" ogni volta
sudo usermod -aG docker $USER
newgrp docker

# Verifica che funzioni
docker --version
docker compose version
```

Se `docker compose version` risponde con un numero di versione, sei a posto.

---

## 3. Portare i file del progetto sul server

Hai due strade. **Consigliata: Git**, perché rende semplicissimi i futuri aggiornamenti (vedi sezione 11).

### Opzione A — Git (consigliata)

Sul tuo PC Windows, dentro la cartella del progetto (`e:\Clienti\AgentMultiPost`), apri Git Bash e crea un repository:

```bash
cd /e/Clienti/AgentMultiPost
git init
git add .
git commit -m "Initial commit"
```

Crea un repository vuoto su GitHub (o GitLab, o un altro servizio) e collegalo:

```bash
git remote add origin https://github.com/raphaelcodeart/agi-postiz.git
git branch -M main
git push -u origin main
```

Sul server:

```bash
git clone https://github.com/raphaelcodeart/agi-postiz.git agi-post
cd agi-post
```

### Opzione B — Copia diretta (senza Git)

Se non vuoi usare Git, copia i file direttamente da Windows al server con `scp` (da Git Bash, sul tuo PC):

```bash
# Attenzione: NON copiare node_modules, .next, __pycache__ (sono pesanti e si rigenerano da soli)
rsync -avz --exclude 'node_modules' --exclude '.next' --exclude '__pycache__' --exclude '.venv' \
  /e/Clienti/AgentMultiPost/ utente@IP_DEL_SERVER:~/agi-post/
```

Se `rsync` non è disponibile su Windows, usa `scp -r` (più lento, copia tutto compresi i file inutili — poi cancellali sul server con `rm -rf node_modules apps/*/node_modules apps/dashboard/.next`).

> Con questa opzione, per aggiornare il codice in futuro dovrai ripetere la copia ogni volta. Con Git basta `git pull`.

---

## 4. Configurare il file .env

Il progetto ha **un solo file `.env` nella cartella principale**, condiviso da backend e frontend (Docker lo carica automaticamente in entrambi i container).

```bash
cd ~/agi-post   # o il nome che hai dato alla cartella
cp .env.example .env
nano .env
```

Cosa cambiare rispetto all'esempio (le altre righe puoi lasciarle come sono):

| Variabile | Cosa metterci | Perché |
|---|---|---|
| `SECRET_KEY` | una stringa casuale lunga | firma i login degli amministratori — se qualcuno la scopre può falsificare l'accesso |
| `ENCRYPTION_KEY` | una chiave generata come spiegato sotto | cripta i token Buffer salvati nel database |
| `POSTGRES_PASSWORD` | una password robusta a tua scelta | password del database |
| `DATABASE_URL` | aggiorna la password se l'hai cambiata sopra | stringa di connessione al database |
| `NEXT_PUBLIC_API_URL` | `http://IP_DEL_SERVER:8000` (o il tuo dominio, vedi sezione 9) | indirizzo che il **browser** userà per l'API |
| `API_INTERNAL_URL` | lascia `http://api:8000` | indirizzo che usa il frontend **dentro Docker** per parlare col backend, non cambia mai |
| `BUFFER_INTEGRATION_MODE` | `mock` finché non hai le credenziali Buffer reali, poi `production` | vedi sezione 12 |
| `OPENAI_API_KEY` | opzionale — di solito lasciala vuota | fallback di primo avvio per il pulsante "Genera con AI" (docs/FUNCTIONALITY.md §5). Il modo normale per configurarla è dalla pagina **Impostazioni** della dashboard (salvata cifrata nel database, non nel `.env`) — questa variabile serve solo se vuoi una chiave di default già attiva prima che un admin configuri la propria |

Genera `SECRET_KEY` con:

```bash
openssl rand -hex 32
```

Genera `ENCRYPTION_KEY` con:

```bash
docker run --rm python:3.12-slim python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

(il secondo comando è un fallback se non hai voglia di scaricare l'immagine Python solo per questo; il formato è compatibile).

Salva con `Ctrl+O`, esci con `Ctrl+X`.

**Importante:** questo file contiene segreti veri. Non finisce mai su Git (è già escluso in `.gitignore`) e non va condiviso.

---

## 5. Creare il database e le tabelle

Qui rispondo alla tua domanda "il database, le tabelle che servono come le creiamo?".

Il progetto usa **Alembic** (lo strumento standard di FastAPI/SQLAlchemy per gestire le tabelle del database in modo tracciato e ripetibile, invece di crearle a mano con SQL). Le migration che descrivono **tutte** le tabelle sono già scritte e salvate nel repository, in `apps/api/alembic/versions/` — non devi generarle tu, ti basta applicarle. Per la spiegazione di cosa contiene ogni tabella e come sono collegate tra loro, vedi **[docs/DATABASE.md](./DATABASE.md)**.

Passo per passo, dalla cartella del progetto sul server:

```bash
# 1) Avvia solo database e redis (non ancora backend/frontend)
docker compose up -d db redis

# 2) Aspetta ~10 secondi che il database sia pronto, poi controlla:
docker compose ps
# la colonna "STATUS" di "db" deve dire "healthy"

# 3) Costruisci l'immagine del backend (serve per eseguire i comandi Python/Alembic)
docker compose build api

# 4) Applica tutte le migration esistenti: QUESTO è il comando che crea davvero le
#    tabelle nel database, leggendo i file già presenti in apps/api/alembic/versions/
docker compose run --rm api alembic upgrade head
```

Se tutto va bene, il comando termina senza errori e ti ritrovi con **tutte** le tabelle di **tutti** i moduli create in un colpo solo (una sola cartella `alembic/versions/`, una sola catena di migration per l'intero progetto): il modulo principale (`users`, `user_groups`, `administrators`, `buffer_connections`, `buffer_organizations`, `social_channels`, `media_files`, `campaigns`, `campaign_targets`, `publications`, `publication_attempts`, `audit_logs`, `ai_settings` — vedi [DATABASE.md](./DATABASE.md)), il modulo Blog Writer (`blog_writer_*`, 3 tabelle — vedi [BLOG_WRITER.md §2](./BLOG_WRITER.md#2-schema-database)), il modulo Omnichannel Responder (`omni_*`, 15 tabelle — vedi [OMNICHANNEL_RESPONDER.md §3](./OMNICHANNEL_RESPONDER.md#3-schema-database)), oltre alla tabella tecnica `alembic_version` che Alembic usa per sapere a che punto è arrivato. Non serve applicare migration separate per ogni modulo: sono tutte nella stessa catena, un unico `alembic upgrade head` le applica tutte nell'ordine corretto. Elenco completo e sempre aggiornato dei nomi tabella, se vuoi verificarlo senza aprire i tre file doc sopra: `grep -rn '__tablename__' apps/api/app/models/*.py`.

Questo è tutto quello che serve per un nuovo server: le migration sono già pronte e versionate insieme al codice, quindi installare su un server nuovo, uno staging, o il tuo PC è sempre lo stesso identico comando (`alembic upgrade head`), senza bisogno di rigenerare nulla.

**Solo se in futuro modifichi i modelli del backend** (aggiungi/togli colonne o tabelle in `apps/api/app/models/`) serve generare una **nuova** migration che descriva quella differenza, poi salvarla su git come qualunque altro file di codice:

```bash
# genera il file che descrive solo la differenza rispetto all'ultima migration applicata
# (serve "docker compose" semplice, non quello di prod, perché solo il file di sviluppo
# collega la cartella apps/api al container - altrimenti il file generato sparisce col container)
docker compose run --rm api alembic revision --autogenerate -m "descrizione della modifica"

git add apps/api/alembic/versions/
git commit -m "Add migration: descrizione della modifica"
git push
```

Da quel momento, `alembic upgrade head` su qualunque ambiente applicherà anche la nuova migration insieme a tutte le precedenti.

---

### Nota: rinomina del database su questo server

Questo deployment e' nato quando il progetto si chiamava ancora diversamente, quindi il suo
database si chiama tuttora `social_publisher`, mentre tutto il resto del progetto (e i default
qui documentati) usa `agi_post`. Le due cose convivono senza problemi perche' il nome reale
arriva dal `.env`, che ha la precedenza sui default.

Per allinearlo, una volta sola, con lo stack in esecuzione:

```bash
cd /opt/agi-postiz
docker compose -f docker-compose.prod.yml stop api worker beat dashboard
docker compose -f docker-compose.prod.yml exec db \
  psql -U postgres -d postgres -c "ALTER DATABASE social_publisher RENAME TO agi_post;"

# poi aggiorna le due righe corrispondenti nel .env:
sed -i 's/^POSTGRES_DB=.*/POSTGRES_DB=agi_post/' .env
sed -i 's|@db:5432/social_publisher|@db:5432/agi_post|' .env

docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
curl -s https://api.46-225-185-149.sslip.io/api/v1/settings/health
```

L'ultimo comando deve rispondere `"database":"ok"`. Su un'installazione nuova non serve niente
di tutto questo: il database nasce gia' con il nome corretto.

---

## 6. Creare l'utente amministratore

Con il database pronto, crea il primo account per accedere alla dashboard:

```bash
docker compose run --rm api python -m app.utils.create_admin \
  --email "tuaemail@esempio.com" \
  --password "UnaPasswordRobusta123!" \
  --name "Il tuo nome"
```

Questo è l'account con cui farai login sulla dashboard (sezione 8).

> In alternativa esiste `make seed`, che crea l'admin **insieme a dati di esempio** (utenti finti, campagne finte) — comodo per fare un test rapido, ma **cancella e ricrea tutte le tabelle**, quindi usalo solo su un database vuoto/di prova, mai su un database con dati veri.

---

## 7. Avviare backend e frontend

Ci sono due file Docker Compose:

- **`docker-compose.yml`** — pensato per test/sviluppo: espone le porte 3000 (dashboard), 8000 (API), 5432 (database) e 6379 (redis) direttamente, così puoi raggiungerle da `http://IP_DEL_SERVER:3000` senza configurare nulla.
- **`docker-compose.prod.yml`** — pensato per produzione: solo Nginx espone le porte 80/443 verso l'esterno, tutto il resto resta interno e più sicuro. Richiede un dominio configurato (sezione 9).

### Per iniziare subito, senza dominio (consigliato per il primo avvio)

```bash
docker compose build
docker compose up -d
docker compose ps
```

Apri il browser su `http://IP_DEL_SERVER:3000` — dovresti vedere la pagina di login.

### Per la produzione vera e propria, con dominio e Nginx

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

(le migration vanno applicate anche qui — se le hai già fatte al passo 5 con l'altro compose file, il database è lo stesso volume solo se non hai cambiato `POSTGRES_DB`/`POSTGRES_USER`; altrimenti ripeti il passo 5 con `-f docker-compose.prod.yml`).

---

## 8. Verificare che tutto funzioni

```bash
# Il backend risponde?
curl http://localhost:8000/
# Deve rispondere: {"status":"online","service":"...","docs_url":"/docs"}

# Il controllo di salute (database, redis, worker) è ok?
curl http://localhost:8000/api/v1/settings/health

# I log, se qualcosa non va:
docker compose logs -f api
docker compose logs -f dashboard
docker compose logs -f worker
```

Poi apri il browser su `http://IP_DEL_SERVER:3000/login` (o il tuo dominio) e prova ad accedere con l'account creato al passo 6.

---

## 9. Dominio e HTTPS (consigliato, richiesto per pubblicare foto/video su Buffer)

HTTPS non è più opzionale se vuoi pubblicare foto/video: Buffer scarica il media dall'URL quando il post va in coda e rifiuta URL non-HTTPS (vedi problema noto #4 nella sezione 12). Le campagne di solo testo funzionano anche senza.

### Se hai già un dominio tuo

Punta questi sottodomini all'IP del server (record DNS di tipo A):

- `app.tuodominio.com` → dashboard
- `api.tuodominio.com` → backend
- `media.tuodominio.com` → file media

Poi modifica `infrastructure/nginx/nginx.conf` sostituendo i tre hostname `*.46-225-185-149.sslip.io` con i tuoi domini reali, e ripeti la procedura sotto passando i tuoi domini invece del valore sslip.io.

### Se non hai un dominio: sslip.io (nessun costo, nessuna registrazione)

[sslip.io](https://sslip.io) è un servizio DNS pubblico reale (non un dominio "interno" o finto) che fa risolvere hostname come `46-225-185-149.sslip.io` direttamente all'IP incorporato nel nome — senza possedere né configurare nulla. Essendo un dominio pubblico realmente risolvibile, **Let's Encrypt può emettere certificati HTTPS validi** per questi hostname tramite la normale challenge HTTP-01 (non serve un certificato wildcard).

`infrastructure/nginx/nginx.conf` in questo repo è già configurato per l'IP di questo server (`46.225.185.149` → `app.46-225-185-149.sslip.io`, `api.46-225-185-149.sslip.io`, `media.46-225-185-149.sslip.io`). Per ottenere i certificati reali:

```bash
docker compose down   # ferma lo stack dev, libera la porta 80
./scripts/setup-https.sh 46-225-185-149.sslip.io tuaemail@esempio.com
```

Lo script (vedi commenti in testa al file per i dettagli):
1. avvia uno stack temporaneo con Nginx in solo HTTP per rispondere alla verifica di Let's Encrypt;
2. richiede un certificato Let's Encrypt valido per tutti e tre gli hostname in un solo comando (Certbot, container ufficiale, nessuna installazione sull'host);
3. ripristina la configurazione Nginx finale con HTTPS attivo e la ricarica.

Da questo momento la piattaforma gira sullo **stack produzione** (`docker-compose.prod.yml`): solo Nginx espone le porte 80/443 verso l'esterno, tutto il resto (Postgres, Redis, API, dashboard) resta interno a Docker. **Nota**: questo stack usa un volume Postgres diverso da quello di sviluppo (`postgres_data_prod`), quindi al primo avvio va **ripetuta la sezione 5** (`alembic upgrade head`) e la **sezione 6** (creare l'amministratore) su questo volume.

Rinnovo automatico: i certificati Let's Encrypt durano 90 giorni. Una volta ottenuto il primo certificato, la configurazione Nginx finale (quella già nel repo) risponde già da sola alla verifica ACME su porta 80, quindi il rinnovo **non richiede più lo script**: basta `certbot renew` seguito da un reload di Nginx. Aggiungi in crontab (stesso schema del backup, sezione 10):

```bash
crontab -e
# Rinnovo certificato ogni notte alle 4:00 (no-op se non vicino a scadenza)
0 4 * * * cd /opt/agi-postiz && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload >> /opt/agi-postiz/backups/certbot-renew.log 2>&1
```

### Hostname temporaneo del provider (in attesa di un dominio)

Finché non viene acquistato un dominio, oltre ai tre hostname sslip.io la dashboard risponde anche
sull'hostname reverse-DNS fornito da Hetzner per questo server:
`https://static.149.185.225.46.clients.your-server.de` (attenzione: Hetzner costruisce quel nome con
gli ottetti **invertiti** rispetto all'IP reale, che è `46.225.185.149` — non è un errore).

Ha un proprio certificato Let's Encrypt, richiesto a parte perché `setup-https.sh` copre solo i tre
sottodomini sslip.io:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d static.149.185.225.46.clients.your-server.de \
  --email tuaemail@esempio.com --agree-tos --non-interactive --keep-until-expiring

docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

In `infrastructure/nginx/nginx.conf` è un semplice alias del vhost `app.*`: essendo un hostname singolo
non può avere i sottodomini `api.`/`media.`, quindi da qui la dashboard raggiunge il backend solo
attraverso il proprio proxy BFF same-origin. Per gli upload media pubblicati su Buffer resta valido
`PUBLIC_MEDIA_BASE_URL=https://media.46-225-185-149.sslip.io`.

Quando arriverà un dominio vero, sostituite i tre hostname sslip.io in `nginx.conf` (vedi sopra),
aggiornate `NEXT_PUBLIC_API_URL` e `PUBLIC_MEDIA_BASE_URL` nel `.env` e la lista CORS in
`apps/api/app/main.py`, poi rifate la procedura dei certificati.

Il cron di rinnovo descritto sopra copre **entrambi** i certificati (sslip.io e hostname temporaneo): `certbot renew` rinnova in un colpo solo tutti i certificati emessi su questo host, non serve una riga per ciascuno.

---

## 10. Backup e ripristino del database (il "dump")

Un **dump** è una fotografia completa del database in un file `.sql`: serve per fare backup, spostare i dati su un altro server, o tornare indietro se qualcosa va storto.

Ho preparato due script pronti in `scripts/`:

```bash
# Crea un backup completo in backups/<data>.sql (e backups/latest.sql)
./scripts/backup-db.sh

# Ripristina un backup (ATTENZIONE: sovrascrive i dati attuali, chiede conferma)
./scripts/restore-db.sh backups/latest.sql
```

Consigli pratici:

- Esegui `./scripts/backup-db.sh` **prima di ogni aggiornamento importante** del progetto.
- Scarica periodicamente i file da `backups/` sul tuo PC o su uno storage esterno (i backup restano solo sul server finché non li copi altrove — se il server si rompe, li perdi insieme al resto).
- Imposta un backup automatico giornaliero con `cron`, ad esempio:
  ```bash
  crontab -e
  # aggiungi questa riga (backup ogni notte alle 3:00):
  0 3 * * * cd ~/agi-post && ./scripts/backup-db.sh >> backups/backup.log 2>&1
  ```

### Backup settimanale automatico (già in uso in produzione su questo server)

Oltre a `backup-db.sh` (dump manuale, prima di un deploy rischioso), c'è un secondo script pensato per girare **da solo su una pianificazione**, senza intervento: `./scripts/weekly-backup-db.sh`. Differenze rispetto a `backup-db.sh`:

- Scrive in `weekly-backup-db/` (non `backups/`), compresso (`.sql.gz`, non `.sql`).
- Usa `docker-compose.prod.yml` di default (`backup-db.sh`/`restore-db.sh` invece di default userebbero `docker-compose.yml`, lo stack dev — funziona comunque in produzione per via di come Docker Compose risolve i container per nome-servizio, vedi l'avviso nella sezione 11, ma qui è esplicito).
- **Fa da solo la pulizia**: tiene solo le ultime `KEEP_WEEKS` copie (default 12 settimane) ed elimina le più vecchie automaticamente, così la cartella non cresce all'infinito.
- Anche questi file restano **solo sul server** (esclusi da git, vedi `.gitignore`) — scaricali periodicamente altrove come per `backups/`.

Su questo server è già installato così (verificalo con `crontab -l` e replica lo stesso su un server nuovo):

```bash
crontab -e
# Backup completo settimanale, ogni domenica alle 3:30, con pulizia automatica
30 3 * * 0 cd /opt/agi-postiz && /usr/bin/env bash scripts/weekly-backup-db.sh >> /opt/agi-postiz/weekly-backup-db/cron.log 2>&1
```

(sostituisci `/opt/agi-postiz` con il path reale del progetto sul server, se diverso).

---

## 11. Aggiornare il progetto in futuro

> **Attenzione se sei passato allo stack produzione (`docker-compose.prod.yml`)**: i due file compose usano
> nomi di servizio identici (`db`, `redis`, `api`, `dashboard`, `nginx`...) sotto lo stesso progetto Docker
> Compose (derivato dal nome della cartella). Questo significa che comandi `docker compose` **senza `-f
> docker-compose.prod.yml`** (cioè che usano implicitamente `docker-compose.yml`) possono rimuovere o
> ricreare containers di produzione già in esecuzione, scambiandoli per lo stesso servizio. **Una volta in
> produzione, usa sempre `-f docker-compose.prod.yml` in ogni comando `docker compose`, mai il file dev.**
> I volumi dati restano comunque separati e al sicuro (`postgres_data` vs `postgres_data_prod`, ecc.), quindi
> nella peggiore ipotesi si tratta di un riavvio, non di perdita dati — ma è comunque da evitare.
>
> Nota anche: se ricostruisci le immagini `api`/`worker`/`beat`/`dashboard` mentre lo stack è già attivo,
> Nginx tiene in cache l'IP dei container upstream e non si accorge da solo che sono stati ricreati — dopo
> ogni `docker compose -f docker-compose.prod.yml up -d <servizio>` che ricrea un container, esegui anche
> `docker compose -f docker-compose.prod.yml exec nginx nginx -s reload` (lo fa già `scripts/deploy.sh`).

Se hai usato Git (opzione A al passo 3), aggiornare è semplice. Ho preparato uno script che fa tutto:

```bash
./scripts/deploy.sh
```

Fa, in ordine: `git pull`, ricostruisce le immagini Docker cambiate, applica eventuali nuove migration del database, riavvia tutti i servizi. Usa `docker-compose.prod.yml` di default; se stai ancora usando la configurazione senza dominio, esegui `COMPOSE_FILE=docker-compose.yml ./scripts/deploy.sh`.

Se hai copiato i file manualmente (opzione B), ripeti la copia con `rsync`, poi:

```bash
docker compose build
docker compose run --rm api alembic upgrade head
docker compose up -d
```

---

## 12. Problemi noti e cose da sistemare

Trasparenza su alcune cose che **non funzioneranno ancora perfettamente** su un server reale, così non perdi tempo a capire perché:

1. ~~Il collegamento OAuth con Buffer reindirizza sempre a `localhost:3000`~~ — **risolto**: il collegamento non usa più OAuth. Verificato su developers.buffer.com (luglio 2026) che Buffer non accetta più registrazioni OAuth di nuove app di terze parti (né sulla vecchia REST API, né — non ancora — sulla nuova API GraphQL). Ogni utente genera una **chiave API personale** dal proprio account Buffer (Settings → API) e la incolla nella dashboard (pulsante "Collega account" in Connessioni Buffer); il backend la valida e la salva cifrata. Nessun redirect, nessun problema di dominio/localhost.
2. **CORS nel backend** (`apps/api/app/main.py`) accetta richieste da `http://localhost:3000`, `http://app.example.com` e dal dominio sslip.io configurato per questo server (`https://app.46-225-185-149.sslip.io`). Se usi un dominio diverso, aggiorna quella lista. Nota: il collegamento Buffer e la maggior parte delle chiamate della dashboard passano dal proxy interno same-origin, quindi non sono influenzate da questo; riguarda solo eventuali chiamate dirette al backend dal browser.
3. **`BUFFER_INTEGRATION_MODE=mock`** nel `.env`: finché resta così, la piattaforma non parla col vero Buffer, usa dati finti generati dal backend stesso (utile per collaudare tutto senza account Buffer reali). Quando un utente fornisce la propria chiave API Buffer reale, va cambiato `BUFFER_INTEGRATION_MODE=production` — non serve più nessuna credenziale a livello di piattaforma (niente `BUFFER_CLIENT_ID`/`BUFFER_CLIENT_SECRET`, rimossi).
4. ~~Pubblicazione di foto/video su Buffer richiede hosting media in HTTPS pubblico~~ — **risolvibile**: segui la sezione 9 (`./scripts/setup-https.sh`) per attivare HTTPS reale con un dominio sslip.io. `PUBLIC_MEDIA_BASE_URL` nel `.env` deve puntare all'origine `https://media.<tuo-dominio>` risultante; il guardrail in `apps/api/app/tasks/publication.py` continuerà a rifiutare esplicitamente (Publication "failed", categoria "configuration_error") solo se questa variabile non è ancora configurata in HTTPS. Le campagne di solo testo funzionano comunque anche senza.
5. **Media caricati**: i file finiscono in un volume Docker (`media_storage`), servito da Nginx. Se cambi server, i file media non si spostano da soli — vanno copiati a parte (non sono nel dump del database).
6. ~~Upload di video nella sezione Media (o nella creazione campagna) non caricava nulla, senza errore chiaro~~ — **risolto**: tutte le richieste della dashboard (incluso l'upload) passano dal proxy BFF same-origin (`app/api/backend/[...path]/route.ts`), quindi da Nginx sul vhost `app.*`, non su quello `api.*`. Quel vhost aveva `client_max_body_size 10M`, mentre il backend accetta fino a `UPLOAD_MAX_SIZE_BYTES` (100MB) — i video, quasi sempre oltre i 10MB, venivano rifiutati da Nginx con un 413 prima ancora di arrivare al backend, e il messaggio d'errore mostrato in dashboard era generico. Corretto allineando `client_max_body_size` a 100M anche sul vhost `app.*` in `infrastructure/nginx/nginx.conf` (poi alzato a 500M assieme a `UPLOAD_MAX_SIZE_BYTES`, vedi commit "Raise media upload limit to 500MB").
7. **Canali Instagram personali (`channel_type="profile"`) non possono mai pubblicare via API** — non è un bug di questo software: è una limitazione strutturale di Instagram/Meta (solo gli account Professional/Business, collegati a una Pagina Facebook, hanno il permesso "Content Publishing"). Confermato con l'errore Buffer reale osservato in produzione: *"Instagram personal profile channels require notification scheduling."* `launch_campaign` intercetta ora questo caso proattivamente ed esclude subito il canale invece di ritentare per giorni sullo stesso errore permanente (vedi [FUNCTIONALITY.md §5](./FUNCTIONALITY.md#5-campagne-targeting-e-testo)) — ma l'unico modo per rendere quel canale davvero pubblicabile resta convertire l'account in Professional/Business su Instagram e ricollegarlo su Buffer. Nota collegata: `SocialChannel.publication_mode` in stato `notification`/`approval` è oggi puramente descrittivo (solo `disabled` ha un effetto reale, vedi [DATABASE.md §5](./DATABASE.md#5-integrazione-buffer)) — impostare un canale su "Notifica" non cambia il comportamento di pubblicazione.
8. ~~Video Instagram oltre 1 minuto falliva sempre con "Video must be no longer than 1 minute for Instagram Posts"~~ — **risolto**: `prod_client.create_post()` pubblica ora come `metadata.instagram.type="reel"` (nessun limite di durata) invece di `"post"` quando `MediaFile.duration_seconds` supera 60s; sotto quella soglia, o con durata sconosciuta, resta `"post"` come prima. Dettagli in [FUNCTIONALITY.md §5](./FUNCTIONALITY.md#5-campagne-targeting-e-testo).
9. ~~Drift tra modelli SQLAlchemy e migration Alembic sul modulo Omnichannel~~ — **risolto** (2026-08-14): il modulo Omnichannel Responder era stato aggiunto senza generare la migration per un indice/vincolo su `omni_ai_agent_configs.owner_id` e `omni_tags.owner_id` (violando la regola descritta in [sezione 5](#5-creare-il-database-e-le-tabelle) di questo stesso file: "se modifichi i modelli, genera una nuova migration"). Verificato con `alembic check` su un database usa-e-getta isolato (mai toccato quello di produzione per la verifica) e corretto con la migration `3eb6838d3b1b`. Se in dubbio in futuro su eventuale drift residuo, `docker compose run --rm api alembic check` lo segnala senza modificare nulla.

Nessuno di questi blocca l'avvio della dashboard, degli utenti, delle campagne o del resto: riguardano solo l'integrazione reale con Buffer.

---

## 13. Istruzioni per Claude Code

Se l'utente ti chiede di fare il deploy su un server a cui hai accesso (es. via terminale SSH collegato), segui questo ordine e **fermati a chiedere conferma prima di ogni passo distruttivo** (sovrascrivere `.env` esistente, `alembic upgrade` su un database con dati veri, `restore-db.sh`, force-push):

0. Determina quale scenario della [sezione 0](#0-due-scenari-diversi-leggi-qui-prima-di-iniziare) vale: se l'utente non lo specifica, **assumi lo scenario A** (installazione nuova vuota, nessun ripristino dati) e dillo esplicitamente nella tua risposta, così può correggerti se intendeva lo scenario B (migrazione con dati) — non indovinare in base al contesto, chiedi se è ambiguo.
1. Verifica cosa esiste già sul server prima di agire: `docker --version`, presenza di una cartella del progetto, un `.env` già configurato, container già in esecuzione (`docker compose ps`). Non sovrascrivere nulla di esistente senza chiedere.
2. Segui le sezioni 2 → 8 in ordine. Salta i passi già completati (es. se Docker è già installato, salta la sezione 2). Se lo scenario è B, salta la creazione dell'admin al passo 6 (sezione 0, punto 1) — arriverà dal ripristino del backup.
3. Per la sezione 4 (`.env`): se il file esiste già, NON rigenerarlo — leggilo e verifica solo che le variabili richieste siano presenti. Se manca, generalo con i comandi indicati e mostra all'utente cosa hai messo (tranne i segreti, di quelli conferma solo che sono stati generati).
4. Per la sezione 5: se `apps/api/alembic/versions/` contiene già dei file, **non generare una nuova migration iniziale** — esegui solo `alembic upgrade head`. Genera una nuova migration solo se l'utente ha modificato i modelli SQLAlchemy e te lo chiede esplicitamente.
5. Dopo ogni `docker compose up -d`, verifica lo stato con `docker compose ps` e i log (`docker compose logs --tail 50 <servizio>`) prima di dichiarare il passo riuscito.
6. Esegui sempre `./scripts/backup-db.sh` prima di un redeploy che tocca un database con dati reali.
7. Se il deploy arriva fino alla sezione 9 (dominio/HTTPS reale, non solo il primo avvio senza dominio): installa anche i due cron job ricorrenti descritti nelle sezioni 9 e 10 (rinnovo certificato Let's Encrypt + backup settimanale `weekly-backup-db.sh`) con `crontab -e`, non solo l'avvio dei container — altrimenti il certificato scadrà in ~90 giorni e non ci sarà nessun backup automatico. Su un'installazione senza dominio (primo avvio, sezione 7 "senza dominio") questo passo non si applica ancora.
8. Alla fine, riporta all'utente: quali container sono attivi, su quale URL è raggiungibile la dashboard, quali credenziali admin sono state create (senza scrivere la password in chiaro nel riepilogo se il canale non è sicuro — di' solo che è stata impostata), quali cron job ricorrenti sono stati installati, e quali dei "problemi noti" (sezione 12) restano da sistemare.

Non modificare l'integrazione Buffer reale, i worker Celery o la logica di pubblicazione durante un deploy, a meno che l'utente non lo chieda esplicitamente (vedi `AGENTS.md` alla radice del progetto).

---

## 14. Comandi di uso quotidiano (riepilogo)

```bash
# Stato dei servizi
docker compose ps

# Log di un servizio in tempo reale
docker compose logs -f api
docker compose logs -f dashboard

# Riavviare un servizio
docker compose restart api

# Fermare tutto
docker compose down

# Backup del database (manuale, prima di un deploy rischioso)
./scripts/backup-db.sh

# Backup settimanale completo con pulizia automatica (di solito su cron, non a mano)
./scripts/weekly-backup-db.sh

# Aggiornare il progetto (dopo git pull automatico)
./scripts/deploy.sh

# Aprire una shell dentro il container del backend (debug)
docker compose exec api bash

# Creare un nuovo amministratore
docker compose run --rm api python -m app.utils.create_admin --email "..." --password "..." --name "..."
```
