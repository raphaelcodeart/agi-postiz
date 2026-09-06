"""
Real Instagram Direct connector. Instagram messaging runs on the exact same
Meta Graph API infrastructure as Messenger since Meta unified the two
platforms (developers.facebook.com/docs/messenger-platform/instagram) -
same webhook payload shape (entry[].messaging[]), same /me/messages Send
API, same X-Hub-Signature-256 signature scheme, same two-secret storage
(Page/IG Access Token + App Secret, see facebook.py's module docstring).

Requires an Instagram **professional** (Business/Creator) account linked to
a Facebook Page, and the same App Review + Business Verification for
`instagram_manage_messages` before it can message real customers - see
docs/OMNICHANNEL_RESPONDER.md §11.

Zero logic differences from FacebookConnector - only channel_label changes,
purely for clearer error/status messages shown to the admin.
"""
from app.integrations.omnichannel.connectors.facebook import FacebookConnector


class InstagramConnector(FacebookConnector):
    channel_label = "Instagram"
