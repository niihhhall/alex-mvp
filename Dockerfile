# Hosted Alex: GitHub App webhook server + review engine.
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git openssl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Pinned so an engine release cannot change reviews without us noticing.
ARG ENGINE_VERSION=1.12.10
# npm's update notifier keeps writing to its cache in the background, which breaks the
# image export ("write too long"). Disable it and keep the cache outside the image.
ENV NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false
RUN npm install -g "@alibaba-group/open-code-review@${ENGINE_VERSION}" --cache /tmp/npm-cache \
 && ocr version \
 && rm -rf /tmp/npm-cache /root/.npm

WORKDIR /app
COPY alex ./alex

RUN useradd --create-home --shell /usr/sbin/nologin alex \
 && mkdir -p /tmp/alex && chown alex /tmp/alex
USER alex

ENV PYTHONUNBUFFERED=1 \
    ALEX_DATA_DIR=/tmp/alex \
    ALEX_ENGINE_CMD=ocr \
    PORT=8080

EXPOSE 8080
CMD ["python3", "-m", "alex.server"]
