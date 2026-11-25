package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

func main() {
	addr := flag.String("addr", ":8080", "HTTP listen address")
	staticDir := flag.String("static-dir", "web/dist", "built frontend directory")
	flag.Parse()

	server := &http.Server{
		Addr:              *addr,
		Handler:           newHandler(*staticDir),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("Graceful shutdown failed: %v", err)
			if err := server.Close(); err != nil {
				log.Printf("Closing server: %v", err)
			}
		}
	}()

	log.Printf("Listening on %s; serving frontend from %s", *addr, *staticDir)
	if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("HTTP server failed: %v", err)
	}
	<-shutdownDone
}

func newHandler(staticDir string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		if r.URL.Path == "/api/health" {
			if r.Method != http.MethodGet {
				w.Header().Set("Allow", http.MethodGet)
				writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
			return
		}
		if r.URL.Path == "/api" || strings.HasPrefix(r.URL.Path, "/api/") {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
			return
		}
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			w.Header().Set("Allow", "GET, HEAD")
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		serveFrontend(w, r, staticDir)
	})
}

func writeJSON(w http.ResponseWriter, status int, body map[string]string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func serveFrontend(w http.ResponseWriter, r *http.Request, staticDir string) {
	// Reject traversal rather than cleaning it into a different, valid route.
	if !strings.HasPrefix(r.URL.Path, "/") || strings.ContainsAny(r.URL.Path, "\\\x00") {
		http.NotFound(w, r)
		return
	}
	for _, part := range strings.Split(r.URL.Path, "/") {
		if part == "." || part == ".." {
			http.NotFound(w, r)
			return
		}
	}

	name := strings.TrimPrefix(r.URL.Path, "/")
	isPage := path.Ext(strings.TrimRight(name, "/")) == ""
	if name == "" {
		name = "index.html"
	}

	// Root prevents both relative traversal and symlinks from escaping staticDir.
	root, err := os.OpenRoot(staticDir)
	if err != nil {
		if isPage {
			frontendUnavailable(w, r)
		} else {
			http.NotFound(w, r)
		}
		return
	}
	defer root.Close()

	file, err := root.Open(filepath.FromSlash(name))
	if errors.Is(err, fs.ErrNotExist) && isPage {
		file, err = root.Open("index.html")
		if errors.Is(err, fs.ErrNotExist) {
			frontendUnavailable(w, r)
			return
		}
	}
	if err != nil {
		// Do not fall back on permission failures or attempts to escape the root.
		http.NotFound(w, r)
		return
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		http.Error(w, "unable to read frontend file", http.StatusInternalServerError)
		return
	}
	if !info.Mode().IsRegular() {
		http.NotFound(w, r)
		return
	}
	http.ServeContent(w, r, info.Name(), info.ModTime(), file)
}

func frontendUnavailable(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusServiceUnavailable)
	if r.Method != http.MethodHead {
		_, _ = w.Write([]byte("Frontend build unavailable. Build the frontend into web/dist, or set -static-dir to its build directory. The API is still available at /api/health.\n"))
	}
}
