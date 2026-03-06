# cmd/server/

> Production HTTP server entry point.

## Overview

Bootstraps the full backend: connects to PostgreSQL via GORM, initializes the WebSocket Hub and Matchmaker, registers API routes, and starts the Gin HTTP server on `:8080`.

## Key Files

- **main.go** — Server bootstrap:
  - PostgreSQL connection (configurable via env vars or defaults to localhost:5432)
  - `models.AutoMigrate()` for schema setup
  - `api.Hub`, `api.Matchmaker` initialization
  - Route registration via `api.SetupRouter()`
  - Listens on `:8080`

## Architecture Notes

- This is the main production binary. Run with `go run cmd/server/main.go`.
- Database config defaults: host=localhost, port=5432, user=fh_admin, dbname=fh_mahjong.
- Redis connection is initialized here but not yet fully utilized (Phase 3).
