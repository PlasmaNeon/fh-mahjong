# Local development helpers.
#
# Client-state redaction is fail-closed (see internal/api/room.go `revealAllHands`):
# opponent hands are hidden unless MAHJONG_DEV_REVEAL_HANDS=1 is explicitly set.
# Production deploys on Zeabur build via the Dockerfile, which sets no such flag,
# so deployed servers always redact. These targets opt the *local* server into
# the all-hands debug god-view; never set this flag in a deployed environment.

.PHONY: dev run

# Run the backend locally with the all-hands debug god-view (see every hand).
dev:
	MAHJONG_DEV_REVEAL_HANDS=1 go run ./cmd/server

# Run the backend locally the way production does: opponent hands redacted.
run:
	go run ./cmd/server
