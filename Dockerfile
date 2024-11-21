ARG PYTHON_VERSION=3.13
FROM public.ecr.aws/vdb-public/python:${PYTHON_VERSION}-slim-bookworm AS dev

USER root

# needed for devcontainers + IntelliJ IDEA
RUN DEBIAN_FRONTEND=noninteractive \
    && apt-get update -y && apt-get install -y  \
    curl \
    git \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install pipenv


FROM dev AS application

# Install the project dependencies.
COPY Pipfile Pipfile.lock /app/mpyl/
RUN pipenv install --system --deploy

# Copy the source code into the container.
COPY --link src/mpyl /app/mpyl/

# Set pythonpath for mpyl
ENV PYTHONPATH=/app

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Run the application.
ENTRYPOINT ["python", "/app/mpyl/__main__.py"]
