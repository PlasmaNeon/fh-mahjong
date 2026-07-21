package remote

import "testing"

// TestSameServiceEndpoint pins adversarial round 9's fix: SameServiceEndpoint
// is the ONE shared normalization used by both cmd/server's
// resolveAIBotEventWindow and internal/api's sameReviewService to decide
// whether two configured URLs name the same backing policy service. A bare
// literal string comparison undercounts equivalent spellings of the same
// endpoint (case, default port, trailing slash, /act vs no /act), which
// forces the event window to 0 and makes the server reject every /act call
// even though it's talking to the correct service.
func TestSameServiceEndpoint(t *testing.T) {
	tests := []struct {
		name string
		a    string
		b    string
		want bool
	}{
		{
			name: "identical URLs",
			a:    "http://policy:8765/act",
			b:    "http://policy:8765/act",
			want: true,
		},
		{
			name: "base URL vs /act endpoint, same host",
			a:    "http://policy:8765",
			b:    "http://policy:8765/act",
			want: true,
		},
		{
			name: "trailing slash on base URL",
			a:    "http://policy:8765/",
			b:    "http://policy:8765/act",
			want: true,
		},
		{
			name: "trailing slash on /act endpoint",
			a:    "http://policy:8765",
			b:    "http://policy:8765/act/",
			want: true,
		},
		{
			name: "uppercase host is equivalent",
			a:    "http://POLICY.example/act",
			b:    "http://policy.example/act",
			want: true,
		},
		{
			name: "uppercase scheme is equivalent",
			a:    "HTTP://policy.example/act",
			b:    "http://policy.example/act",
			want: true,
		},
		{
			name: "explicit default http port :80 matches implicit",
			a:    "http://policy.example:80/act",
			b:    "http://policy.example/act",
			want: true,
		},
		{
			name: "explicit default https port :443 matches implicit",
			a:    "https://policy.example:443/act",
			b:    "https://policy.example/act",
			want: true,
		},
		{
			name: "non-default port must still match exactly",
			a:    "http://policy.example:8765/act",
			b:    "http://policy.example:8080/act",
			want: false,
		},
		{
			name: "different host",
			a:    "http://policy-a:8765/act",
			b:    "http://policy-b:8765/act",
			want: false,
		},
		{
			name: "different scheme",
			a:    "http://policy.example/act",
			b:    "https://policy.example/act",
			want: false,
		},
		{
			name: "different path shape",
			a:    "http://policy.example/act",
			b:    "http://policy.example/evaluate",
			want: false,
		},
		{
			name: "unparseable first URL fails closed",
			a:    "http://policy:8765\x7f",
			b:    "http://policy:8765/act",
			want: false,
		},
		{
			name: "unparseable second URL fails closed",
			a:    "http://policy:8765",
			b:    "http://policy:8765/act\x7f",
			want: false,
		},
		{
			name: "empty strings fail closed",
			a:    "",
			b:    "",
			want: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := SameServiceEndpoint(tc.a, tc.b); got != tc.want {
				t.Fatalf("SameServiceEndpoint(%q, %q) = %v, want %v", tc.a, tc.b, got, tc.want)
			}
			// Symmetric by construction (a<->b) — verify the reverse call
			// matches too, since callers pass args in different orders in
			// the two call sites this helper serves.
			if got := SameServiceEndpoint(tc.b, tc.a); got != tc.want {
				t.Fatalf("SameServiceEndpoint(%q, %q) (reversed) = %v, want %v", tc.b, tc.a, got, tc.want)
			}
		})
	}
}
