# internal/review/reviewtest/

> The shared `/evaluate` policy-server stub for `internal/api` and `internal/review` tests.

A normal (non-`_test`) package because `_test.go` helpers cannot be imported across packages.
Extend this stub instead of writing another `httptest` server; the remaining bespoke stubs (fixed
probability vectors, a sha that changes between chunks) stay separate on purpose.
