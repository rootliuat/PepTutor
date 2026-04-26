FROM node:24-trixie AS build-stage

WORKDIR /app

RUN apt update && apt install -y ca-certificates curl
RUN update-ca-certificates
RUN apt update && apt install -y build-essential python3 python3-setuptools curl

RUN corepack enable

COPY . .
RUN --mount=type=cache,id=pnpm-store,target=/root/.pnpm-store \
    pnpm install --frozen-lockfile

RUN pnpm -F @proj-airi/stage-web run build && \
    pnpm -F @proj-airi/docs run build:base && \
    mv ./docs/.vitepress/dist ./apps/stage-web/dist/docs && \
    pnpm -F @proj-airi/stage-ui run story:build && \
    mv ./packages/stage-ui/.histoire/dist ./apps/stage-web/dist/ui

FROM nginx:stable-alpine AS production-stage

COPY --from=build-stage /app/apps/stage-web/dist /usr/share/nginx/html
COPY ./apps/stage-web/production/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY ./apps/stage-web/production/docker-entrypoint.d/40-peptutor-runtime-config.sh /docker-entrypoint.d/40-peptutor-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/40-peptutor-runtime-config.sh

ENV PEPTUTOR_BACKEND_UPSTREAM=http://127.0.0.1:9621
ENV PEPTUTOR_RUNTIME_LESSON_API_URL=/peptutor-api

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
