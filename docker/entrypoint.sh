#!/bin/sh
# Docker entrypoint for Ada backend.
#
# Responsibilities:
#   1. Ensure the data directory exists and is writable (in case the named
#      volume was just created and the path doesn't exist yet).
#   2. Exec the Python module so signals (SIGTERM) are forwarded correctly
#      to uvicorn, enabling graceful shutdown.
#
# Using `exec` replaces this shell process with Python, making Python PID 1.
# This is important for Docker signal handling — without exec, SIGTERM from
# `docker stop` would be caught by the shell, not uvicorn.
set -e

mkdir -p /app/data

exec python -m ada.main
