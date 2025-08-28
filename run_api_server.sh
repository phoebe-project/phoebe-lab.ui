#!/bin/bash
# Activate the required Python environment and run the API server
# Only reload on API and manager changes, not UI changes
source ~/.venvs/phoebe.api/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir api --reload-dir manager
