package remote

import (
	"fmt"
	"path"
)

// checkpointIdentity renders a public-safe checkpoint label. Paipu (and the
// replay API serving it) are public, so only the checkpoint file's base name
// is kept — never the server's filesystem path, and never an endpoint URL
// (which could carry internal hostnames or credentials).
func checkpointIdentity(checkpointPath string, step int64) string {
	return fmt.Sprintf("%s@step%d", path.Base(checkpointPath), step)
}
