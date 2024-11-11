ARG PYTHON_VERSION=3.11
FROM public.ecr.aws/vdb-public/python:${PYTHON_VERSION}-slim-bookworm AS base

USER root

# Switch to mpyl source code directory
WORKDIR /app/mpyl

# Install the dependencies.
RUN pip install pipenv
COPY Pipfile Pipfile.lock ./
RUN pipenv install --system --deploy

# Copy the source code into the container.
COPY src/mpyl ./

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
