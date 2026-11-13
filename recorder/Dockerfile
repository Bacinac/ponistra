# Records meetings for the backend (S2-5): joins a LiveKit room as a hidden participant and
# writes each participant's sound and picture as they were sent, without decoding them.
FROM golang:1.27.4-trixie@sha256:b54b2639de8c1bfe538ec5ffc45f29b1932235ac5f6d63c059853646677112d9 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN go vet ./... && go test ./...
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /recorder . \
    && mkdir -m 700 /recordings

FROM gcr.io/distroless/static-debian13:nonroot@sha256:25ac8f0c3b2334a9eb05452266bd4697864a8c8ef0ef71e5e6480d7f92868329
COPY --from=build /recorder /recorder
COPY --from=build --chown=nonroot:nonroot /recordings /recordings
EXPOSE 8080
ENTRYPOINT ["/recorder"]
