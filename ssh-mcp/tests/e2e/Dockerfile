FROM alpine:3.20

RUN apk add --no-cache openssh \
    && adduser -D -s /bin/sh mcpuser \
    && echo 'mcpuser:dockerpass' | chpasswd \
    && mkdir -p /home/mcpuser/.ssh /run/sshd \
    && chown -R mcpuser:mcpuser /home/mcpuser/.ssh \
    && chmod 700 /home/mcpuser/.ssh \
    && ssh-keygen -A \
    && printf '%s\n' \
       'PermitRootLogin no' \
       'PasswordAuthentication yes' \
       'KbdInteractiveAuthentication yes' \
       'PubkeyAuthentication yes' \
       'AuthorizedKeysFile .ssh/authorized_keys' \
       'AllowUsers mcpuser' \
       >> /etc/ssh/sshd_config

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 2222

CMD ["/entrypoint.sh"]
