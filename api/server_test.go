package api

import (
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/plasma/fh-mahjong/web"
)

func TestFrontendAssetRouteServesJavaScript(t *testing.T) {
	server := NewServer(nil, NewHub(), nil)

	assetPath, ok := findBuiltAssetPath(".js")
	if !ok {
		t.Skip("no built frontend JS asset present in this checkout")
	}

	req := httptest.NewRequest(http.MethodGet, assetPath, nil)
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

func findBuiltAssetPath(extension string) (string, bool) {
	distDir, ok := locateFrontendDist()
	if ok {
		entries, err := os.ReadDir(filepath.Join(distDir, "assets"))
		if err != nil {
			return "", false
		}

		for _, entry := range entries {
			if strings.HasSuffix(entry.Name(), extension) {
				return "/assets/" + entry.Name(), true
			}
		}
	}

	entries, err := fs.ReadDir(web.DistFS, "dist/assets")
	if err != nil {
		return "", false
	}

	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), extension) {
			return "/assets/" + entry.Name(), true
		}
	}

	return "", false
}
