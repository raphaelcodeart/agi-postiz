export const queryKeys = {
  me: ["me"] as const,
  users: {
    list: (params?: unknown) => ["users", "list", params] as const,
    detail: (id: string) => ["users", "detail", id] as const,
    summary: () => ["users", "summary"] as const,
  },
  groups: {
    list: () => ["groups", "list"] as const,
    users: (groupId: string) => ["groups", "users", groupId] as const,
  },
  bufferConnections: {
    list: () => ["buffer-connections", "list"] as const,
  },
  channels: {
    list: (params?: unknown) => ["channels", "list", params] as const,
  },
  media: {
    list: () => ["media", "list"] as const,
    detail: (id: string) => ["media", "detail", id] as const,
  },
  campaigns: {
    list: (params?: unknown) => ["campaigns", "list", params] as const,
    detail: (id: string) => ["campaigns", "detail", id] as const,
    metrics: (id: string) => ["campaigns", "metrics", id] as const,
    summary: () => ["campaigns", "summary"] as const,
  },
  publications: {
    list: (params?: unknown) => ["publications", "list", params] as const,
    detail: (id: string) => ["publications", "detail", id] as const,
    metrics: (id: string) => ["publications", "metrics", id] as const,
    feed: (params?: unknown) => ["publications", "feed", params] as const,
    summary: () => ["publications", "summary"] as const,
  },
  settings: {
    detail: () => ["settings", "detail"] as const,
    health: () => ["settings", "health"] as const,
    ai: () => ["settings", "ai"] as const,
  },
  blogWriter: {
    sites: () => ["blog-writer", "sites"] as const,
    articles: (params?: unknown) => ["blog-writer", "articles", params] as const,
    articleDetail: (id: string) => ["blog-writer", "article-detail", id] as const,
    dashboard: () => ["blog-writer", "dashboard"] as const,
  },
  omnichannel: {
    channelAccounts: () => ["omnichannel", "channel-accounts"] as const,
    conversations: (params?: unknown) => ["omnichannel", "conversations", params] as const,
    conversationDetail: (id: string) => ["omnichannel", "conversation-detail", id] as const,
    tags: () => ["omnichannel", "tags"] as const,
    aiAgent: () => ["omnichannel", "ai-agent"] as const,
    knowledgeBase: () => ["omnichannel", "knowledge-base"] as const,
    notifications: (unreadOnly?: boolean) => ["omnichannel", "notifications", unreadOnly] as const,
    analytics: () => ["omnichannel", "analytics"] as const,
    pendingCount: () => ["omnichannel", "pending-count"] as const,
  },
  statistics: {
    dashboard: () => ["statistics", "dashboard"] as const,
    userDetail: (userId: string) => ["statistics", "user-detail", userId] as const,
    channelDetail: (userId: string, channelId: string) =>
      ["statistics", "channel-detail", userId, channelId] as const,
    syncRun: (syncRunId: string) => ["statistics", "sync-run", syncRunId] as const,
  },
} as const;
