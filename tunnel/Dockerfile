# The VPN tunnels (D54): WireGuard in user space and SoftEther's client, offered to the backend
# as one SOCKS5 port.
FROM golang:1.27.4-trixie@sha256:b54b2639de8c1bfe538ec5ffc45f29b1932235ac5f6d63c059853646677112d9 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN go vet ./... && go test ./...
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /tunnel .

# SoftEther VPN (Apache 2.0) from its source, its console against BSD libedit rather than GNU
# readline; with OpenSSL 3.5 it leaves liboqs out by itself.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS softether
ARG SOFTETHER=5.2.5190
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git cmake make gcc g++ pkgconf \
       libssl-dev libsodium-dev zlib1g-dev libncurses-dev libeditreadline-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "$SOFTETHER" https://github.com/SoftEtherVPN/SoftEtherVPN.git /softether \
    && cd /softether \
    && git submodule update --init --depth 1 src/libhamcore src/Mayaqua/3rdparty/cpu_features \
       3rdparty/tinydir 3rdparty/BLAKE2
WORKDIR /softether/build
RUN cmake .. -DCMAKE_BUILD_TYPE=Release -DSE_PIDDIR=/run/softether -DSE_DBDIR=/run/softether \
       -DSE_LOGDIR=/run/softether/log \
    && make -j"$(nproc)" vpnclient vpncmd vpnserver hamcore-archive-build \
    && mkdir /opt/softether \
    && cp vpnclient vpncmd hamcore.se2 libcedar.so libmayaqua.so /opt/softether/

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libssl3t64 libsodium23 zlib1g \
       libedit2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=softether /opt/softether /opt/softether
COPY --from=build /tunnel /tunnel
ENV LD_LIBRARY_PATH=/opt/softether
EXPOSE 8090 1080
ENTRYPOINT ["/tunnel"]
