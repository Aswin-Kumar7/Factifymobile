# The Factify website (Next.js), as a small standalone server.
#
# It talks to the API over the compose network (FACTIFY_API_INTERNAL); Caddy sends
# /v1 straight to the API and everything else here (deploy/Caddyfile).

FROM node:22-alpine AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S web && adduser -S web -G web
COPY --from=build --chown=web:web /web/.next/standalone ./
COPY --from=build --chown=web:web /web/.next/static ./.next/static
COPY --from=build --chown=web:web /web/public ./public
USER web
EXPOSE 3000
CMD ["node", "server.js"]
