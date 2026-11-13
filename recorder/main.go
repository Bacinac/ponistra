// The recorder: the backend asks it to record a meeting's room and to stop, and reads back
// what it wrote; a recording that ends on its own, as the room empties or the recorder starts
// again after a crash, is told to the backend at the address it gave.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sync"
	"time"
)

const (
	address = ":8080"
	root    = "/recordings"
)

var (
	named   = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
	running sync.Map
)

type started struct {
	ID       string `json:"id"`
	URL      string `json:"url"`
	Token    string `json:"token"`
	Callback string `json:"callback"`
	Key      string `json:"key"`
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "health" {
		answer, err := http.Get("http://127.0.0.1" + address + "/health")
		if err != nil || answer.StatusCode != http.StatusOK {
			os.Exit(1)
		}
		return
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	recover_()
	http.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	http.HandleFunc("POST /recordings", start)
	http.HandleFunc("POST /recordings/{id}/stop", stop)
	http.HandleFunc("GET /recordings/{id}", manifestOf)
	http.HandleFunc("GET /recordings/{id}/files/{name}", file)
	http.HandleFunc("DELETE /recordings/{id}", remove)
	slog.Info("recorder listening", "address", address)
	if err := http.ListenAndServe(address, nil); err != nil {
		slog.Error("recorder stopped", "error", err)
		os.Exit(1)
	}
}

func reply(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func refuse(w http.ResponseWriter, status int, code string) {
	reply(w, status, map[string]string{"error": code})
}

func start(w http.ResponseWriter, r *http.Request) {
	var asked started
	if err := json.NewDecoder(r.Body).Decode(&asked); err != nil || !named.MatchString(asked.ID) ||
		asked.URL == "" || asked.Token == "" || asked.Callback == "" || asked.Key == "" {
		refuse(w, http.StatusBadRequest, "invalid")
		return
	}
	folder := filepath.Join(root, asked.ID)
	if err := os.Mkdir(folder, 0o700); err != nil {
		refuse(w, http.StatusConflict, "exists")
		return
	}
	if err := writeJSON(filepath.Join(folder, "start.json"), asked); err != nil {
		refuse(w, http.StatusInternalServerError, "unwritable")
		return
	}
	session, err := record(asked, folder, func() {
		running.Delete(asked.ID)
		go tell(asked)
	})
	if err != nil {
		slog.Error("joining the room failed", "id", asked.ID, "error", err)
		_ = os.RemoveAll(folder)
		refuse(w, http.StatusBadGateway, "unjoined")
		return
	}
	running.Store(asked.ID, session)
	reply(w, http.StatusCreated, map[string]string{"id": asked.ID})
}

func stop(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if found, ok := running.LoadAndDelete(id); ok {
		found.(*recording).finish(false)
	}
	manifestOf(w, r)
}

func manifestOf(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if !named.MatchString(id) {
		refuse(w, http.StatusNotFound, "unknown")
		return
	}
	if _, ok := running.Load(id); ok {
		refuse(w, http.StatusConflict, "recording")
		return
	}
	data, err := os.ReadFile(filepath.Join(root, id, "manifest.json"))
	if err != nil {
		refuse(w, http.StatusNotFound, "unknown")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(data)
}

func file(w http.ResponseWriter, r *http.Request) {
	id, name := r.PathValue("id"), r.PathValue("name")
	data, err := os.ReadFile(filepath.Join(root, id, "manifest.json"))
	if !named.MatchString(id) || err != nil {
		refuse(w, http.StatusNotFound, "unknown")
		return
	}
	var kept manifest
	if json.Unmarshal(data, &kept) != nil || !kept.names(name) {
		refuse(w, http.StatusNotFound, "unknown")
		return
	}
	w.Header().Set("Content-Type", "video/webm")
	http.ServeFile(w, r, filepath.Join(root, id, name))
}

func remove(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if !named.MatchString(id) {
		refuse(w, http.StatusNotFound, "unknown")
		return
	}
	if _, ok := running.Load(id); ok {
		refuse(w, http.StatusConflict, "recording")
		return
	}
	if err := os.RemoveAll(filepath.Join(root, id)); err != nil {
		refuse(w, http.StatusInternalServerError, "kept")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// recover_ ends each recording a crash or a restart cut off with what it had written, and
// tells the backend.
func recover_() {
	entries, err := os.ReadDir(root)
	if err != nil {
		slog.Error("the recordings cannot be read", "error", err)
		os.Exit(1)
	}
	for _, entry := range entries {
		folder := filepath.Join(root, entry.Name())
		if _, err := os.Stat(filepath.Join(folder, "manifest.json")); err == nil {
			continue
		}
		var asked started
		data, err := os.ReadFile(filepath.Join(folder, "start.json"))
		if err != nil || json.Unmarshal(data, &asked) != nil {
			continue
		}
		if err := cutOff(folder); err != nil {
			slog.Error("a recording cut off cannot be ended", "id", asked.ID, "error", err)
			continue
		}
		slog.Warn("a recording cut off was ended with what it had", "id", asked.ID)
		go tell(asked)
	}
}

// tell lets the backend know the recording ended, until it answers.
func tell(asked started) {
	body, _ := json.Marshal(map[string]string{"id": asked.ID, "key": asked.Key})
	client := http.Client{Timeout: 10 * time.Second}
	for wait := 5 * time.Second; ; wait = min(wait*2, 5*time.Minute) {
		answer, err := client.Post(asked.Callback, "application/json", bytes.NewReader(body))
		if err == nil {
			answer.Body.Close()
			if answer.StatusCode < 300 {
				return
			}
			if answer.StatusCode == http.StatusNotFound {
				slog.Warn("the backend knows no such recording", "id", asked.ID)
				return
			}
			err = fmt.Errorf("answered %d", answer.StatusCode)
		}
		slog.Warn("telling the backend failed", "id", asked.ID, "error", err)
		time.Sleep(wait)
	}
}

func writeJSON(path string, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	temporary := path + ".part"
	if err := os.WriteFile(temporary, data, 0o600); err != nil {
		return err
	}
	return os.Rename(temporary, path)
}
