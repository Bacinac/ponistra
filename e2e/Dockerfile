# The browsers in this image belong to one Playwright release, so its tag and the
# @playwright/test version in package.json move together.
FROM mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f
WORKDIR /e2e
RUN npm install -g npm@12.2.1 --no-audit --no-fund
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
USER pwuser
CMD ["node_modules/.bin/playwright", "test"]
