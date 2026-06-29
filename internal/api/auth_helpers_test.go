package api

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
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

func TestIssueTokenClaims(t *testing.T) {
	tok, err := issueToken(54321, "Alex", time.Hour)
	if err != nil {
		t.Fatalf("issueToken: %v", err)
	}
	parsed, err := jwt.Parse(tok, func(*jwt.Token) (interface{}, error) { return jwtSecret, nil })
	if err != nil || !parsed.Valid {
		t.Fatalf("parse token: %v", err)
	}
	claims := parsed.Claims.(jwt.MapClaims)
	if uint(claims["sub"].(float64)) != 54321 {
		t.Fatalf("sub = %v, want 54321", claims["sub"])
	}
	if claims["username"].(string) != "Alex" {
		t.Fatalf("username = %v, want Alex", claims["username"])
	}
}
