package main

import (
	"log"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
)

// defaultPolicyServeCmd launches serve_policy.py through uv from the repo root.
// The Go server appends --host/--port (derived from the RL endpoint URL) and,
// when RL_AGENT_CHECKPOINT_ID is set, --checkpoint-id.
const defaultPolicyServeCmd = "uv run --project ai fh-mj-serve-policy"

// rlEndpointURL picks the private-room RL endpoint and reports whether it is the
// local default (the only case eligible for child-process autostart). An
// explicit RL override (RL_AGENT_POLICY_URL) wins, then AI_BOT_POLICY_URL, then
// the local default.
func rlEndpointURL(rlOverride, botPolicyURL string) (endpoint string, isLocalDefault bool) {
	if rlOverride != "" {
		return rlOverride, false
	}
	if botPolicyURL != "" {
		return botPolicyURL, false
	}
	return defaultRLPolicyURL, true
}

// maybeStartPolicyServer launches the Python policy server as a managed child
// process so the private-room RL agent is available without a separate manual
// step. It returns a cleanup func (terminate the child) or nil when nothing was
// started.
//
// It is best-effort and never fatal: if autostart is disabled, the launcher
// binary is missing, or the process fails to start, it logs and returns nil —
// the RL option simply stays disabled, governed by the health check. Callers
// should only invoke this when using the local default endpoint (not when the
// operator pointed AI_BOT_POLICY_URL at their own server).
func maybeStartPolicyServer(rlPolicyURL string) func() {
	if !envBool("RL_AGENT_AUTOSTART", true) {
		log.Printf("RL agent autostart disabled (RL_AGENT_AUTOSTART)")
		return nil
	}

	fields := strings.Fields(getEnv("RL_AGENT_SERVE_CMD", defaultPolicyServeCmd))
	if len(fields) == 0 {
		return nil
	}
	bin := fields[0]
	if _, err := exec.LookPath(bin); err != nil {
		log.Printf("RL agent autostart skipped: %q not on PATH (set RL_AGENT_AUTOSTART=0 to silence)", bin)
		return nil
	}

	host, port := hostPortFromURL(rlPolicyURL)
	args := append([]string{}, fields[1:]...)
	args = append(args, "--host", host, "--port", port)
	if ckpt := strings.TrimSpace(os.Getenv("RL_AGENT_CHECKPOINT_ID")); ckpt != "" {
		args = append(args, "--checkpoint-id", ckpt)
	}

	cmd := exec.Command(bin, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	// Own process group so we can terminate uv and the python grandchild it
	// spawns together.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := cmd.Start(); err != nil {
		log.Printf("RL agent autostart failed to launch %q: %v", bin, err)
		return nil
	}
	log.Printf("RL agent autostart: launched %q (pid %d) for %s; option enables once it is healthy",
		strings.Join(append([]string{bin}, args...), " "), cmd.Process.Pid, rlPolicyURL)

	go func() {
		// Reap the child and surface an early exit (e.g. missing checkpoint).
		if err := cmd.Wait(); err != nil {
			log.Printf("RL agent process exited: %v", err)
		}
	}()

	return func() { terminateProcessGroup(cmd) }
}

// installSignalCleanup terminates the child policy server when the Go server
// receives SIGINT/SIGTERM, so a Ctrl-C doesn't leave an orphaned uv/python.
func installSignalCleanup(cleanup func()) {
	if cleanup == nil {
		return
	}
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigs
		cleanup()
		os.Exit(0)
	}()
}

func terminateProcessGroup(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	// Negative PID signals the whole process group (Setpgid above).
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM); err != nil {
		_ = cmd.Process.Kill()
	}
}

// hostPortFromURL extracts host and port from an /act endpoint URL, falling
// back to the serve_policy.py defaults (127.0.0.1:8765).
func hostPortFromURL(raw string) (host, port string) {
	host, port = "127.0.0.1", "8765"
	u, err := url.Parse(raw)
	if err != nil {
		return host, port
	}
	if h := u.Hostname(); h != "" {
		host = h
	}
	if p := u.Port(); p != "" {
		port = p
	}
	return host, port
}

// envBool reads a boolean-ish env var. Empty/unset returns the fallback;
// "0", "false", "no", "off" (case-insensitive) are false, anything else true.
func envBool(key string, fallback bool) bool {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return fallback
	}
	switch strings.ToLower(v) {
	case "0", "false", "no", "off":
		return false
	default:
		return true
	}
}
