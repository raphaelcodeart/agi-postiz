-- ============================================================================
-- Dump di sola STRUTTURA (schema-only, zero dati/righe) del database
-- "social_publisher" — generato con:
--   pg_dump -U postgres -d social_publisher --schema-only --no-owner --no-privileges
--
-- Snapshot generato: 2026-08-26 21:45 UTC, dal server di produzione di questo
-- progetto, alla revisione Alembic "e5f6a7b8c9d0" (head) - `SELECT version_num
-- FROM alembic_version;`. Rigenerato per una migration reale dal precedente
-- snapshot (2026-08-26 21:01, revisione "d4e5f6a7b8c9"): "e5f6a7b8c9d0"
-- aggiunge a stat_metric_history le colonne likes/impressions/reach, mancanti
-- da quando la tabella e' stata creata - fix di un bug reale (vedi
-- STATISTICS.md §2 e §9). Include quindi sia le tabelle/colonne nuove sia
-- tutte quelle preesistenti.
--
-- QUESTO FILE NON È LA FONTE DI VERITÀ DELLO SCHEMA. Lo sono le migration in
-- apps/api/alembic/versions/ (vedi docs/DEPLOYMENT.md §5): per creare il
-- database su un server nuovo, esegui `alembic upgrade head`, NON importare
-- questo file con `psql`. Le migration restano sempre sincronizzate col
-- codice (ogni modifica ai modelli SQLAlchemy genera una nuova migration);
-- questo dump invece è una fotografia statica che invecchia dal momento in
-- cui viene generata — utile solo per una lettura rapida "a colpo d'occhio"
-- dell'intero schema in un unico file SQL standard, o per un confronto
-- manuale, non per un restore.
--
-- Per rigenerarlo dopo un cambiamento reale di schema:
--   docker exec <container_db> pg_dump -U postgres -d social_publisher \
--     --schema-only --no-owner --no-privileges > docs/schema.sql
-- (poi ripeti manualmente la pulizia delle righe \restrict/\unrestrict,
-- token casuali per esecuzione introdotti da pg_dump 16.10+, privi di
-- significato in un file versionato — non servono per un semplice restore
-- di sola lettura).
-- ============================================================================

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: administrators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.administrators (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: ai_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_settings (
    id uuid NOT NULL,
    openai_api_key_encrypted character varying(1000),
    openai_model character varying(100) NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    administrator_id uuid,
    action character varying(255) NOT NULL,
    entity_type character varying(100) NOT NULL,
    entity_id uuid,
    metadata jsonb,
    ip_address character varying(45),
    user_agent character varying(500),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: blog_writer_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_writer_articles (
    id uuid NOT NULL,
    user_id uuid,
    title character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    excerpt character varying(1000),
    content character varying NOT NULL,
    hashtags jsonb,
    primary_keyword character varying(255),
    secondary_keywords jsonb,
    meta_title character varying(255),
    meta_description character varying(500),
    language character varying(10) NOT NULL,
    tone character varying(100),
    target_audience character varying(255),
    article_goal character varying(255),
    generation_prompt jsonb,
    generation_model character varying(100),
    status character varying(30) NOT NULL,
    created_by uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    last_edited_at timestamp with time zone,
    published_at timestamp with time zone,
    media_file_id uuid
);


--
-- Name: blog_writer_publications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_writer_publications (
    id uuid NOT NULL,
    article_id uuid NOT NULL,
    wordpress_site_id uuid NOT NULL,
    wordpress_post_id integer,
    wordpress_post_url character varying(1000),
    wordpress_status character varying(20),
    publication_status character varying(20) NOT NULL,
    request_payload jsonb,
    response_summary jsonb,
    error_message character varying(1000),
    retry_count integer NOT NULL,
    published_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: blog_writer_wordpress_sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blog_writer_wordpress_sites (
    id uuid NOT NULL,
    user_id uuid,
    name character varying(255) NOT NULL,
    site_url character varying(1000) NOT NULL,
    api_url character varying(1000) NOT NULL,
    username character varying(255) NOT NULL,
    encrypted_application_password character varying(1000) NOT NULL,
    default_author_id integer,
    default_author_name character varying(255),
    default_category_id integer,
    default_category_name character varying(255),
    default_status character varying(20) NOT NULL,
    language character varying(10) NOT NULL,
    is_active boolean NOT NULL,
    connection_status character varying(20) NOT NULL,
    last_connection_test_at timestamp with time zone,
    last_connection_error character varying(1000),
    last_published_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: buffer_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.buffer_connections (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    authentication_type character varying(50) NOT NULL,
    external_account_id character varying(255),
    access_token_encrypted character varying(1000),
    refresh_token_encrypted character varying(1000),
    token_expires_at timestamp with time zone,
    scopes character varying(500),
    status character varying(50) NOT NULL,
    last_sync_at timestamp with time zone,
    last_error character varying(1000),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: buffer_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.buffer_organizations (
    id uuid NOT NULL,
    buffer_connection_id uuid NOT NULL,
    external_organization_id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    raw_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: campaign_targets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaign_targets (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    user_id uuid NOT NULL,
    social_channel_id uuid NOT NULL,
    resolved_text character varying(5000) NOT NULL,
    status character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaigns (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    default_text character varying(5000) NOT NULL,
    instagram_text character varying(5000),
    facebook_text character varying(5000),
    linkedin_text character varying(5000),
    tiktok_text character varying(5000),
    youtube_title character varying(100),
    youtube_description character varying(5000),
    x_text character varying(280),
    threads_text character varying(500),
    media_file_id uuid,
    publishing_mode character varying(50) NOT NULL,
    scheduled_at timestamp with time zone,
    timezone character varying(100) NOT NULL,
    targeting_mode character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    created_by uuid,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    metadata jsonb,
    article_id uuid,
    include_referral_link boolean NOT NULL,
    include_personal_contacts boolean NOT NULL
);


--
-- Name: media_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media_files (
    id uuid NOT NULL,
    original_filename character varying(255) NOT NULL,
    stored_filename character varying(255) NOT NULL,
    storage_key character varying(500) NOT NULL,
    public_url character varying(1000) NOT NULL,
    mime_type character varying(100) NOT NULL,
    size_bytes integer NOT NULL,
    duration_seconds double precision,
    width integer,
    height integer,
    aspect_ratio character varying(50),
    video_codec character varying(50),
    audio_codec character varying(50),
    checksum character varying(64),
    processing_status character varying(50) NOT NULL,
    validation_status character varying(50) NOT NULL,
    validation_errors jsonb,
    metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: omni_ai_agent_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_ai_agent_configs (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    system_prompt text,
    language character varying(10) NOT NULL,
    tone character varying(50) NOT NULL,
    temperature double precision NOT NULL,
    company_description text,
    allowed_topics jsonb,
    forbidden_topics jsonb,
    signature character varying(255),
    max_context_messages integer NOT NULL,
    knowledge_base_enabled boolean NOT NULL,
    automatic_language_detection boolean NOT NULL,
    response_mode character varying(30) NOT NULL,
    sensitive_categories jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    auto_generate_draft boolean NOT NULL
);


--
-- Name: omni_ai_drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_ai_drafts (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    source_message_id uuid,
    original_ai_text text,
    edited_text text,
    status character varying(30) NOT NULL,
    model character varying(100),
    prompt_version character varying(50),
    confidence_score double precision,
    sensitive_category character varying(100),
    failure_reason text,
    created_at timestamp with time zone NOT NULL,
    approved_at timestamp with time zone,
    approved_by uuid,
    sent_at timestamp with time zone
);


--
-- Name: omni_ai_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_ai_usage (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    conversation_id uuid,
    model character varying(100) NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    estimated_cost double precision NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_audit_logs (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    admin_id uuid,
    action character varying(100) NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid,
    metadata jsonb,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_channel_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_channel_accounts (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    channel character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    external_account_id character varying(255),
    status character varying(50) NOT NULL,
    access_token_encrypted text,
    webhook_secret character varying(64) NOT NULL,
    config jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: omni_conversation_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_conversation_tags (
    owner_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


--
-- Name: omni_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_conversations (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    channel_account_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    status character varying(50) NOT NULL,
    assigned_admin_id uuid,
    unread_count integer NOT NULL,
    last_message_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: omni_customer_identities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_customer_identities (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    channel character varying(50) NOT NULL,
    external_user_id character varying(255) NOT NULL,
    display_name character varying(255),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_customers (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    name character varying(255),
    first_name character varying(255),
    last_name character varying(255),
    phone character varying(50),
    email character varying(255),
    language character varying(10),
    timezone character varying(100),
    notes text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    last_contact_at timestamp with time zone,
    is_blocked boolean NOT NULL
);


--
-- Name: omni_internal_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_internal_notes (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    admin_id uuid,
    text text NOT NULL,
    mentions jsonb,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_knowledge_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_knowledge_chunks (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    document_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_knowledge_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_knowledge_documents (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    source_type character varying(20) NOT NULL,
    content_text text,
    source_url character varying(1000),
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: omni_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_messages (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    channel_account_id uuid NOT NULL,
    direction character varying(20) NOT NULL,
    sender_type character varying(20) NOT NULL,
    external_message_id character varying(255),
    text text,
    message_type character varying(20) NOT NULL,
    attachments jsonb,
    metadata jsonb,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_notifications (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    admin_id uuid,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    entity_type character varying(50),
    entity_id uuid,
    read_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: omni_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.omni_tags (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    color character varying(20),
    created_at timestamp with time zone NOT NULL
);


--
-- Name: publication_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publication_attempts (
    id uuid NOT NULL,
    publication_id uuid NOT NULL,
    attempt_number integer NOT NULL,
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    success boolean NOT NULL,
    http_status integer,
    external_error_code character varying(100),
    error_category character varying(100),
    error_message character varying(1000),
    sanitized_request jsonb,
    sanitized_response jsonb,
    duration_ms integer,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: publications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publications (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    campaign_target_id uuid NOT NULL,
    user_id uuid NOT NULL,
    social_channel_id uuid NOT NULL,
    buffer_connection_id uuid NOT NULL,
    external_channel_id character varying(255) NOT NULL,
    status character varying(50) NOT NULL,
    attempt_count integer NOT NULL,
    max_attempts integer NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    scheduled_at timestamp with time zone,
    next_attempt_at timestamp with time zone,
    processing_started_at timestamp with time zone,
    submitted_at timestamp with time zone,
    confirmed_at timestamp with time zone,
    published_at timestamp with time zone,
    external_post_id character varying(255),
    external_post_url character varying(1000),
    error_category character varying(100),
    error_code character varying(100),
    error_message character varying(1000),
    request_metadata jsonb,
    response_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: social_channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.social_channels (
    id uuid NOT NULL,
    buffer_organization_id uuid NOT NULL,
    external_channel_id character varying(255) NOT NULL,
    platform character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    username character varying(255),
    avatar_url character varying(1000),
    channel_type character varying(100),
    is_active boolean NOT NULL,
    auto_publish_enabled boolean NOT NULL,
    publication_mode character varying(50) NOT NULL,
    last_sync_at timestamp with time zone,
    raw_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    external_link character varying(1000)
);


--
-- Name: stat_metric_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stat_metric_history (
    id uuid NOT NULL,
    publication_id uuid NOT NULL,
    synced_at timestamp with time zone NOT NULL,
    reactions double precision,
    views double precision,
    follows double precision,
    clicks double precision,
    comments double precision,
    shares double precision,
    engagement_rate double precision,
    metrics_raw jsonb,
    created_at timestamp with time zone NOT NULL,
    likes double precision,
    impressions double precision,
    reach double precision
);


--
-- Name: stat_post_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stat_post_metrics (
    id uuid NOT NULL,
    publication_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    user_id uuid NOT NULL,
    social_channel_id uuid NOT NULL,
    buffer_connection_id uuid NOT NULL,
    platform character varying(50) NOT NULL,
    external_post_id character varying(255) NOT NULL,
    external_post_url character varying(1000),
    published_at timestamp with time zone,
    reactions double precision,
    likes double precision,
    views double precision,
    impressions double precision,
    reach double precision,
    follows double precision,
    clicks double precision,
    comments double precision,
    shares double precision,
    engagement_rate double precision,
    metrics_raw jsonb,
    metrics_updated_at timestamp with time zone,
    last_synced_at timestamp with time zone,
    last_sync_error character varying(1000),
    last_sync_run_id uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: stat_sync_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stat_sync_runs (
    id uuid NOT NULL,
    scope character varying(20) NOT NULL,
    scope_user_id uuid,
    scope_campaign_id uuid,
    triggered_by uuid,
    status character varying(30) NOT NULL,
    total_posts integer NOT NULL,
    synced_posts integer NOT NULL,
    failed_posts integer NOT NULL,
    skipped_posts integer NOT NULL,
    error_message character varying(1000),
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: user_group_association; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_group_association (
    user_id uuid NOT NULL,
    group_id uuid NOT NULL
);


--
-- Name: user_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_groups (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description character varying(500),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    company_name character varying(255),
    status character varying(50) NOT NULL,
    notes character varying(1000),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    deleted_at timestamp with time zone,
    referral_link character varying(1000),
    personal_contacts character varying(1000)
);


--
-- Name: administrators administrators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.administrators
    ADD CONSTRAINT administrators_pkey PRIMARY KEY (id);


--
-- Name: ai_settings ai_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_settings
    ADD CONSTRAINT ai_settings_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: blog_writer_articles blog_writer_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_articles
    ADD CONSTRAINT blog_writer_articles_pkey PRIMARY KEY (id);


--
-- Name: blog_writer_publications blog_writer_publications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_publications
    ADD CONSTRAINT blog_writer_publications_pkey PRIMARY KEY (id);


--
-- Name: blog_writer_wordpress_sites blog_writer_wordpress_sites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_wordpress_sites
    ADD CONSTRAINT blog_writer_wordpress_sites_pkey PRIMARY KEY (id);


--
-- Name: buffer_connections buffer_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buffer_connections
    ADD CONSTRAINT buffer_connections_pkey PRIMARY KEY (id);


--
-- Name: buffer_organizations buffer_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buffer_organizations
    ADD CONSTRAINT buffer_organizations_pkey PRIMARY KEY (id);


--
-- Name: campaign_targets campaign_targets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_targets
    ADD CONSTRAINT campaign_targets_pkey PRIMARY KEY (id);


--
-- Name: campaigns campaigns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_pkey PRIMARY KEY (id);


--
-- Name: media_files media_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_files
    ADD CONSTRAINT media_files_pkey PRIMARY KEY (id);


--
-- Name: omni_ai_agent_configs omni_ai_agent_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_agent_configs
    ADD CONSTRAINT omni_ai_agent_configs_pkey PRIMARY KEY (id);


--
-- Name: omni_ai_drafts omni_ai_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_drafts
    ADD CONSTRAINT omni_ai_drafts_pkey PRIMARY KEY (id);


--
-- Name: omni_ai_usage omni_ai_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_usage
    ADD CONSTRAINT omni_ai_usage_pkey PRIMARY KEY (id);


--
-- Name: omni_audit_logs omni_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_audit_logs
    ADD CONSTRAINT omni_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: omni_channel_accounts omni_channel_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_channel_accounts
    ADD CONSTRAINT omni_channel_accounts_pkey PRIMARY KEY (id);


--
-- Name: omni_conversation_tags omni_conversation_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversation_tags
    ADD CONSTRAINT omni_conversation_tags_pkey PRIMARY KEY (conversation_id, tag_id);


--
-- Name: omni_conversations omni_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversations
    ADD CONSTRAINT omni_conversations_pkey PRIMARY KEY (id);


--
-- Name: omni_customer_identities omni_customer_identities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customer_identities
    ADD CONSTRAINT omni_customer_identities_pkey PRIMARY KEY (id);


--
-- Name: omni_customers omni_customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customers
    ADD CONSTRAINT omni_customers_pkey PRIMARY KEY (id);


--
-- Name: omni_internal_notes omni_internal_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_internal_notes
    ADD CONSTRAINT omni_internal_notes_pkey PRIMARY KEY (id);


--
-- Name: omni_knowledge_chunks omni_knowledge_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_knowledge_chunks
    ADD CONSTRAINT omni_knowledge_chunks_pkey PRIMARY KEY (id);


--
-- Name: omni_knowledge_documents omni_knowledge_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_knowledge_documents
    ADD CONSTRAINT omni_knowledge_documents_pkey PRIMARY KEY (id);


--
-- Name: omni_messages omni_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_messages
    ADD CONSTRAINT omni_messages_pkey PRIMARY KEY (id);


--
-- Name: omni_notifications omni_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_notifications
    ADD CONSTRAINT omni_notifications_pkey PRIMARY KEY (id);


--
-- Name: omni_tags omni_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_tags
    ADD CONSTRAINT omni_tags_pkey PRIMARY KEY (id);


--
-- Name: publication_attempts publication_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publication_attempts
    ADD CONSTRAINT publication_attempts_pkey PRIMARY KEY (id);


--
-- Name: publications publications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_pkey PRIMARY KEY (id);


--
-- Name: social_channels social_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.social_channels
    ADD CONSTRAINT social_channels_pkey PRIMARY KEY (id);


--
-- Name: stat_metric_history stat_metric_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_metric_history
    ADD CONSTRAINT stat_metric_history_pkey PRIMARY KEY (id);


--
-- Name: stat_post_metrics stat_post_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_pkey PRIMARY KEY (id);


--
-- Name: stat_sync_runs stat_sync_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_sync_runs
    ADD CONSTRAINT stat_sync_runs_pkey PRIMARY KEY (id);


--
-- Name: blog_writer_publications uq_blog_publication_article_site; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_publications
    ADD CONSTRAINT uq_blog_publication_article_site UNIQUE (article_id, wordpress_site_id);


--
-- Name: campaign_targets uq_campaign_target_campaign_channel; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_targets
    ADD CONSTRAINT uq_campaign_target_campaign_channel UNIQUE (campaign_id, social_channel_id);


--
-- Name: omni_customer_identities uq_omni_identity_owner_channel_external; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customer_identities
    ADD CONSTRAINT uq_omni_identity_owner_channel_external UNIQUE (owner_id, channel, external_user_id);


--
-- Name: omni_messages uq_omni_message_channel_external; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_messages
    ADD CONSTRAINT uq_omni_message_channel_external UNIQUE (channel_account_id, external_message_id);


--
-- Name: omni_tags uq_omni_tag_owner_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_tags
    ADD CONSTRAINT uq_omni_tag_owner_name UNIQUE (owner_id, name);


--
-- Name: publications uq_publication_campaign_channel; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT uq_publication_campaign_channel UNIQUE (campaign_id, social_channel_id);


--
-- Name: publications uq_publication_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT uq_publication_idempotency_key UNIQUE (idempotency_key);


--
-- Name: stat_post_metrics uq_stat_post_metrics_publication; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT uq_stat_post_metrics_publication UNIQUE (publication_id);


--
-- Name: user_group_association user_group_association_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_association
    ADD CONSTRAINT user_group_association_pkey PRIMARY KEY (user_id, group_id);


--
-- Name: user_groups user_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT user_groups_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_publication_campaign_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publication_campaign_id ON public.publications USING btree (campaign_id);


--
-- Name: idx_publication_next_attempt_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publication_next_attempt_at ON public.publications USING btree (next_attempt_at);


--
-- Name: idx_publication_scheduled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publication_scheduled_at ON public.publications USING btree (scheduled_at);


--
-- Name: idx_publication_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publication_status ON public.publications USING btree (status);


--
-- Name: idx_stat_metric_history_publication_synced; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_metric_history_publication_synced ON public.stat_metric_history USING btree (publication_id, synced_at);


--
-- Name: idx_stat_post_metrics_campaign_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_post_metrics_campaign_id ON public.stat_post_metrics USING btree (campaign_id);


--
-- Name: idx_stat_post_metrics_last_synced_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_post_metrics_last_synced_at ON public.stat_post_metrics USING btree (last_synced_at);


--
-- Name: idx_stat_post_metrics_social_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_post_metrics_social_channel_id ON public.stat_post_metrics USING btree (social_channel_id);


--
-- Name: idx_stat_post_metrics_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_post_metrics_user_id ON public.stat_post_metrics USING btree (user_id);


--
-- Name: idx_stat_sync_runs_scope_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_sync_runs_scope_campaign ON public.stat_sync_runs USING btree (scope_campaign_id);


--
-- Name: idx_stat_sync_runs_scope_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_sync_runs_scope_user ON public.stat_sync_runs USING btree (scope_user_id);


--
-- Name: idx_stat_sync_runs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stat_sync_runs_started_at ON public.stat_sync_runs USING btree (started_at);


--
-- Name: ix_administrators_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_administrators_email ON public.administrators USING btree (email);


--
-- Name: ix_omni_ai_agent_configs_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_omni_ai_agent_configs_owner_id ON public.omni_ai_agent_configs USING btree (owner_id);


--
-- Name: ix_omni_ai_drafts_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_ai_drafts_owner_id ON public.omni_ai_drafts USING btree (owner_id);


--
-- Name: ix_omni_ai_usage_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_ai_usage_owner_id ON public.omni_ai_usage USING btree (owner_id);


--
-- Name: ix_omni_audit_logs_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_audit_logs_owner_id ON public.omni_audit_logs USING btree (owner_id);


--
-- Name: ix_omni_channel_accounts_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_channel_accounts_owner_id ON public.omni_channel_accounts USING btree (owner_id);


--
-- Name: ix_omni_conversations_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_conversations_owner_id ON public.omni_conversations USING btree (owner_id);


--
-- Name: ix_omni_customer_identities_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_customer_identities_owner_id ON public.omni_customer_identities USING btree (owner_id);


--
-- Name: ix_omni_customers_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_customers_owner_id ON public.omni_customers USING btree (owner_id);


--
-- Name: ix_omni_internal_notes_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_internal_notes_owner_id ON public.omni_internal_notes USING btree (owner_id);


--
-- Name: ix_omni_knowledge_chunks_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_knowledge_chunks_owner_id ON public.omni_knowledge_chunks USING btree (owner_id);


--
-- Name: ix_omni_knowledge_documents_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_knowledge_documents_owner_id ON public.omni_knowledge_documents USING btree (owner_id);


--
-- Name: ix_omni_messages_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_messages_owner_id ON public.omni_messages USING btree (owner_id);


--
-- Name: ix_omni_notifications_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_notifications_owner_id ON public.omni_notifications USING btree (owner_id);


--
-- Name: ix_omni_tags_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_omni_tags_owner_id ON public.omni_tags USING btree (owner_id);


--
-- Name: ix_user_groups_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_user_groups_name ON public.user_groups USING btree (name);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: audit_logs audit_logs_administrator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_administrator_id_fkey FOREIGN KEY (administrator_id) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: blog_writer_articles blog_writer_articles_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_articles
    ADD CONSTRAINT blog_writer_articles_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: blog_writer_articles blog_writer_articles_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_articles
    ADD CONSTRAINT blog_writer_articles_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_files(id) ON DELETE SET NULL;


--
-- Name: blog_writer_articles blog_writer_articles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_articles
    ADD CONSTRAINT blog_writer_articles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: blog_writer_publications blog_writer_publications_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_publications
    ADD CONSTRAINT blog_writer_publications_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.blog_writer_articles(id) ON DELETE CASCADE;


--
-- Name: blog_writer_publications blog_writer_publications_wordpress_site_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_publications
    ADD CONSTRAINT blog_writer_publications_wordpress_site_id_fkey FOREIGN KEY (wordpress_site_id) REFERENCES public.blog_writer_wordpress_sites(id) ON DELETE CASCADE;


--
-- Name: blog_writer_wordpress_sites blog_writer_wordpress_sites_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blog_writer_wordpress_sites
    ADD CONSTRAINT blog_writer_wordpress_sites_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: buffer_connections buffer_connections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buffer_connections
    ADD CONSTRAINT buffer_connections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: buffer_organizations buffer_organizations_buffer_connection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buffer_organizations
    ADD CONSTRAINT buffer_organizations_buffer_connection_id_fkey FOREIGN KEY (buffer_connection_id) REFERENCES public.buffer_connections(id) ON DELETE CASCADE;


--
-- Name: campaign_targets campaign_targets_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_targets
    ADD CONSTRAINT campaign_targets_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;


--
-- Name: campaign_targets campaign_targets_social_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_targets
    ADD CONSTRAINT campaign_targets_social_channel_id_fkey FOREIGN KEY (social_channel_id) REFERENCES public.social_channels(id) ON DELETE CASCADE;


--
-- Name: campaign_targets campaign_targets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaign_targets
    ADD CONSTRAINT campaign_targets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: campaigns campaigns_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.blog_writer_articles(id) ON DELETE SET NULL;


--
-- Name: campaigns campaigns_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: campaigns campaigns_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_files(id) ON DELETE SET NULL;


--
-- Name: omni_ai_agent_configs omni_ai_agent_configs_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_agent_configs
    ADD CONSTRAINT omni_ai_agent_configs_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_ai_drafts omni_ai_drafts_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_drafts
    ADD CONSTRAINT omni_ai_drafts_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: omni_ai_drafts omni_ai_drafts_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_drafts
    ADD CONSTRAINT omni_ai_drafts_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.omni_conversations(id) ON DELETE CASCADE;


--
-- Name: omni_ai_drafts omni_ai_drafts_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_drafts
    ADD CONSTRAINT omni_ai_drafts_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_ai_drafts omni_ai_drafts_source_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_drafts
    ADD CONSTRAINT omni_ai_drafts_source_message_id_fkey FOREIGN KEY (source_message_id) REFERENCES public.omni_messages(id) ON DELETE SET NULL;


--
-- Name: omni_ai_usage omni_ai_usage_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_usage
    ADD CONSTRAINT omni_ai_usage_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.omni_conversations(id) ON DELETE SET NULL;


--
-- Name: omni_ai_usage omni_ai_usage_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_ai_usage
    ADD CONSTRAINT omni_ai_usage_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_audit_logs omni_audit_logs_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_audit_logs
    ADD CONSTRAINT omni_audit_logs_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: omni_audit_logs omni_audit_logs_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_audit_logs
    ADD CONSTRAINT omni_audit_logs_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_channel_accounts omni_channel_accounts_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_channel_accounts
    ADD CONSTRAINT omni_channel_accounts_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_conversation_tags omni_conversation_tags_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversation_tags
    ADD CONSTRAINT omni_conversation_tags_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.omni_conversations(id) ON DELETE CASCADE;


--
-- Name: omni_conversation_tags omni_conversation_tags_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversation_tags
    ADD CONSTRAINT omni_conversation_tags_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_conversation_tags omni_conversation_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversation_tags
    ADD CONSTRAINT omni_conversation_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.omni_tags(id) ON DELETE CASCADE;


--
-- Name: omni_conversations omni_conversations_assigned_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversations
    ADD CONSTRAINT omni_conversations_assigned_admin_id_fkey FOREIGN KEY (assigned_admin_id) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: omni_conversations omni_conversations_channel_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversations
    ADD CONSTRAINT omni_conversations_channel_account_id_fkey FOREIGN KEY (channel_account_id) REFERENCES public.omni_channel_accounts(id) ON DELETE CASCADE;


--
-- Name: omni_conversations omni_conversations_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversations
    ADD CONSTRAINT omni_conversations_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.omni_customers(id) ON DELETE CASCADE;


--
-- Name: omni_conversations omni_conversations_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_conversations
    ADD CONSTRAINT omni_conversations_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_customer_identities omni_customer_identities_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customer_identities
    ADD CONSTRAINT omni_customer_identities_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.omni_customers(id) ON DELETE CASCADE;


--
-- Name: omni_customer_identities omni_customer_identities_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customer_identities
    ADD CONSTRAINT omni_customer_identities_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_customers omni_customers_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_customers
    ADD CONSTRAINT omni_customers_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_internal_notes omni_internal_notes_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_internal_notes
    ADD CONSTRAINT omni_internal_notes_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: omni_internal_notes omni_internal_notes_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_internal_notes
    ADD CONSTRAINT omni_internal_notes_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.omni_conversations(id) ON DELETE CASCADE;


--
-- Name: omni_internal_notes omni_internal_notes_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_internal_notes
    ADD CONSTRAINT omni_internal_notes_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_knowledge_chunks omni_knowledge_chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_knowledge_chunks
    ADD CONSTRAINT omni_knowledge_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.omni_knowledge_documents(id) ON DELETE CASCADE;


--
-- Name: omni_knowledge_chunks omni_knowledge_chunks_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_knowledge_chunks
    ADD CONSTRAINT omni_knowledge_chunks_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_knowledge_documents omni_knowledge_documents_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_knowledge_documents
    ADD CONSTRAINT omni_knowledge_documents_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_messages omni_messages_channel_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_messages
    ADD CONSTRAINT omni_messages_channel_account_id_fkey FOREIGN KEY (channel_account_id) REFERENCES public.omni_channel_accounts(id) ON DELETE CASCADE;


--
-- Name: omni_messages omni_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_messages
    ADD CONSTRAINT omni_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.omni_conversations(id) ON DELETE CASCADE;


--
-- Name: omni_messages omni_messages_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_messages
    ADD CONSTRAINT omni_messages_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_notifications omni_notifications_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_notifications
    ADD CONSTRAINT omni_notifications_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_notifications omni_notifications_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_notifications
    ADD CONSTRAINT omni_notifications_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: omni_tags omni_tags_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.omni_tags
    ADD CONSTRAINT omni_tags_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.administrators(id) ON DELETE CASCADE;


--
-- Name: publication_attempts publication_attempts_publication_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publication_attempts
    ADD CONSTRAINT publication_attempts_publication_id_fkey FOREIGN KEY (publication_id) REFERENCES public.publications(id) ON DELETE CASCADE;


--
-- Name: publications publications_buffer_connection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_buffer_connection_id_fkey FOREIGN KEY (buffer_connection_id) REFERENCES public.buffer_connections(id) ON DELETE CASCADE;


--
-- Name: publications publications_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;


--
-- Name: publications publications_campaign_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_campaign_target_id_fkey FOREIGN KEY (campaign_target_id) REFERENCES public.campaign_targets(id) ON DELETE CASCADE;


--
-- Name: publications publications_social_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_social_channel_id_fkey FOREIGN KEY (social_channel_id) REFERENCES public.social_channels(id) ON DELETE CASCADE;


--
-- Name: publications publications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: social_channels social_channels_buffer_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.social_channels
    ADD CONSTRAINT social_channels_buffer_organization_id_fkey FOREIGN KEY (buffer_organization_id) REFERENCES public.buffer_organizations(id) ON DELETE CASCADE;


--
-- Name: stat_metric_history stat_metric_history_publication_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_metric_history
    ADD CONSTRAINT stat_metric_history_publication_id_fkey FOREIGN KEY (publication_id) REFERENCES public.publications(id) ON DELETE CASCADE;


--
-- Name: stat_post_metrics stat_post_metrics_buffer_connection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_buffer_connection_id_fkey FOREIGN KEY (buffer_connection_id) REFERENCES public.buffer_connections(id) ON DELETE CASCADE;


--
-- Name: stat_post_metrics stat_post_metrics_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;


--
-- Name: stat_post_metrics stat_post_metrics_last_sync_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_last_sync_run_id_fkey FOREIGN KEY (last_sync_run_id) REFERENCES public.stat_sync_runs(id) ON DELETE SET NULL;


--
-- Name: stat_post_metrics stat_post_metrics_publication_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_publication_id_fkey FOREIGN KEY (publication_id) REFERENCES public.publications(id) ON DELETE CASCADE;


--
-- Name: stat_post_metrics stat_post_metrics_social_channel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_social_channel_id_fkey FOREIGN KEY (social_channel_id) REFERENCES public.social_channels(id) ON DELETE CASCADE;


--
-- Name: stat_post_metrics stat_post_metrics_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_post_metrics
    ADD CONSTRAINT stat_post_metrics_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: stat_sync_runs stat_sync_runs_scope_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_sync_runs
    ADD CONSTRAINT stat_sync_runs_scope_campaign_id_fkey FOREIGN KEY (scope_campaign_id) REFERENCES public.campaigns(id) ON DELETE SET NULL;


--
-- Name: stat_sync_runs stat_sync_runs_scope_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_sync_runs
    ADD CONSTRAINT stat_sync_runs_scope_user_id_fkey FOREIGN KEY (scope_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: stat_sync_runs stat_sync_runs_triggered_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stat_sync_runs
    ADD CONSTRAINT stat_sync_runs_triggered_by_fkey FOREIGN KEY (triggered_by) REFERENCES public.administrators(id) ON DELETE SET NULL;


--
-- Name: user_group_association user_group_association_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_association
    ADD CONSTRAINT user_group_association_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.user_groups(id) ON DELETE CASCADE;


--
-- Name: user_group_association user_group_association_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_group_association
    ADD CONSTRAINT user_group_association_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


