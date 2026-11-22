# The SFTP server the backend's tests and the browser's sign in to (D54): OpenSSH, its account
# `sftp` with the password `sftpsftp`, a key it is given in its own ~/.ssh/authorized_keys, and
# forwarding on for a jump through itself.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/sh sftp \
    && echo 'sftp:sftpsftp' | chpasswd \
    && install -d -o sftp -g sftp /home/sftp/files \
    && mkdir -p /run/sshd \
    && ssh-keygen -A
COPY sshd.conf /etc/ssh/sshd_config.d/test.conf
CMD ["/usr/sbin/sshd", "-D", "-e"]
