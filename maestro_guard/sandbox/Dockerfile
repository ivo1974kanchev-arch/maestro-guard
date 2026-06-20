FROM python:3.11-slim

# Install system deps for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates gnupg \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install maestro-guard from local dist
COPY dist/maestro_guard-*.tar.gz /tmp/
RUN pip install --no-cache-dir /tmp/maestro_guard-*.tar.gz playwright \
    && playwright install chromium \
    && playwright install-deps chromium \
    && rm /tmp/maestro_guard-*.tar.gz

# Create non-root user
RUN useradd -m -u 1001 maestro
USER maestro
WORKDIR /work

# Default: run check with --exec-spec
ENTRYPOINT ["maestro-guard"]
CMD ["--help"]
