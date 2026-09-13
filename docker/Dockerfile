# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN python -m pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.11-slim-bookworm AS runtime

ARG ROXYWI_UID=10001
ARG ROXYWI_GID=10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ROXYWI_DEPLOYMENT_MODE=compose \
    ROXYWI_FULLPATH=/var/www/haproxy-wi \
    ROXYWI_LIB_PATH=/var/lib/roxy-wi \
    ROXYWI_LOG_PATH=/var/log/roxy-wi \
    ROXYWI_LOG_CONSOLE=1 \
    ROXYWI_LOG_FILE_ENABLED=0 \
    ROXYWI_AUTO_MIGRATE=0 \
    ROXYWI_ANSIBLE_PRIVATE_DATA_DIR=/var/lib/roxy-wi/ansible \
    ROXYWI_ANSIBLE_ROLES_PATH=/var/lib/roxy-wi/ansible/roles \
    ROXYWI_ANSIBLE_COLLECTIONS_PATH=/var/lib/roxy-wi/ansible/collections \
    ANSIBLE_ROLES_PATH=/var/lib/roxy-wi/ansible/roles:/var/www/haproxy-wi/app/scripts/ansible/roles:/usr/share/ansible/roles \
    ANSIBLE_COLLECTIONS_PATH=/var/lib/roxy-wi/ansible/collections:/usr/share/ansible/collections

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates curl dnsutils git iputils-ping nmap netcat-openbsd \
        openssh-client procps rsync socat whois \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${ROXYWI_GID}" roxywi \
    && useradd --uid "${ROXYWI_UID}" --gid roxywi --home-dir /var/lib/roxy-wi --create-home roxywi

COPY --from=wheels /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

WORKDIR /var/www/haproxy-wi
COPY --chown=roxywi:roxywi . .
COPY docker/roxy-wi.docker.cfg /etc/roxy-wi/roxy-wi.cfg

RUN mkdir -p /var/lib/roxy-wi/ansible/inventory /var/lib/roxy-wi/ansible/roles /var/lib/roxy-wi/ansible/collections /var/log/roxy-wi /usr/share/ansible/roles /usr/share/ansible/collections \
    && ansible-galaxy collection install \
        -r app/scripts/ansible/collections-requirements.yml \
        --collections-path /usr/share/ansible/collections \
    && ansible-galaxy role install \
        -r app/scripts/ansible/roles-requirements.yml \
        --roles-path /usr/share/ansible/roles \
    && chown -R roxywi:roxywi /var/lib/roxy-wi /var/log/roxy-wi /var/www/haproxy-wi

USER roxywi

EXPOSE 8080
VOLUME ["/var/lib/roxy-wi"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3)"

ENTRYPOINT ["python", "/var/www/haproxy-wi/roxy_wi.py"]
CMD ["web"]
