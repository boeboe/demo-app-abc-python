FROM ubuntu:focal
# https://hub.docker.com/_/ubuntu?tab=tags

LABEL maintainer="bartvanbos@gmail.com"

# Build arguments
ARG BUILD_DATE
ARG BUILD_VERSION
ARG DOCKER_ACCOUNT
ARG IMAGE_DESCRIPTION
ARG IMAGE_NAME
ARG APP_VERSION
ARG REPO_URL
ARG URL

# Labels
LABEL org.label-schema.build-date=$BUILD_DATE
LABEL org.label-schema.description=$IMAGE_DESCRIPTION
LABEL org.label-schema.name=$DOCKER_ACCOUNT/$IMAGE_NAME
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.url=$URL
LABEL org.label-schema.vcs-url=$REPO_URL
LABEL org.label-schema.vendor=$DOCKER_ACCOUNT
LABEL org.label-schema.version=$BUILD_VERSION

ENV APP_VERSION=$APP_VERSION
ENV CONF_FILE=/etc/app-abc/config.yaml
ENV PYTHONUNBUFFERED=1

ADD server.py /usr/local/bin
ADD entrypoint.sh /usr/local/bin
ADD requirements.txt /

RUN apt update -y \
    && apt install -y python3 python3-pip \
    && pip3 install -r /requirements.txt \
    && rm -rf /var/lib/apt/lists/* \
    && rm /requirements.txt \
    && mkdir -p /etc/app-abc

VOLUME [ "/etc/app-abc" ]

ENV OTEL_PYTHON_LOG_CORRELATION=true

STOPSIGNAL SIGTERM

CMD ["entrypoint.sh"]