# Docker Configuration

This directory contains all Docker-related files for the Phoebe UI project.

## Files

- `docker-compose.yml` - Main compose file for running all services
- `Dockerfile.api` - API server container
- `Dockerfile.ui` - NiceGUI UI container  
- `Dockerfile.server` - Phoebe server container
- `Dockerfile.manager` - Session manager container
- `requirements.api.txt` - Dependencies for API service
- `requirements.ui.txt` - Dependencies for UI service
- `requirements.server.txt` - Dependencies for server service
- `requirements.manager.txt` - Dependencies for session manager service

## Usage

From the project root directory:

```bash
# Build and run all services
docker compose -f docker/docker-compose.yml up --build

# Run in background
docker compose -f docker/docker-compose.yml up -d

# Stop all services
docker compose -f docker/docker-compose.yml down
```

## Services

- **API**: Port 8001 - FastAPI backend
- **UI**: Port 8080 - NiceGUI frontend
- **Redis**: Port 6379 - Cache/session storage
- **Server**: Internal - Phoebe computation servers
- **Session Manager**: Internal - Manages server instances
