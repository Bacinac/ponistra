#!/bin/sh
set -e
grep -q '^Include /etc/ssh/sshd_config.d/' /etc/ssh/sshd_config \
    || echo 'Include /etc/ssh/sshd_config.d/*.conf' >> /etc/ssh/sshd_config
/usr/sbin/sshd -e
(
    until docker info >/dev/null 2>&1; do sleep 0.5; done
    tar -C /rootfs -c . | docker import --change 'CMD ["sh"]' - ponistra/test:1 >/dev/null
) &
exec dockerd-entrypoint.sh dockerd --group docker
