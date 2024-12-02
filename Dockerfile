ARG PYTHON_VERSION=3.13
FROM public.ecr.aws/vdb-public/python:${PYTHON_VERSION}-slim-bookworm

USER root

# install Helm
RUN set -eux ; \
    apt-get update -y ; \
    apt-get install -y curl ; \
    curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 ; \
    chmod 700 get_helm.sh ; \
    ./get_helm.sh ; \
    rm -rf /var/lib/apt/lists/*

# install pipenv for dependency management
# TODO fix the base python image so that it creates a home directory for the vdnonroot user
# USER vdbnonroot
ENV LANG="en_US.UTF-8"
ENV LC_ALL="en_US.UTF-8"
RUN pip install pipenv

# Switch to mpyl source code directory
WORKDIR /app/mpyl

# Install the project dependencies.
COPY Pipfile Pipfile.lock ./
RUN pipenv sync --system

# Copy the source code into the container.
COPY --link src/mpyl ./

# Set pythonpath for mpyl
ENV PYTHONPATH=/app

# Switch to the directory of the calling repo
WORKDIR /repo

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Run the application.
ENTRYPOINT ["python", "/app/mpyl/__main__.py"]
