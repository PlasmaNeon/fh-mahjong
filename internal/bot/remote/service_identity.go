package remote

import (
	"net/url"
	"strings"
)

// SameServiceEndpoint reports whether a and b name the same backing policy
// service, tolerating equivalent spellings rather than requiring
// byte-for-byte string equality (adversarial round 9). It is the single
// shared normalization behind:
//   - cmd/server's resolveAIBotEventWindow (AI_BOT_POLICY_URL vs the
//     resolved RL endpoint), and
//   - internal/api's sameReviewService (POLICY_SERVER_URL, a BASE URL, vs
//     the resolved RL endpoint, which ends in "/act").
//
// A literal string comparison undercounts same-service configs like
// "http://policy:8765" vs "http://policy:8765/act/", or
// "http://Policy:80/act" vs "http://policy/act" — every one of these pairs
// hits the identical server, but a naive == treats them as different
// services, which forces the caller's event window to 0 and makes every
// /act call get rejected by an event-aware server that isn't actually a
// different service at all.
//
// Normalization applied before comparing:
//   - scheme and host are lowercased (URLs are case-insensitive there);
//   - an explicit default port (:80 for http, :443 for https) is treated as
//     equivalent to no port at all;
//   - a trailing "/" is stripped from the path;
//   - a trailing "/act" (and any trailing slash after that) is stripped,
//     mirroring how internal/bot/remote's deriveHealthURL maps an /act
//     endpoint onto its sibling route on the same service.
//
// Either URL failing to parse, or lacking a scheme/host, reports false
// (fail closed) rather than guessing a match.
func SameServiceEndpoint(a, b string) bool {
	na, ok := normalizeServiceEndpoint(a)
	if !ok {
		return false
	}
	nb, ok := normalizeServiceEndpoint(b)
	if !ok {
		return false
	}
	return na == nb
}

// normalizeServiceEndpoint canonicalizes endpoint into a
// "scheme://host/path" identity comparable by SameServiceEndpoint. ok is
// false when endpoint cannot be parsed or lacks a scheme/host.
func normalizeServiceEndpoint(endpoint string) (identity string, ok bool) {
	u, err := url.Parse(endpoint)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return "", false
	}

	scheme := strings.ToLower(u.Scheme)
	host := strings.ToLower(u.Hostname())
	port := u.Port()
	if (scheme == "http" && port == "80") || (scheme == "https" && port == "443") {
		port = ""
	}
	if port != "" {
		host = host + ":" + port
	}

	path := strings.TrimSuffix(u.Path, "/")
	path = strings.TrimSuffix(path, "/act")
	path = strings.TrimSuffix(path, "/")

	return scheme + "://" + host + path, true
}
