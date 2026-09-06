# Import all the models, so that Base has them before being
# imported by Alembic or used in other places.
from app.db.session import Base  # noqa
from app.models.administrator import Administrator  # noqa
from app.models.user import User, UserGroup  # noqa
from app.models.buffer import BufferConnection, BufferOrganization, SocialChannel  # noqa
from app.models.media import MediaFile  # noqa
from app.models.campaign import Campaign, CampaignTarget  # noqa
from app.models.publication import Publication, PublicationAttempt  # noqa
from app.models.audit import AuditLog  # noqa
from app.models.omnichannel import (  # noqa
    OmniChannelAccount,
    OmniCustomer,
    OmniCustomerIdentity,
    OmniConversation,
    OmniMessage,
    OmniAIDraft,
    OmniAIAgentConfig,
    OmniKnowledgeDocument,
    OmniKnowledgeChunk,
    OmniTag,
    omni_conversation_tags,
    OmniInternalNote,
    OmniAuditLog,
    OmniNotification,
    OmniAIUsage,
)
from app.models.statistics import StatSyncRun, StatPostMetric, StatMetricHistory  # noqa
