import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.config import settings
from app.models.campaign import Campaign, CampaignTarget
from app.models.user import User, UserGroup
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.media import MediaFile
from app.models.publication import Publication
from app.models.audit import AuditLog

# Hard per-platform text limits enforced by Buffer itself. Mirrors the max_length
# already validated on CampaignCreateRequest.x_text/threads_text (schemas.py) - but
# that only bounds the *override* field. When no override is set, resolve_text_for_channel
# falls back to default_text (max 5000 chars, no platform cap), which would otherwise
# only be caught after a real, wasted Buffer API call. Platforms not listed here have
# no separately documented limit in this codebase, so none is invented (AGENTS.md rule 14).
# Keyed by "twitter" - Buffer's own API reports X/Twitter channels with
# service/platform="twitter" (see prod_client.py list_channels), never "x", confirmed
# against this deployment's production data (2026-08-11). Using "x" here silently
# disabled this check for every real X/Twitter channel - see resolve_text_for_channel.
PLATFORM_TEXT_LIMITS = {"twitter": 280, "threads": 500}

# Hard per-platform video-duration limit enforced by Buffer's own documented specs
# (support.buffer.com/article/616, "Sharing videos through Buffer": "X/Twitter videos
# must be between 0.5 seconds to 140 seconds long", verified 2026-08). Only X/Twitter
# has a stable, Buffer-documented figure here, so it's the only one proactively
# blocked pre-launch (AGENTS.md rule 14: no invented limits for other platforms).
# Instagram isn't listed here even though it does have a duration ceiling
# (INSTAGRAM_POST_MAX_VIDEO_DURATION_SECONDS in prod_client.py, 60s for feed
# "post" videos): prod_client.create_post() reacts to it automatically by
# switching metadata.instagram.type to "reel" for longer videos instead of
# rejecting the channel, so there's nothing to block here. Facebook has no
# equivalent branching yet and always publishes as a normal feed "post".
PLATFORM_VIDEO_MAX_DURATION_SECONDS = {"twitter": 140.0}

# Instagram channels Buffer reports with channel_type="profile" (a personal,
# non-Business/Creator account - value observed directly from Buffer's own API via
# sync_buffer_connection, see models/buffer.py SocialChannel.channel_type) always
# reject scheduled/immediate publishing with the same permanent error:
# "Instagram personal profile channels require notification scheduling. Use
# notification scheduling instead." - confirmed against this deployment's own
# production Buffer API responses (2026-08-06/10, campaign "500€ instagram"), not
# a documented Buffer spec page, per AGENTS.md rule 14 (verify, don't invent).
# This is a structural Instagram/Meta Graph API limitation (personal profiles have
# no Content Publishing permission at all, only Business/Creator accounts do) - no
# retry ever succeeds, so this is caught here instead of burning the full retry
# backoff sequence (up to ~6h per attempt, MAX_PUBLICATION_ATTEMPTS attempts) against
# a call that can never work. This does NOT make the channel publishable - the only
# real fix is converting the Instagram account to Professional/Business and
# reconnecting; SocialChannel.publication_mode="notification" is purely descriptive
# in this codebase today (see api/v1/buffer.py), not wired to a distinct Buffer call.
CHANNEL_TYPES_REQUIRING_NOTIFICATION_SCHEDULING = {"instagram": {"profile"}}

class CampaignResolver:
    @staticmethod
    def resolve_targets(db: Session, campaign: Campaign, targeting_params: Dict[str, Any]) -> List[SocialChannel]:
        """
        Resolves the target social channels based on the campaign's targeting mode
        and criteria parameters.

        targeting_params may contain:
        - user_ids: List[str]
        - group_ids: List[str]
        - platform_names: List[str]
        - channel_ids: List[str]

        For "all_active_channels", "selected_users" and "selected_groups", an
        optional "platform_names" list narrows the resolved channels down to just
        those platforms for the matched users (e.g. group "Clienti VIP" but only
        their Instagram/Facebook channels, skipping any TikTok/YouTube they also
        have connected) - it's a filter layered on top of who is targeted, not a
        separate mode. Absent or empty means "every platform they have", same as
        before this was added. "selected_channels" ignores it (channels are
        already explicit) and "selected_platforms" already *is* the platform
        filter, so there's nothing to layer it on top of.
        """
        mode = campaign.targeting_mode

        # Base query to fetch active channels with active connections & users
        query = db.query(SocialChannel).join(
            BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id
        ).join(
            BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id
        ).join(
            User, BufferConnection.user_id == User.id
        )

        # Apply general status exclusions
        query = query.filter(
            User.status == "active",
            User.deleted_at.is_(None),
            BufferConnection.status == "connected",
            SocialChannel.is_active.is_(True),
            # Removed by its owner: never targetable again, whatever a later
            # sync says about it upstream. Same soft-delete rule already applied
            # to User above.
            SocialChannel.deleted_at.is_(None),
            SocialChannel.publication_mode != "disabled"
        )

        if mode == "all_active_channels":
            pass

        elif mode == "selected_users":
            user_ids = [uuid.UUID(uid) for uid in targeting_params.get("user_ids", [])]
            if not user_ids:
                return []
            query = query.filter(User.id.in_(user_ids))

        elif mode == "selected_groups":
            group_ids = [uuid.UUID(gid) for gid in targeting_params.get("group_ids", [])]
            if not group_ids:
                return []
            query = query.filter(User.groups.any(UserGroup.id.in_(group_ids)))

        elif mode == "selected_channels":
            channel_ids = [uuid.UUID(cid) for cid in targeting_params.get("channel_ids", [])]
            if not channel_ids:
                return []
            return query.filter(SocialChannel.id.in_(channel_ids)).all()

        elif mode == "selected_platforms":
            platforms = [p.lower().strip() for p in targeting_params.get("platform_names", [])]
            if not platforms:
                return []
            return query.filter(SocialChannel.platform.in_(platforms)).all()

        else:
            return []

        # Optional secondary platform narrowing for the three "who" based modes above.
        platform_names = targeting_params.get("platform_names")
        if platform_names:
            platforms = [p.lower().strip() for p in platform_names]
            query = query.filter(SocialChannel.platform.in_(platforms))

        return query.all()



    @staticmethod
    def _explain_no_targets(db: Session) -> str:
        """
        Turn "no channels matched" into the actual reason.

        Counts channels excluded by each criterion in resolve_targets, in the
        order an administrator can act on them, and names the first that
        explains the emptiness.
        """
        base = (
            db.query(SocialChannel)
            .join(BufferOrganization, SocialChannel.buffer_organization_id == BufferOrganization.id)
            .join(BufferConnection, BufferOrganization.buffer_connection_id == BufferConnection.id)
            .join(User, BufferConnection.user_id == User.id)
            .filter(SocialChannel.deleted_at.is_(None))
        )

        total = base.count()
        if total == 0:
            return (
                "Nessun canale social collegato. Gli utenti devono prima collegare "
                "i propri canali dal portale."
            )

        inactive_users = base.filter(User.status != "active", User.deleted_at.is_(None)).count()
        if inactive_users == total:
            return (
                f"Tutti i {total} canali appartengono a utenti non ancora attivi. "
                "Attiva gli utenti dalla pagina Utenti per includerli nelle campagne."
            )

        disabled = base.filter(
            User.status == "active",
            SocialChannel.publication_mode == "disabled",
        ).count()
        inactive_channels = base.filter(
            User.status == "active",
            SocialChannel.is_active.is_(False),
        ).count()
        broken_connections = base.filter(
            User.status == "active",
            BufferConnection.status != "connected",
        ).count()

        motivi = []
        if inactive_users:
            motivi.append(f"{inactive_users} di utenti non attivi")
        if disabled:
            motivi.append(f"{disabled} con pubblicazione disabilitata")
        if inactive_channels:
            motivi.append(f"{inactive_channels} non piu' collegati")
        if broken_connections:
            motivi.append(f"{broken_connections} con connessione da ripristinare")

        if motivi:
            return f"Nessun canale utilizzabile su {total}: " + ", ".join(motivi) + "."

        return (
            f"Nessuno dei {total} canali collegati rientra nei criteri di questa "
            "campagna. Verifica la selezione dei destinatari."
        )

    @staticmethod
    def _affiliate_disclosure_texts(db: Session) -> tuple:
        """
        The configured disclosure wording, long and short.

        Falls back to the built-in defaults when an administrator has not set
        anything yet, so switching the option on always produces a usable
        disclosure rather than silently appending nothing - which would be the
        worst outcome: the campaign would look compliant and not be.
        """
        from app.models.platform_settings import (
            DEFAULT_AFFILIATE_DISCLOSURE,
            DEFAULT_AFFILIATE_DISCLOSURE_SHORT,
            PlatformSettings,
        )

        settings_row = db.query(PlatformSettings).first()
        long_text = (settings_row.affiliate_disclosure_text if settings_row else None) or DEFAULT_AFFILIATE_DISCLOSURE
        short_text = (settings_row.affiliate_disclosure_text_short if settings_row else None) or DEFAULT_AFFILIATE_DISCLOSURE_SHORT
        return long_text, short_text

    @staticmethod
    def resolve_text_for_channel(
        campaign: Campaign,
        channel: SocialChannel,
        channel_override_text: str = None,
        referral_link: Optional[str] = None,
        personal_contacts: Optional[str] = None,
        affiliate_disclosure: Optional[str] = None,
    ) -> str:
        """
        Text resolution order of priority:
        1. Channel-specific text override
        2. Platform-specific campaign text
        3. Default campaign text

        Then, if campaign.include_referral_link is on: appends the caller-supplied
        referral_link (the *owning user's own* User.referral_link - the caller is
        responsible for loading the right one, this method never looks it up
        itself, so a channel can never end up with another user's link). A user
        with no referral_link configured (referral_link=None/empty here) leaves
        the text exactly as before this feature existed - no placeholder, no
        error.

        Then, if campaign.include_personal_contacts is on: same mechanics, but
        appends the caller-supplied personal_contacts (the owning user's own
        User.personal_contacts signature block) right after the referral link
        above - deliberately the step right after it, so a recipient sees their
        promoter link first, then their personal contacts, matching how the two
        "Includi ..." checkboxes are ordered in the campaign wizard.

        Then, if campaign.include_affiliate_disclosure is on: appends the
        caller-supplied disclosure wording. Required whenever the post carries an
        affiliate link - the promoter earns a commission, which makes it
        commercial communication whether or not anyone pays them directly. The
        caller passes the short form on platforms with a tight character budget.

        All three are deliberately the *last* steps: PLATFORM_TEXT_LIMITS validation
        in launch_campaign runs on the value this returns, so appended text that
        pushes a target over its platform's character limit is caught the same
        way an over-limit plain text already is today.
        """
        if channel_override_text:
            text = channel_override_text
        else:
            platform = channel.platform.lower().strip()
            if platform == "instagram" and campaign.instagram_text:
                text = campaign.instagram_text
            elif platform == "facebook" and campaign.facebook_text:
                text = campaign.facebook_text
            elif platform == "linkedin" and campaign.linkedin_text:
                text = campaign.linkedin_text
            elif platform == "tiktok" and campaign.tiktok_text:
                text = campaign.tiktok_text
            elif platform == "twitter" and campaign.x_text:
                text = campaign.x_text
            elif platform == "threads" and campaign.threads_text:
                text = campaign.threads_text
            elif platform == "youtube":
                # YouTube's title is sent as structured metadata
                # (YoutubePostMetadataInput.title, resolved separately in the
                # publication task from campaign.youtube_title), not folded into
                # the post text - this is just the video description body.
                text = campaign.youtube_description or campaign.default_text
            else:
                text = campaign.default_text

        if campaign.include_referral_link and referral_link:
            text = f"{text}\n\nISCRIVITI QUI: {referral_link}"

        if campaign.include_personal_contacts and personal_contacts:
            text = f"{text}\n\n{personal_contacts}"

        # Advertising disclosure, last of the three appends. Deliberately after
        # the referral link so it sits next to the thing it is declaring, which
        # is what makes it readable rather than a footnote: on Instagram and
        # TikTok anything far down the caption disappears behind "... more".
        # getattr with a default, not a bare attribute access: this method is
        # called with anything campaign-shaped - including objects built before
        # the field existed - and a missing flag must mean "off", not a crash
        # that takes the whole campaign launch down.
        if getattr(campaign, "include_affiliate_disclosure", False) and affiliate_disclosure:
            text = f"{text}\n\n{affiliate_disclosure}"

        return text

    @staticmethod
    def compute_video_duration_validation_error(
        platform: str, media_file: Optional[MediaFile]
    ) -> Optional[str]:
        """
        Proactive check mirroring PLATFORM_TEXT_LIMITS above, but only for the one
        platform (X/Twitter) with a stable, Buffer-documented duration ceiling. Fails
        open (returns None) when duration is unknown yet (media still being inspected)
        rather than blocking the channel on missing data - Buffer's own live rejection
        remains the backstop for that case.
        """
        platform_key = platform.lower().strip()
        duration_limit = PLATFORM_VIDEO_MAX_DURATION_SECONDS.get(platform_key)
        if duration_limit is None or media_file is None:
            return None
        if not media_file.mime_type or "video" not in media_file.mime_type:
            return None
        duration = media_file.duration_seconds
        if duration is None or duration <= duration_limit:
            return None

        return (
            f"Video di {duration:.0f}s supera il limite di {duration_limit:.0f}s per "
            f"{platform} (fonte: Buffer Help Center, support.buffer.com/article/616). "
            f"Questo canale è escluso automaticamente; gli altri canali della campagna "
            f"non sono influenzati."
        )


    # Platforms that cannot publish a post without media, and what they accept.
    # Observed directly from the provider's own rejections ("At least 1
    # upload(s) required", "Tiktok video must have only videos"), not from a
    # documentation page - these are the errors a real campaign would hit.
    MEDIA_REQUIRED_PLATFORMS = {"instagram", "tiktok"}
    VIDEO_ONLY_PLATFORMS = {"tiktok"}

    @classmethod
    def compute_media_validation_error(
        cls, platform: str, media_file: Optional[MediaFile]
    ) -> Optional[str]:
        """
        Proactive check for platforms that refuse a post outright.

        Same purpose as compute_video_duration_validation_error: catch it here,
        where the administrator sees a readable reason next to the channel,
        instead of letting every affected target burn an API call and come back
        as a failed publication with a provider error string.
        """
        platform_key = platform.lower().strip()

        if platform_key in cls.MEDIA_REQUIRED_PLATFORMS and media_file is None:
            return (
                f"{platform.title()} non accetta post senza immagine o video. "
                f"Aggiungi un media alla campagna oppure escludi i canali {platform.title()}."
            )

        if platform_key in cls.VIDEO_ONLY_PLATFORMS and media_file is not None:
            is_video = bool(media_file.mime_type) and "video" in media_file.mime_type
            if not is_video:
                return (
                    "TikTok accetta solo video, non immagini. "
                    "Usa un video oppure escludi i canali TikTok da questa campagna."
                )

        return None

    @staticmethod
    def compute_channel_type_validation_error(platform: str, channel_type: Optional[str]) -> Optional[str]:
        """
        Proactive check mirroring compute_video_duration_validation_error above, but
        for channels whose Buffer-reported channel_type can never accept a real
        publish - currently only Instagram "profile" (personal, non-Business/Creator)
        channels, see CHANNEL_TYPES_REQUIRING_NOTIFICATION_SCHEDULING above. Fails
        open (returns None) if channel_type is unknown, same fail-open policy as the
        video-duration check.
        """
        if not channel_type:
            return None
        platform_key = platform.lower().strip()
        blocked_types = CHANNEL_TYPES_REQUIRING_NOTIFICATION_SCHEDULING.get(platform_key)
        if not blocked_types or channel_type.lower().strip() not in blocked_types:
            return None

        return (
            f"Canale {platform} di tipo \"{channel_type}\" (profilo personale, non Professional/Business): "
            f"Instagram non permette la pubblicazione automatica su profili personali, solo su account "
            f"Professional/Business collegati a una Pagina Facebook - Buffer rifiuta sempre questo tipo di "
            f"pubblicazione con lo stesso errore permanente. Converti l'account in Professional/Business su "
            f"Instagram e ricollegalo su Buffer per poterlo pubblicare da qui. Questo canale è escluso "
            f"automaticamente; gli altri canali della campagna non sono influenzati."
        )

    @classmethod
    def preview_campaign_targets(
        cls, db: Session, campaign: Campaign, targeting_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generates target details for preview before launching a campaign.
        """
        channels = cls.resolve_targets(db, campaign, targeting_params)
        
        # Excluded counts logic (simulate what gets filtered out)
        # Fetch total targets in database to compare
        total_active_users = db.query(User).filter(User.status == "active", User.deleted_at.is_(None)).count()
        total_channels = db.query(SocialChannel).filter(SocialChannel.is_active.is_(True)).count()
        
        platform_distribution = {}
        users_set = set()
        notification_approval_count = 0

        for chan in channels:
            platform_distribution[chan.platform] = platform_distribution.get(chan.platform, 0) + 1
            # Retrieve connection owner
            conn = chan.buffer_organization.buffer_connection
            users_set.add(conn.user_id)
            if chan.publication_mode in ("notification", "approval"):
                notification_approval_count += 1

        # Build list of excluded channels for visual warning
        # An user or connection might be disconnected or suspended
        excluded_channels_count = total_channels - len(channels)

        return {
            "estimated_publications_count": len(channels),
            "total_users_targeted": len(users_set),
            "platform_distribution": platform_distribution,
            "channels_requiring_notification_approval": notification_approval_count,
            "excluded_channels_count": max(0, excluded_channels_count),
            "total_active_users": total_active_users,
        }

    @classmethod
    def launch_campaign(
        cls, 
        db: Session, 
        campaign_id: uuid.UUID, 
        targeting_params: Dict[str, Any],
        admin_id: Optional[uuid.UUID] = None,
        channel_overrides: Optional[Dict[str, str]] = None # maps channel_id -> custom_text
    ) -> Tuple[Campaign, List[Publication]]:
        """
        Launches a campaign: resolves targets, creates CampaignTargets & Publications,
        commits atomic transaction, and logs audit record.
        """
        if channel_overrides is None:
            channel_overrides = {}

        # 1. Fetch Campaign
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found.")

        if campaign.status not in ("draft", "failed", "paused"):
            raise ValueError(f"Campaign is in status {campaign.status} and cannot be launched.")

        campaign.status = "preparing"
        db.flush()

        # 2. Resolve target channels
        channels = cls.resolve_targets(db, campaign, targeting_params)
        if not channels:
            campaign.status = "failed"
            db.commit()
            # Say WHY, not just "none matched". The exclusion criteria are
            # invisible from the campaign screen - an administrator looking at
            # four healthy channels has no way to guess that their owners are
            # still awaiting activation, which is the most common cause now that
            # self-registered users start inactive by design.
            raise ValueError(cls._explain_no_targets(db))

        publications_created = []

        # Disclosure wording resolved once for the whole campaign, not per
        # channel: it is a platform-wide setting, and reading it inside the loop
        # would be one query per target.
        disclosure_long = disclosure_short = None
        if getattr(campaign, "include_affiliate_disclosure", False):
            disclosure_long, disclosure_short = cls._affiliate_disclosure_texts(db)

        # 3. Create CampaignTargets & Publications
        # We wrap in sub-transactions/flushes for atomicity
        for chan in channels:
            conn = chan.buffer_organization.buffer_connection
            user_id = conn.user_id

            # Resolve text - conn.user is this channel's *own* owning user, loaded
            # fresh per channel in this loop, so referral_link/personal_contacts
            # can never leak across users even when a campaign targets channels
            # from many users at once.
            override_text = channel_overrides.get(str(chan.id))
            # Short disclosure where the character budget is tight (X allows 280,
            # and the full sentence would eat a fifth of the post).
            platform_key = chan.platform.lower().strip()
            disclosure = disclosure_long
            if disclosure_long and PLATFORM_TEXT_LIMITS.get(platform_key, 10_000) <= 500:
                disclosure = disclosure_short

            resolved_text = cls.resolve_text_for_channel(
                campaign, chan, override_text, conn.user.referral_link,
                conn.user.personal_contacts, disclosure,
            )

            # Catch platform text-length violations here instead of letting them reach
            # Buffer as a wasted, confusing API call - see PLATFORM_TEXT_LIMITS above.
            text_limit = PLATFORM_TEXT_LIMITS.get(chan.platform.lower().strip())
            validation_error = None
            if text_limit is not None and len(resolved_text) > text_limit:
                validation_error = (
                    f"Testo di {len(resolved_text)} caratteri supera il limite di {text_limit} "
                    f"per {chan.platform}. Imposta un testo specifico per questa piattaforma piu breve."
                )

            if validation_error is None:
                validation_error = cls.compute_media_validation_error(chan.platform, campaign.media_file)

            if validation_error is None:
                validation_error = cls.compute_video_duration_validation_error(
                    chan.platform, campaign.media_file
                )

            if validation_error is None:
                validation_error = cls.compute_channel_type_validation_error(
                    chan.platform, chan.channel_type
                )

            # Check unique constraint to avoid duplicating targets on retry launch
            existing_target = db.query(CampaignTarget).filter(
                CampaignTarget.campaign_id == campaign.id,
                CampaignTarget.social_channel_id == chan.id
            ).first()

            if existing_target:
                target = existing_target
                target.resolved_text = resolved_text
                target.status = "failed" if validation_error else "created"
            else:
                target = CampaignTarget(
                    campaign_id=campaign.id,
                    user_id=user_id,
                    social_channel_id=chan.id,
                    resolved_text=resolved_text,
                    status="failed" if validation_error else "created"
                )
                db.add(target)
            db.flush() # get target ID
            
            # Deterministic idempotency key: campaign_id:channel_id
            idempotency_key = f"{campaign.id}:{chan.id}"
            
            existing_pub = db.query(Publication).filter(
                Publication.idempotency_key == idempotency_key
            ).first()
            
            # Determine initial status
            initial_pub_status = "pending"
            # If campaign scheduled for future
            scheduled_time = None
            if campaign.publishing_mode == "scheduled":
                scheduled_time = campaign.scheduled_at
                initial_pub_status = "pending" # will be picked up by scheduler when time matches
            elif campaign.publishing_mode == "immediate":
                initial_pub_status = "pending" # ready to process immediately
            elif campaign.publishing_mode == "buffer_queue":
                initial_pub_status = "pending" # will queue on buffer
                
            if validation_error:
                initial_pub_status = "failed"

            if not existing_pub:
                publication = Publication(
                    campaign_id=campaign.id,
                    campaign_target_id=target.id,
                    user_id=user_id,
                    social_channel_id=chan.id,
                    buffer_connection_id=conn.id,
                    external_channel_id=chan.external_channel_id,
                    status=initial_pub_status,
                    attempt_count=0,
                    max_attempts=settings.MAX_PUBLICATION_ATTEMPTS,
                    idempotency_key=idempotency_key,
                    scheduled_at=scheduled_time,
                    error_category="validation_failed" if validation_error else None,
                    error_message=validation_error,
                )
                db.add(publication)
                publications_created.append(publication)
            elif validation_error:
                # Never dispatch a text known to violate the platform's limit, even
                # if a previous launch had left this target pending/retry_wait/failed.
                existing_pub.status = "failed"
                existing_pub.error_category = "validation_failed"
                existing_pub.error_code = None
                existing_pub.error_message = validation_error
                publications_created.append(existing_pub)
            else:
                # If publication already failed or retry-wait, we reset it to pending
                if existing_pub.status in ("failed", "cancelled", "retry_wait"):
                    existing_pub.status = initial_pub_status
                    existing_pub.attempt_count = 0
                    existing_pub.error_message = None
                    existing_pub.error_code = None
                    existing_pub.error_category = None
                    publications_created.append(existing_pub)

        # 4. Update Campaign Status
        campaign.status = "queued"
        campaign.started_at = datetime.now(timezone.utc)
        
        # Create audit log
        audit = AuditLog(
            administrator_id=admin_id,
            action="campaign_launch",
            entity_type="campaign",
            entity_id=campaign.id,
            metadata_json={
                "targeted_channels_count": len(channels),
                "publishing_mode": campaign.publishing_mode,
            }
        )
        db.add(audit)
        
        # Commit transaction atomically
        db.commit()
        
        return campaign, publications_created
