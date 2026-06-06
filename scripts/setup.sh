#!/bin/bash
# setup.sh — deploiement/mise a jour idempotent de l'application medicale.
# VM_EXISTS=false → nouvelle VM (user_data bootstrap en cours, on attend).
# VM_EXISTS=true  → VM existante, mise a jour complete.
set -euo pipefail
exec > >(tee /var/log/setup.log 2>&1) 2>&1

BACKEND_URL="https://github.com/WiemHamila/pipeline_medical_LEONI/releases/download/v1.0/backend-service-medical_linux.zip"
FRONTEND_URL="https://github.com/WiemHamila/pipeline_medical_LEONI/releases/download/v1.0/frontend-service-medical_linux.zip"
INSTALL_DIR="/opt/backend"
FRONTEND_DIR="/opt/frontend"
WEB_ROOT="/var/www/medical-frontend"
SERVICE_USER="ubuntu"
ELASTIC_IP="${ELASTIC_IP:-$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'localhost')}"
VM_EXISTS="${VM_EXISTS:-false}"

echo "=========================================================="
echo "  Setup Medical App — $(date)"
echo "  Mode : $([ "$VM_EXISTS" = "true" ] && echo 'mise a jour VM existante' || echo 'nouvelle VM')"
echo "  IP   : $ELASTIC_IP"
echo "=========================================================="

# ── Cas 1 : nouvelle VM ───────────────────────────────────────────────────
if [ "$VM_EXISTS" != "true" ]; then
  echo "Nouvelle VM — attente du bootstrap user_data (max 30 min)..."
  for i in $(seq 1 60); do
    if grep -q "Bootstrap complete" /var/log/medical-bootstrap.log 2>/dev/null; then
      echo "Bootstrap complete detecte"; break
    fi
    if systemctl is-active --quiet medical-backend && systemctl is-active --quiet nginx; then
      echo "Services actifs — bootstrap termine"; break
    fi
    [ "$i" -eq 60 ] && echo "WARN: timeout atteint"
    echo "  Attente $i/60 (30s)..." && sleep 30
  done
  systemctl status medical-backend nginx mysql --no-pager || true
  exit 0
fi

# ── Cas 2 : mise a jour VM existante ─────────────────────────────────────
echo ""
echo "=== [1/8] Installation des dependances systeme ==="
apt-get install -y python3-dev libmysqlclient-dev pkg-config build-essential 2>/dev/null | tail -3

echo ""
echo "=== [2/8] Mise a jour du backend ==="

# Arreter tout ce qui tourne sur le port 8000
echo "  Liberation port 8000..."
fuser -k 8000/tcp 2>/dev/null || true
systemctl stop medical-backend 2>/dev/null || true
sleep 2

# Telecharger et extraire
echo "  Telechargement backend..."
curl -fL --retry 3 -o /tmp/backend_new.zip "$BACKEND_URL"
unzip -o /tmp/backend_new.zip -d /tmp/backend_new_raw

MANAGE_PY=$(find /tmp/backend_new_raw -name "manage.py" | sort | head -1)
[ -z "$MANAGE_PY" ] && { echo "ERROR: manage.py introuvable"; exit 1; }
PROJECT_ROOT=$(dirname "$MANAGE_PY")

# Sauvegarder .env
cp "$INSTALL_DIR/.env" /tmp/.env_backup 2>/dev/null || true

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_ROOT"/. "$INSTALL_DIR/"
cp /tmp/.env_backup "$INSTALL_DIR/.env" 2>/dev/null || true

# Mettre a jour l'IP dans .env
if [ -f "$INSTALL_DIR/.env" ]; then
  sed -i "s/ALLOWED_HOSTS=.*/ALLOWED_HOSTS=localhost,127.0.0.1,$ELASTIC_IP/" "$INSTALL_DIR/.env"
  sed -i "s|CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=https://$ELASTIC_IP|" "$INSTALL_DIR/.env"
fi

echo ""
echo "=== [3/8] Recreation du venv Python ==="
# Supprimer l'ancien venv (y compris celui du zip) et en creer un propre
rm -rf "$INSTALL_DIR/venv"
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q
deactivate
echo "  Venv recrée et dependances installees"

# Patch STATIC_ROOT si absent
grep -q "STATIC_ROOT" "$INSTALL_DIR/medical_platform/settings.py" || \
  printf '\nSTATIC_ROOT = BASE_DIR / '"'"'staticfiles'"'"'\n' >> "$INSTALL_DIR/medical_platform/settings.py"

mkdir -p "$INSTALL_DIR/media"

echo ""
echo "=== [4/8] Migrations Django ==="
cd "$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/python" manage.py migrate --noinput
"$INSTALL_DIR/venv/bin/python" manage.py migrate --database=im_db --noinput 2>/dev/null || \
  echo "  WARN: im_db migration skipped"
"$INSTALL_DIR/venv/bin/python" manage.py collectstatic --noinput 2>/dev/null || true

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo ""
echo "=== [5/8] Correctifs noms de fichiers (case-sensitive Linux) ==="
# Telecharger et extraire le frontend pour les corrections
curl -fL --retry 3 -o /tmp/frontend_new.zip "$FRONTEND_URL"
unzip -o /tmp/frontend_new.zip -d /tmp/frontend_new_raw

PACKAGE_JSON=$(find /tmp/frontend_new_raw -name "package.json" ! -path "*/node_modules/*" | sort | head -1)
[ -z "$PACKAGE_JSON" ] && { echo "ERROR: package.json introuvable"; exit 1; }
FRONTEND_ROOT=$(dirname "$PACKAGE_JSON")

rm -rf "$FRONTEND_DIR"
mkdir -p "$FRONTEND_DIR"
cp -r "$FRONTEND_ROOT"/. "$FRONTEND_DIR/"

# Corriger les noms de fichiers avec mauvaise casse
COMPONENTS_DIR="$FRONTEND_DIR/src/components"
if [ -f "$COMPONENTS_DIR/medecinTraitant/Fileattente.jsx" ]; then
  mv "$COMPONENTS_DIR/medecinTraitant/Fileattente.jsx" \
     "$COMPONENTS_DIR/medecinTraitant/FileAttente.jsx"
  echo "  Renomme: Fileattente.jsx → FileAttente.jsx"
fi
if [ -f "$COMPONENTS_DIR/medecinTravail/Searchcollaborateur.jsx" ]; then
  mv "$COMPONENTS_DIR/medecinTravail/Searchcollaborateur.jsx" \
     "$COMPONENTS_DIR/medecinTravail/SearchCollaborateur.jsx"
  echo "  Renomme: Searchcollaborateur.jsx → SearchCollaborateur.jsx"
fi

echo ""
echo "=== [6/8] Mise a jour vite.config.js ==="
cat > "$FRONTEND_DIR/vite.config.js" << 'VITE_CONF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  define: {
    global: {},
  },
  resolve: {
    alias: {
      stream: fileURLToPath(new URL('./src/shims/stream-browser-empty.js', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
VITE_CONF
echo "  vite.config.js mis a jour (host: 0.0.0.0, port: 5173)"

echo ""
echo "=== [7/8] Build frontend ==="
cd "$FRONTEND_DIR"

# Supprimer node_modules du zip (mauvaise version de vite)
rm -rf node_modules

echo "  npm install..."
npm install --legacy-peer-deps --no-progress --no-audit --no-fund 2>&1 | tail -5

# react-is : dependance implicite de recharts, requise par Vite 8/Rolldown
npm install react-is --legacy-peer-deps --silent --no-progress

echo "  npm run build..."
npm run build 2>&1 | tail -10

BUILD_DIR=""
[ -d "$FRONTEND_DIR/dist"  ] && [ -f "$FRONTEND_DIR/dist/index.html"  ] && BUILD_DIR="$FRONTEND_DIR/dist"
[ -d "$FRONTEND_DIR/build" ] && [ -f "$FRONTEND_DIR/build/index.html" ] && BUILD_DIR="$FRONTEND_DIR/build"
[ -z "$BUILD_DIR" ] && { echo "ERROR: pas de dossier dist/ ou build/"; exit 1; }

echo "  Build OK : $BUILD_DIR"
rm -rf "$WEB_ROOT"
mkdir -p "$WEB_ROOT"
cp -r "$BUILD_DIR"/. "$WEB_ROOT/"

echo ""
echo "=== [8/8] Configuration nginx ==="
# Certificat SSL auto-signe
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/medical.key \
  -out    /etc/nginx/ssl/medical.crt \
  -subj "/C=TN/ST=Tunis/O=LEONI/CN=$ELASTIC_IP" 2>/dev/null
chmod 600 /etc/nginx/ssl/medical.key

cat > /etc/nginx/sites-available/medical-app << 'NGINX_CONF'
# HTTP -> HTTPS redirect
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS principal
server {
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/medical.crt;
    ssl_certificate_key /etc/nginx/ssl/medical.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    add_header Strict-Transport-Security "max-age=31536000" always;

    root /var/www/medical-frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

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

    location /media/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 60s;
    }

    location /static/ {
        alias   /opt/backend/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/javascript;
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/medical-app /etc/nginx/sites-enabled/medical-app
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

# Nettoyage
rm -f /tmp/backend_new.zip /tmp/frontend_new.zip
rm -rf /tmp/backend_new_raw /tmp/frontend_new_raw

echo ""
echo "=========================================================="
echo "  Setup termine — $(date)"
echo "  Backend pret sur :8000 (sera lance par Job 4)"
echo "  Frontend servi par nginx sur :80"
echo "=========================================================="