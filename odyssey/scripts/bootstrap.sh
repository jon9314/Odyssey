#!/bin/bash

# Odyssey Project Bootstrapping Script
# Sets up the initial environment, databases, etc.

echo "Starting Odyssey bootstrap process..."

# --- Configuration ---
ENV_FILE_SOURCE="config/secrets.env"
ENV_FILE_DEST=".env"
SETTINGS_FILE="config/settings.yaml"
PYTHON_VERSION_REQUIRED="3.9" # Example, adjust as needed

# --- Helper Functions ---
check_command() {
    if ! command -v $1 &> /dev/null
    then
        echo "$1 could not be found. Please install it and try again."
        exit 1
    fi
}

check_python_version() {
    current_version=$(python3 -c 'import sys; print(str(sys.version_info.major) + "." + str(sys.version_info.minor))')
    if [[ "$current_version" < "$PYTHON_VERSION_REQUIRED" ]]; then
        echo "Python version $PYTHON_VERSION_REQUIRED or higher is required. You have $current_version."
        # Consider adding instructions for pyenv or similar version managers
        exit 1
    else
        echo "Python version $current_version found."
    fi
}


# --- Main Setup ---

# 1. Check for required tools
echo "Checking for required tools (python3, pip, git, docker)..."
check_command python3
check_command pip
check_command git
# check_command docker # Uncomment if Docker is a hard requirement for bootstrap

# 2. Check Python version
check_python_version

# 3. Create .env file if it doesn't exist
if [ ! -f "$ENV_FILE_DEST" ]; then
    echo "Creating $ENV_FILE_DEST from $ENV_FILE_SOURCE..."
    if [ -f "$ENV_FILE_SOURCE" ]; then
        cp "$ENV_FILE_SOURCE" "$ENV_FILE_DEST"
        echo "$ENV_FILE_DEST created. Please fill it with your secrets."
    else
        echo "Warning: $ENV_FILE_SOURCE not found. Please create it manually or copy from a template."
        # Create an empty .env as a fallback
        touch "$ENV_FILE_DEST"
        echo "Empty $ENV_FILE_DEST created. Please populate it with necessary environment variables."
    fi
else
    echo "$ENV_FILE_DEST already exists. Skipping creation."
fi

# 4. Create Python virtual environment
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created. Activate it using: source $VENV_DIR/bin/activate"
else
    echo "Virtual environment $VENV_DIR already exists."
fi
# Activate virtual environment for subsequent steps (optional, depends on script's scope)
# source "$VENV_DIR/bin/activate"

# 5. Install Python dependencies
echo "Installing Python dependencies from requirements.txt..."
if [ -f "requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r requirements.txt
    echo "Python dependencies installed."
else
    echo "Warning: requirements.txt not found. Skipping dependency installation."
fi

# 6. Setup database (Example: SQLite directory, migrations for other DBs)
# This part is highly dependent on your database choice in settings.yaml
DB_SQLITE_PATH_VAR=$(grep 'sqlite_db_path:' $SETTINGS_FILE | awk '{print $2}' | tr -d '"') # Basic parsing
if [ -n "$DB_SQLITE_PATH_VAR" ]; then
    DB_DIR=$(dirname "$DB_SQLITE_PATH_VAR")
    if [ ! -d "$DB_DIR" ]; then
        echo "Creating database directory: $DB_DIR"
        mkdir -p "$DB_DIR"
    fi
    # If using Alembic for migrations with SQLAlchemy:
    # echo "Running database migrations (if applicable)..."
    # "$VENV_DIR/bin/alembic" upgrade head
fi

# 7. Create other necessary directories (e.g., for logs, vector stores from settings.yaml)
LOG_FILE_PATH_VAR=$(grep 'file:' $SETTINGS_FILE | grep 'logging:' -B1 | tail -n1 | awk '{print $2}' | tr -d '"')
if [ -n "$LOG_FILE_PATH_VAR" ]; then
    LOG_DIR=$(dirname "$LOG_FILE_PATH_VAR")
    if [ ! -d "$LOG_DIR" ]; then
        echo "Creating log directory: $LOG_DIR"
        mkdir -p "$LOG_DIR"
    fi
fi

VECTOR_STORE_PATH_VAR=$(grep 'vector_store_path:' $SETTINGS_FILE | awk '{print $2}' | tr -d '"')
if [ -n "$VECTOR_STORE_PATH_VAR" ]; then
    if [ ! -d "$VECTOR_STORE_PATH_VAR" ]; then
        echo "Creating vector store directory: $VECTOR_STORE_PATH_VAR"
        mkdir -p "$VECTOR_STORE_PATH_VAR"
    fi
fi


# 8. Docker setup (if using Docker Compose)
if [ -f "docker-compose.yml" ]; then
    echo "Docker Compose file found."
    # You might want to prompt the user before running this
    # read -p "Do you want to start services with Docker Compose? (y/N): " choice
    # if [[ "$choice" == [Yy]* ]]; then
    #     echo "Building and starting Docker containers..."
    #     docker-compose up --build -d
    # else
    #     echo "Skipping Docker Compose startup. You can run 'docker-compose up --build -d' manually."
    # fi
    echo "To start services with Docker Compose, run: docker-compose up --build -d"
fi

echo "Bootstrap process completed."
echo "Remember to activate your virtual environment: source $VENV_DIR/bin/activate"
echo "Please ensure all secrets are correctly set in $ENV_FILE_DEST."
echo "You may need to run additional setup steps depending on your project configuration (e.g., frontend build)."
