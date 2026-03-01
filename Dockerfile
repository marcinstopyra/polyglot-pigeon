# ── Stage 1: export locked dependencies ───────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /build

RUN pip install --no-cache-dir poetry==2.3.1 poetry-plugin-export

COPY pyproject.toml poetry.lock ./

RUN poetry export --without dev --without-hashes -f requirements.txt -o requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=deps /build/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src

CMD ["python", "src/polyglot_pigeon/main.py", "-c", "/app/config.yaml", "--daemon"]
