# Odyssey: A Self-Rewriting AI Agent

Odyssey is an open-source AI agent that can rewrite its own code, manage tasks, and grow its own capabilities over time.  
It uses Ollama-hosted LLMs, a hybrid memory system, and a plugin-based architecture for safe, observable self-improvement.

## Features

- **Self-Rewriting:** Proposes, tests, and merges its own code changes via GitHub.
- **Dual LLMs:** Uses both a local CPU model and a LAN-based GPU model via Ollama.
- **Hybrid Memory:** Combines SQLite (structured), Chroma/FAISS (vector/semantic), and JSON (backup); all actions observable via Langfuse.
- **Web UI:** Manage tasks, logs, memory, and agent config in your browser.
- **Extensible Tools:** Easily add plugins (file ops, calendar, OCR, browser, etc).
- **Dockerized:** Backend, frontend, Valkey, Langfuse, and Ollama all run with Docker Compose.

## Quickstart

### 1. Clone & Configure

```sh
git clone https://github.com/your-org/odyssey.git
cd odyssey
cp config/settings.example.yaml config/settings.yaml
cp .env.example .env
# Edit configs as needed (Ollama endpoints, secrets)
