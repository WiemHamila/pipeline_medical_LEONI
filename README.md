# Pipeline CI/CD — Plateforme Médicale LEONI

---

### Statut des pipelines

[![Deploy Medical Project](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/deploy.yml/badge.svg)](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/deploy.yml)
[![DAST - Tests Dynamiques](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/dast.yml/badge.svg)](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/dast.yml)
[![DevSecOps - Alertes Telegram](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/telegram-notify.yml/badge.svg)](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/telegram-notify.yml)
[![Monitoring CloudWatch](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/monitoring.yml/badge.svg)](https://github.com/ngrassa/pipeline_medical_LEONI/actions/workflows/monitoring.yml)

---

### Stack technique

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)
![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=black)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)
![nginx](https://img.shields.io/badge/nginx-Reverse_Proxy-009639?logo=nginx&logoColor=white)
![AWS EC2](https://img.shields.io/badge/AWS-EC2_t2.large-FF9900?logo=amazonaws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.7.5-7B42BC?logo=terraform&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)

---

### Sécurité DevSecOps

![Bandit](https://img.shields.io/badge/SAST-Bandit-FFD43B?logo=python&logoColor=black)
![pip-audit](https://img.shields.io/badge/CVE-pip--audit-3776AB?logo=pypi&logoColor=white)
![OWASP ZAP](https://img.shields.io/badge/DAST-OWASP_ZAP-000000?logo=owasp&logoColor=white)
![Mistral AI](https://img.shields.io/badge/AI-Mistral_Remédiation-FF7000?logo=mistral&logoColor=white)
![Telegram](https://img.shields.io/badge/Alertes-Telegram-26A5E4?logo=telegram&logoColor=white)

---

Déploiement automatisé et tests de sécurité dynamiques (DAST) d'une application médicale full-stack Django + React sur AWS EC2, orchestrés via GitHub Actions et Terraform.

---

## Table des matières

1. [Architecture globale](#architecture-globale)
2. [Structure du projet](#structure-du-projet)
3. [Prérequis et secrets GitHub](#prérequis-et-secrets-github)
4. [Pipeline de déploiement — `deploy.yml`](#pipeline-de-déploiement--deployyml)
   - [Déclenchement](#déclenchement)
   - [Job 1 — Check VM existante](#job-1--check-vm-existante)
   - [Job 2 — Provision EC2 via Terraform](#job-2--provision-ec2-via-terraform)
   - [Job 3 — Déploiement de l'application](#job-3--déploiement-de-lapplication)
   - [Job 4 — Démarrage des services](#job-4--démarrage-des-services)
5. [Pipeline DAST — `dast.yml`](#pipeline-dast--dastyml)
   - [Déclenchement](#déclenchement-1)
   - [Phase 0 — Préparation de la cible](#phase-0--préparation-de-la-cible)
   - [Phase 1 — En-têtes HTTP de sécurité](#phase-1--en-têtes-http-de-sécurité)
   - [Phase 2 — OWASP ZAP Scan Passif](#phase-2--owasp-zap-scan-passif)
   - [Phase 3 — Sondes API actives](#phase-3--sondes-api-actives)
   - [Phase 4 — Sécurité JWT et CORS](#phase-4--sécurité-jwt-et-cors)
   - [Phase 5 — OWASP ZAP Scan Actif complet](#phase-5--owasp-zap-scan-actif-complet)
   - [Phase 6 — Synthèse DAST](#phase-6--synthèse-dast)
6. [Complémentarité SAST / DAST](#complémentarité-sast--dast)
7. [Lancer les pipelines manuellement](#lancer-les-pipelines-manuellement)
8. [Artefacts générés](#artefacts-générés)
9. [Dépannage](#dépannage)

---

## Architecture globale

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Repository                         │
│                                                             │
│   push sur main                                             │
│        │                                                    │
│        ▼                                                    │
│   deploy.yml ──────────────────────────────────────────┐   │
│   (4 jobs)                                             │   │
│                                                        │   │
│   dast.yml ────────────────────────────────────────┐  │   │
│   (6 phases, déclenché après deploy ou manuellement)│  │   │
└────────────────────────────────────────────────────┼──┼───┘
                                                     │  │
                                                     ▼  ▼
                              ┌──────────────────────────────┐
                              │      AWS EC2 (us-east-1)     │
                              │      Ubuntu 24.04 — t2.large │
                              │                              │
                              │  ┌──────────┐ ┌──────────┐  │
                              │  │  nginx   │ │  MySQL   │  │
                              │  │  :80     │ │  :3306   │  │
                              │  └────┬─────┘ └──────────┘  │
                              │       │ proxy /api/          │
                              │  ┌────▼─────────────────┐   │
                              │  │  Django / Gunicorn   │   │
                              │  │  :8000               │   │
                              │  └──────────────────────┘   │
                              │                              │
                              │  Elastic IP (stable)         │
                              └──────────────────────────────┘
```

**Stack technique :**
- **Backend** : Django 5.x + Django REST Framework + JWT (SimpleJWT)
- **Frontend** : React + Vite 8, servi par nginx
- **Base de données** : MySQL 8 (deux bases : `medical_db` + `im_db`)
- **Serveur** : Gunicorn (WSGI) + nginx (reverse proxy)
- **Infrastructure** : Terraform + AWS EC2 t2.large + Elastic IP
- **CI/CD** : GitHub Actions

---

## Structure du projet

```
pipeline_medical_LEONI/
├── .github/
│   └── workflows/
│       ├── deploy.yml          ← Pipeline de déploiement (4 jobs)
│       ├── dast.yml            ← Tests dynamiques de sécurité (6 phases)
│       └── tests.yml           ← Tests SAST (Bandit, pytest, ZAP baseline, Locust)
│
├── terraform/                  ← Infrastructure as Code
│   ├── main.tf                 ← Provider AWS, EC2, Elastic IP
│   ├── variables.tf            ← Variables (région, type, clé SSH, mots de passe)
│   ├── outputs.tf              ← Outputs (IP, URLs, SSH command)
│   ├── security-group.tf       ← Ports ouverts : 22, 80, 8000, 3000, 5173
│   ├── user_data.sh            ← Script bootstrap EC2 (lancé au 1er démarrage)
│   ├── terraform.tfstate       ← État Terraform (contient l'IP de l'instance)
│   └── install/
│       ├── backend.sh          ← Installation Django + MySQL + Gunicorn
│       └── frontend.sh         ← Installation React + npm build + nginx
│
├── scripts/
│   └── setup.sh                ← Script de déploiement/mise à jour idempotent
│
├── backend-service-medical_linux/   ← Code source Django (sans venv)
└── frontend-service-medical_linux/  ← Code source React/Vite (sans node_modules)
```

---

## Prérequis et secrets GitHub

Aller dans **Settings → Secrets and variables → Actions** et créer les 6 secrets suivants :

| Secret | Description | Exemple |
|--------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | Clé d'accès AWS (depuis AWS Academy) | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | Clé secrète AWS | `wJal...` |
| `AWS_SESSION_TOKEN` | Token de session (AWS Academy uniquement) | `IQoJb...` |
| `SSH_PRIVATE_KEY` | Contenu complet du fichier `labsuser.pem` | `-----BEGIN RSA PRIVATE KEY-----...` |
| `DB_APP_PASSWORD` | Mot de passe MySQL pour l'utilisateur `medical_user` | `MonMotDePasse123!` |
| `MYSQL_ROOT_PASSWORD` | Mot de passe MySQL pour root | `RootPass456!` |

> **Important** : Coller le contenu **entier** de `labsuser.pem` dans `SSH_PRIVATE_KEY`, y compris les lignes `-----BEGIN` et `-----END`.

---

## Pipeline de déploiement — `deploy.yml`

### Déclenchement

```yaml
on:
  push:
    branches: [main]
```

Le pipeline se déclenche automatiquement à **chaque push sur `main`**.

---

### Job 1 — Check VM existante

**Objectif** : Détecter si une instance EC2 est déjà en cours d'exécution pour ne pas en créer une nouvelle inutilement.

```
push → Job 1 (check) → vm_exists=true/false
                              │
                    ┌─────────┴─────────┐
                    │                   │
              vm_exists=true      vm_exists=false
                    │                   │
              skip Job 2          Job 2 (terraform)
```

**Fonctionnement détaillé :**

1. **Lecture du `terraform.tfstate`** : Le job lit le fichier `terraform/terraform.tfstate` présent dans le repo Git et en extrait l'IP publique de l'Elastic IP via `jq` :
   ```bash
   jq -r '[.resources[] | select(.type=="aws_eip") | .instances[0].attributes.public_ip] | first' terraform.tfstate
   ```

2. **Test SSH** : Si une IP est trouvée, le job tente une connexion SSH avec la clé privée du secret `SSH_PRIVATE_KEY` :
   ```bash
   ssh -o ConnectTimeout=10 -o BatchMode=yes -i ~/.ssh/labsuser.pem ubuntu@<IP> "echo ok"
   ```

3. **Sortie** : Émet `vm_exists=true` + `server_ip=<IP>` si la VM répond, `vm_exists=false` sinon.

**Output utilisé par les jobs suivants :**
- `needs.check.outputs.vm_exists` → décide si Terraform doit tourner
- `needs.check.outputs.server_ip` → IP de la VM existante (réutilisée dans Job 3 et 4)

---

### Job 2 — Provision EC2 via Terraform

**Condition** : Ne s'exécute que si `vm_exists != 'true'` (aucune VM active détectée).

**Étapes :**

#### 1. Configuration AWS
```yaml
uses: aws-actions/configure-aws-credentials@v4
```
Injecte les credentials AWS depuis les secrets GitHub dans l'environnement du runner.

#### 2. Terraform Init
```bash
terraform init
```
Télécharge le provider AWS Hashicorp (~100 MB) et initialise le backend local.

#### 3. Import des ressources existantes
Avant d'appliquer, le job vérifie si des ressources AWS portant les mêmes noms existent déjà (cas d'une reprise après un `terraform destroy` partiel) et les importe dans le state :

```bash
# Security Group
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=medical-app-sg" ...)
terraform import aws_security_group.medical_sg "$SG_ID"

# Instance EC2
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=medical-app-server" ...)
terraform import aws_instance.medical_app "$INSTANCE_ID"

# Elastic IP
EIP_ALLOC=$(aws ec2 describe-addresses --filters "Name=tag:Name,Values=medical-app-eip" ...)
terraform import aws_eip.medical_eip "$EIP_ALLOC"
```

> **Pourquoi ?** Sans import, Terraform essaierait de créer un Security Group avec le même nom → erreur `InvalidGroup.Duplicate`.

#### 4. Terraform Plan & Apply
```bash
terraform plan \
  -var="db_app_password=${{ secrets.DB_APP_PASSWORD }}" \
  -var="mysql_root_password=${{ secrets.MYSQL_ROOT_PASSWORD }}" \
  -out=tfplan

terraform apply -auto-approve tfplan
```

Les mots de passe des bases de données sont injectés via les variables Terraform (jamais écrits en dur dans le code).

**Ressources créées par Terraform :**

| Ressource | Description |
|-----------|-------------|
| `aws_security_group.medical_sg` | Ports 22, 80, 8000, 3000, 5173 |
| `aws_eip.medical_eip` | Elastic IP allouée avant l'instance |
| `aws_instance.medical_app` | Ubuntu 24.04, t2.large, 20 GB gp3 |
| `aws_eip_association.eip_assoc` | Association EIP → instance |

**Bootstrap automatique (`user_data.sh`)** : Au démarrage, l'instance exécute automatiquement `user_data.sh` qui :
1. Met à jour les packages système (`apt upgrade`)
2. Installe Python 3, Node.js 20, nginx, MySQL, build-essential
3. Exécute `install/backend.sh` → Django + Gunicorn
4. Exécute `install/frontend.sh` → React build + nginx

Durée totale du bootstrap : **~15 minutes**.

#### 5. Sauvegarde du Terraform State
```bash
git add terraform.tfstate terraform.tfstate.backup
git commit -m "chore: update terraform state [skip ci]"
git push
```
Le `terraform.tfstate` est commité dans le repo Git pour que les prochains runs de pipeline (et le DAST) puissent retrouver l'IP de l'instance.

---

### Job 3 — Déploiement de l'application

**Condition** : S'exécute toujours si Job 1 a réussi ET (Job 2 a réussi OU Job 2 a été ignoré).

**Logique selon le cas :**

```
VM existante (vm_exists=true) → setup.sh en mode "mise à jour"
     ↓
  Télécharge les nouveaux ZIPs depuis GitHub Releases
  Recrée le venv Python (rm -rf venv + python3 -m venv)
  pip install requirements.txt
  Corrige les noms de fichiers (casse Linux)
  Met à jour vite.config.js
  npm install + react-is + npm run build
  Configure nginx
  Redémarre les services

VM nouvelle (vm_exists=false) → setup.sh en mode "attente"
     ↓
  Attend jusqu'à 30 min que le bootstrap user_data se termine
  Vérifie les services (systemctl status)
```

**Correction de casse des fichiers** (sensibilité Linux) :
```bash
mv medecinTraitant/Fileattente.jsx  medecinTraitant/FileAttente.jsx
mv medecinTravail/Searchcollaborateur.jsx medecinTravail/SearchCollaborateur.jsx
```

**Mise à jour de `vite.config.js`** :
```javascript
server: {
  host: '0.0.0.0',   // écoute sur toutes les interfaces
  port: 5173,
  proxy: { '/api': { target: 'http://localhost:8000' } }
}
```

---

### Job 4 — Démarrage des services

**Objectif** : S'assurer que tous les services sont démarrés et vérifier les endpoints.

**Script exécuté sur le serveur :**

```
1. Attendre "Bootstrap complete" dans le log (max 25 min)
        ↓
2. Démarrer MySQL
        ↓
3. Libérer le port 8000 : sudo fuser -k 8000/tcp
        ↓
4. Vérifier le venv Python
   ├─ venv OK → lancer directement
   ├─ requirements.txt présent → recréer le venv + pip install
   └─ /opt/backend absent → afficher le log + exit 1
        ↓
5. Lancer Django en arrière-plan :
   nohup python manage.py runserver 0.0.0.0:8000 > /tmp/backend.log &
        ↓
6. Démarrer nginx
        ↓
7. Vérifier les endpoints :
   curl http://localhost/         → HTTP 200 attendu
   curl http://localhost:8000/api/ → HTTP 404 attendu (normal)
```

> **Note** : HTTP 404 sur `/api/` est **normal** — Django n'a pas de vue sur la racine `/api/`. Les vrais endpoints sont sur `/api/account/login/`, `/api/consultations/`, etc.

**Affichage final des URLs :**
```
==========================================
  PROJET MEDICAL - DEPLOYE AVEC SUCCES
==========================================
  Frontend : http://<ELASTIC_IP>
  Backend  : http://<ELASTIC_IP>:8000
  API      : http://<ELASTIC_IP>/api/
  SSH      : ssh -i labsuser.pem ubuntu@<ELASTIC_IP>
==========================================
```

---

## Pipeline DAST — `dast.yml`

Le DAST (Dynamic Application Security Testing) teste l'application **en cours d'exécution**, contrairement au SAST qui analyse le code statique. Il simule des attaques réelles contre l'instance déployée.

### Déclenchement

```yaml
on:
  workflow_dispatch:          # Déclenchement manuel avec IP optionnelle
    inputs:
      target_ip:
        description: "IP cible (vide = lire depuis tfstate)"
  workflow_run:               # Automatique après deploy.yml
    workflows: ["Deploy Medical Project"]
    types: [completed]
```

Deux modes :
- **Manuel** : Aller dans Actions → DAST → Run workflow → entrer l'IP ou laisser vide
- **Automatique** : Se lance après chaque run de `deploy.yml`

---

### Phase 0 — Préparation de la cible

**Objectif** : Trouver l'IP de l'instance à scanner.

```bash
# Priorité 1 : IP fournie manuellement via workflow_dispatch
TARGET_IP="${{ github.event.inputs.target_ip }}"

# Priorité 2 : Lire depuis terraform/terraform.tfstate
jq -r '[.resources[] | select(.type=="aws_eip") | .instances[0].attributes.public_ip] | first' terraform.tfstate

# Vérification accessibilité
curl -s "http://$TARGET_IP/"         # Frontend
curl -s "http://$TARGET_IP/api/..."  # Backend
```

Si aucune IP n'est trouvée → exit 1 (le DAST ne peut pas continuer sans cible).

---

### Phase 1 — En-têtes HTTP de sécurité

**Objectif** : Vérifier la présence des en-têtes de sécurité HTTP recommandés par l'OWASP.

**En-têtes vérifiés :**

| En-tête | Rôle | Impact si absent |
|---------|------|-----------------|
| `X-Content-Type-Options` | Empêche le MIME sniffing | XSS via fichiers mal typés |
| `X-Frame-Options` | Prévient le clickjacking | L'app peut être intégrée dans un iframe malicieux |
| `Content-Security-Policy` | Contrôle les ressources chargées | XSS, injection de scripts |
| `Referrer-Policy` | Contrôle les infos dans Referer | Fuite d'URLs internes |
| `Permissions-Policy` | Limite l'accès aux API navigateur | Accès abusif caméra/micro/géoloc |
| `Strict-Transport-Security` | Force HTTPS | Downgrade attack vers HTTP |

**Vérification de la divulgation du serveur :**
```bash
curl -sI http://<IP>/ | grep "Server:"
# Résultat OK  : "Server: nginx" sans version
# Résultat WARN: "Server: nginx/1.24.0" → version divulguée
```

---

### Phase 2 — OWASP ZAP Scan Passif

**Outil** : [OWASP ZAP](https://www.zaproxy.org/) (Zed Attack Proxy) en mode **passif** (écoute et analyse sans attaquer).

**Deux scans parallèles :**

```
ZAP Baseline → http://<IP>     (frontend nginx :80)
               artifact_name: zap-baseline-frontend

ZAP Baseline → http://<IP>:8000 (backend Django :8000)
               artifact_name: zap-baseline-api
```

**Ce que détecte ZAP passif :**
- En-têtes manquants (CSP, HSTS, X-Frame-Options)
- Cookies sans flags `HttpOnly` ou `Secure`
- Informations de version exposées
- Formulaires sans protection CSRF
- Redirections non sécurisées

**Fichier de règles** : `backend-service-medical_linux/.zap/rules.tsv` — configure quelles alertes ZAP sont WARN, IGNORE ou FAIL.

---

### Phase 3 — Sondes API actives

**Objectif** : Tester manuellement les vulnérabilités les plus courantes via `curl`.

#### Injection SQL
```bash
Payloads testés :
  ' OR '1'='1        → tentative de bypass auth
  admin'--           → commentaire SQL
  1; DROP TABLE users-- → injection destructive
  ' UNION SELECT 1,2,3-- → extraction de données

Endpoint ciblé : POST /api/account/login/
Résultat attendu : HTTP 400 (rejet) — jamais HTTP 200 (succès auth)
```

#### Injection XSS (Cross-Site Scripting)
```bash
Payloads testés :
  <script>alert(1)</script>
  javascript:alert(1)
  <img src=x onerror=alert(1)>

Résultat attendu : payload renvoyé encodé ou rejeté (jamais exécuté)
```

#### Bypass d'authentification
```bash
# Accès aux endpoints protégés sans token
GET /api/account/users/       → attendu : 401 Unauthorized
GET /api/consultations/       → attendu : 401 Unauthorized
GET /api/stock/               → attendu : 401 Unauthorized
GET /api/planning/            → attendu : 401 Unauthorized
GET /api/employees/           → attendu : 401 Unauthorized
```

#### IDOR (Insecure Direct Object Reference)
```bash
# Énumération d'IDs sans authentification
GET /api/account/users/1/     → attendu : 401 (pas 200)
GET /api/account/users/2/     → attendu : 401 (pas 200)
GET /api/account/users/9999/  → attendu : 401 (pas 404 qui révèle l'existence)
```

#### Méthodes HTTP non autorisées
```bash
DELETE /api/account/login/ → attendu : 405 Method Not Allowed
TRACE  /api/account/login/ → attendu : 405 (TRACE activé = XST vulnerability)
```

---

### Phase 4 — Sécurité JWT et CORS

**Objectif** : Tester la robustesse de l'authentification par token JWT.

#### Tokens JWT invalides
```bash
# Aucun token
GET /api/account/users/ → attendu : 401

# Token vide
Authorization: Bearer
GET /api/account/users/ → attendu : 401

# Token malformé
Authorization: Bearer not.a.valid.jwt
GET /api/account/users/ → attendu : 401

# Algorithme "none" (vulnérabilité JWT classique)
# JWT avec alg=none : contournement de la vérification de signature
Authorization: Bearer eyJhbGciOiJub25lIn0.eyJ1c2VyX2lkIjoxfQ.
GET /api/account/users/ → attendu : 401 (si vulnérable → 200 = CRITICAL)
```

#### Protection brute-force
```bash
# 10 tentatives de connexion avec mauvais mot de passe
for i in 1..10:
  POST /api/account/login/ {"username":"admin","password":"wrong_$i"}

# Résultat attendu :
# HTTP 400 (rejection) + éventuellement HTTP 429 (rate limiting après N tentatives)
# Si toutes les tentatives → HTTP 400 sans ralentissement → WARN (pas de protection)
```

#### CORS malicieux
```bash
OPTIONS /api/account/login/ \
  -H "Origin: http://evil.example.com" \
  -H "Access-Control-Request-Method: POST"

# Résultat attendu :
# Access-Control-Allow-Origin: http://localhost (domaine spécifique)
# WARN si : Access-Control-Allow-Origin: * (wildcard = tout domaine autorisé)
```

#### Clickjacking
```bash
curl -sI http://<IP>/ | grep "X-Frame-Options"
# Attendu : X-Frame-Options: DENY ou SAMEORIGIN
# ou CSP avec frame-ancestors: 'none'
```

---

### Phase 5 — OWASP ZAP Scan Actif complet

**Outil** : OWASP ZAP en mode **actif** — envoie des attaques réelles contre l'application.

> ⚠️ Le scan actif envoie des payloads malicieux réels. Ne jamais lancer contre une application de production sans autorisation explicite.

**Deux scans en séquence :**

#### ZAP Full Scan (application complète)
```yaml
uses: zaproxy/action-full-scan@v0.10.0
with:
  target: "http://<IP>"
  artifact_name: "zap-full-scan"
  cmd_options: "-T 10"   # timeout 10 min
```

**Attaques testées par ZAP actif :**
- Injection SQL active (contenu des réponses analysé)
- Cross-Site Scripting (XSS réfléchi et stocké)
- Directory traversal (`../../../etc/passwd`)
- Remote File Inclusion
- Command injection
- CSRF (Cross-Site Request Forgery)
- Server-Side Template Injection (SSTI)
- XML External Entity (XXE)
- Broken Access Control

#### ZAP API Scan (endpoints `/api/`)
```yaml
uses: zaproxy/action-api-scan@v0.7.0
with:
  target: "http://<IP>/api/"
  artifact_name: "zap-api-scan"
```

Scan spécialisé pour les APIs REST — teste les endpoints Django REST Framework.

---

### Phase 6 — Synthèse DAST

**Objectif** : Afficher un résumé de toutes les phases avec leurs statuts.

```
=======================================================
  RAPPORT DAST — PLATEFORME MEDICALE LEONI
  Cible : http://44.197.32.80
=======================================================

  Phase 1 - En-tetes HTTP         : success
  Phase 2 - ZAP Passif (baseline) : success
  Phase 3 - Sondes API             : success
  Phase 4 - Securite JWT/CORS      : success
  Phase 5 - ZAP Actif complet      : success

  Artefacts disponibles :
  - zap-passive-reports/   : rapports HTML baseline
  - zap-active-reports/    : rapports HTML full scan + API scan
=======================================================
```

---

## Complémentarité SAST / DAST

| Critère | SAST (`tests.yml`) | DAST (`dast.yml`) |
|---------|-------------------|-------------------|
| **Quand** | Avant déploiement (code statique) | Après déploiement (app en vie) |
| **Outil injection** | pytest (simulation Python) | curl avec payloads réels |
| **Outil ZAP** | Baseline passif uniquement | Baseline **+** Full actif **+** API scan |
| **JWT** | Tests unitaires Python | Tokens réels envoyés à l'API live |
| **CORS** | Non testé | Origin `evil.example.com` en live |
| **Brute-force** | Non testé | 10 tentatives réelles sur `/api/login/` |
| **Clickjacking** | Non testé | Vérification en-têtes HTTP réels |
| **IDOR** | Non testé | Énumération IDs via HTTP réels |
| **Performance** | Locust (50 users) | Non testé |
| **Qualité frontend** | Lighthouse | Non testé |
| **Analyse code** | Bandit + Safety | Non applicable |

---

## Lancer les pipelines manuellement

### Lancer `deploy.yml`
1. Aller dans **Actions** → **Deploy Medical Project**
2. Cliquer **Run workflow**
3. Sélectionner la branche `main`
4. Cliquer **Run workflow**

### Lancer `dast.yml`
1. Aller dans **Actions** → **DAST - Tests Dynamiques de Securite**
2. Cliquer **Run workflow**
3. Champ `target_ip` : laisser vide (lit le tfstate) ou entrer une IP manuellement
4. Cliquer **Run workflow**

### Relancer après un `terraform destroy` local
```bash
# 1. Redéployer localement
cd project/
terraform apply -auto-approve

# 2. Copier le nouveau tfstate dans le repo pipeline
cp project/terraform.tfstate pipeline_medical_LEONI/terraform/terraform.tfstate

# 3. Commiter et pousser
cd pipeline_medical_LEONI/
git add terraform/terraform.tfstate
git commit -m "chore: update tfstate after local redeploy"
git push
```

---

## Artefacts générés

Après chaque run DAST, les rapports sont disponibles dans **Actions → run → Artifacts** :

| Artefact | Contenu | Phase |
|----------|---------|-------|
| `zap-passive-reports` | `zap_frontend.html` + `zap_api.html` | Phase 2 |
| `zap-baseline-frontend` | Rapport ZAP baseline frontend | Phase 2 |
| `zap-baseline-api` | Rapport ZAP baseline API :8000 | Phase 2 |
| `zap-active-reports` | `zap_active_report.html` + `zap_api_active_report.html` | Phase 5 |
| `zap-full-scan` | Rapport ZAP full scan | Phase 5 |
| `zap-api-scan` | Rapport ZAP API scan | Phase 5 |

---

## Dépannage

### `vm_exists=false` alors qu'une instance tourne

Le `terraform.tfstate` n'est pas à jour dans le repo. Copier et commiter le tfstate local :
```bash
cp project/terraform.tfstate pipeline_medical_LEONI/terraform/terraform.tfstate
cd pipeline_medical_LEONI && git add terraform/terraform.tfstate && git commit -m "fix: sync tfstate" && git push
```

### `No such file: requirements.txt` (Job 4)

Le bootstrap `user_data.sh` n'était pas encore terminé quand Job 4 a démarré. Le Job 4 attend maintenant jusqu'à 25 min. Si l'erreur persiste :
```bash
# Vérifier le bootstrap
ssh -i labsuser.pem ubuntu@<IP> 'sudo tail -50 /var/log/medical-bootstrap.log'
```

### `InvalidGroup.Duplicate` (Terraform)

Le Security Group existe déjà dans AWS. Importer avant d'appliquer :
```bash
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=medical-app-sg" --query "SecurityGroups[0].GroupId" --output text)
terraform import aws_security_group.medical_sg "$SG_ID"
terraform apply -auto-approve
```

### Gunicorn `203/EXEC` (binary not found)

Gunicorn n'est pas installé dans le venv :
```bash
ssh -i labsuser.pem ubuntu@<IP> \
  '/opt/backend/venv/bin/pip install gunicorn && sudo systemctl restart medical-backend'
```

### `artifact name zap_scan is not valid` (DAST)

Plusieurs jobs ZAP créaient un artefact avec le même nom. Corrigé dans la version actuelle (`artifact_name` unique par action ZAP).

### SSH `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED`

L'instance a été recréée (nouvelle clé SSH). Supprimer l'ancienne entrée :
```bash
ssh-keygen -f ~/.ssh/known_hosts -R '<ANCIENNE_IP>'
```

---

## Informations techniques

- **AMI** : Ubuntu 24.04 LTS (Noble Numbat) — Canonical officiel (`ami-0fc0d6e8d70ab2d42`)
- **Région AWS** : `us-east-1`
- **Instance** : `t2.large` (2 vCPU, 8 GB RAM)
- **Disque** : 20 GB gp3
- **Gunicorn** : 4 workers, timeout 120s, bind `0.0.0.0:8000`
- **nginx** : proxy `/api/` et `/media/` → Gunicorn, sert `dist/` pour React
- **Node.js** : 20 LTS (via NodeSource)
- **MySQL** : 8.0 (Ubuntu apt), bases `medical_db` + `im_db`
"test" 
