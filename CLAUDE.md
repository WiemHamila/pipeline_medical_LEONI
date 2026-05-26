# CLAUDE.md — Pipeline CI/CD Médical LEONI

Mémoire de projet pour Claude. Ce fichier décrit l'architecture, les workflows, les fichiers clés,
les correctifs appliqués et les points d'attention pour toute future intervention.

---

## Identité du projet

| Champ | Valeur |
|---|---|
| Repo principal | `ngrassa/pipeline_medical_LEONI` (branche `master`) |
| Repo secondaire | `WiemHamila/pipeline_medical_LEONI` (remote `origin`) |
| Branche locale | `main` → poussée vers `ngrassa/master` avec `git push ngrassa main:master` |
| Application | Plateforme médicale Django 5.x + React/Vite |
| Serveur | AWS EC2 `t2.large` Ubuntu 24.04, région `us-east-1` |
| Clé SSH | `vockey` / fichier `labsuser.pem` |
| Elastic IP | Lue depuis `terraform/terraform.tfstate` (champ `aws_eip`) |

---

## Structure du dépôt

```
pipeline_medical_LEONI/
├── .github/workflows/
│   ├── deploy.yml          # Pipeline de déploiement (EC2 + app)
│   ├── dast.yml            # DAST OWASP ZAP (6 phases)
│   ├── telegram-notify.yml # SAST Bandit+pip-audit + rapport Telegram
│   ├── monitoring.yml      # CloudWatch + CloudTrail
│   └── destroy.yml         # Destruction manuelle de l'infrastructure
├── scripts/
│   ├── deploy_app.sh       # Script de déploiement exécuté via SSH sur EC2
│   └── telegram_alert.py   # Notifications Telegram multi-abonnés + SAST/DAST
├── terraform/
│   ├── main.tf             # EC2 + Elastic IP + security group
│   ├── user_data.sh        # Bootstrap cloud-init (installe MySQL, nginx, Node.js)
│   ├── install/
│   │   ├── backend.sh      # Setup Django (injecté dans user_data au premier boot)
│   │   └── frontend.sh     # Setup React (injecté dans user_data au premier boot)
│   ├── terraform.tfstate   # État Terraform (commité dans le repo, mis à jour par CI)
│   └── variables.tf        # Variables (instance_type=t2.large, region=us-east-1)
├── backend-service-medical_linux/
│   ├── db/
│   │   ├── medical_db.sql  # Dump SQL base principale (trackée dans git)
│   │   └── im_db.sql       # Dump SQL base IM (trackée dans git)
│   └── .zap/rules.tsv      # Règles OWASP ZAP
└── frontend-service-medical_linux/
```

---

## Chaîne CI/CD complète (ordre d'exécution)

```
PUSH sur master  ─────────────────────────────────────────────────────────────┐
                                                                              │
  1. deploy.yml  ─── "Deploy Medical Project"                                │
     │                                                                        │
     ├── Job 1 : Check VM existante (AWS describe-instances)                 │
     │    └─ Si instance stoppée → la démarrer (aws ec2 start-instances)    │
     │    └─ Si instance running → vérifier SSH                              │
     │    └─ Si aucune instance → vm_exists=false                            │
     │                                                                        │
     ├── Job 2 : Provision EC2 via Terraform (si vm_exists=false seulement) │
     │    └─ terraform init → import ressources existantes → plan → apply   │
     │    └─ Sauvegarde terraform.tfstate dans le repo (commit auto)         │
     │                                                                        │
     ├── Job 3 : Deploy Application (toujours si Job 1 ou 2 réussi)         │
     │    ├─ rsync backend → /opt/backend/                                   │
     │    ├─ rsync frontend → /opt/frontend/                                 │
     │    ├─ rsync db/*.sql → /tmp/sql_dumps/                                │
     │    ├─ SSH : exécute deploy_app.sh                                     │
     │    │   [cloud-init wait] → [MySQL config+import] → [venv+pip]        │
     │    │   → [.env] → [migrations] → [Gunicorn] → [React build+nginx]    │
     │    └─ Notification Telegram "✅ Déploiement réussi + IP + URLs"       │
     │                                                                        │
     └── DÉCLENCHE (si conclusion == 'success') ──────────────────────────┐  │
                                                                           │  │
  2. dast.yml  ─── "DAST - Tests Dynamiques de Securite"                  │  │
     │  (workflow_run: Deploy, branches: [main,master],                    │  │
     │   if: conclusion == 'success'  ← CONDITION CRITIQUE)               │  │
     │                                                                     │  │
     ├── Phase 0 : Récupération IP depuis terraform.tfstate                │  │
     ├── Phase 1 : Vérification en-têtes HTTP (CSP, HSTS, X-Frame...)    │  │
     ├── Phase 2 : OWASP ZAP Baseline passif (frontend :80 + API :8000)  │  │
     ├── Phase 3 : Sondes API actives (SQLi, XSS, bypass auth, IDOR)     │  │
     ├── Phase 4 : Sécurité JWT, brute-force, CORS, clickjacking         │  │
     ├── Phase 5 : OWASP ZAP Full active scan                             │  │
     └── Phase 6 : Synthèse DAST                                          │  │
                                                                           │  │
     └── DÉCLENCHE (si conclusion == 'success') ──────────────────┐       │  │
                                                                   │       │  │
  3. telegram-notify.yml  ─── "DevSecOps - Alertes Telegram"      │       │  │
     │  (workflow_run: DAST,                                        │       │  │
     │   if: conclusion == 'success'  ← CONDITION CRITIQUE)        │       │  │
     │                                                              │       │  │
     ├── Job 1 SAST : Bandit (analyse statique code Django)        │       │  │
     │             + pip-audit (CVEs dépendances Python)            │       │  │
     └── Job 2 : Analyse Mistral AI + Envoi Telegram               │       │  │
          ├─ Lit SERVER_IP depuis terraform.tfstate (jq)            │       │  │
          ├─ get_all_subscribers() → collecte tous les chat IDs    │       │  │
          ├─ Alertes CVE individuelles (par paquet vulnérable)      │       │  │
          ├─ Alerte SAST Bandit HIGH/CRITICAL                       │       │  │
          └─ Rapport d'audit global (score/100, IP, URL CI/CD)     │       │  │
```

**Règle absolue** : le DAST ne se lance JAMAIS si le deploy a échoué.
Le Telegram ne se lance JAMAIS si le DAST a échoué. Chaîne séquentielle stricte.

---

## Secrets GitHub requis

| Secret | Usage |
|---|---|
| `AWS_ACCESS_KEY_ID` | Credentials AWS |
| `AWS_SECRET_ACCESS_KEY` | Credentials AWS |
| `AWS_SESSION_TOKEN` | Credentials AWS (session temporaire) |
| `SSH_PRIVATE_KEY` | Clé privée PEM pour SSH vers EC2 |
| `DB_APP_PASSWORD` | Mot de passe MySQL utilisateur `medical_user` |
| `MYSQL_ROOT_PASSWORD` | Mot de passe MySQL root |
| `DJANGO_SECRET_KEY` | SECRET_KEY Django |
| `TELEGRAM_BOT_TOKEN` | Token du bot `@medical_Leoni_bot` |
| `TELEGRAM_CHAT_ID` | Chat ID admin (fallback si getUpdates vide) |
| `MISTRAL_API_KEY` | Clé Mistral AI (remédiation automatique) |

---

## Bot Telegram — système multi-abonnés

**Bot** : `@medical_Leoni_bot`

**Architecture** : push-only, pas de serveur webhook permanent. Le script CI/CD
collecte dynamiquement les abonnés à chaque run via `getUpdates`.

**Fonctionnement (`scripts/telegram_alert.py`)** :

1. `get_all_subscribers()` appelle `GET /bot{TOKEN}/getUpdates?limit=100`
   - Collecte tous les `chat_id` uniques des 100 derniers messages reçus
   - Ne fait PAS avancer l'offset → les abonnés restent visibles entre les runs
   - Répond automatiquement aux `/start` de moins de 24h avec un message de bienvenue
   - Inclut toujours `TELEGRAM_CHAT_ID` (admin) dans la liste

2. Pour s'abonner : envoyer `/start` au bot → sera inclus dès le prochain run CI

3. `DEPLOY_MODE=true` → envoie uniquement la notification de déploiement (IP + URLs)
   sans lancer le SAST/DAST report

4. `SERVER_IP` → injecté depuis `terraform.tfstate` via jq dans `telegram-notify.yml`
   et depuis la variable d'env `SERVER_IP` dans `deploy.yml`

**Contenu des messages envoyés** :

| Message | Déclenché par | Contenu |
|---|---|---|
| Bienvenue | `/start` < 24h | Confirmation abonnement + description |
| Déploiement réussi | Fin du Job 3 deploy.yml | IP, URL app, URL admin, commande SSH |
| Alerte CVE | pip-audit finding | Package, version, CVE ID, remédiation Mistral |
| Alerte SAST | Bandit HIGH/CRITICAL | Fichier, ligne, issue, remédiation Mistral |
| Rapport d'audit | Fin pipeline complet | Score/100, findings, IP instance, URL CI |

---

## deploy_app.sh — points clés

Chemin : `scripts/deploy_app.sh`, copié via SSH et exécuté en root sur EC2.

**Ordre des étapes** :
```
[cloud-init wait]  ← CRITIQUE sur nouvelle instance (bloque jusqu'à fin MySQL install)
[1/8] mkdir /opt/backend /opt/frontend /var/www/medical-frontend
[2/8] Config MySQL : ALTER USER root, CREATE DATABASE medical_db + im_db,
                     CREATE USER medical_user, import dumps si < 5 tables
[3/8] apt install mysql-server nginx python3-venv libmysqlclient-dev nodejs
      ← mysql-server + nginx ici pour idempotence si cloud-init pas encore fini
[4/8] pip install -r requirements.txt dans venv
[5/8] Écriture du fichier .env (SECRET_KEY, ALLOWED_HOSTS, DB_USER, etc.)
[6/8] manage.py migrate + collectstatic
[7/8] Service Gunicorn (systemd medical-backend)
[8/8] npm install + npm run build + config nginx
      Vérification finale : curl frontend + API + static
```

**Bases de données** :
- `medical_db` — base principale (medical_user)
- `im_db` — base IM (medical_user)
- Dumps SQL dans `backend-service-medical_linux/db/` (trackés dans git)
- Import ignoré si la base contient déjà ≥ 5 tables (idempotent)

---

## Terraform — infrastructure

- **AMI** : Ubuntu 24.04 LTS Canonical (`ubuntu-noble-24.04-amd64-server-*`)
- **Instance** : `t2.large`, 20 Go gp3, tag `Name=medical-app-server`
- **Elastic IP** : tag `Name=medical-app-eip`, associée à l'instance
- **lifecycle** : `ignore_changes = [ami, user_data]` — évite la recréation sur AMI update
- **user_data.sh** : installe MySQL, nginx, Node.js 20.x, puis exécute
  `terraform/install/backend.sh` et `terraform/install/frontend.sh` (premier boot uniquement)
- **tfstate** : commité dans le repo par le Job 2, lu par les jobs DAST et Telegram pour l'IP

**Récupérer l'IP courante** :
```bash
jq -r '[.resources[] | select(.type=="aws_eip") | .instances[0].attributes.public_ip] | first' terraform/terraform.tfstate
```

---

## Workflow — déclencheurs et conditions

```yaml
# deploy.yml
on:
  push:
    branches: [main, master]   # les deux branches
  workflow_dispatch:

# dast.yml
on:
  workflow_run:
    workflows: ["Deploy Medical Project"]
    types: [completed]
    branches: [main, master]
  workflow_dispatch:
jobs:
  prepare:
    if: >
      github.event_name == 'workflow_dispatch' ||
      github.event.workflow_run.conclusion == 'success'

# telegram-notify.yml
on:
  workflow_run:
    workflows: ["DAST - Tests Dynamiques de Securite"]
    types: [completed]
  workflow_dispatch:
jobs:
  sast-scan:
    if: >
      github.event_name == 'workflow_dispatch' ||
      github.event.workflow_run.conclusion == 'success'
```

---

## Correctifs appliqués (historique)

| Problème | Cause | Correctif |
|---|---|---|
| DAST lancé après deploy échoué | `types: [completed]` sans vérifier `conclusion` | `if: conclusion == 'success'` sur le job `prepare` |
| Telegram lancé après DAST échoué | Même cause | `if: conclusion == 'success'` sur `sast-scan` |
| Pipeline ne se déclenche pas sur `master` | `branches: [main]` seulement | Ajout de `master` dans deploy.yml et dast.yml |
| `mysql` introuvable (exit 127) sur nouvelle VM | Race condition cloud-init : Job 3 SSH avant fin de l'install MySQL | `cloud-init status --wait` + `apt install mysql-server` dans [3/8] |
| Autres utilisateurs ne reçoivent pas les rapports | Bot push-only vers un seul `TELEGRAM_CHAT_ID` | `get_all_subscribers()` via `getUpdates`, diffusion à tous les chat IDs |
| IP absente des notifications Telegram | `SERVER_IP` non transmis au script | Lecture depuis tfstate (jq) dans telegram-notify.yml + DEPLOY_MODE dans deploy.yml |
| Deux deploys simultanés | Push déclenche deploy + tfstate push re-déclenche deploy | Annuler le doublon avec `gh run cancel` |

---

## Commandes utiles

```bash
# Push local vers le repo principal
git push ngrassa main:master

# Récupérer le tfstate commité par Terraform (avant de pousser)
git fetch ngrassa && git rebase ngrassa/master

# Déclencher le pipeline complet manuellement
gh workflow run "deploy.yml" --repo ngrassa/pipeline_medical_LEONI

# Déclencher uniquement le rapport Telegram (SAST + Telegram)
gh workflow run telegram-notify.yml --repo ngrassa/pipeline_medical_LEONI --field force_alert=true

# Déclencher uniquement le DAST sur l'IP courante
gh workflow run dast.yml --repo ngrassa/pipeline_medical_LEONI

# Voir les runs en cours
gh run list --repo ngrassa/pipeline_medical_LEONI --limit 10

# Surveiller un run
gh run watch <RUN_ID> --repo ngrassa/pipeline_medical_LEONI

# Logs d'un run
gh run view <RUN_ID> --repo ngrassa/pipeline_medical_LEONI --log-failed

# Annuler un run
gh run cancel <RUN_ID> --repo ngrassa/pipeline_medical_LEONI
```

---

## Points d'attention pour les prochaines sessions

1. **Branche `master` vs `main`** : le repo ngrassa utilise `master`. Toujours pousser avec
   `git push ngrassa main:master`. Le rebase avant push est souvent nécessaire car le Job 2
   Terraform commite le tfstate sur master de façon automatique.

2. **Race condition Terraform tfstate** : après un `terraform apply`, le Job 2 commite
   le tfstate sur master. Si on pousse immédiatement après, git rejette le push → `git fetch ngrassa && git rebase ngrassa/master` avant de pousher.

3. **DEPLOY_MODE** : quand `DEPLOY_MODE=true`, `telegram_alert.py` envoie UNIQUEMENT
   la notification de déploiement et s'arrête. Ne pas oublier de ne PAS l'activer
   dans `telegram-notify.yml`.

4. **getUpdates et offset** : le bot ne fait jamais avancer l'offset Telegram. Si
   quelqu'un a envoyé `/start` très longtemps avant (hors des 100 derniers updates),
   il ne sera plus dans la liste automatiquement. Solution : lui demander de renvoyer `/start`.

5. **AWS Session Token** : les credentials AWS Labs expirent. Si le pipeline échoue
   sur les étapes AWS, renouveler `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `AWS_SESSION_TOKEN` dans les secrets GitHub.

6. **cloud-init sur nouvelle instance** : le `cloud-init status --wait` dans `deploy_app.sh`
   peut bloquer jusqu'à 10 minutes. C'est normal sur une instance fraîchement créée.
