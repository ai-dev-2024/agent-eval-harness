FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . 'pytest>=8,<10' \
    && useradd --create-home --uid 10001 evaluator \
    && mkdir -p /app/runs \
    && chown evaluator:evaluator /app/runs

USER evaluator
ENTRYPOINT ["agent-eval"]
CMD ["--help"]
