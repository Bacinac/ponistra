package main

import (
	"bufio"
	"context"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"log/slog"
	"net"
	"net/netip"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

// A WireGuard tunnel runs in user space over gVisor's network stack: no device, no route and no
// capability in the container, and two tunnels into networks of the same addresses never meet.
type wireguardSpec struct {
	PrivateKey string          `json:"private_key"`
	Addresses  []string        `json:"addresses"`
	DNS        []string        `json:"dns"`
	MTU        int             `json:"mtu"`
	Peers      []wireguardPeer `json:"peers"`
}

type wireguardPeer struct {
	PublicKey    string   `json:"public_key"`
	PresharedKey string   `json:"preshared_key"`
	Endpoint     string   `json:"endpoint"`
	AllowedIPs   []string `json:"allowed_ips"`
	Keepalive    int      `json:"keepalive"`
}

const (
	// A peer that has not shaken hands for this long no longer answers: WireGuard renews its
	// keys every two minutes while packets flow, and the keepalive keeps them flowing.
	answering = 3 * time.Minute
	// A tunnel that never shook hands is told as not answering after this.
	unanswered = 30 * time.Second
	keepalive  = 25
	defaultMTU = 1420
)

func (s wireguardSpec) valid() error {
	if _, err := key(s.PrivateKey); err != nil {
		return fmt.Errorf("private key: %w", err)
	}
	if len(s.Addresses) == 0 {
		return fmt.Errorf("no address")
	}
	for _, each := range s.Addresses {
		if _, err := netip.ParsePrefix(each); err != nil {
			return err
		}
	}
	for _, each := range s.DNS {
		if _, err := netip.ParseAddr(each); err != nil {
			return err
		}
	}
	if len(s.Peers) == 0 {
		return fmt.Errorf("no peer")
	}
	for _, peer := range s.Peers {
		if _, err := key(peer.PublicKey); err != nil {
			return fmt.Errorf("public key: %w", err)
		}
		if peer.PresharedKey != "" {
			if _, err := key(peer.PresharedKey); err != nil {
				return fmt.Errorf("preshared key: %w", err)
			}
		}
		if _, _, err := net.SplitHostPort(peer.Endpoint); err != nil {
			return fmt.Errorf("endpoint: %w", err)
		}
		for _, each := range peer.AllowedIPs {
			if _, err := netip.ParsePrefix(each); err != nil {
				return err
			}
		}
	}
	return nil
}

func key(given string) (string, error) {
	raw, err := base64.StdEncoding.DecodeString(given)
	if err != nil || len(raw) != 32 {
		return "", fmt.Errorf("not a WireGuard key")
	}
	return hex.EncodeToString(raw), nil
}

type wireguardTunnel struct {
	id      string
	spec    wireguardSpec
	device  *device.Device
	net     *netstack.Net
	started time.Time
	// The peers' endpoints as last resolved.
	endpoints []string
	mu        sync.Mutex
	renewed   time.Time
}

func startWireguard(id string, given wireguardSpec) (tunnel, error) {
	var addresses, servers []netip.Addr
	for _, each := range given.Addresses {
		addresses = append(addresses, netip.MustParsePrefix(each).Addr())
	}
	for _, each := range given.DNS {
		servers = append(servers, netip.MustParseAddr(each))
	}
	mtu := given.MTU
	if mtu == 0 {
		mtu = defaultMTU
	}
	tun, stack, err := netstack.CreateNetTUN(addresses, servers, mtu)
	if err != nil {
		return nil, err
	}
	logger := &device.Logger{
		Verbosef: device.DiscardLogf,
		Errorf: func(format string, args ...any) {
			slog.Warn("tunnel: wireguard", "id", id, "message", fmt.Sprintf(format, args...))
		},
	}
	made := &wireguardTunnel{
		id:      id,
		spec:    given,
		device:  device.NewDevice(tun, conn.NewDefaultBind(), logger),
		net:     stack,
		started: time.Now(),
	}
	set, err := made.configuration()
	if err != nil {
		made.device.Close()
		return nil, err
	}
	if err := made.device.IpcSet(set); err != nil {
		made.device.Close()
		return nil, refused("invalid", "%v", err)
	}
	if err := made.device.Up(); err != nil {
		made.device.Close()
		return nil, err
	}
	return made, nil
}

// Configuration is the device's UAPI text, each peer's endpoint resolved now.
func (w *wireguardTunnel) configuration() (string, error) {
	var b strings.Builder
	w.endpoints = make([]string, len(w.spec.Peers))
	private, _ := key(w.spec.PrivateKey)
	fmt.Fprintf(&b, "private_key=%s\nreplace_peers=true\n", private)
	for i, peer := range w.spec.Peers {
		public, _ := key(peer.PublicKey)
		endpoint, err := resolved(peer.Endpoint)
		if err != nil {
			return "", refused("resolve", "%s: %v", peer.Endpoint, err)
		}
		w.endpoints[i] = endpoint
		fmt.Fprintf(&b, "public_key=%s\nendpoint=%s\n", public, endpoint)
		if peer.PresharedKey != "" {
			shared, _ := key(peer.PresharedKey)
			fmt.Fprintf(&b, "preshared_key=%s\n", shared)
		}
		every := peer.Keepalive
		if every == 0 {
			every = keepalive
		}
		fmt.Fprintf(&b, "persistent_keepalive_interval=%d\nreplace_allowed_ips=true\n", every)
		for _, each := range peer.AllowedIPs {
			fmt.Fprintf(&b, "allowed_ip=%s\n", each)
		}
	}
	return b.String(), nil
}

func resolved(endpoint string) (string, error) {
	host, port, _ := net.SplitHostPort(endpoint)
	if ip, err := netip.ParseAddr(host); err == nil {
		return netip.AddrPortFrom(ip, mustPort(port)).String(), nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	found, err := net.DefaultResolver.LookupNetIP(ctx, "ip", host)
	if err != nil {
		return "", err
	}
	chosen := found[0]
	for _, each := range found {
		if each.Unmap().Is4() {
			chosen = each.Unmap()
			break
		}
	}
	return netip.AddrPortFrom(chosen, mustPort(port)).String(), nil
}

func mustPort(given string) uint16 {
	port, _ := strconv.ParseUint(given, 10, 16)
	return uint16(port)
}

func (w *wireguardTunnel) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	made, err := w.net.DialContext(ctx, network, address)
	if err != nil {
		return nil, netstackError(err)
	}
	return made, nil
}

// gVisor's adapter hands a dial's failure on as its text alone, so what it means is read back
// from that text for the SOCKS reply.
var netstackErrors = map[string]syscall.Errno{
	"connection was refused": syscall.ECONNREFUSED,
	"network is unreachable": syscall.ENETUNREACH,
	"no route to host":       syscall.EHOSTUNREACH,
	"operation timed out":    syscall.ETIMEDOUT,
}

func netstackError(err error) error {
	for text, errno := range netstackErrors {
		if strings.HasSuffix(err.Error(), text) {
			return fmt.Errorf("%w: %w", errno, err)
		}
	}
	return err
}

// Handshake is the latest handshake with any peer, zero before the first.
func (w *wireguardTunnel) handshake() time.Time {
	got, err := w.device.IpcGet()
	if err != nil {
		return time.Time{}
	}
	var latest int64
	lines := bufio.NewScanner(strings.NewReader(got))
	for lines.Scan() {
		if value, found := strings.CutPrefix(lines.Text(), "last_handshake_time_sec="); found {
			if seconds, _ := strconv.ParseInt(value, 10, 64); seconds > latest {
				latest = seconds
			}
		}
	}
	if latest == 0 {
		return time.Time{}
	}
	return time.Unix(latest, 0)
}

func (w *wireguardTunnel) Status() status {
	address := netip.MustParsePrefix(w.spec.Addresses[0]).Addr().String()
	shook := w.handshake()
	if !shook.IsZero() && time.Since(shook) < answering {
		return status{State: up, Address: address}
	}
	if shook.IsZero() && time.Since(w.started) < unanswered {
		return status{State: connecting, Address: address}
	}
	w.renew()
	endpoints := make([]string, len(w.spec.Peers))
	for i, peer := range w.spec.Peers {
		endpoints[i] = peer.Endpoint
	}
	return status{
		State:   connecting,
		Error:   "no_answer",
		Detail:  strings.Join(endpoints, ", "),
		Address: address,
	}
}

// Renew resolves the peers' endpoints named by a host again, at most once a minute, as a peer
// behind a dynamic address moves; a peer whose address is unchanged is left as it is.
func (w *wireguardTunnel) renew() {
	if !w.mu.TryLock() {
		return
	}
	defer w.mu.Unlock()
	if time.Since(w.renewed) < time.Minute {
		return
	}
	w.renewed = time.Now()
	for i, peer := range w.spec.Peers {
		host, _, _ := net.SplitHostPort(peer.Endpoint)
		if _, err := netip.ParseAddr(host); err == nil {
			continue
		}
		endpoint, err := resolved(peer.Endpoint)
		if err != nil || endpoint == w.endpoints[i] {
			continue
		}
		public, _ := key(peer.PublicKey)
		set := fmt.Sprintf("public_key=%s\nupdate_only=true\nendpoint=%s\n", public, endpoint)
		if err := w.device.IpcSet(set); err != nil {
			slog.Warn("tunnel: wireguard endpoint not renewed", "id", w.id, "error", err)
			continue
		}
		slog.Info("tunnel: wireguard endpoint moved", "id", w.id, "endpoint", endpoint)
		w.endpoints[i] = endpoint
	}
}

func (w *wireguardTunnel) Close() { w.device.Close() }
