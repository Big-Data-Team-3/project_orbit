# Use Python 3.11 slim image for smaller size and security
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update --fix-missing || true && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/archives/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire application code
COPY . .

# Add src directory to Python path
ENV PYTHONPATH=/app/src:/app

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Switch to non-root user
USER app

# Expose both ports (API and Streamlit)
EXPOSE 8000 8501

# Health check to ensure the service is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command for FastAPI (will be overridden by docker-compose for Streamlit)
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]