package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFrontendAssetRouteServesJavaScript(t *testing.T) {
	server := NewServer(nil, NewHub(), nil)

	req := httptest.NewRequest(http.MethodGet, "/assets/index-CFV0k2ai.js", nil)
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200 for built JS asset, got %d", recorder.Code)
	}
	if strings.Contains(recorder.Body.String(), "<!DOCTYPE html>") {
		t.Fatalf("expected JS asset response, got HTML fallback")
	}
	contentType := recorder.Header().Get("Content-Type")
	if !strings.Contains(contentType, "javascript") {
		t.Fatalf("expected javascript content type, got %q", contentType)
	}
}

func TestFrontendMissingAssetDoesNotReturnSPAHTML(t *testing.T) {
	server := NewServer(nil, NewHub(), nil)

	req := httptest.NewRequest(http.MethodGet, "/assets/does-not-exist.js", nil)
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)

	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for missing asset, got %d", recorder.Code)
	}
	if strings.Contains(recorder.Body.String(), "<!DOCTYPE html>") {
		t.Fatalf("missing asset should not return index.html")
	}
}
