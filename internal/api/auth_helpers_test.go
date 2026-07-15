package api

import (
	"testing"
)

func TestNormalizeEmail(t *testing.T) {
	cases := map[string]string{
		"  Foo@X.com ": "foo@x.com",
		"BAR@Y.IO":     "bar@y.io",
		"baz@z.net":    "baz@z.net",
	}
	for in, want := range cases {
		if got := normalizeEmail(in); got != want {
			t.Fatalf("normalizeEmail(%q) = %q, want %q", in, got, want)
		}
	}
}
