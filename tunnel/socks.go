package main

import (
	"context"
	"encoding/binary"
	"errors"
	"io"
	"log/slog"
	"net"
	"strconv"
	"syscall"
	"time"
)

// SOCKS5 (RFC 1928) with user name and password (RFC 1929): the user name is the tunnel's id,
// the password is not asked for, as only the backend reaches the port. CONNECT alone.
const (
	socksVersion   = 5
	authVersion    = 1
	methodPassword = 2
	methodNone     = 0xff
	commandConnect = 1
	kindIPv4       = 1
	kindName       = 3
	kindIPv6       = 4

	replyOK          = 0
	replyFailure     = 1
	replyNetwork     = 3
	replyHost        = 4
	replyRefused     = 5
	replyCommand     = 7
	replyAddressKind = 8

	handshake = 10 * time.Second
	dialing   = 20 * time.Second
)

type finder interface{ find(id string) tunnel }

func serveSocks(address string, tunnels finder) error {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return err
	}
	return acceptSocks(listener, tunnels)
}

func acceptSocks(listener net.Listener, tunnels finder) error {
	for {
		client, err := listener.Accept()
		if err != nil {
			return err
		}
		go func() {
			defer client.Close()
			if err := relay(client, tunnels); err != nil && !errors.Is(err, io.EOF) {
				slog.Debug("tunnel: SOCKS5 connection ended", "error", err)
			}
		}()
	}
}

func relay(client net.Conn, tunnels finder) error {
	_ = client.SetDeadline(time.Now().Add(handshake))
	through, err := authenticated(client, tunnels)
	if err != nil {
		return err
	}
	target, err := requested(client)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), dialing)
	defer cancel()
	remote, err := through.DialContext(ctx, "tcp", target)
	if err != nil {
		_ = reply(client, replyFor(err))
		return err
	}
	defer remote.Close()
	if err := reply(client, replyOK); err != nil {
		return err
	}
	_ = client.SetDeadline(time.Time{})
	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(remote, client); closeWrite(remote); done <- struct{}{} }()
	go func() { _, _ = io.Copy(client, remote); closeWrite(client); done <- struct{}{} }()
	<-done
	<-done
	return nil
}

func closeWrite(conn net.Conn) {
	if half, ok := conn.(interface{ CloseWrite() error }); ok {
		_ = half.CloseWrite()
	} else {
		_ = conn.Close()
	}
}

func authenticated(client net.Conn, tunnels finder) (tunnel, error) {
	head := make([]byte, 2)
	if _, err := io.ReadFull(client, head); err != nil {
		return nil, err
	}
	if head[0] != socksVersion {
		return nil, errors.New("not SOCKS5")
	}
	methods := make([]byte, head[1])
	if _, err := io.ReadFull(client, methods); err != nil {
		return nil, err
	}
	offered := false
	for _, each := range methods {
		offered = offered || each == methodPassword
	}
	if !offered {
		_, _ = client.Write([]byte{socksVersion, methodNone})
		return nil, errors.New("no user name offered")
	}
	if _, err := client.Write([]byte{socksVersion, methodPassword}); err != nil {
		return nil, err
	}
	if _, err := io.ReadFull(client, head[:1]); err != nil {
		return nil, err
	}
	if head[0] != authVersion {
		return nil, errors.New("unknown authentication version")
	}
	user, err := counted(client)
	if err != nil {
		return nil, err
	}
	if _, err := counted(client); err != nil {
		return nil, err
	}
	found := tunnels.find(string(user))
	if found == nil {
		_, _ = client.Write([]byte{authVersion, 1})
		return nil, errors.New("no tunnel " + strconv.Quote(string(user)))
	}
	_, err = client.Write([]byte{authVersion, 0})
	return found, err
}

func counted(client net.Conn) ([]byte, error) {
	length := make([]byte, 1)
	if _, err := io.ReadFull(client, length); err != nil {
		return nil, err
	}
	read := make([]byte, length[0])
	_, err := io.ReadFull(client, read)
	return read, err
}

func requested(client net.Conn) (string, error) {
	head := make([]byte, 4)
	if _, err := io.ReadFull(client, head); err != nil {
		return "", err
	}
	if head[0] != socksVersion {
		return "", errors.New("not SOCKS5")
	}
	if head[1] != commandConnect {
		_ = reply(client, replyCommand)
		return "", errors.New("only CONNECT")
	}
	var host string
	switch head[3] {
	case kindIPv4, kindIPv6:
		size := net.IPv4len
		if head[3] == kindIPv6 {
			size = net.IPv6len
		}
		address := make([]byte, size)
		if _, err := io.ReadFull(client, address); err != nil {
			return "", err
		}
		host = net.IP(address).String()
	case kindName:
		name, err := counted(client)
		if err != nil {
			return "", err
		}
		host = string(name)
	default:
		_ = reply(client, replyAddressKind)
		return "", errors.New("unknown address kind")
	}
	port := make([]byte, 2)
	if _, err := io.ReadFull(client, port); err != nil {
		return "", err
	}
	return net.JoinHostPort(host, strconv.Itoa(int(binary.BigEndian.Uint16(port)))), nil
}

func reply(client net.Conn, code byte) error {
	_, err := client.Write([]byte{socksVersion, code, 0, kindIPv4, 0, 0, 0, 0, 0, 0})
	return err
}

func replyFor(err error) byte {
	switch {
	case errors.Is(err, syscall.ECONNREFUSED):
		return replyRefused
	case errors.Is(err, syscall.ENETUNREACH):
		return replyNetwork
	case errors.Is(err, syscall.EHOSTUNREACH), errors.Is(err, syscall.ETIMEDOUT),
		errors.Is(err, context.DeadlineExceeded):
		return replyHost
	}
	var dns *net.DNSError
	if errors.As(err, &dns) {
		return replyHost
	}
	return replyFailure
}
