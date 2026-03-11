package web

import "embed"

// DistFS contains the frontend build output (web/dist/).
// It is embedded at compile time so the binary is self-contained for deploy.
// During local development the server falls back to reading from disk.
//
//go:embed dist/*
var DistFS embed.FS
