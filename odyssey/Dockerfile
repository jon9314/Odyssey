# Use an official Python runtime as a parent image
FROM python:3.11-slim-bullseye # Updated to Python 3.11+ slim image

# Set environment variables
# PYTHONUNBUFFERED ensures that Python output is sent straight to terminal without being first buffered,
# which is good for Docker logging.
ENV PYTHONUNBUFFERED 1
# PIP_NO_CACHE_DIR disables the pip cache, which can reduce image size.
ENV PIP_NO_CACHE_DIR off
# PYTHONDONTWRITEBYTECODE prevents Python from writing .pyc files to disc.
ENV PYTHONDONTWRITEBYTECODE 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by Python packages or tools
# Example: build-essential for compiling some packages, git for versioning or fetching deps.
# Add other dependencies as needed (e.g., for database connectors, Tesseract for OCR).
# RUN apt-get update && apt-get install -y --no-install-recommends \
#    build-essential \
#    git \
#    # Add other system packages here, e.g.:
#    # libpq-dev (for psycopg2 if using PostgreSQL)
#    # default-libmysqlclient-dev (for mysqlclient if using MySQL)
#    # tesseract-ocr (if using pytesseract for OCR plugin)
#    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed Python packages specified in requirements.txt
# It's good practice to install requirements before copying the rest of the app code.
# This way, Docker can cache this layer if requirements.txt doesn't change, speeding up builds.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . .

# Create necessary directories that might be defined in settings.yaml but expected by the app at runtime
# These should match paths used for volumes in docker-compose.yml if persistence is desired.
# Ensure these directories are writable by the user the container runs as.
# RUN mkdir -p /app/var /app/logs
# The user running the process inside the container needs write access to these.
# If running as root (default), this is fine. If using a non-root user, adjust permissions.

# Expose the port the app runs on (e.g., FastAPI default is 8000)
# This is documentation; the actual port mapping is done in docker-compose.yml or `docker run -p`.
EXPOSE 8000

# Define the command to run your application
# This command will be executed when the container starts.
# Use Uvicorn to run the FastAPI application (agent.main:app)
# --host 0.0.0.0 makes it accessible externally (from other Docker containers or host)
# --port 8000 matches the EXPOSE directive
# --reload enables auto-reloading on code changes, useful for development.
#   For production, you might remove --reload and use more workers.
CMD ["uvicorn", "odyssey.agent.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# If you have a separate entrypoint script for Docker:
# COPY entrypoint.sh /usr/local/bin/
# RUN chmod +x /usr/local/bin/entrypoint.sh
# ENTRYPOINT ["entrypoint.sh"]
# CMD ["python", "odyssey/agent/main.py"] # Default command if entrypoint.sh doesn't override

# If you need to run as a non-root user for security:
# RUN useradd -m myuser
# USER myuser
# Then ensure /app and any volume mount points are writable by myuser.
