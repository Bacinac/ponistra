package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"regexp"
	"sync"
	"time"
)

var named = regexp.MustCompile(`^[1-9][0-9]{0,8}$`)

// A tunnel as the backend asks for it; the id is the backend's, and the SOCKS5 user name that
// chooses it.
type spec struct {
	ID        string         `json:"id"`
	Kind      string         `json:"kind"`
	WireGuard *wireguardSpec `json:"wireguard,omitempty"`
	SoftEther *softetherSpec `json:"softether,omitempty"`
}

func (s spec) valid() error {
	if !named.MatchString(s.ID) {
		return fmt.Errorf("invalid tunnel id %q", s.ID)
	}
	switch {
	case s.Kind == "wireguard" && s.WireGuard != nil:
		return s.WireGuard.valid()
	case s.Kind == "softether" && s.SoftEther != nil:
		return s.SoftEther.valid()
	}
	return fmt.Errorf("tunnel %s: unknown kind %q", s.ID, s.Kind)
}

func (s spec) digest() string {
	written, _ := json.Marshal(s)
	sum := sha256.Sum256(written)
	return hex.EncodeToString(sum[:])
}

// What the backend shows of a tunnel. Error is a code the interface words, detail what the
// other side or the system said.
type status struct {
	State   string `json:"state"`
	Error   string `json:"error,omitempty"`
	Detail  string `json:"detail,omitempty"`
	Address string `json:"address,omitempty"`
}

const (
	connecting = "connecting"
	up         = "up"
	failed     = "failed"
)

type tunnel interface {
	DialContext(ctx context.Context, network, address string) (net.Conn, error)
	Status() status
	Close()
}

// A tunnel that could not start: it says why and reaches nothing.
type broken struct{ status }

func (b broken) DialContext(context.Context, string, string) (net.Conn, error) {
	return nil, errors.New(b.Error + ": " + b.Detail)
}
func (b broken) Status() status { return b.status }
func (b broken) Close()         {}

type starters struct {
	wireguard func(id string, given wireguardSpec) (tunnel, error)
	softether func(id string, given softetherSpec) (tunnel, error)
}

func (s starters) start(given spec) tunnel {
	var (
		made tunnel
		err  error
	)
	if given.Kind == "wireguard" {
		made, err = s.wireguard(given.ID, *given.WireGuard)
	} else {
		made, err = s.softether(given.ID, *given.SoftEther)
	}
	if err != nil {
		var told *refusal
		if errors.As(err, &told) {
			return broken{status{State: failed, Error: told.code, Detail: told.detail}}
		}
		return broken{status{State: failed, Error: "failed", Detail: err.Error()}}
	}
	return made
}

// A failure the interface words by its code.
type refusal struct{ code, detail string }

func (r *refusal) Error() string { return r.code + ": " + r.detail }

func refused(code string, detail string, args ...any) error {
	return &refusal{code, fmt.Sprintf(detail, args...)}
}

type running struct {
	digest string
	tunnel tunnel
}

// Report is what the backend reads: Boot changes as the service starts again, so the backend
// knows to hand it the tunnels anew; Applied is the backend's own digest of what it handed last.
type report struct {
	Boot    string            `json:"boot"`
	Gen     uint64            `json:"gen"`
	Applied string            `json:"applied"`
	Tunnels map[string]status `json:"tunnels"`
}

type hub struct {
	starters starters
	mu       sync.Mutex
	boot     string
	gen      uint64
	applied  string
	changed  chan struct{}
	running  map[string]*running
	seen     map[string]status
}

func newHub(s starters) *hub {
	boot := make([]byte, 8)
	_, _ = rand.Read(boot)
	return &hub{
		starters: s,
		boot:     hex.EncodeToString(boot),
		changed:  make(chan struct{}),
		running:  map[string]*running{},
		seen:     map[string]status{},
	}
}

// The tunnels the backend hands over, all of them each time, under its digest of them.
type handed struct {
	Digest  string `json:"digest"`
	Tunnels []spec `json:"tunnels"`
}

// Apply keeps the tunnels whose spec is unchanged, starts the new and changed ones and closes
// those no longer asked for.
func (h *hub) apply(given handed) {
	h.mu.Lock()
	defer h.mu.Unlock()
	wanted := map[string]bool{}
	for _, each := range given.Tunnels {
		wanted[each.ID] = true
		digest := each.digest()
		if found := h.running[each.ID]; found != nil {
			if found.digest == digest {
				continue
			}
			found.tunnel.Close()
		}
		slog.Info("tunnel: starting", "id", each.ID, "kind", each.Kind)
		h.running[each.ID] = &running{digest, h.starters.start(each)}
	}
	for id, found := range h.running {
		if !wanted[id] {
			slog.Info("tunnel: closing", "id", id)
			found.tunnel.Close()
			delete(h.running, id)
		}
	}
	h.applied = given.Digest
	h.refresh()
}

func (h *hub) find(id string) tunnel {
	h.mu.Lock()
	defer h.mu.Unlock()
	if found := h.running[id]; found != nil {
		return found.tunnel
	}
	return nil
}

// Refresh reads each tunnel's state, waking those waiting where any changed; the caller holds
// the lock.
func (h *hub) refresh() {
	now := make(map[string]status, len(h.running))
	for id, found := range h.running {
		now[id] = found.tunnel.Status()
	}
	same := len(now) == len(h.seen)
	for id, each := range now {
		if h.seen[id] != each {
			same = false
		}
	}
	if same {
		return
	}
	h.seen = now
	h.gen++
	close(h.changed)
	h.changed = make(chan struct{})
}

func (h *hub) watch(ctx context.Context, every time.Duration) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			h.mu.Lock()
			h.refresh()
			h.mu.Unlock()
		}
	}
}

func (h *hub) report() report {
	h.mu.Lock()
	defer h.mu.Unlock()
	tunnels := make(map[string]status, len(h.seen))
	for id, each := range h.seen {
		tunnels[id] = each
	}
	return report{Boot: h.boot, Gen: h.gen, Applied: h.applied, Tunnels: tunnels}
}

// After answers once the tunnels changed since gen, or as ctx ends.
func (h *hub) after(ctx context.Context, gen uint64) report {
	h.mu.Lock()
	current, changed := h.gen, h.changed
	h.mu.Unlock()
	if current == gen {
		select {
		case <-changed:
		case <-ctx.Done():
		}
	}
	return h.report()
}
