package main

import (
	"encoding/json"

	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testIndex = "<!doctype html><title>Commute</title>"

func testFrontend(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "assets"), 0o755); err != nil {
		t.Fatal(err)
	}
	for name, content := range map[string]string{
		"index.html":    testIndex,
		"assets/app.js": "console.log('commute');",
		"robots.txt":    "User-agent: *",
		"LICENSE":       "test license",
	} {
		if err := os.WriteFile(filepath.Join(dir, filepath.FromSlash(name)), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

func TestAPIRoutes(t *testing.T) {
	// The API must work without a frontend build.
	handler := newHandler(filepath.Join(t.TempDir(), "absent"))
	for _, tc := range []struct {
		method string
		path   string
		status int
		key    string
		value  string
		allow  string
	}{
		{http.MethodGet, "/api/health", 200, "status", "ok", ""},
		{http.MethodGet, "/api/health?probe=1", 200, "status", "ok", ""},
		{http.MethodPost, "/api/health", 405, "error", "method not allowed", "GET"},
		{http.MethodHead, "/api/health", 405, "error", "method not allowed", "GET"},
		{http.MethodOptions, "/api/health", 405, "error", "method not allowed", "GET"},
		{http.MethodGet, "/api", 404, "error", "not found", ""},
		{http.MethodGet, "/api/", 404, "error", "not found", ""},
		{http.MethodGet, "/api/health/", 404, "error", "not found", ""},
		{http.MethodGet, "/api/journeys", 404, "error", "not found", ""},
		{http.MethodPost, "/api/journeys", 404, "error", "not found", ""},
		{http.MethodGet, "/api/../index.html", 404, "error", "not found", ""},
	} {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, httptest.NewRequest(tc.method, tc.path, nil))
			if rr.Code != tc.status {
				t.Fatalf("status = %d, want %d: %s", rr.Code, tc.status, rr.Body.String())
			}
			if got := rr.Header().Get("Content-Type"); got != "application/json" {
				t.Errorf("Content-Type = %q, want application/json", got)
			}
			if got := rr.Header().Get("Allow"); got != tc.allow {
				t.Errorf("Allow = %q, want %q", got, tc.allow)
			}
			var body map[string]string
			if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
				t.Fatal(err)
			}
			if len(body) != 1 || body[tc.key] != tc.value {
				t.Errorf("body = %v, want %s=%s", body, tc.key, tc.value)
			}
		})
	}
}

func TestFrontendRoutes(t *testing.T) {
	handler := newHandler(testFrontend(t))
	for _, tc := range []struct {
		method string
		path   string
		status int
		body   string
		typeOf string
	}{
		{http.MethodGet, "/", 200, testIndex, "text/html"},
		{http.MethodGet, "/index.html", 200, testIndex, "text/html"},
		{http.MethodGet, "/compare/home", 200, testIndex, "text/html"},
		{http.MethodGet, "/compare/home/?mode=map", 200, testIndex, "text/html"},
		{http.MethodGet, "/apiculture", 200, testIndex, "text/html"},
		{http.MethodHead, "/compare/home", 200, "", "text/html"},
		{http.MethodHead, "/", 200, "", "text/html"},
		{http.MethodGet, "/assets/app.js?v=1", 200, "console.log('commute');", "javascript"},
		{http.MethodHead, "/assets/app.js", 200, "", "javascript"},
		{http.MethodGet, "/robots.txt", 200, "User-agent: *", "text/plain"},
		{http.MethodGet, "/LICENSE", 200, "test license", "text/plain"},
		{http.MethodGet, "/assets/missing.js", 404, "", "text/plain"},
		{http.MethodGet, "/assets/missing.js/", 404, "", "text/plain"},
		{http.MethodGet, "/missing.css", 404, "", "text/plain"},
		{http.MethodGet, "/favicon.ico", 404, "", "text/plain"},
		{http.MethodGet, "/assets", 404, "", "text/plain"},
		{http.MethodGet, "/assets/", 404, "", "text/plain"},
		{http.MethodPost, "/compare/home", 405, "", "text/plain"},
		{http.MethodPut, "/assets/app.js", 405, "", "text/plain"},
		{http.MethodOptions, "/", 405, "", "text/plain"},
	} {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, httptest.NewRequest(tc.method, tc.path, nil))
			if rr.Code != tc.status {
				t.Fatalf("status = %d, want %d: %s", rr.Code, tc.status, rr.Body.String())
			}
			if tc.status == http.StatusOK && rr.Body.String() != tc.body {
				t.Errorf("body = %q, want %q", rr.Body.String(), tc.body)
			}
			if got := rr.Header().Get("Content-Type"); !strings.Contains(got, tc.typeOf) {
				t.Errorf("Content-Type = %q, want to contain %q", got, tc.typeOf)
			}
			if tc.status == http.StatusMethodNotAllowed && rr.Header().Get("Allow") != "GET, HEAD" {
				t.Errorf("Allow = %q, want GET, HEAD", rr.Header().Get("Allow"))
			}
		})
	}
}

func TestFrontendUnavailable(t *testing.T) {
	for _, state := range []string{"absent directory", "absent index", "not a directory"} {
		t.Run(state, func(t *testing.T) {
			dir := t.TempDir()
			switch state {
			case "absent directory":
				dir = filepath.Join(dir, "missing")
			case "not a directory":
				dir = filepath.Join(dir, "file")
				if err := os.WriteFile(dir, []byte("not a build"), 0o644); err != nil {
					t.Fatal(err)
				}
			}
			handler := newHandler(dir)
			for _, route := range []string{"/", "/compare/home"} {
				for _, method := range []string{http.MethodGet, http.MethodHead} {
					rr := httptest.NewRecorder()
					handler.ServeHTTP(rr, httptest.NewRequest(method, route, nil))
					if rr.Code != http.StatusServiceUnavailable {
						t.Fatalf("%s %s: status = %d, want 503", method, route, rr.Code)
					}
					if method == http.MethodGet && !strings.Contains(rr.Body.String(), "-static-dir") {
						t.Errorf("missing build instructions: %q", rr.Body.String())
					}
					if method == http.MethodHead && rr.Body.Len() != 0 {
						t.Errorf("HEAD returned a body: %q", rr.Body.String())
					}
				}
			}
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/assets/missing.js", nil))
			if rr.Code != http.StatusNotFound {
				t.Errorf("missing asset status = %d, want 404", rr.Code)
			}
		})
	}
}

func TestStaticTraversal(t *testing.T) {
	parent := t.TempDir()
	dir := filepath.Join(parent, "dist")
	if err := os.Mkdir(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, body := range map[string]string{"secret.txt": "outside secret", "dist/index.html": testIndex} {
		if err := os.WriteFile(filepath.Join(parent, filepath.FromSlash(name)), []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	for name, target := range map[string]string{
		"leak.txt":    filepath.Join(parent, "secret.txt"),
		"leak":        "../secret.txt",
		"outside":     parent,
		"inside.html": "index.html",
	} {
		if err := os.Symlink(target, filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	handler := newHandler(dir)
	for _, route := range []string{
		"/../secret.txt", "/%2e%2e/secret.txt", "/%2E%2E%2Fsecret.txt",
		"/compare/../../secret.txt", "/./index.html", "/compare/%2e%2e/home",
		"/..%5csecret.txt", "/%5c..%5csecret.txt", "/%00secret.txt",
		"//../secret.txt", "/leak.txt", "/leak", "/outside/secret.txt",
		"/outside/nonexistent", "/outside/", "//" + filepath.ToSlash(filepath.Join(parent, "secret.txt")),
	} {
		t.Run(route, func(t *testing.T) {
			for _, method := range []string{http.MethodGet, http.MethodHead} {
				rr := httptest.NewRecorder()
				handler.ServeHTTP(rr, httptest.NewRequest(method, route, nil))
				if rr.Code != http.StatusNotFound {
					t.Errorf("%s: status = %d, want 404; body = %q", method, rr.Code, rr.Body.String())
				}
				if strings.Contains(rr.Body.String(), "outside secret") {
					t.Fatal("exposed a file outside the static directory")
				}
			}
		})
	}
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/inside.html", nil))
	if rr.Code != http.StatusOK || rr.Body.String() != testIndex {
		t.Errorf("safe internal symlink: status = %d, body = %q", rr.Code, rr.Body.String())
	}
}

func TestStaticRange(t *testing.T) {
	handler := newHandler(testFrontend(t))
	req := httptest.NewRequest(http.MethodGet, "/assets/app.js", nil)
	req.Header.Set("Range", "bytes=0-6")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusPartialContent || rr.Body.String() != "console" {
		t.Errorf("range: status = %d, body = %q", rr.Code, rr.Body.String())
	}
}
