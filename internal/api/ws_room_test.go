package api

import "testing"

func TestHubUnbindRoom_RemovesOnlyUsersStillAssignedToRoom(t *testing.T) {
	hub := NewHub()
	closing := NewRoom("closing", nil, nil)
	newer := NewRoom("newer", nil, nil)
	hub.UserRooms[1] = closing
	hub.UserRooms[2] = closing
	hub.UserRooms[3] = newer

	hub.unbindRoom(closing)

	if _, exists := hub.UserRooms[1]; exists {
		t.Fatal("user 1 remained assigned to the closed room")
	}
	if _, exists := hub.UserRooms[2]; exists {
		t.Fatal("user 2 remained assigned to the closed room")
	}
	if got := hub.UserRooms[3]; got != newer {
		t.Fatal("closing an old room disturbed a newer room assignment")
	}
}
