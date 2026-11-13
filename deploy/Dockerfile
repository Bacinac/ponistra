# The release: the compose files and the ponistra command of one version. Run, it prints the command,
# which installs that version; an installation updating to it takes its files from here.
FROM alpine:3@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
COPY compose.yaml compose.docker.yaml ponistra /release/
CMD ["cat", "/release/ponistra"]
