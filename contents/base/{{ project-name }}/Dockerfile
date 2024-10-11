FROM python:3.11-buster

ARG artifactory_username
ARG artifactory_password
ARG org_name
ARG venture_name

RUN pip install poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache
ENV POETRY_HTTP_BASIC_P6M_AI_PLATFORM_PYPI_USERNAME=$artifactory_username
ENV POETRY_HTTP_BASIC_P6M_AI_PLATFORM_PYPI_PASSWORD=$artifactory_password

WORKDIR /app

COPY pyproject.toml ./
RUN touch README.md

COPY src /app/src

RUN poetry config http-basic.${org_name}_${venture_name}_pypi_local  $artifactory_username  $artifactory_password
RUN poetry install --without dev && rm -rf $POETRY_CACHE_DIR

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY logging.yaml ./
