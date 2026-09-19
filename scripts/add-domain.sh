#!/usr/bin/env bash
# Adds a real (owned) domain as an additional HTTPS vhost for the dashboard,
# alongside the sslip.io hostnames created by scripts/setup-https.sh.
#
# Unlike setup-https.sh, this does NOT need a bootstrap dance: nginx is already
# running with a working config that answers the ACME HTTP-01 challenge on port
# 80 for any hostname listed in its first server block. So the order here is:
# issue the certificate first, then append the 443 vhost that references it -
# appending it first would make every nginx reload fail (ssl_certificate
# pointing at a file that does not exist yet).
#
# The new domain is served as an alias of the dashboard, exactly like the
# provider rDNS hostname already in nginx.conf: api.* and media.* keep their own
# sslip.io hostnames, and the dashboard reaches the backend through its
# same-origin BFF proxy, so one hostname is enough for the whole app.
#
# Prerequisite: an A record for <domain> pointing at this server's public IP,
# already propagated. The script refuses to run otherwise, because a failed
# ACME validation counts against Let's Encrypt rate limits.
#
# Usage (from the repository root, on the server):
#   ./scripts/add-domain.sh agipostapp.mamify.ai novarese.michele@gmail.com
set -euo pipefail

cd "$(dirname "$0")/.."

DOMAIN="${1:?Usage: ./scripts/add-domain.sh <domain> you@email.com}"
EMAIL="${2:?Provide an email for Lets Encrypt expiry notices}"
COMPOSE_FILE="docker-compose.prod.yml"
NGINX_CONF="infrastructure/nginx/nginx.conf"

SERVER_IP="$(curl -fsS -4 ifconfig.me)"
RESOLVED="$(dig +short A "$DOMAIN" @1.1.1.1 | tail -n1)"

echo "==> Checking DNS: ${DOMAIN} -> ${RESOLVED:-<nothing>} (this server: ${SERVER_IP})"
if [ "$RESOLVED" != "$SERVER_IP" ]; then
  echo "ERROR: ${DOMAIN} does not resolve to ${SERVER_IP} yet." >&2
  echo "Create an A record ${DOMAIN} -> ${SERVER_IP} and wait for it to propagate." >&2
  exit 1
fi

if ! grep -q "server_name .*${DOMAIN}" "$NGINX_CONF"; then
  echo "ERROR: ${DOMAIN} is not listed in the port 80 server block of ${NGINX_CONF}," >&2
  echo "so nginx would not answer the ACME challenge for it. Add it there first." >&2
  exit 1
fi

echo "==> Requesting certificate from Let's Encrypt for: ${DOMAIN}"
docker compose -f "$COMPOSE_FILE" run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$EMAIL" --agree-tos --non-interactive --keep-until-expiring

if grep -q "server_name ${DOMAIN};" "$NGINX_CONF"; then
  echo "==> HTTPS vhost for ${DOMAIN} already present, skipping"
else
  echo "==> Appending the HTTPS vhost for ${DOMAIN}"
  # Insert before the final closing brace of the http {} block.
  python3 - "$NGINX_CONF" "$DOMAIN" <<'PY'
import sys
path, domain = sys.argv[1], sys.argv[2]
conf = open(path).read()
block = f"""
    # Owned domain, served as an alias of the dashboard vhost above (see the
    # provider rDNS hostname block for the same pattern). Added by
    # scripts/add-domain.sh.
    server {{
        listen 443 ssl;
        server_name {domain};

        ssl_certificate     /etc/letsencrypt/live/{domain}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

        client_max_body_size 500M;

        location / {{
            proxy_pass http://dashboard:3000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";

            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
        }}
    }}
}}
"""
assert conf.rstrip().endswith("}"), "unexpected nginx.conf tail"
conf = conf.rstrip()[:-1].rstrip("\n") + "\n" + block
open(path, "w").write(conf)
PY
fi

echo "==> Validating and reloading nginx"
docker compose -f "$COMPOSE_FILE" exec nginx nginx -t
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload

echo "==> Done: https://${DOMAIN}"
