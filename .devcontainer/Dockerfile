ARG PYTHON_VERSION=3.13
FROM public.ecr.aws/vdb-public/python:3.13-slim-bookworm AS dev

USER root
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
RUN pip install pipenv pre-commit
