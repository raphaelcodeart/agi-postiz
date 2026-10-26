import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # General
    ENVIRONMENT: str = "local"
    PROJECT_NAME: str = "Agi Post"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(default="supersecretjwtkeyforadminauthsocialpublisher123!")
    ENCRYPTION_KEY: str = Field(default="38x26P_s-Ld_j4pL9V10L1-82h0YF6p2-LpE10d9Y2I=")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Databases
    DATABASE_URL: str = Field(default="postgresql+psycopg://postgres:postgres_secure_pass_123@db:5432/agi_post")
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # Buffer API - connections authenticate with a per-user personal API key
    # pasted into the dashboard, not OAuth (see app/integrations/buffer/client.py)
    BUFFER_INTEGRATION_MODE: str = "mock"  # "mock" or "production"

    # bundle.social: multi-tenant provider where ONE platform key serves every
    # end user, who is identified by team id instead. Keep "mock" until the
    # production client is completed - see
    # app/integrations/bundle_social/prod_client.py.
    BUNDLE_SOCIAL_INTEGRATION_MODE: str = "mock"  # "mock" or "production"
    BUNDLE_SOCIAL_API_KEY: str = ""
    # Every connection of this provider shares one upstream quota, so its
    # concurrency is capped per provider rather than per connection
    # (see services/rate_limiter.py).
    BUNDLE_SOCIAL_CONCURRENCY_LIMIT: int = 4
    # Public origin of the portal, used to build the return URL of the hosted
    # OAuth flow. Must be the address the END USER sees in their browser, not an
    # internal one, or the provider bounces them somewhere unreachable.
    PORTAL_PUBLIC_BASE_URL: str = "http://localhost:3000"
    # Logo shown on the provider's hosted connect page, so the step looks like
    # ours. Must be a public absolute URL the provider can load.
    PORTAL_BRAND_LOGO_URL: str = ""
    # Shared secret from the provider's webhook dashboard, used to verify the
    # HMAC-SHA256 signature on incoming deliveries. Empty = webhook disabled.
    BUNDLE_SOCIAL_WEBHOOK_SECRET: str = ""

    # OpenAI - optional, powers the campaign wizard's AI text-generation helper
    # (app/integrations/openai/client.py). Feature is hidden in the dashboard
    # when unset; never exposed to the frontend, requests are proxied server-side.
    OPENAI_API_KEY: Optional[str] = None
    # CRM Mamify per l'Omnichannel Responder: ripiego a livello di
    # installazione, la chiave salvata dalla pagina AI Agent vince sempre.
    MAMIFY_RAG_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Email transazionali (SMTP) ---
    # Usate per la conferma dell'indirizzo alla registrazione e per il reset
    # della password: due messaggi che, se non partono, lasciano l'utente fuori
    # dal proprio account. Vuote = invio disattivato (vedi
    # services/email/mailer.py): in locale e nei test non si manda niente e non
    # si fallisce, in produzione l'assenza di configurazione e' un errore
    # esplicito nei log, mai un'email silenziosamente persa.
    SMTP_HOST: str = ""
    # 587 + STARTTLS e non 465: la 465 verso smtp.hostinger.com e' filtrata in
    # uscita da questo server (verificato aprendo i socket: la 587 risponde con
    # il banner ESMTP, la 465 va in timeout). Chi cambia provider cambia anche
    # SMTP_USE_SSL.
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    # True = TLS implicito (porta 465). False = connessione in chiaro promossa
    # con STARTTLS (porta 587); la promozione e' obbligatoria, mai opzionale -
    # se il server non offre STARTTLS l'invio fallisce invece di spedire le
    # credenziali in chiaro.
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 20
    # Mittente. EMAIL_FROM_ADDRESS deve appartenere a un dominio che autorizza
    # questo server in SPF, altrimenti i messaggi finiscono in spam: mamify.ai
    # pubblica "v=spf1 include:_spf.mail.hostinger.com ~all", quindi l'invio
    # deve passare per l'SMTP di Hostinger con una casella di quel dominio.
    EMAIL_FROM_ADDRESS: str = ""
    EMAIL_FROM_NAME: str = "AGI Post"
    # Dove finiscono le risposte: la casella noreply non e' letta da nessuno, e
    # un utente che risponde a un'email di benvenuto merita di essere letto.
    EMAIL_REPLY_TO: str = ""
    # Validita' dei link inviati per email. Quello di conferma e' lungo (una
    # registrazione puo' essere letta il giorno dopo), quello di reset e' corto
    # perche' e' un'apertura temporanea sull'account.
    EMAIL_VERIFICATION_TTL_HOURS: int = 72
    PASSWORD_RESET_TTL_MINUTES: int = 60
    # Informative linkate nell'email di benvenuto: cliccare il pulsante vale
    # come accettazione, quindi il testo deve poterle mostrare prima del clic.
    # Sono gli stessi documenti linkati nel footer di mamify.ai e della landing
    # di AGI Post, e devono restare gli stessi: il portale non ha condizioni
    # proprie. Il frontend ne tiene la copia in
    # apps/dashboard/app/portal/_shared/legal.tsx, perche' quelle pagine non
    # leggono la configurazione del backend.
    PRIVACY_POLICY_URL: str = "https://mamify.ai/privacy"
    TERMS_URL: str = "https://mamify.ai/termini"
    COOKIE_POLICY_URL: str = "https://mamify.ai/cookie"

    # --- Requisito canali social per promoter ---
    # Il progetto chiede a ogni promoter almeno questo numero di canali social
    # collegati e utilizzabili (stessa regola di idoneita' delle campagne, vedi
    # services/channel_requirement_service.py). La pagina "Canali insufficienti"
    # della dashboard elenca chi e' sotto soglia e permette di avvisarlo via
    # email; il cooldown evita che "Notifica a tutti" premuto due volte in una
    # settimana mandi due volte lo stesso messaggio alla stessa persona.
    MIN_SOCIAL_CHANNELS_PER_USER: int = 2
    CHANNEL_NOTICE_COOLDOWN_DAYS: int = 7

    @property
    def email_enabled(self) -> bool:
        """
        Vero solo quando c'e' tutto il necessario per spedire davvero.

        Un mittente senza host, o un host senza mittente, e' una configurazione
        a meta': meglio trattarla come "invio spento" ed esserne avvisati nei
        log che tentare una connessione che non puo' funzionare a ogni
        registrazione.
        """
        return bool(self.SMTP_HOST and self.EMAIL_FROM_ADDRESS)

    # Media Storage
    UPLOAD_MAX_SIZE_BYTES: int = 524288000  # 500MB - see infrastructure/nginx/nginx.conf client_max_body_size, must match
    MEDIA_STORAGE_DIR: str = "/storage/uploads"
    THUMBNAIL_STORAGE_DIR: str = "/storage/thumbnails"
    # Public origin the "media" nginx vhost is reachable at (see
    # infrastructure/nginx/nginx.conf). Must be HTTPS in production - Buffer
    # fetches media by URL and requires it to be public HTTPS.
    PUBLIC_MEDIA_BASE_URL: str = "http://localhost:8080"
    TEMPORARY_STORAGE_DIR: str = "/storage/temporary"

    # Concurrency & Policies
    GLOBAL_CONCURRENCY_LIMIT: int = 5
    CONCURRENT_JOBS_PER_CONNECTION: int = 1
    PAUSE_BETWEEN_REQUESTS_SECONDS: int = 10
    # Randomness added to the pause above. A request landing on exactly the same
    # interval every time is itself a machine signature; a few seconds of jitter
    # makes the cadence irregular at no cost.
    PAUSE_JITTER_SECONDS: int = 5
    # Minimum spacing between two posts on the SAME channel. This is the limit
    # that protects a promoter's own account: what a platform sees is one
    # profile's posting frequency, not our aggregate throughput. Set to 0 to
    # disable (not recommended with a shared-quota provider, where nothing else
    # would space out two campaigns hitting the same profile).
    MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL: int = 900
    MAX_PUBLICATION_ATTEMPTS: int = 5

    # Retry sequence in seconds (comma-separated list parsed by property)
    RETRY_BACKOFF_SEQUENCE_SECONDS: str = "60,300,900,3600,21600"

    @property
    def retry_backoff_list(self) -> List[int]:
        try:
            return [int(x.strip()) for x in self.RETRY_BACKOFF_SEQUENCE_SECONDS.split(",")]
        except ValueError:
            return [60, 300, 900, 3600, 21600]

    # Ensure storage paths exist
    def create_directories(self) -> None:
        for path in [self.MEDIA_STORAGE_DIR, self.THUMBNAIL_STORAGE_DIR, self.TEMPORARY_STORAGE_DIR]:
            os.makedirs(path, exist_ok=True)

settings = Settings()
# Execute directory creation during startup configuration parsing
try:
    settings.create_directories()
except Exception:
    # Fail silently if running in environments where storage volumes aren't mounted yet (e.g., local builds)
    pass
