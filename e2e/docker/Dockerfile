# The Docker host the backend's tests and the browser's reach (D55): Docker in Docker beside
# OpenSSH, the account `dock` (password `dockdock`, in the group docker) taking the forced command
# the installation shows in its own ~/.ssh/authorized_keys. No registry is reached, so the image
# its stacks run, ponistra/test:1, is made from busybox's files as the daemon starts.
FROM busybox:1.37-musl@sha256:f6a95d611e0a8780fabdb2aec43e31275b2720dfefa3e41b16835bfc42454478 AS rootfs
FROM docker:29.10-dind@sha256:4bbc7223f81db790097c6dea42fb93e05b8fead4f0431fbe6ccaba6e8473201c
RUN apk add --no-cache openssh-server \
    && (getent group docker || addgroup -S docker) \
    && adduser -D -s /bin/sh dock \
    && addgroup dock docker \
    && echo 'dock:dockdock' | chpasswd \
    && install -d -m 700 -o dock -g dock /home/dock/.ssh /home/dock/stacks \
    && ssh-keygen -A
COPY --from=rootfs / /rootfs/
COPY sshd.conf /etc/ssh/sshd_config.d/test.conf
COPY start.sh /start.sh
ENV DOCKER_TLS_CERTDIR=""
HEALTHCHECK --interval=2s --start-period=180s CMD docker image inspect ponistra/test:1 >/dev/null
ENTRYPOINT ["/start.sh"]
