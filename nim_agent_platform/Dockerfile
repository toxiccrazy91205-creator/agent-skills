FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install python packages
COPY nim_agent_platform/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy both django application and senior engineering skills repository
COPY nim_agent_platform/ /app/nim_agent_platform/
COPY agent-skills/ /app/agent-skills/

# Ensure workspace and database persistent mount directories exist
RUN mkdir -p /data/workspace

# Configure default persistent storage paths
ENV PYTHONUNBUFFERED=1 \
    DEFAULT_WORKSPACE_PATH=/data/workspace \
    DATABASE_PATH=/data/db.sqlite3 \
    PORT=8000

# Make entrypoint script executable
RUN chmod +x /app/nim_agent_platform/entrypoint.sh

# Expose port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["/app/nim_agent_platform/entrypoint.sh"]
