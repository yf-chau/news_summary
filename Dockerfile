FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "--no-dev", "python", "main.py"]
