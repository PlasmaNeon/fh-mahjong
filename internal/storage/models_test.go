package storage

import "testing"

func TestNormalizeUsernameFriendlyNames(t *testing.T) {
	tests := []struct {
		input       string
		wantDisplay string
		wantKey     string
	}{
		{"  Rain   Player  ", "Rain Player", "rain player"},
		{"雨夜_Club-2", "雨夜_Club-2", "雨夜_club-2"},
		{"River@Home!!!", "River-at-Home", "river-at-home"},
	}
	for _, tc := range tests {
		display, key := NormalizeUsername(tc.input)
		if display != tc.wantDisplay || key != tc.wantKey {
			t.Fatalf("NormalizeUsername(%q) = (%q, %q), want (%q, %q)", tc.input, display, key, tc.wantDisplay, tc.wantKey)
		}
	}
}

func TestGenerateUserIDInRange(t *testing.T) {
	for i := 0; i < 2000; i++ {
		id, err := generateUserID()
		if err != nil {
			t.Fatalf("generateUserID error: %v", err)
		}
		if id < 10000 || id > 99999 {
			t.Fatalf("id %d out of range [10000,99999]", id)
		}
	}
}

func TestBeforeCreateAssignsIDWhenZero(t *testing.T) {
	u := &User{}
	if err := u.BeforeCreate(nil); err != nil {
		t.Fatalf("BeforeCreate error: %v", err)
	}
	if u.ID < 10000 || u.ID > 99999 {
		t.Fatalf("expected assigned id in range, got %d", u.ID)
	}
}

func TestBeforeCreatePreservesExistingID(t *testing.T) {
	u := &User{ID: 12345}
	if err := u.BeforeCreate(nil); err != nil {
		t.Fatalf("BeforeCreate error: %v", err)
	}
	if u.ID != 12345 {
		t.Fatalf("expected id preserved, got %d", u.ID)
	}
}
