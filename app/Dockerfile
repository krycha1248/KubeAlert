# Use official lightweight Python Alpine base image (~50MB uncompressed, ~18MB compressed)
FROM python:3.12-alpine

# Prevent Python from writing .pyc bytecode files and enable unbuffered logging for Kubernetes
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Create dedicated non-root user and group for Kubernetes security compliance
RUN addgroup -g 10001 -S appgroup && \
    adduser -u 10001 -S appuser -G appgroup

WORKDIR /app

# Copy application source code
COPY --chown=appuser:appgroup . .

# Switch to unprivileged user
USER 10001:10001

# Expose HTTP port
EXPOSE 8080

# Run application
ENTRYPOINT ["python", "main.py"]
