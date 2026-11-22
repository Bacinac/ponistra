package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/crypto/curve25519"
	"golang.org/x/net/proxy"
	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

type direct struct{ closed atomic.Bool }

func (d *direct) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	return (&net.Dialer{}).DialContext(ctx, network, address)
}
func (d *direct) Status() status { return status{State: up} }
func (d *direct) Close()         { d.closed.Store(true) }

type finders map[string]tunnel

func (f finders) find(id string) tunnel { return f[id] }

func socks(t *testing.T, tunnels finder) string {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	go acceptSocks(listener, tunnels)
	return listener.Addr().String()
}

func served(t *testing.T, listener net.Listener, text string) {
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, text)
	})}
	go server.Serve(listener)
	t.Cleanup(func() { server.Close() })
}

func fetched(t *testing.T, through, user, address string) (string, error) {
	dialer, err := proxy.SOCKS5("tcp", through, &proxy.Auth{User: user, Password: "-"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	client := &http.Client{
		Transport: &http.Transport{Dial: dialer.Dial},
		Timeout:   20 * time.Second,
	}
	answer, err := client.Get("http://" + address + "/")
	if err != nil {
		return "", err
	}
	defer answer.Body.Close()
	read, err := io.ReadAll(answer.Body)
	return string(read), err
}

func TestSocksReachesThroughTheNamedTunnel(t *testing.T) {
	listener, _ := net.Listen("tcp", "127.0.0.1:0")
	served(t, listener, "behind")
	through := socks(t, finders{"7": &direct{}})
	got, err := fetched(t, through, "7", listener.Addr().String())
	if err != nil || got != "behind" {
		t.Fatalf("got %q, %v", got, err)
	}
	if _, err := fetched(t, through, "8", listener.Addr().String()); err == nil {
		t.Fatal("an unknown tunnel let a connection through")
	}
}

func TestSocksWantsAUserName(t *testing.T) {
	through := socks(t, finders{"7": &direct{}})
	dialer, _ := proxy.SOCKS5("tcp", through, nil, nil)
	if _, err := dialer.Dial("tcp", "127.0.0.1:1"); err == nil {
		t.Fatal("a connection without a user name came through")
	}
}

func TestSocksTellsARefusedConnection(t *testing.T) {
	listener, _ := net.Listen("tcp", "127.0.0.1:0")
	closed := listener.Addr().String()
	listener.Close()
	through := socks(t, finders{"7": &direct{}})
	dialer, _ := proxy.SOCKS5("tcp", through, &proxy.Auth{User: "7", Password: "-"}, nil)
	_, err := dialer.Dial("tcp", closed)
	if err == nil || !strings.Contains(err.Error(), "refused") {
		t.Fatalf("got %v", err)
	}
}

func TestHubKeepsRestartsAndCloses(t *testing.T) {
	var made []*direct
	start := func() (tunnel, error) {
		each := &direct{}
		made = append(made, each)
		return each, nil
	}
	tunnels := newHub(starters{
		wireguard: func(string, wireguardSpec) (tunnel, error) { return start() },
		softether: func(string, softetherSpec) (tunnel, error) { return start() },
	})
	one := spec{ID: "1", Kind: "softether", SoftEther: &softetherSpec{Server: "a", Port: 443, Hub: "h", Username: "u", Password: "p"}}
	two := spec{ID: "2", Kind: "softether", SoftEther: &softetherSpec{Server: "b", Port: 443, Hub: "h", Username: "u", Password: "p"}}
	tunnels.apply(handed{Digest: "first", Tunnels: []spec{one, two}})
	if len(made) != 2 || tunnels.report().Applied != "first" {
		t.Fatalf("made %d, applied %q", len(made), tunnels.report().Applied)
	}
	changed := two
	changed.SoftEther = &softetherSpec{Server: "c", Port: 443, Hub: "h", Username: "u", Password: "p"}
	tunnels.apply(handed{Digest: "second", Tunnels: []spec{one, changed}})
	if len(made) != 3 || made[0].closed.Load() || !made[1].closed.Load() {
		t.Fatalf("made %d, closed %v %v", len(made), made[0].closed.Load(), made[1].closed.Load())
	}
	tunnels.apply(handed{Digest: "third", Tunnels: []spec{changed}})
	if !made[0].closed.Load() || tunnels.find("1") != nil || tunnels.find("2") != made[2] {
		t.Fatal("a tunnel no longer asked for stayed")
	}
}

func TestHubTellsAFailedStart(t *testing.T) {
	tunnels := newHub(starters{
		softether: func(string, softetherSpec) (tunnel, error) {
			return nil, refused("no_device", "open /dev/net/tun: operation not permitted")
		},
	})
	tunnels.apply(handed{Tunnels: []spec{{ID: "4", Kind: "softether", SoftEther: &softetherSpec{}}}})
	got := tunnels.report().Tunnels["4"]
	if got.State != failed || got.Error != "no_device" {
		t.Fatalf("got %+v", got)
	}
}

func TestHubWakesTheWaitingOnAChange(t *testing.T) {
	tunnels := newHub(starters{wireguard: func(string, wireguardSpec) (tunnel, error) { return &direct{}, nil }})
	gen := tunnels.report().Gen
	woke := make(chan report)
	go func() { woke <- tunnels.after(context.Background(), gen) }()
	time.Sleep(50 * time.Millisecond)
	tunnels.apply(handed{Tunnels: []spec{{ID: "3", Kind: "wireguard", WireGuard: &wireguardSpec{}}}})
	select {
	case got := <-woke:
		if got.Tunnels["3"].State != up {
			t.Fatalf("got %+v", got)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("the change woke nobody")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if got := tunnels.after(ctx, tunnels.report().Gen); got.Gen != tunnels.report().Gen {
		t.Fatal("an unchanged look did not wait")
	}
}

func TestSpecsRefuseWhatTheyCannotRun(t *testing.T) {
	good := softetherSpec{Server: "vpn.example.com", Port: 443, Hub: "VPN", Username: "ivo", Password: "a b\"c"}
	if err := (spec{ID: "1", Kind: "softether", SoftEther: &good}).valid(); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []spec{
		{ID: "0", Kind: "softether", SoftEther: &good},
		{ID: "x", Kind: "softether", SoftEther: &good},
		{ID: "1", Kind: "softether"},
		{ID: "1", Kind: "other", SoftEther: &good},
		{ID: "1", Kind: "softether", SoftEther: &softetherSpec{Server: "a b", Port: 443, Hub: "h", Username: "u", Password: "p"}},
		{ID: "1", Kind: "softether", SoftEther: &softetherSpec{Server: "a", Port: 0, Hub: "h", Username: "u", Password: "p"}},
		{ID: "1", Kind: "softether", SoftEther: &softetherSpec{Server: "a", Port: 443, Hub: "/HUB:x", Username: "u", Password: "p"}},
		{ID: "1", Kind: "softether", SoftEther: &softetherSpec{Server: "a", Port: 443, Hub: "h", Username: "u", Password: "p\nq"}},
		{ID: "1", Kind: "wireguard", WireGuard: &wireguardSpec{PrivateKey: "short"}},
	} {
		if bad.valid() == nil {
			t.Errorf("%+v passed", bad)
		}
	}
}

func TestConsoleFieldsAreRead(t *testing.T) {
	got := fields("Item,Value\r\nVPN Connection Setting Name,a1\r\n\"Session Status\",\"Connection Completed (Session Established)\"\r\n")
	if got["Session Status"] != "Connection Completed (Session Established)" || got["VPN Connection Setting Name"] != "a1" {
		t.Fatalf("got %v", got)
	}
}

func keys(t *testing.T) (private, public string) {
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		t.Fatal(err)
	}
	secret[0] &= 248
	secret[31] = secret[31]&127 | 64
	shared, err := curve25519.X25519(secret, curve25519.Basepoint)
	if err != nil {
		t.Fatal(err)
	}
	return base64.StdEncoding.EncodeToString(secret), base64.StdEncoding.EncodeToString(shared)
}

func hexed(t *testing.T, given string) string {
	found, err := key(given)
	if err != nil {
		t.Fatal(err)
	}
	return found
}

// A peer standing in for a WireGuard server, on a network stack of its own.
func peer(t *testing.T, private, client string) (endpoint string, stack *netstack.Net) {
	free, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	port := free.LocalAddr().(*net.UDPAddr).Port
	free.Close()
	tun, stack, err := netstack.CreateNetTUN([]netip.Addr{netip.MustParseAddr("10.9.0.1")}, nil, defaultMTU)
	if err != nil {
		t.Fatal(err)
	}
	server := device.NewDevice(tun, conn.NewDefaultBind(), device.NewLogger(device.LogLevelSilent, ""))
	t.Cleanup(server.Close)
	set := fmt.Sprintf("private_key=%s\nlisten_port=%d\npublic_key=%s\nallowed_ip=10.9.0.2/32\n",
		hexed(t, private), port, hexed(t, client))
	if err := server.IpcSet(set); err != nil {
		t.Fatal(err)
	}
	if err := server.Up(); err != nil {
		t.Fatal(err)
	}
	return fmt.Sprintf("localhost:%d", port), stack
}

func TestWireguardReachesThePeersNetwork(t *testing.T) {
	serverPrivate, serverPublic := keys(t)
	clientPrivate, clientPublic := keys(t)
	endpoint, stack := peer(t, serverPrivate, clientPublic)
	listener, err := stack.ListenTCP(&net.TCPAddr{IP: net.IPv4(10, 9, 0, 1), Port: 80})
	if err != nil {
		t.Fatal(err)
	}
	served(t, listener, "far side")
	given := spec{ID: "5", Kind: "wireguard", WireGuard: &wireguardSpec{
		PrivateKey: clientPrivate,
		Addresses:  []string{"10.9.0.2/32"},
		Peers: []wireguardPeer{{
			PublicKey:  serverPublic,
			Endpoint:   endpoint,
			AllowedIPs: []string{"10.9.0.0/24"},
		}},
	}}
	if err := given.valid(); err != nil {
		t.Fatal(err)
	}
	tunnels := newHub(starters{wireguard: startWireguard})
	tunnels.apply(handed{Tunnels: []spec{given}})
	defer tunnels.apply(handed{})
	got, err := fetched(t, socks(t, tunnels), "5", "10.9.0.1:80")
	if err != nil || got != "far side" {
		t.Fatalf("got %q, %v", got, err)
	}
	if state := tunnels.find("5").Status(); state.State != up || state.Address != "10.9.0.2" {
		t.Fatalf("status %+v", state)
	}
	if _, err := fetched(t, socks(t, tunnels), "5", "10.9.0.1:81"); err == nil || !strings.Contains(err.Error(), "refused") {
		t.Fatalf("a closed port behind the peer: %v", err)
	}
}

func TestWireguardTellsAPeerThatDoesNotAnswer(t *testing.T) {
	clientPrivate, _ := keys(t)
	_, serverPublic := keys(t)
	made, err := startWireguard("6", wireguardSpec{
		PrivateKey: clientPrivate,
		Addresses:  []string{"10.9.0.2/32"},
		Peers:      []wireguardPeer{{PublicKey: serverPublic, Endpoint: "127.0.0.1:9", AllowedIPs: []string{"0.0.0.0/0"}}},
	})
	if err != nil {
		t.Fatal(err)
	}
	defer made.Close()
	quiet := made.(*wireguardTunnel)
	quiet.started = time.Now().Add(-time.Minute)
	if got := quiet.Status(); got.State != connecting || got.Error != "no_answer" || got.Detail != "127.0.0.1:9" {
		t.Fatalf("got %+v", got)
	}
}
