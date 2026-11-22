// The tunnel: the backend hands it the installation's VPN tunnels, WireGuard and SoftEther, and
// reaches what stands behind each through one SOCKS5 port, naming the tunnel as the user name.
// The backend itself never gets a route into another network, nor the right to make one.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"
)

const (
	control = ":8090"
	proxied = ":1080"
	// How long the backend's look at the tunnels waits for one of them to change.
	waited = 25 * time.Second
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "health" {
		answer, err := http.Get("http://127.0.0.1" + control + "/health")
		if err != nil || answer.StatusCode != http.StatusOK {
			os.Exit(1)
		}
		return
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))
	tunnels := newHub(starters{wireguard: startWireguard, softether: startSoftether})
	go tunnels.watch(context.Background(), 2*time.Second)
	go func() {
		if err := serveSocks(proxied, tunnels); err != nil {
			slog.Error("tunnel: SOCKS5 stopped", "error", err)
			os.Exit(1)
		}
	}()
	slog.Info("tunnel listening", "control", control, "socks", proxied)
	if err := http.ListenAndServe(control, routes(tunnels)); err != nil {
		slog.Error("tunnel stopped", "error", err)
		os.Exit(1)
	}
}

func routes(tunnels *hub) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("PUT /tunnels", func(w http.ResponseWriter, r *http.Request) {
		var given handed
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&given); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		for _, each := range given.Tunnels {
			if err := each.valid(); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
		}
		tunnels.apply(given)
		answer(w, tunnels.report())
	})
	mux.HandleFunc("GET /tunnels", func(w http.ResponseWriter, r *http.Request) {
		given := r.URL.Query().Get("after")
		if given == "" {
			answer(w, tunnels.report())
			return
		}
		after, _ := strconv.ParseUint(given, 10, 64)
		ctx, cancel := context.WithTimeout(r.Context(), waited)
		defer cancel()
		answer(w, tunnels.after(ctx, after))
	})
	return mux
}

func answer(w http.ResponseWriter, body any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(body)
}
