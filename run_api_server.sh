#!/bin/bash

uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir api --reload-dir manager
