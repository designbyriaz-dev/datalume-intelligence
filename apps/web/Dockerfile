FROM node:20-slim AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

# Next.js inlines NEXT_PUBLIC_* variables into the client bundle at
# build time, not read at container runtime — a plain runtime env var
# set by the hosting platform would silently have no effect, leaving
# the deployed frontend calling localhost:8000. Must be passed as a
# Docker build ARG (e.g. Railway's "Build Variables") so it's baked in
# during `npm run build` below.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:20-slim

WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json

EXPOSE 3000

CMD ["npm", "run", "start"]
