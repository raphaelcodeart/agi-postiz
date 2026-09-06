import uuid
from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal, Base, engine
from app.core.security import SecurityService, EncryptionService
from app.models.administrator import Administrator
from app.models.user import User, UserGroup
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel
from app.models.media import MediaFile
from app.models.campaign import Campaign, CampaignTarget
from app.models.publication import Publication, PublicationAttempt
from app.models.audit import AuditLog

def seed_database():
    print("Initializing database tables...")
    # Drop and recreate for seed consistency
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        print("Creating Administrator...")
        admin = Administrator(
            email="admin@example.com",
            password_hash=SecurityService.hash_password("admin_secure_pass_123"),
            full_name="Chief Publisher Admin",
            is_active=True
        )
        db.add(admin)
        db.flush()

        print("Creating User Groups...")
        g_hotels = UserGroup(name="Hotels", description="Algarve & Lisbon hospitality clients")
        g_restaurants = UserGroup(name="Restaurants", description="Dining and bistro customers")
        g_premium = UserGroup(name="Premium Clients", description="VIP priority subscribers")
        db.add_all([g_hotels, g_restaurants, g_premium])
        db.flush()

        print("Creating Users / Clients...")
        # Algarve Hotel
        u_algarve = User(
            name="Algarve Beach Resort",
            email="info@algarvebeachresort.com",
            company_name="Algarve Resorts Ltd",
            status="active"
        )
        u_algarve.groups = [g_hotels, g_premium]
        
        # Sintra B&B
        u_sintra = User(
            name="Sintra Castle B&B",
            email="booking@sintracastle.com",
            company_name="Sintra Boutique Hotels",
            status="active"
        )
        u_sintra.groups = [g_hotels]

        # Porto Bistro
        u_porto = User(
            name="Porto Wine Bistro",
            email="contact@portowinebistro.com",
            company_name="Porto Bistro Group",
            status="active"
        )
        u_porto.groups = [g_restaurants]

        # Lisbon Surf
        u_lisbon = User(
            name="Lisbon Surf Academy",
            email="hello@lisbonsurf.com",
            company_name="Lisbon Surf & Outdoors",
            status="suspended", # Suspended to test targeting exclusions
            notes="Suspended due to missing invoice settlement."
        )
        
        db.add_all([u_algarve, u_sintra, u_porto, u_lisbon])
        db.flush()

        print("Creating Buffer Connections, Organizations, and Social Channels...")
        # 1. Algarve connection (connected)
        conn_algarve = BufferConnection(
            user_id=u_algarve.id,
            authentication_type="oauth2",
            external_account_id="buf_acct_algarve_1",
            access_token_encrypted=EncryptionService.encrypt("mock_access_token_algarve_1"),
            refresh_token_encrypted=EncryptionService.encrypt("mock_refresh_token_algarve_1"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes="profile:read profile:write",
            status="connected",
            last_sync_at=datetime.now(timezone.utc)
        )
        db.add(conn_algarve)
        db.flush()

        org_algarve = BufferOrganization(
            buffer_connection_id=conn_algarve.id,
            external_organization_id="org_algarve_1",
            name="Algarve Resorts Workspace",
            is_active=True
        )
        db.add(org_algarve)
        db.flush()

        chan_algarve_ig = SocialChannel(
            buffer_organization_id=org_algarve.id,
            external_channel_id="chan_algarve_ig",
            platform="instagram",
            name="Algarve Beach IG",
            username="@algarvebeach",
            avatar_url="https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=80&h=80&fit=crop",
            channel_type="instagram_business",
            is_active=True,
            publication_mode="automatic"
        )
        chan_algarve_fb = SocialChannel(
            buffer_organization_id=org_algarve.id,
            external_channel_id="chan_algarve_fb",
            platform="facebook",
            name="Algarve Beach Resort Facebook",
            username="algarvebeachresort",
            avatar_url="https://images.unsplash.com/photo-1519125323398-675f0ddb6308?w=80&h=80&fit=crop",
            channel_type="facebook_page",
            is_active=True,
            publication_mode="approval" # Requires manual approval
        )
        chan_algarve_li = SocialChannel(
            buffer_organization_id=org_algarve.id,
            external_channel_id="chan_algarve_li",
            platform="linkedin",
            name="Algarve Beach Resort Company Page",
            username="algarve-beach-resort",
            avatar_url="https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?w=80&h=80&fit=crop",
            channel_type="linkedin_organization",
            is_active=True,
            publication_mode="automatic"
        )
        db.add_all([chan_algarve_ig, chan_algarve_fb, chan_algarve_li])

        # 2. Sintra connection (connected)
        conn_sintra = BufferConnection(
            user_id=u_sintra.id,
            authentication_type="oauth2",
            external_account_id="buf_acct_sintra_1",
            access_token_encrypted=EncryptionService.encrypt("mock_access_token_sintra_1"),
            refresh_token_encrypted=EncryptionService.encrypt("mock_refresh_token_sintra_1"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes="profile:read profile:write",
            status="connected",
            last_sync_at=datetime.now(timezone.utc)
        )
        db.add(conn_sintra)
        db.flush()

        org_sintra = BufferOrganization(
            buffer_connection_id=conn_sintra.id,
            external_organization_id="org_sintra_1",
            name="Sintra B&B Workspace",
            is_active=True
        )
        db.add(org_sintra)
        db.flush()

        chan_sintra_x = SocialChannel(
            buffer_organization_id=org_sintra.id,
            external_channel_id="chan_sintra_x",
            platform="twitter",
            name="Sintra Castle B&B Twitter",
            username="@sintrabnb",
            avatar_url="https://images.unsplash.com/photo-1566073771259-6a8506099945?w=80&h=80&fit=crop",
            channel_type="x_profile",
            is_active=True,
            publication_mode="automatic"
        )
        db.add(chan_sintra_x)

        # 3. Porto connection (disconnected status)
        conn_porto = BufferConnection(
            user_id=u_porto.id,
            authentication_type="oauth2",
            external_account_id="buf_acct_porto_1",
            access_token_encrypted=EncryptionService.encrypt("mock_access_token_porto_invalid"),
            refresh_token_encrypted=EncryptionService.encrypt("mock_refresh_token_porto_invalid"),
            token_expires_at=datetime.now(timezone.utc) - timedelta(days=1), # Expired!
            status="disconnected",
            last_sync_at=datetime.now(timezone.utc) - timedelta(days=5),
            last_error="Authorization revoked by user on Buffer dashboard."
        )
        db.add(conn_porto)
        db.flush()

        org_porto = BufferOrganization(
            buffer_connection_id=conn_porto.id,
            external_organization_id="org_porto_1",
            name="Porto Bistro Workspace",
            is_active=True
        )
        db.add(org_porto)
        db.flush()

        chan_porto_fb = SocialChannel(
            buffer_organization_id=org_porto.id,
            external_channel_id="chan_porto_fb",
            platform="facebook",
            name="Porto Wine Bistro Page",
            username="portowinebistro",
            avatar_url="https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=80&h=80&fit=crop",
            channel_type="facebook_page",
            is_active=True,
            publication_mode="automatic"
        )
        db.add(chan_porto_fb)

        # 4. Lisbon Surf (suspended connection)
        conn_lisbon = BufferConnection(
            user_id=u_lisbon.id,
            authentication_type="oauth2",
            external_account_id="buf_acct_lisbon_1",
            access_token_encrypted=EncryptionService.encrypt("mock_access_token_lisbon_1"),
            status="error",
            last_error="User account suspended globally."
        )
        db.add(conn_lisbon)
        
        db.commit()

        print("Creating Sample Media File...")
        media = MediaFile(
            original_filename="summer_beach_resort_vibe.jpg",
            stored_filename="seed_summer_vibe.jpg",
            storage_key="/storage/uploads/seed_summer_vibe.jpg",
            public_url="https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&auto=format&fit=crop",
            mime_type="image/jpeg",
            size_bytes=412356,
            processing_status="ready",
            validation_status="valid"
        )
        db.add(media)
        db.commit()

        # ==============================================================================
        # SEEDING CAMPAIGNS & PUBLICATION HISTORY
        # ==============================================================================
        print("Seeding Campaign 1 (Completed)...")
        c1 = Campaign(
            title="Summer Launch Promo",
            default_text="Experience luxury at its finest. Book your dream vacation now! ☀️🏖️ #portugal #tourism",
            instagram_text="Sunset views at the pool. Grab your drinks! 🍹🏖️ #resortlife",
            media_file_id=media.id,
            publishing_mode="immediate",
            targeting_mode="all_active_channels",
            status="completed",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc) - timedelta(days=2),
            completed_at=datetime.now(timezone.utc) - timedelta(days=2) + timedelta(minutes=5)
        )
        db.add(c1)
        db.flush()

        # Targets and successful publications for Algarve (IG and LI) and Sintra (X)
        # FB is skipped/approval or published successfully
        active_channels_c1 = [chan_algarve_ig, chan_algarve_fb, chan_algarve_li, chan_sintra_x]
        for c in active_channels_c1:
            u_id = u_algarve.id if "algarve" in c.external_channel_id else u_sintra.id
            conn_id = conn_algarve.id if "algarve" in c.external_channel_id else conn_sintra.id
            
            resolved = c1.instagram_text if c.platform == "instagram" else c1.default_text
            
            target = CampaignTarget(
                campaign_id=c1.id,
                user_id=u_id,
                social_channel_id=c.id,
                resolved_text=resolved,
                status="created"
            )
            db.add(target)
            db.flush()

            pub = Publication(
                campaign_id=c1.id,
                campaign_target_id=target.id,
                user_id=u_id,
                social_channel_id=c.id,
                buffer_connection_id=conn_id,
                external_channel_id=c.external_channel_id,
                status="published",
                attempt_count=1,
                idempotency_key=f"{c1.id}:{c.id}",
                published_at=datetime.now(timezone.utc) - timedelta(days=2),
                submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
                external_post_id=f"ext_pub_{uuid.uuid4().hex[:8]}",
                external_post_url=f"https://publish.buffer.com/updates/seed_{uuid.uuid4().hex[:6]}"
            )
            db.add(pub)
            db.flush()

            attempt = PublicationAttempt(
                publication_id=pub.id,
                attempt_number=1,
                started_at=datetime.now(timezone.utc) - timedelta(days=2),
                completed_at=datetime.now(timezone.utc) - timedelta(days=2) + timedelta(seconds=2),
                success=True,
                http_status=200,
                sanitized_request={"channel_id": c.external_channel_id},
                sanitized_response={"status": "published", "id": pub.external_post_id},
                duration_ms=1850
            )
            db.add(attempt)

        print("Seeding Campaign 2 (Running / Mixed publication states)...")
        c2 = Campaign(
            title="Winter Holidays Discount Campaign",
            default_text="Escape the cold weather. Get a 25% discount on hotel rooms and bistro dinners. ❄️🍷 #winterescape",
            facebook_text="Cozy winter fireplace dinners. book a dining table today! 🍷🔥 #bistro",
            publishing_mode="immediate",
            targeting_mode="all_active_channels",
            status="running",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        db.add(c2)
        db.flush()

        # Algarve IG (published)
        t_c2_ig = CampaignTarget(campaign_id=c2.id, user_id=u_algarve.id, social_channel_id=chan_algarve_ig.id, resolved_text=c2.default_text, status="created")
        db.add(t_c2_ig)
        db.flush()
        
        pub_c2_ig = Publication(
            campaign_id=c2.id, campaign_target_id=t_c2_ig.id, user_id=u_algarve.id, social_channel_id=chan_algarve_ig.id,
            buffer_connection_id=conn_algarve.id, external_channel_id=chan_algarve_ig.external_channel_id,
            status="published", attempt_count=1, idempotency_key=f"{c2.id}:{chan_algarve_ig.id}",
            published_at=datetime.now(timezone.utc) - timedelta(minutes=8), external_post_id="ext_c2_ig_123"
        )
        db.add(pub_c2_ig)
        
        # Algarve LI (queued)
        t_c2_li = CampaignTarget(campaign_id=c2.id, user_id=u_algarve.id, social_channel_id=chan_algarve_li.id, resolved_text=c2.default_text, status="created")
        db.add(t_c2_li)
        db.flush()
        pub_c2_li = Publication(
            campaign_id=c2.id, campaign_target_id=t_c2_li.id, user_id=u_algarve.id, social_channel_id=chan_algarve_li.id,
            buffer_connection_id=conn_algarve.id, external_channel_id=chan_algarve_li.external_channel_id,
            status="queued", attempt_count=0, idempotency_key=f"{c2.id}:{chan_algarve_li.id}"
        )
        db.add(pub_c2_li)

        # Algarve FB (retry_wait - simulated temporary fail)
        t_c2_fb = CampaignTarget(campaign_id=c2.id, user_id=u_algarve.id, social_channel_id=chan_algarve_fb.id, resolved_text=c2.default_text, status="created")
        db.add(t_c2_fb)
        db.flush()
        pub_c2_fb = Publication(
            campaign_id=c2.id, campaign_target_id=t_c2_fb.id, user_id=u_algarve.id, social_channel_id=chan_algarve_fb.id,
            buffer_connection_id=conn_algarve.id, external_channel_id=chan_algarve_fb.external_channel_id,
            status="retry_wait", attempt_count=1, idempotency_key=f"{c2.id}:{chan_algarve_fb.id}",
            next_attempt_at=datetime.now(timezone.utc) + timedelta(minutes=4),
            error_category="rate_limit", error_code="429", error_message="simulate-fail-temp-429: API rate limit exceeded."
        )
        db.add(pub_c2_fb)
        db.flush()
        attempt_c2_fb = PublicationAttempt(
            publication_id=pub_c2_fb.id, attempt_number=1, started_at=datetime.now(timezone.utc) - timedelta(minutes=9),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=9) + timedelta(seconds=1), success=False,
            http_status=429, external_error_code="rate_limit", error_category="rate_limit",
            error_message="simulate-fail-temp-429: Buffer API rate limit hit."
        )
        db.add(attempt_c2_fb)

        # Sintra X (failed - simulated permanent fail)
        t_c2_x = CampaignTarget(campaign_id=c2.id, user_id=u_sintra.id, social_channel_id=chan_sintra_x.id, resolved_text=c2.default_text, status="created")
        db.add(t_c2_x)
        db.flush()
        pub_c2_x = Publication(
            campaign_id=c2.id, campaign_target_id=t_c2_x.id, user_id=u_sintra.id, social_channel_id=chan_sintra_x.id,
            buffer_connection_id=conn_sintra.id, external_channel_id=chan_sintra_x.external_channel_id,
            status="failed", attempt_count=1, idempotency_key=f"{c2.id}:{chan_sintra_x.id}",
            error_category="invalid_media", error_code="invalid_media_format", error_message="simulate-fail-perm: Invalid or unsupported image size constraints for Twitter."
        )
        db.add(pub_c2_x)
        db.flush()
        attempt_c2_x = PublicationAttempt(
            publication_id=pub_c2_x.id, attempt_number=1, started_at=datetime.now(timezone.utc) - timedelta(minutes=8),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=8) + timedelta(seconds=2), success=False,
            http_status=400, external_error_code="invalid_media_format", error_category="invalid_media",
            error_message="simulate-fail-perm: Invalid aspect ratio for X publishing rules."
        )
        db.add(attempt_c2_x)

        print("Seeding Campaign 3 (Draft)...")
        c3 = Campaign(
            title="Spring Flowers and Wine Festival",
            default_text="Celebrate spring in the Douro Valley! 🌸🍷 Enjoy wine tastings and accommodation deals.",
            publishing_mode="scheduled",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=5),
            targeting_mode="all_active_channels",
            status="draft",
            created_by=admin.id
        )
        db.add(c3)

        print("Adding Audit Logs...")
        db.add_all([
            AuditLog(administrator_id=admin.id, action="login", entity_type="administrator", entity_id=admin.id, metadata_json={"ip": "127.0.0.1"}),
            AuditLog(administrator_id=admin.id, action="user_create", entity_type="user", entity_id=u_algarve.id),
            AuditLog(administrator_id=admin.id, action="campaign_launch", entity_type="campaign", entity_id=c1.id)
        ])

        db.commit()
        print("Database seeded successfully with test records!")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {str(e)}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
