ARG PYTHON_VERSION=3.13
FROM public.ecr.aws/vdb-public/python:${PYTHON_VERSION}-slim-bookworm AS dev

USER root
ENV PIPENV_VENV_IN_PROJECT=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
RUN pip install pipenv pre-commit


FROM dev AS application

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
