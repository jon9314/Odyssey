"""
Celery application setup for Odyssey.

This module initializes the Celery application, configures it with settings
from the application's configuration (loaded via environment variables or defaults),
and sets up task auto-discovery.

To run a Celery worker for Odyssey:
1. Ensure Valkey (or Redis) is running and accessible.
2. Activate your Python virtual environment: `source .venv/bin/activate`
3. From the project root directory (`odyssey/`), run:
   `celery -A odyssey.agent.celery_app worker -l INFO -Q default`
   (Replace `default` with specific queue names if you configure routing).

You can also use `docker compose run --rm celery_worker` if defined in docker-compose.yml.
"""
from celery import Celery
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)

# --- Celery Settings Model using Pydantic-Settings ---
# This helps in loading settings from environment variables (via .env)
# and provides type validation and defaults.
class CelerySettings(BaseSettings):
    # These names (e.g., celery_broker_url) should match how they are defined
    # in your .env file or system environment.
    # The defaults here are for local development if .env is not set.
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend_url: str = "redis://localhost:6379/0"
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list[str] = ["json"]
    celery_timezone: str = "UTC"
    celery_enable_utc: bool = True
    celery_include_tasks: list[str] = ["odyssey.agent.tasks"] # Module(s) where tasks are defined

    class Config:
        env_prefix = "" # Consider using a prefix like "CELERY_" if vars are CELERY_BROKER_URL etc.
                        # If env vars are exactly as field names, no prefix is needed.
                        # Or, rely on settings.yaml to map env vars if using a global AppSettings.
                        # For simplicity here, assuming direct env var names or they are loaded by a global settings object.
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Load Celery settings
# In a larger app, this might come from a central configuration management system.
# For now, we load them directly here.
try:
    settings = CelerySettings()
    logger.info("Celery settings loaded successfully.")
    logger.debug(f"Celery Settings: Broker URL='{settings.celery_broker_url}', Include Tasks='{settings.celery_include_tasks}'")
except Exception as e:
    logger.error(f"Failed to load Celery settings: {e}. Using hardcoded defaults.", exc_info=True)
    # Fallback to hardcoded defaults if settings loading fails (less ideal)
    class FallbackSettings:
        celery_broker_url = "redis://localhost:6379/0"
        celery_result_backend_url = "redis://localhost:6379/0"
        celery_task_serializer = "json"
        celery_result_serializer = "json"
        celery_accept_content = ["json"]
        celery_timezone = "UTC"
        celery_enable_utc = True
        celery_include_tasks = ["odyssey.agent.tasks"]
    settings = FallbackSettings()


# Initialize Celery application
# The first argument is the name of the current module, important for Celery.
# The `main` argument can also be used to name the application.
celery_app = Celery(
    'odyssey_agent', # Application name
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend_url,
    include=settings.celery_include_tasks
)

# Update Celery configuration from our settings object
celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    # Optional: Add other Celery configurations if needed
    # result_expires=3600, # Example: How long to keep task results
    # worker_prefetch_multiplier=1, # Can be important for long-running tasks
)

# Optional: Configure Celery logging further if needed
# Celery uses Python's logging module, so basicConfig in main.py might cover it.
# from celery.signals import setup_logging
# @setup_logging.connect
# def config_loggers(*args, **kwargs):
#     from logging.config import dictConfig
#     from odyssey.config.logging_config import LOGGING_CONFIG # If you have a central dictConfig
#     dictConfig(LOGGING_CONFIG)

# Example task (can be moved to odyssey.agent.tasks module as per `include` setting)
# If tasks are in a separate file (e.g., odyssey/agent/tasks.py),
# they would be defined there and auto-discovered due to the `include` config.
# For this example, we'll keep one here to ensure celery_app is usable directly.
@celery_app.task(bind=True) # `bind=True` gives access to `self` (the task instance)
def self_aware_example_task(self, x, y):
    logger.info(f"[CeleryTask:{self.request.id}] self_aware_example_task started with x={x}, y={y}")
    result = x + y
    logger.info(f"[CeleryTask:{self.request.id}] self_aware_example_task finished. Result: {result}")
    return result


if __name__ == '__main__':
    # This block allows running the Celery worker directly using:
    # `python -m odyssey.agent.celery_app worker -l INFO`
    # (Though typically you'd use `celery -A odyssey.agent.celery_app worker ...`)

    # For testing, you can also submit a task:
    # from .celery_app import self_aware_example_task
    # result = self_aware_example_task.delay(5, 7)
    # print(f"Submitted example task. Task ID: {result.id}")
    # print("Run a Celery worker to process this task.")
    # print("`celery -A odyssey.agent.celery_app worker -l INFO -Q default`")

    logger.info("Celery app `odyssey.agent.celery_app` is defined.")
    logger.info("To start a worker from project root: `celery -A odyssey.agent.celery_app worker -l INFO -Q default`")
    logger.info("Ensure your broker (Valkey/Redis) is running and configured in .env or settings.")
