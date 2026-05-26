#!/bin/bash
# deploy_app.sh — Déploiement complet de la plateforme médicale LEONI
# Appelé via SSH depuis GitHub Actions après provisioning Terraform.
# Idempotent : peut être relancé sans casse sur une VM existante.
set -euo pipefail
exec > >(tee /var/log/deploy_app.log 2>&1) 2>&1

# ── Credentials (GitHub Secrets injectés depuis le runner) ────────────────
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-Leoni2024!}"
DB_APP_PASSWORD="${DB_APP_PASSWORD:-Medical2024!}"
DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-SqPLwZuUTSlW_PfetPuBCHGf8bUHgKqb1HF3FJs5Um4}"
SERVER_IP="${SERVER_IP:-$(curl -s --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || hostname -I | awk '{print $1}')}"

# ── Chemins ────────────────────────────────────────────────────────────────
BACKEND_DIR="/opt/backend"
FRONTEND_DIR="/opt/frontend"
WEB_ROOT="/var/www/medical-frontend"
SQL_DIR="/tmp/sql_dumps"
DB_MAIN="medical_db"
DB_IM="im_db"
DB_USER="medical_user"

echo "=========================================================="
echo "  Deploy Medical LEONI — $(date)"
echo "  IP serveur : $SERVER_IP"
echo "=========================================================="

# ── [1/8] Répertoires ─────────────────────────────────────────────────────
echo ""
echo "=== [1/8] Préparation des répertoires ==="
mkdir -p "$BACKEND_DIR" "$FRONTEND_DIR" "$WEB_ROOT"
chown -R ubuntu:ubuntu "$BACKEND_DIR" "$FRONTEND_DIR"

# ── [2/8] MySQL — bases + import dumps ────────────────────────────────────
echo ""
echo "=== [2/8] Configuration MySQL ==="

# Définir le mot de passe root (idempotent via sudo)
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$MYSQL_ROOT_PASSWORD'; FLUSH PRIVILEGES;" 2>/dev/null || true

# Créer les bases et l'utilisateur applicatif
mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "
  CREATE DATABASE IF NOT EXISTS $DB_MAIN CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE DATABASE IF NOT EXISTS $DB_IM     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_APP_PASSWORD';
  GRANT ALL PRIVILEGES ON ${DB_MAIN}.* TO '$DB_USER'@'localhost';
  GRANT ALL PRIVILEGES ON ${DB_IM}.*   TO '$DB_USER'@'localhost';
  FLUSH PRIVILEGES;
" 2>/dev/null
echo "  Bases '$DB_MAIN' et '$DB_IM' prêtes."

# Importer les dumps SQL (seulement si la base est vide)
TABLES_MAIN=$(mysql -u root -p"$MYSQL_ROOT_PASSWORD" -se \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_MAIN';" 2>/dev/null || echo "0")

if [ "$TABLES_MAIN" -lt "5" ]; then
  echo "  Import medical_db.sql..."
  [ -f "$SQL_DIR/medical_db.sql" ] && mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$DB_MAIN" < "$SQL_DIR/medical_db.sql" 2>/dev/null && echo "  medical_db importé ($(wc -l < "$SQL_DIR/medical_db.sql") lignes)"
  echo "  Import im_db.sql..."
  [ -f "$SQL_DIR/im_db.sql" ]     && mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$DB_IM"   < "$SQL_DIR/im_db.sql"   2>/dev/null && echo "  im_db importé"
else
  echo "  Bases déjà peuplées ($TABLES_MAIN tables) — import ignoré."
fi

# ── [3/8] Dépendances système ──────────────────────────────────────────────
echo ""
echo "=== [3/8] Dépendances système ==="
apt-get update -qq
apt-get install -y python3-venv python3-dev libmysqlclient-dev \
  pkg-config build-essential 2>&1 | tail -3

# Node.js via NodeSource (évite les conflits apt)
if ! command -v node &>/dev/null || [ "$(node --version 2>/dev/null | cut -d. -f1 | tr -d v)" -lt 18 ]; then
  echo "  Installation Node.js 20.x via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>&1 | tail -3
  apt-get install -y nodejs 2>&1 | tail -3
else
  echo "  Node.js $(node --version) déjà installé."
fi

# ── [4/8] Backend Django — venv + requirements ────────────────────────────
echo ""
echo "=== [4/8] Backend — virtualenv et dépendances ==="
if [ ! -f "$BACKEND_DIR/venv/bin/python" ]; then
  echo "  Création venv..."
  python3 -m venv "$BACKEND_DIR/venv"
fi
"$BACKEND_DIR/venv/bin/pip" install --upgrade pip -q
"$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q 2>&1 | tail -3
echo "  Dépendances Python installées."

# ── [5/8] Fichier .env ────────────────────────────────────────────────────
echo ""
echo "=== [5/8] Fichier .env ==="
cat > "$BACKEND_DIR/.env" << ENV
SECRET_KEY=${DJANGO_SECRET_KEY}
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,${SERVER_IP}
CORS_ALLOWED_ORIGINS=http://${SERVER_IP},http://${SERVER_IP}:8000
DB_USER=${DB_USER}
DB_PASSWORD=${DB_APP_PASSWORD}
IM_DB_USER=${DB_USER}
IM_DB_PASSWORD=${DB_APP_PASSWORD}
TUNISIESMS_API_KEY=
TUNISIESMS_SENDER=LEONI
TUNISIESMS_API_URL=https://app.tunisiesms.tn/api/Api.aspx
ENV
echo "  .env créé pour IP $SERVER_IP"

# ── [6/8] Migrations Django + staticfiles ────────────────────────────────
echo ""
echo "=== [6/8] Migrations et fichiers statiques ==="
cd "$BACKEND_DIR"

# Ajouter STATIC_ROOT si absent
grep -q "STATIC_ROOT" medical_platform/settings.py || \
  printf '\nSTATIC_ROOT = BASE_DIR / "staticfiles"\n' >> medical_platform/settings.py

mkdir -p staticfiles media
"$BACKEND_DIR/venv/bin/python" manage.py migrate --noinput 2>&1 | tail -5
"$BACKEND_DIR/venv/bin/python" manage.py migrate --database=im_db --noinput 2>&1 | tail -3
"$BACKEND_DIR/venv/bin/python" manage.py collectstatic --noinput 2>&1 | tail -3
chown -R ubuntu:ubuntu "$BACKEND_DIR"
echo "  Migrations et static OK."

# ── [7/8] Service Gunicorn ────────────────────────────────────────────────
echo ""
echo "=== [7/8] Service Gunicorn (medical-backend) ==="
cat > /etc/systemd/system/medical-backend.service << UNIT
[Unit]
Description=Gunicorn — Medical LEONI Backend
After=network.target mysql.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=${BACKEND_DIR}
EnvironmentFile=${BACKEND_DIR}/.env
ExecStart=${BACKEND_DIR}/venv/bin/gunicorn medical_platform.wsgi:application \
  --bind 127.0.0.1:8000 --workers 3 --timeout 120 --access-logfile - --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable medical-backend
systemctl restart medical-backend
sleep 3
systemctl is-active medical-backend && echo "  Gunicorn actif." || echo "  WARN: Gunicorn non actif — voir journalctl -u medical-backend"

# ── [8/8] Frontend React + nginx ─────────────────────────────────────────
echo ""
echo "=== [8/8] Frontend React — build et nginx ==="

# Corrections casse Linux (case-sensitive)
[ -f "$FRONTEND_DIR/src/components/medecinTraitant/Fileattente.jsx" ] && \
  mv "$FRONTEND_DIR/src/components/medecinTraitant/Fileattente.jsx" \
     "$FRONTEND_DIR/src/components/medecinTraitant/FileAttente.jsx" && echo "  Renommé Fileattente.jsx"
[ -f "$FRONTEND_DIR/src/components/medecinTravail/Searchcollaborateur.jsx" ] && \
  mv "$FRONTEND_DIR/src/components/medecinTravail/Searchcollaborateur.jsx" \
     "$FRONTEND_DIR/src/components/medecinTravail/SearchCollaborateur.jsx" && echo "  Renommé Searchcollaborateur.jsx"

# vite.config.js
cat > "$FRONTEND_DIR/vite.config.js" << 'VITE'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({
  plugins: [react()],
  define: { global: {} },
  resolve: {
    alias: { stream: fileURLToPath(new URL('./src/shims/stream-browser-empty.js', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0', port: 5173, strictPort: true,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
VITE

cd "$FRONTEND_DIR"
rm -rf node_modules  # repartir d'un npm install propre
npm install --legacy-peer-deps --silent 2>&1 | tail -3
npm install react-is --legacy-peer-deps --silent
npm run build 2>&1 | tail -5

BUILD_DIR=""
[ -d "$FRONTEND_DIR/dist"  ] && [ -f "$FRONTEND_DIR/dist/index.html"  ] && BUILD_DIR="$FRONTEND_DIR/dist"
[ -d "$FRONTEND_DIR/build" ] && [ -f "$FRONTEND_DIR/build/index.html" ] && BUILD_DIR="$FRONTEND_DIR/build"
[ -z "$BUILD_DIR" ] && { echo "ERREUR : build frontend introuvable"; exit 1; }

rm -rf "$WEB_ROOT" && mkdir -p "$WEB_ROOT"
cp -r "$BUILD_DIR"/. "$WEB_ROOT/"
chown -R www-data:www-data "$WEB_ROOT"
echo "  Build copié vers $WEB_ROOT"

# Configuration nginx
cat > /etc/nginx/sites-available/medical-app << 'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

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
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias   /opt/backend/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/javascript;
}
NGINX

ln -sf /etc/nginx/sites-available/medical-app /etc/nginx/sites-enabled/medical-app
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
echo "  nginx rechargé."

# ── Vérification finale ───────────────────────────────────────────────────
echo ""
echo "=== Vérification finale ==="
sleep 4
FRONT=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ --max-time 5 || echo "000")
API=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/account/login/ \
  -X POST -H "Content-Type: application/json" -d '{"username":"x","password":"x"}' --max-time 5 || echo "000")
STATIC=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/admin/css/base.css --max-time 5 || echo "000")

echo "  Frontend  :80        → HTTP $FRONT"
echo "  API       /api/      → HTTP $API"
echo "  Static    /static/   → HTTP $STATIC"

echo ""
echo "=========================================================="
echo "  Déploiement terminé — $(date)"
echo "  Application : http://${SERVER_IP}/"
echo "  Admin       : http://${SERVER_IP}/api/admin/"
if [ "$FRONT" = "200" ] && [ "$API" != "000" ]; then
  echo "  STATUS      : ✅ OK"
else
  echo "  STATUS      : ⚠️  Vérifier les logs : journalctl -u medical-backend"
fi
echo "=========================================================="
