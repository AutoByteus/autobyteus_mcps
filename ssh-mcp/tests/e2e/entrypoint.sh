#!/bin/sh
set -eu

mkdir -p /home/mcpuser/.ssh
chown mcpuser:mcpuser /home/mcpuser/.ssh
chmod 700 /home/mcpuser/.ssh

if [ -n "${PUBLIC_KEY:-}" ]; then
  printf '%s\n' "$PUBLIC_KEY" > /home/mcpuser/.ssh/authorized_keys
else
  : > /home/mcpuser/.ssh/authorized_keys
fi
chown mcpuser:mcpuser /home/mcpuser/.ssh/authorized_keys
chmod 600 /home/mcpuser/.ssh/authorized_keys

exec /usr/sbin/sshd -D -e -p 2222
