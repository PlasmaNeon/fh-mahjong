package api

// ServerCommit is stamped at build time via
//
//	go build -ldflags "-X github.com/plasma/fh-mahjong/internal/api.ServerCommit=$(git rev-parse --short HEAD)"
//
// and recorded into every paipu (v2 provenance). "unknown" means the binary
// was built without the stamp (local `go run`, tests).
var ServerCommit = "unknown"
