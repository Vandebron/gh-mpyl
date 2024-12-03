# syntax=docker/dockerfile:1.7-labs
ARG PYTHON_VERSION=3.13
FROM public.ecr.aws/vdb-public/python:${PYTHON_VERSION}-slim-bookworm

USER root

# install Helm (necessary only for legacy Dagster deployments, remove after they're on Argo CD)
RUN set -eux ; \
    apt-get update -y ; \
    apt-get install -y curl ; \
    curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 ; \
    chmod 700 get_helm.sh ; \
    ./get_helm.sh ; \
    rm -rf /var/lib/apt/lists/*

# install pipenv for dependency management
RUN pip install pipenv

# Switch to mpyl source code directory
WORKDIR /app/mpyl

# Install the project dependencies.
USER vdbnonroot
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
COPY Pipfile Pipfile.lock ./
RUN pipenv sync

# Copy the source code into the container.
COPY --link --parents src/mpyl ./

# Make sure Python doesn't expect src. in the package names
ENV PYTHONPATH=/app/mpyl/src
# Use MPyL's Pipfile, not the one from the caller repo
ENV PIPENV_PIPFILE=/app/mpyl/Pipfile
# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

## Switch to the directory of the caller repo (must be mounted while running)
WORKDIR /repo

# Run the application.
ENTRYPOINT ["pipenv", "run", "python", "/app/mpyl/src/mpyl/__main__.py"]
CMD ["health"]
