# Chromium, headless, prints a document's print page to PDF or counts its pages for the backend.
# Debian's Chromium headless shell rather than Playwright's: it gets Debian's security updates, has
# an arm64 build, and comes from no Microsoft registry or CDN. The print page brings the documents'
# fonts; these cover every other script a reader's browser would fall back on, under the OFL.
FROM node:26-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium-headless-shell fontconfig fonts-liberation fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g npm@12.2.1 --no-audit --no-fund
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY serve.mjs ./
ENV HOME=/tmp
USER node
EXPOSE 8050
CMD ["node", "serve.mjs"]
