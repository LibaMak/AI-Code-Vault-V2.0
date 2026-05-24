# Deployment Guide — AI Code Vault 2.0

This guide provides setup and deployment instructions for running **AI Code Vault 2.0 (v2.5.9)** in local development, containers, and cloud environments.

---

## 1. Prerequisites

- **Python**: version `3.11` is recommended.
- **Git**: required for repository scanning and local workspace checks.
- **SQLite3**: default local database engine.

---

## 2. Local Setup

Follow these steps to run the application on your local machine:

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd AI-Code-VAult-v2.0-agentic
   ```

2. **Create a Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file in the root directory by copying the template:
   ```bash
   copy .env.example .env
   ```
   Edit the `.env` file to configure your keys (see **Environment Variables** below).

5. **Launch the Streamlit Server**:
   ```bash
   streamlit run streamlit_app.py
   ```
   The application will be accessible at `http://localhost:8501`.

---

## 3. Containerized Deployment

### Docker Setup

You can containerize the application using the following configurations:

#### Create `Dockerfile` in root:
```dockerfile
FROM python:3.11-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port
EXPOSE 8501

# Run health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Start the Streamlit application
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  code-vault:
    build: .
    ports:
      - "8501:8501"
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GROQ_MODEL=llama-3.3-70b-versatile
      - GROQ_FAST_MODEL=llama-3.1-8b-instant
      - DATABASE_URL=sqlite:///./vault_v5.db
      - ADMIN_EMAIL=${ADMIN_EMAIL}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

To run:
```bash
docker-compose up --build -d
```

---

## 4. Codespaces / DevContainer Setup

The workspace is pre-configured with a `.devcontainer/devcontainer.json`.
- **Environment**: Python 3.11 (Debian Bookworm).
- **Auto-setup**: Installs all pip dependencies and launches `streamlit run streamlit_app.py` automatically.
- **Port Forwarding**: Port `8501` is forwarded automatically for web browser access.

---

## 5. Cloud Platform Deployment (Streamlit Community Cloud / Render)

When deploying to Streamlit Community Cloud or similar PaaS providers:
1. Specify Python `3.11` in `runtime.txt`.
2. Connect your Git repository.
3. Configure the platform's Environment Secrets/Variables:
   - `GROQ_API_KEY`
   - `ADMIN_EMAIL`
   - `ADMIN_PASSWORD`
   - `DATABASE_URL` (use default if relying on SQLite)

---

## 6. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | None | API Key required to authenticate against Groq's LLM endpoint. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | The main LLM model used for complex reasoning tasks. |
| `GROQ_FAST_MODEL` | `llama-3.1-8b-instant` | The LLM model used for heuristic parsing and rapid routing. |
| `DATABASE_URL` | `sqlite:///./vault_v5.db` | Connection string for database. PostgreSQL supported. |
| `LOCAL_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Model name for generating local embeddings. |
| `ADMIN_EMAIL` | None | Email of the administrator user to auto-provision on first start. |
| `ADMIN_PASSWORD` | None | Password of the administrator user to auto-provision. |

---

## 7. Security Best Practices

- **Admin Provisioning**: Set strong `ADMIN_PASSWORD` strings during initial deployment.
- **Encryption**: Utilize HTTPS configurations via a reverse proxy (such as Nginx) in production.
- **Storage Limits**: Admin users should monitor sqlite db size over time.
- **Key Pools**: Key values added to the admin pool are stored encrypted in the database.
