FROM python:3.11-slim

# Install maestro-guard + playwright + chromium
COPY dist/maestro_guard-*.tar.gz /tmp/
RUN pip install --no-cache-dir /tmp/maestro_guard-*.tar.gz playwright \
    && playwright install chromium \
    && playwright install-deps chromium \
    && rm /tmp/maestro_guard-*.tar.gz

# Create non-root user
RUN useradd -m -u 1001 maestro
USER maestro
WORKDIR /work

ENTRYPOINT ["maestro-guard"]
CMD ["--help"]
