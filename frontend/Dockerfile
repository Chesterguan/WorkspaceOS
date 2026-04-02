# ---- deps stage: install all node_modules ----
FROM node:20-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json* ./
# Use ci for reproducible installs; fall back to install if no lockfile exists
RUN npm ci || npm install

# ---- builder stage: compile the Next.js app ----
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args are baked into the static bundle at build time.
# Pass them with --build-arg when building outside of compose,
# or let compose inject them via the environment block.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_API_KEY=dev-secret-key
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY

RUN npm run build

# ---- runner stage: minimal production image ----
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Only copy what next start needs
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
