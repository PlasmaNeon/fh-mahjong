package api

import "sync"

// InMemoryQueue is a mutex-guarded in-process FIFO queue keyed by name, used by
// the matchmaker to hold players waiting for a table.
//
// It was once backed by Redis; that dependency was removed in PR #129 (it was
// never actually wired up) and matchmaking is in-process by design while the
// server is single-process. A Redis-backed implementation would only be needed
// if the server ever ran multi-instance.

type InMemoryQueue struct {
	mu    sync.Mutex
	lists map[string][]string
}

func NewInMemoryQueue() *InMemoryQueue {
	return &InMemoryQueue{
		lists: make(map[string][]string),
	}
}

func (q *InMemoryQueue) Push(key string, val string) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.lists[key] = append(q.lists[key], val)
}

// PushUnique appends val only when it is not already waiting in the queue.
// The membership check and append share one lock so duplicate join requests
// cannot create duplicate seats.
func (q *InMemoryQueue) PushUnique(key string, val string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()

	for _, queued := range q.lists[key] {
		if queued == val {
			return false
		}
	}
	q.lists[key] = append(q.lists[key], val)
	return true
}

// Remove deletes every occurrence of val from key and reports whether the
// player was still waiting. A false result means the queue watcher may already
// have claimed the player for a match.
func (q *InMemoryQueue) Remove(key string, val string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()

	list := q.lists[key]
	kept := list[:0]
	removed := false
	for _, queued := range list {
		if queued == val {
			removed = true
			continue
		}
		kept = append(kept, queued)
	}
	q.lists[key] = kept
	return removed
}

func (q *InMemoryQueue) Items(key string) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	// Return a copy to avoid race conditions
	if lst, ok := q.lists[key]; ok {
		copied := make([]string, len(lst))
		copy(copied, lst)
		return copied
	}
	return nil
}

func (q *InMemoryQueue) Len(key string) int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.lists[key])
}

func (q *InMemoryQueue) PopN(key string, count int) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	lst, ok := q.lists[key]
	if !ok || len(lst) < count {
		return nil
	}

	popped := lst[:count]
	q.lists[key] = lst[count:]

	return popped
}

func (q *InMemoryQueue) Keys(pattern string) []string {
	q.mu.Lock()
	defer q.mu.Unlock()

	var prefix string
	if len(pattern) > 2 && pattern[len(pattern)-2:] == ":*" {
		prefix = pattern[:len(pattern)-1]
	}

	var matched []string
	for k := range q.lists {
		if prefix == "" || (len(k) >= len(prefix) && k[:len(prefix)] == prefix) {
			matched = append(matched, k)
		}
	}
	return matched
}
