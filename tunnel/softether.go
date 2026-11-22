package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/netip"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/insomniacslk/dhcp/dhcpv4"
	"github.com/insomniacslk/dhcp/dhcpv4/nclient4"
	"github.com/vishvananda/netlink"
	"golang.org/x/sys/unix"
)

// A SoftEther tunnel is an account of SoftEther's own client, whose virtual adapter the client
// makes in the kernel; the tunnel takes its address by DHCP from the far side and keeps its
// routes in a table of its own, which only connections marked with its number reach. The main
// table never learns the far network, so its addresses meet neither the container's networks
// nor another tunnel's.
type softetherSpec struct {
	Server   string `json:"server"`
	Port     int    `json:"port"`
	Hub      string `json:"hub"`
	Username string `json:"username"`
	Password string `json:"password"`
}

const (
	softetherHome = "/opt/softether"
	softetherRun  = "/run/softether"
	// Marks and route tables of the tunnels start here, clear of the kernel's own (253-255).
	firstTable = 1000
	rulePlace  = 100
	looked     = 2 * time.Second
	asked      = 15 * time.Second
)

var plain = func(given string) bool {
	return given != "" && !strings.ContainsAny(given, " \t\r\n\"/:")
}

func (s softetherSpec) valid() error {
	if !plain(s.Server) && net.ParseIP(s.Server) == nil {
		return fmt.Errorf("invalid server %q", s.Server)
	}
	if s.Port < 1 || s.Port > 65535 {
		return fmt.Errorf("invalid port %d", s.Port)
	}
	if !plain(s.Hub) || !plain(s.Username) {
		return fmt.Errorf("invalid hub or user name")
	}
	if s.Password == "" || strings.ContainsAny(s.Password, "\r\n") {
		return fmt.Errorf("invalid password")
	}
	return nil
}

// The one SoftEther client of the container, started as the first SoftEther tunnel asks for it.
type softetherClient struct {
	mu      sync.Mutex
	running bool
}

var client softetherClient

func (c *softetherClient) ensure() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.running {
		return nil
	}
	if err := tunDevice(); err != nil {
		return err
	}
	if err := os.MkdirAll(softetherRun+"/log", 0o700); err != nil {
		return err
	}
	process := exec.Command(softetherHome+"/vpnclient", "execsvc")
	process.Dir = softetherRun
	if err := process.Start(); err != nil {
		return err
	}
	c.running = true
	go func() {
		err := process.Wait()
		slog.Error("tunnel: the SoftEther client ended", "error", err)
		c.mu.Lock()
		c.running = false
		c.mu.Unlock()
	}()
	deadline := time.Now().Add(asked)
	for {
		if _, err := vpncmd("", "VersionGet"); err == nil {
			return nil
		} else if time.Now().After(deadline) {
			return fmt.Errorf("the SoftEther client does not answer: %w", err)
		}
		time.Sleep(200 * time.Millisecond)
	}
}

// TunDevice makes /dev/net/tun where the container was not given it; whether the host lets the
// container open it is the host's to say (docs/INSTALL.md).
func tunDevice() error {
	const path = "/dev/net/tun"
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		if err := os.MkdirAll("/dev/net", 0o755); err != nil {
			return refused("no_device", "%v", err)
		}
		if err := unix.Mknod(path, unix.S_IFCHR|0o666, int(unix.Mkdev(10, 200))); err != nil {
			return refused("no_device", "%v", err)
		}
	}
	opened, err := os.OpenFile(path, os.O_RDWR, 0)
	if err != nil {
		return refused("no_device", "%v", err)
	}
	return opened.Close()
}

// Vpncmd runs one command of SoftEther's console against the local client, input its answers
// to what the command asks, as a password is asked rather than given in its arguments.
func vpncmd(input string, command ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), asked)
	defer cancel()
	args := append([]string{"localhost", "/CLIENT", "/CSV", "/CMD"}, command...)
	run := exec.CommandContext(ctx, softetherHome+"/vpncmd", args...)
	run.Dir = softetherRun
	run.Stdin = strings.NewReader(input)
	out, err := run.CombinedOutput()
	if err != nil {
		return string(out), fmt.Errorf("%s: %s", command[0], consoleError(string(out), err))
	}
	return string(out), nil
}

// ConsoleError is the line of the console's output that tells what went wrong.
func consoleError(out string, err error) string {
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "Error occurred") || strings.Contains(line, "Error code") {
			return line
		}
	}
	return err.Error()
}

// Fields reads the console's CSV of items and values.
func fields(out string) map[string]string {
	found := map[string]string{}
	for _, line := range strings.Split(out, "\n") {
		item, value, ok := strings.Cut(strings.TrimSpace(line), ",")
		if ok {
			found[strings.Trim(item, `"`)] = strings.Trim(value, `"`)
		}
	}
	return found
}

type softetherTunnel struct {
	id      string
	spec    softetherSpec
	nic     string
	account string
	link    string
	mark    int
	cancel  context.CancelFunc
	done    chan struct{}

	mu      sync.Mutex
	status  status
	dhcp    *nclient4.Client
	lease   *nclient4.Lease
	leased  time.Time
	servers []netip.Addr
}

func startSoftether(id string, given softetherSpec) (tunnel, error) {
	number, _ := strconv.Atoi(id)
	ctx, cancel := context.WithCancel(context.Background())
	made := &softetherTunnel{
		id:      id,
		spec:    given,
		nic:     "p" + id,
		account: "a" + id,
		link:    "vpn_p" + id,
		mark:    firstTable + number,
		cancel:  cancel,
		done:    make(chan struct{}),
		status:  status{State: connecting},
	}
	go made.run(ctx)
	return made, nil
}

func (s *softetherTunnel) set(state status) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.status = state
}

func (s *softetherTunnel) Status() status {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.status
}

func (s *softetherTunnel) fail(err error) {
	var told *refusal
	if errors.As(err, &told) {
		s.set(status{State: failed, Error: told.code, Detail: told.detail})
	} else {
		s.set(status{State: failed, Error: "failed", Detail: err.Error()})
	}
}

func (s *softetherTunnel) run(ctx context.Context) {
	defer close(s.done)
	for {
		err := s.connect()
		if err == nil {
			break
		}
		slog.Warn("tunnel: SoftEther account not set up", "id", s.id, "error", err)
		s.fail(err)
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Minute):
		}
	}
	ticker := time.NewTicker(looked)
	defer ticker.Stop()
	for {
		s.look()
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (s *softetherTunnel) connect() error {
	if err := client.ensure(); err != nil {
		return err
	}
	s.remove()
	if _, err := vpncmd("", "NicCreate", s.nic); err != nil {
		return err
	}
	server := net.JoinHostPort(s.spec.Server, strconv.Itoa(s.spec.Port))
	if _, err := vpncmd("", "AccountCreate", s.account, "/SERVER:"+server, "/HUB:"+s.spec.Hub,
		"/USERNAME:"+s.spec.Username, "/NICNAME:"+s.nic); err != nil {
		return err
	}
	password := s.spec.Password + "\n" + s.spec.Password + "\n"
	if _, err := vpncmd(password, "AccountPasswordSet", s.account, "/TYPE:standard"); err != nil {
		return err
	}
	if _, err := vpncmd("", "AccountRetrySet", s.account, "/NUM:999", "/INTERVAL:15"); err != nil {
		return err
	}
	_, err := vpncmd("", "AccountConnect", s.account)
	return err
}

// Remove takes the account and its adapter out of the client, as a tunnel changed or closed
// leaves them.
func (s *softetherTunnel) remove() {
	_, _ = vpncmd("", "AccountDisconnect", s.account)
	_, _ = vpncmd("", "AccountDelete", s.account)
	_, _ = vpncmd("", "NicDelete", s.nic)
}

// Look reads the account's session: an established one gets its address and routes, one that
// fell away loses them until it is back.
func (s *softetherTunnel) look() {
	out, err := vpncmd("", "AccountStatusGet", s.account)
	session := fields(out)["Session Status"]
	established := err == nil && strings.Contains(session, "Established")
	if !established {
		s.unconfigure()
		detail := session
		if err != nil {
			detail = err.Error()
		}
		code, cause := s.cause()
		if cause != "" {
			detail = cause
		}
		s.set(status{State: connecting, Error: code, Detail: detail})
		return
	}
	if err := s.configure(); err != nil {
		slog.Warn("tunnel: SoftEther address not taken", "id", s.id, "error", err)
		s.unconfigure()
		s.fail(err)
		return
	}
	s.mu.Lock()
	address := s.lease.ACK.YourIPAddr.String()
	s.mu.Unlock()
	s.set(status{State: up, Address: address})
}

var causes = regexp.MustCompile(`VPN Connection Setting "([^"]+)": .*Cause: (.*) \(code (\d+)\)`)

// Cause is why the account's last connection failed, as the client's log tells it: the code
// the interface words and the client's own words.
func (s *softetherTunnel) cause() (string, string) {
	logs, _ := filepath.Glob(softetherRun + "/log/client_log/*.log")
	if len(logs) == 0 {
		return "", ""
	}
	sort.Strings(logs)
	written, err := os.ReadFile(logs[len(logs)-1])
	if err != nil {
		return "", ""
	}
	var code, cause string
	for _, found := range causes.FindAllStringSubmatch(string(written), -1) {
		if found[1] == s.account {
			code, cause = found[3], found[2]
		}
	}
	switch code {
	case "":
		return "", ""
	case "7", "9", "12":
		return "refused", cause
	case "8":
		return "no_hub", cause
	case "1", "2", "3", "13":
		return "no_answer", cause
	}
	return "failed", cause
}

func (s *softetherTunnel) configure() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.lease != nil {
		renewAt := s.lease.ACK.IPAddressLeaseTime(time.Hour) / 2
		if time.Since(s.leased) < renewAt {
			return nil
		}
		renewed, err := s.dhcp.Renew(context.Background(), s.lease)
		if err == nil && renewed.ACK.YourIPAddr.Equal(s.lease.ACK.YourIPAddr) {
			s.lease, s.leased = renewed, time.Now()
			return nil
		}
		s.dropped()
	}
	link, err := netlink.LinkByName(s.link)
	if err != nil {
		return refused("dhcp", "%s: %v", s.link, err)
	}
	if err := netlink.LinkSetUp(link); err != nil {
		return err
	}
	if s.dhcp == nil {
		s.dhcp, err = nclient4.New(s.link, nclient4.WithTimeout(5*time.Second), nclient4.WithRetry(3))
		if err != nil {
			return refused("dhcp", "%v", err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), asked)
	defer cancel()
	lease, err := s.dhcp.Request(ctx)
	if err != nil {
		return refused("dhcp", "%v", err)
	}
	if err := s.routed(link, lease.ACK); err != nil {
		return err
	}
	s.lease, s.leased = lease, time.Now()
	s.servers = nil
	for _, each := range lease.ACK.DNS() {
		if found, ok := netip.AddrFromSlice(each.To4()); ok {
			s.servers = append(s.servers, found)
		}
	}
	slog.Info("tunnel: SoftEther address taken", "id", s.id, "address", lease.ACK.YourIPAddr)
	return nil
}

// Routed gives the adapter its address without the main table's route to its network, and the
// tunnel's own table that network and the far side's router as its way to everything else.
func (s *softetherTunnel) routed(link netlink.Link, ack *dhcpv4.DHCPv4) error {
	mask := ack.SubnetMask()
	if mask == nil {
		mask = net.CIDRMask(24, 32)
	}
	own := &net.IPNet{IP: ack.YourIPAddr.To4(), Mask: mask}
	network := &net.IPNet{IP: own.IP.Mask(mask), Mask: mask}
	address := &netlink.Addr{IPNet: own, Flags: unix.IFA_F_NOPREFIXROUTE}
	if err := netlink.AddrReplace(link, address); err != nil {
		return err
	}
	index := link.Attrs().Index
	routes := []*netlink.Route{{
		LinkIndex: index, Dst: network, Src: own.IP, Table: s.mark, Scope: netlink.SCOPE_LINK,
	}}
	if routers := ack.Router(); len(routers) > 0 {
		routes = append(routes, &netlink.Route{
			LinkIndex: index, Gw: routers[0], Src: own.IP, Table: s.mark,
		})
	}
	for _, route := range routes {
		if err := netlink.RouteReplace(route); err != nil {
			return err
		}
	}
	rule := netlink.NewRule()
	rule.Mark, rule.Table, rule.Priority = uint32(s.mark), s.mark, rulePlace
	if err := netlink.RuleAdd(rule); err != nil && !errors.Is(err, syscall.EEXIST) {
		return err
	}
	return nil
}

// Dropped forgets the lease and what it set; the caller holds the lock.
func (s *softetherTunnel) dropped() {
	if s.lease == nil {
		return
	}
	if link, err := netlink.LinkByName(s.link); err == nil {
		addresses, _ := netlink.AddrList(link, netlink.FAMILY_V4)
		for _, each := range addresses {
			_ = netlink.AddrDel(link, &each)
		}
	}
	routes, _ := netlink.RouteListFiltered(netlink.FAMILY_V4,
		&netlink.Route{Table: s.mark}, netlink.RT_FILTER_TABLE)
	for _, each := range routes {
		_ = netlink.RouteDel(&each)
	}
	rule := netlink.NewRule()
	rule.Mark, rule.Table, rule.Priority = uint32(s.mark), s.mark, rulePlace
	_ = netlink.RuleDel(rule)
	s.lease, s.servers = nil, nil
}

func (s *softetherTunnel) unconfigure() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.dropped()
	if s.dhcp != nil {
		_ = s.dhcp.Close()
		s.dhcp = nil
	}
}

func (s *softetherTunnel) marked(_, _ string, raw syscall.RawConn) error {
	var failure error
	err := raw.Control(func(fd uintptr) {
		failure = unix.SetsockoptInt(int(fd), unix.SOL_SOCKET, unix.SO_MARK, s.mark)
	})
	if err != nil {
		return err
	}
	return failure
}

func (s *softetherTunnel) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	s.mu.Lock()
	if s.lease == nil {
		s.mu.Unlock()
		return nil, syscall.ENETUNREACH
	}
	servers := s.servers
	s.mu.Unlock()
	dialer := &net.Dialer{Control: s.marked}
	if len(servers) > 0 {
		dialer.Resolver = &net.Resolver{
			PreferGo: true,
			Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
				asking := &net.Dialer{Control: s.marked}
				return asking.DialContext(ctx, network, netip.AddrPortFrom(servers[0], 53).String())
			},
		}
	}
	return dialer.DialContext(ctx, network, address)
}

func (s *softetherTunnel) Close() {
	s.cancel()
	<-s.done
	s.unconfigure()
	s.remove()
}
