# Build context is the monorepo root (see docker-compose.yml: context: ., dockerfile: apps/dashboard/Dockerfile)
# so pnpm can resolve the workspace (pnpm-workspace.yaml + root pnpm-lock.yaml) correctly.

FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# ---------------------------------------------------------------------------
FROM base AS deps
WORKDIR /repo
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN pnpm install --frozen-lockfile --filter dashboard...

# ---------------------------------------------------------------------------
FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/dashboard/node_modules ./apps/dashboard/node_modules
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/dashboard apps/dashboard
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter dashboard build

# ---------------------------------------------------------------------------
# Dev image: dependencies are baked in at build time; docker-compose bind-mounts
# apps/dashboard source over this for hot reload, while anonymous volumes on the
# two node_modules paths keep these baked-in installs from being hidden by the mount.
FROM base AS dev
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/dashboard/node_modules ./apps/dashboard/node_modules
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/dashboard apps/dashboard
WORKDIR /repo/apps/dashboard
ENV NODE_ENV=development
EXPOSE 3000
CMD ["pnpm", "dev"]

# ---------------------------------------------------------------------------
FROM node:22-slim AS production
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder /repo/apps/dashboard/public ./apps/dashboard/public
COPY --from=builder --chown=nextjs:nodejs /repo/apps/dashboard/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/dashboard/.next/static ./apps/dashboard/.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "apps/dashboard/server.js"]
