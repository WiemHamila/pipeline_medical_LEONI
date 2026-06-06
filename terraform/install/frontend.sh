#!/bin/bash
# Frontend install script — executed by user_data.sh.
# Builds the Vite/React app and serves it via nginx on port 80.
# nginx also reverse-proxies /api/ and /media/ to Gunicorn on :8000.
set -euo pipefail

FRONTEND_ZIP_URL="https://github.com/WiemHamila/pipeline_medical_LEONI/releases/download/v1.0/frontend-service-medical_linux.zip"
INSTALL_DIR="/opt/frontend"
WEB_ROOT="/var/www/medical-frontend"

# ── Download & extract ────────────────────────────────────────────────────
echo "[frontend] Downloading application archive..."
mkdir -p "$INSTALL_DIR"
curl -fL --retry 3 -o /tmp/frontend.zip "$FRONTEND_ZIP_URL"

echo "[frontend] Extracting..."
unzip -o /tmp/frontend.zip -d /tmp/frontend_raw

# Locate package.json (Vite project root)
PACKAGE_JSON=$(find /tmp/frontend_raw -name "package.json" \
  ! -path "*/node_modules/*" | sort | head -1)
if [ -z "$PACKAGE_JSON" ]; then
  echo "[frontend] ERROR: package.json not found in archive"
  exit 1
fi
FRONTEND_ROOT=$(dirname "$PACKAGE_JSON")
echo "[frontend] Frontend root: $FRONTEND_ROOT"
cp -r "$FRONTEND_ROOT"/. "$INSTALL_DIR/"

# ── Vite environment for production build ────────────────────────────────
# The app defaults to '/api' when VITE_API_BASE_URL is unset.
# nginx proxies /api/ → Gunicorn on :8000, so no rebuild is needed to set an IP.
# We deliberately leave VITE_API_BASE_URL unset so the nginx proxy is used.
cd "$INSTALL_DIR"

# Remove any stale node_modules that came bundled inside the zip
rm -rf "$INSTALL_DIR/node_modules"

# ── npm install + build ───────────────────────────────────────────────────
echo "[frontend] Installing npm dependencies..."
npm install --legacy-peer-deps 2>&1 | tail -5

# react-is is an undeclared peer dep of recharts; Vite 8/Rolldown requires it explicitly
npm install react-is --legacy-peer-deps --silent

echo "[frontend] Building production bundle..."
npm run build 2>&1

# Determine the build output directory (Vite defaults to dist/)
if [ -d "$INSTALL_DIR/dist" ] && [ -f "$INSTALL_DIR/dist/index.html" ]; then
  BUILD_DIR="$INSTALL_DIR/dist"
elif [ -d "$INSTALL_DIR/build" ] && [ -f "$INSTALL_DIR/build/index.html" ]; then
  BUILD_DIR="$INSTALL_DIR/build"
else
  echo "[frontend] ERROR: no build output (dist/ or build/) found after npm run build"
  exit 1
fi

echo "[frontend] Build output: $BUILD_DIR"

# ── Deploy to web root ────────────────────────────────────────────────────
mkdir -p "$WEB_ROOT"
cp -r "$BUILD_DIR"/. "$WEB_ROOT/"

# ── Certificat SSL auto-signé ────────────────────────────────────────────
echo "[frontend] Generating self-signed SSL certificate..."
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/medical.key \
  -out    /etc/nginx/ssl/medical.crt \
  -subj "/C=TN/ST=Tunis/O=LEONI/CN=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'medical-app')"
chmod 600 /etc/nginx/ssl/medical.key

# ── nginx configuration ───────────────────────────────────────────────────
echo "[frontend] Configuring nginx..."
cat > /etc/nginx/sites-available/medical-app <<'NGINX_CONF'
# Bloc HTTP : redirection permanente vers HTTPS
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://$host$request_uri;
}

# Bloc HTTPS principal
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/medical.crt;
    ssl_certificate_key /etc/nginx/ssl/medical.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header Strict-Transport-Security "max-age=31536000" always;

    root /var/www/medical-frontend;
    index index.html;

    # React SPA — unknown paths fall back to index.html for client-side routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Reverse-proxy API calls to Gunicorn — keeps the app same-origin (no CORS needed)
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   X-Forwarded-Host  $host;
        proxy_read_timeout 120s;
    }

    # Proxy media files so Django can construct correct absolute URLs
    location /media/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   X-Forwarded-Host  $host;
        proxy_read_timeout 60s;
    }

    # Serve Django-collected static files directly from disk
    location /static/ {
        alias   /opt/backend/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Cache hashed React asset files
    location ~* \.(js|css|woff2?|ttf|eot|svg|png|jpg|jpeg|gif|ico|webp)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    gzip on;
    gzip_comp_level 5;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml text/javascript image/svg+xml;
}
NGINX_CONF

# Enable site, remove default
ln -sf /etc/nginx/sites-available/medical-app /etc/nginx/sites-enabled/medical-app
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl enable nginx
systemctl restart nginx

sleep 2
echo "[frontend] nginx status:"
systemctl status nginx --no-pager || true

# ── Cleanup ───────────────────────────────────────────────────────────────
rm -f /tmp/frontend.zip
rm -rf /tmp/frontend_raw

echo "[frontend] Done — React app served at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo '<ip>')"
