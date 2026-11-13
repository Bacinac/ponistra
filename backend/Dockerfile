FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
# Snapshots: restic, and the Postgres the installation runs, from PostgreSQL's own repository,
# since Debian's is a major version behind it; its server recovers a snapshot in a cluster of its own,
# which needs the locale Postgres's image makes its databases with.
COPY --from=restic/restic:0.19.1 /usr/bin/restic /usr/local/bin/restic
RUN apt-get update \
    && apt-get install -y --no-install-recommends locales postgresql-common \
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf \
    && apt-get install -y --no-install-recommends postgresql-18 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
# PyICU and python-ldap ship only as source; they build against the system ICU, OpenLDAP and SASL,
# which stay for the runtime.
# numpy builds from source without BLAS: its wheels bundle OpenBLAS with libgfortran (GPL).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libicu76 libicu-dev libldap2 libldap-dev libsasl2-2 libsasl2-dev pkg-config g++ \
    && uv pip install --system --require-hashes --no-deps --no-binary numpy \
        --config-settings-package numpy:setup-args=-Dblas=none \
        --config-settings-package numpy:setup-args=-Dlapack=none \
        --config-settings-package numpy:setup-args=-Dallow-noblas=true \
        -r requirements.lock \
    && apt-get purge -y --auto-remove libicu-dev libldap-dev libsasl2-dev pkg-config g++ \
    && rm -rf /var/lib/apt/lists/*
COPY --from=fonts . /fonts
COPY --from=colors . /colors
COPY --from=schema . /schema
COPY --from=help . /help
COPY --from=i18n . /i18n

FROM base AS dev
COPY requirements-dev.lock ./
RUN uv pip install --system --require-hashes --no-deps -r requirements-dev.lock
COPY . .
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8030", "--lifespan", "on", "--timeout-graceful-shutdown", "15", "--reload"]

FROM base AS prod
# The tests' fixtures hold real names and messages, and the image is public.
COPY --exclude=**/tests --exclude=**/conftest.py . .
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8030", "--lifespan", "on", "--timeout-graceful-shutdown", "15"]
