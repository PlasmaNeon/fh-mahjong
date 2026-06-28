package storage

import "testing"

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
