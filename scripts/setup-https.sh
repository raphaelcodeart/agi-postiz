#!/usr/bin/env bash
# One-time setup: obtains the FIRST real Let's Encrypt HTTPS certificate for
# the platform's three nginx vhosts, using a sslip.io hostname so no owned
# domain is required (sslip.io is a public DNS service: <ip-with-dashes>.sslip.io
# resolves to that IP - see docs/DEPLOYMENT.md section 9).
#
# For RENEWAL, don't re-run this script: once a certificate exists, the final
# nginx config (already committed) answers the ACME HTTP-01 challenge on its
# own, so renewal is just `docker compose -f docker-compose.prod.yml run --rm
# certbot renew` followed by an nginx reload - see the cron example in
# docs/DEPLOYMENT.md section 9. This script's bootstrap/swap dance is only
# needed when no certificate exists yet (nginx can't start with the final
# config's ssl_certificate directives pointing at nonexistent files).
#
# Usage (from the repository root, on the server):
#   ./scripts/setup-https.sh <ip-with-dashes>.sslip.io you@email.com
# Example:
#   ./scripts/setup-https.sh 162-55-187-18.sslip.io novarese.michele@gmail.com
#
# Requires infrastructure/nginx/nginx.conf to already reference the same
# hostnames passed here (app./api./media. + this domain) - regenerate it if
# you point this at a different server/domain.
set -euo pipefail

cd "$(dirname "$0")/.."

DOMAIN_BASE="${1:?Usage: ./scripts/setup-https.sh <ip-with-dashes>.sslip.io you@email.com}"
EMAIL="${2:?Provide an email for Lets Encrypt expiry notices}"
COMPOSE_FILE="docker-compose.prod.yml"

APP_DOMAIN="app.${DOMAIN_BASE}"
API_DOMAIN="api.${DOMAIN_BASE}"
MEDIA_DOMAIN="media.${DOMAIN_BASE}"

NGINX_CONF="infrastructure/nginx/nginx.conf"
FINAL_CONF="$(mktemp)"
trap 'rm -f "$FINAL_CONF"' EXIT

cp "$NGINX_CONF" "$FINAL_CONF"  # the committed, final HTTPS config - restored at the end

echo "==> Writing a temporary HTTP-only bootstrap nginx config (needed until the first certificate exists)"
cat > "$NGINX_CONF" <<EOF
user  nginx;
worker_processes  auto;
events { worker_connections 1024; }
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile on;

    server {
        listen 80;
        server_name ${APP_DOMAIN} ${API_DOMAIN} ${MEDIA_DOMAIN} localhost;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            proxy_pass http://dashboard:3000;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
        }
    }
}
EOF

echo "==> Starting backend services and bootstrap nginx"
docker compose -f "$COMPOSE_FILE" up -d db redis api dashboard nginx

echo "==> Requesting certificate from Let's Encrypt for: ${APP_DOMAIN} ${API_DOMAIN} ${MEDIA_DOMAIN}"
docker compose -f "$COMPOSE_FILE" run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$APP_DOMAIN" -d "$API_DOMAIN" -d "$MEDIA_DOMAIN" \
  --email "$EMAIL" --agree-tos --non-interactive --keep-until-expiring

echo "==> Restoring the final HTTPS nginx config and reloading"
cp "$FINAL_CONF" "$NGINX_CONF"
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload

echo "==> Done."
echo "    Dashboard: https://${APP_DOMAIN}"
echo "    API:       https://${API_DOMAIN}"
echo "    Media:     https://${MEDIA_DOMAIN}"
