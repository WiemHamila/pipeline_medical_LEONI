# Compte rendu détaillé — Pipeline SAST `tests.yml`
## Plateforme Médicale LEONI

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

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Variables d'environnement globales](#variables-denvironnement-globales)
3. [Ordre d'exécution et dépendances](#ordre-dexécution-et-dépendances)
4. [Job 1 — Analyse statique (Bandit + Safety)](#job-1--analyse-statique-bandit--safety)
5. [Job 2 — Tests unitaires (pytest ≥ 70%)](#job-2--tests-unitaires-pytest--70)
6. [Job 3 — Tests RBAC](#job-3--tests-rbac)
7. [Job 4 — Tests de sécurité (ZAP + injection + JWT)](#job-4--tests-de-sécurité-zap--injection--jwt)
8. [Job 5 — Tests E2E Playwright](#job-5--tests-e2e-playwright)
9. [Job 6 — Tests de performance Locust](#job-6--tests-de-performance-locust)
10. [Job 7 — Audit Lighthouse](#job-7--audit-lighthouse)
11. [Artefacts générés](#artefacts-générés)
12. [Différence SAST vs DAST](#différence-sast-vs-dast)

---

## Vue d'ensemble

Le fichier `tests.yml` est un pipeline de **SAST (Static Application Security Testing)** et de **tests fonctionnels** qui s'exécute **avant le déploiement**, directement sur le code source, sans instance EC2.

```
push / pull_request sur main ou tests-backend
              │
              ▼
┌─────────────────────────────────────────────────────┐
│  Job 1 — static-analysis   (Bandit + Safety)        │
└──────────────────────┬──────────────────────────────┘
                       │ needs: static-analysis
┌──────────────────────▼──────────────────────────────┐
│  Job 2 — unit-tests         (pytest + couverture)   │
└──────────────────────┬──────────────────────────────┘
                       │ needs: unit-tests
┌──────────────────────▼──────────────────────────────┐
│  Job 3 — rbac-tests         (isolation rôles)       │
└──────────────────────┬──────────────────────────────┘
                       │ needs: rbac-tests
┌──────────────────────▼──────────────────────────────┐
│  Job 4 — security-tests     (ZAP + injection + JWT) │
└──────────────────────┬──────────────────────────────┘
                       │ needs: security-tests
┌──────────────────────▼──────────────────────────────┐
│  Job 5 — e2e-tests          (Playwright, 19 tests)  │
└──────────────────────┬──────────────────────────────┘
                       │ needs: e2e-tests
┌──────────────────────▼──────────────────────────────┐
│  Job 6 — performance-tests  (Locust, 50 users)      │
└──────────────────────┬──────────────────────────────┘
                       │ needs: performance-tests
┌──────────────────────▼──────────────────────────────┐
│  Job 7 — lighthouse-audit   (qualité frontend)      │
└─────────────────────────────────────────────────────┘
```

**Déclenchement :**
```yaml
on:
  push:
    branches: [main, tests-backend]
  pull_request:
    branches: [main, tests-backend]
```
Le pipeline se déclenche sur tout push ou pull request vers `main` ou `tests-backend`.

---

## Variables d'environnement globales

Ces variables sont injectées dans **tous les jobs** qui exécutent Django, évitant de répéter la configuration dans chaque job :

| Variable | Valeur | Rôle |
|----------|--------|------|
| `DJANGO_SETTINGS_MODULE` | `medical_platform.settings` | Indique à Django quel fichier de configuration utiliser |
| `SECRET_KEY` | `test-secret-key-ci-github-actions` | Clé secrète Django (valeur fixe pour les tests CI, sans valeur réelle) |
| `DEBUG` | `"True"` | Mode debug activé pour avoir des erreurs détaillées en CI |
| `DB_HOST` | `127.0.0.1` | Adresse du serveur MySQL (service Docker sur le runner) |
| `DB_PORT` | `"3306"` | Port MySQL standard |
| `DB_NAME` | `medical_db` | Nom de la base de données principale |
| `DB_USER` | `root` | Utilisateur MySQL (accès root en CI uniquement) |
| `DB_PASSWORD` | `root` | Mot de passe MySQL CI (non sécurisé, acceptable en CI isolé) |
| `IM_DB_USER` | `root` | Utilisateur pour la seconde base `im_db` |
| `IM_DB_PASSWORD` | `root` | Mot de passe pour `im_db` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | Hôtes autorisés par Django en CI |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Origines CORS autorisées (frontend Vite en dev) |
| `TUNISIESMS_API_KEY` | `fake-key-ci` | Clé SMS fictive (évite les appels API réels en CI) |
| `TUNISIESMS_SENDER` | `LEONI` | Expéditeur SMS (fictif en CI) |
| `TUNISIESMS_API_URL` | `https://app.tunisiesms.tn/api/Api.aspx` | URL API SMS (non appelée en CI) |

> **Note sur le service MySQL** : GitHub Actions ne supporte pas les anchors YAML (`&anchor`, `*anchor`). Le bloc `services: mysql:` doit donc être **répété dans chaque job** qui en a besoin (Jobs 2, 3, 4, 5, 6). C'est une limitation connue de GitHub Actions documentée dans le code.

---

## Ordre d'exécution et dépendances

```
Job 1 (static-analysis)
    └── Job 2 (unit-tests)        ← needs: static-analysis
            └── Job 3 (rbac-tests)        ← needs: unit-tests
                    └── Job 4 (security-tests)  ← needs: rbac-tests
                            └── Job 5 (e2e-tests)       ← needs: security-tests
                                    └── Job 6 (performance-tests)  ← needs: e2e-tests
                                            └── Job 7 (lighthouse-audit)  ← needs: performance-tests
```

Les jobs s'exécutent **en séquence** : si un job échoue, les suivants ne démarrent pas. Cela garantit que les tests les plus rapides (analyse statique) filtrent les problèmes évidents avant de lancer les tests lourds (Playwright, Locust).

---

## Job 1 — Analyse statique (Bandit + Safety)

**Phase 1 du rapport — Durée estimée : ~3 minutes**

Ce job analyse le code source Python **sans l'exécuter**, en cherchant des patterns connus de vulnérabilités.

### Bandit — Analyse des vulnérabilités du code

```bash
bandit -r ./apps -ll --exit-zero -f txt
```

| Option | Signification |
|--------|---------------|
| `-r ./apps` | Analyse récursive du dossier `apps/` (tous les modules Django) |
| `-ll` | Niveau de sévérité minimum : **LOW** (toutes les alertes rapportées) |
| `--exit-zero` | Ne fait pas échouer le pipeline même si des vulnérabilités sont trouvées (mode rapport) |
| `-f txt` | Sortie en format texte lisible |

**Ce que Bandit détecte dans le code Python :**

| Catégorie | Exemples de vulnérabilités détectées |
|-----------|--------------------------------------|
| Injections | `os.system()`, `subprocess.shell=True`, `eval()` |
| Cryptographie faible | MD5, SHA1, DES, clés codées en dur |
| Exposition de données | Mots de passe en clair, tokens dans le code |
| Configuration Django | `DEBUG=True` en production, `SECRET_KEY` faible |
| Gestion des fichiers | Ouvertures de fichiers non sécurisées, path traversal |
| SQL | Requêtes SQL construites par concaténation de chaînes |

**Résultat typique :**
```
>> Issue: [B303:blacklist] Use of MD5 or SHA1 hash function.
   Severity: Medium   Confidence: High
   Location: apps/account/utils.py:45

Total issues (by severity):
   Low: 3, Medium: 1, High: 0
```

### Safety — Audit des dépendances CVE

```bash
pip install -r requirements.txt
safety check --continue-on-error || true
```

Safety compare les versions des packages installés avec la base de données CVE (Common Vulnerabilities and Exposures) publique pour détecter les dépendances ayant des failles de sécurité connues.

**Ce que Safety vérifie :**
- Chaque package dans `requirements.txt`
- Comparaison avec la base [PyUp.io Safety DB](https://github.com/pyupio/safety-db)
- Alertes sur les CVE avec numéro, sévérité et version fixée

**Exemple d'alerte Safety :**
```
-> Vulnerability found in django version 4.2.0
   Vulnerability ID: 51099
   Affected spec: <4.2.7
   ADVISORY: Django 4.2.7 includes fix for CVE-2023-46695
   Fix: upgrade to 4.2.7
```

**Pourquoi `--continue-on-error` ?** En CI, on veut toujours avoir le rapport complet même si des CVE sont détectées. Le pipeline continue pour générer tous les rapports.

---

## Job 2 — Tests unitaires (pytest ≥ 70%)

**Phase 2 du rapport — Durée estimée : ~8 minutes**

Ce job exécute la suite de tests unitaires avec une exigence de couverture de code minimale de **70%**.

### Service MySQL Docker

```yaml
services:
  mysql:
    image: mysql:8.0
    env:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: medical_db
    ports:
      - 3306:3306
    options: >-
      --health-cmd="mysqladmin ping -h localhost"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=5
```

GitHub Actions démarre un conteneur MySQL 8.0 et attend qu'il soit opérationnel (healthcheck) avant d'exécuter les tests. Le conteneur est isolé dans le runner et détruit après le job.

### Création de la base de données

```bash
mysql -h 127.0.0.1 -u root -proot \
  -e "CREATE DATABASE IF NOT EXISTS medical_db CHARACTER SET utf8mb4;"
```

La base `medical_db` est créée avec l'encodage `utf8mb4` (support Unicode complet, y compris les caractères arabes des patients).

### Migrations Django

```bash
python manage.py migrate --run-syncdb
```

`--run-syncdb` crée les tables pour les modèles qui n'ont pas de migrations explicites (utile en développement ou pour les modèles ajoutés sans `makemigrations`).

### Exécution pytest avec couverture

```bash
python -m pytest apps/ \
  --cov=apps \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-fail-under=70 \
  -q
```

| Option | Signification |
|--------|---------------|
| `apps/` | Dossier racine des tests (tous les modules Django) |
| `--cov=apps` | Mesure la couverture du code dans `apps/` |
| `--cov-report=term-missing` | Affiche les lignes non couvertes dans le terminal |
| `--cov-report=xml:coverage.xml` | Génère un rapport XML pour les outils externes (SonarQube, Codecov) |
| `--cov-fail-under=70` | **Fait échouer le job si la couverture est inférieure à 70%** |
| `-q` | Mode silencieux (affiche seulement les résultats) |

**Couverture attendue :** 1 039 tests dans 42 fichiers, couvrant les apps : `account`, `consultations`, `stock`, `planning`, `employees`, `embauche`, `surveillance_speciale`, `hsee`, etc.

**Rapport de couverture (extrait typique) :**
```
apps/account/models.py          95%   45-47
apps/consultations/views.py     78%   120-135, 200
apps/stock/serializers.py       82%   88-90
----------------------------------------------
TOTAL                           73%

47 passed, 2 skipped in 45.3s
```

### Artefact généré

```yaml
- name: Publier le rapport de couverture
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
```

Le fichier `coverage.xml` est sauvegardé comme artefact GitHub Actions, téléchargeable après le run.

---

## Job 3 — Tests RBAC

**Phase 3 du rapport — Durée estimée : ~5 minutes**

RBAC = **Role-Based Access Control** — Tests de l'isolation des permissions par rôle et par site dans la plateforme médicale.

### Contexte métier

La plateforme LEONI gère plusieurs sites (Mateur, Sousse, etc.). Un utilisateur du **Site A** ne doit jamais pouvoir accéder aux données du **Site B**, et les rôles (Médecin, Infirmier, RH, HSEE) ont des droits strictement séparés.

### Tests RBAC — isolation des rôles (étape 1)

```bash
python -m pytest apps/account/test_rbac.py \
                 apps/account/test_permissions.py \
                 apps/account/test_isolation_sites.py \
                 --override-ini="addopts=" \
                 -v --tb=short
```

| Fichier de test | Ce qui est testé |
|-----------------|------------------|
| `test_rbac.py` | Matrice des droits : qui peut faire quoi (lecture, écriture, suppression) par rôle |
| `test_permissions.py` | Vérification des permissions Django DRF (`IsAuthenticated`, permissions custom) |
| `test_isolation_sites.py` | Un utilisateur du site A ne voit PAS les données du site B |

**Exemple de scénario test d'isolation :**
```python
def test_infirmier_site_a_ne_voit_pas_donnees_site_b(self):
    # Créer patient au site B
    patient_site_b = Patient.objects.create(site=self.site_b, ...)
    
    # Se connecter en tant qu'infirmier du site A
    self.client.force_authenticate(user=self.infirmier_site_a)
    
    # L'infirmier du site A ne doit pas voir le patient du site B
    response = self.client.get('/api/patients/')
    ids = [p['id'] for p in response.data['results']]
    self.assertNotIn(patient_site_b.id, ids)  # doit être absent
```

**Option `--override-ini="addopts="`** : Surcharge la configuration `pytest.ini` qui pourrait ajouter des options supplémentaires non souhaitées lors de l'exécution d'un sous-ensemble de tests.

### Tests RBAC — comptes et viewsets (étape 2)

```bash
python -m pytest apps/account/test_account_viewsets.py \
                 apps/account/test_auth_views.py \
                 -v --tb=short
```

| Fichier de test | Ce qui est testé |
|-----------------|------------------|
| `test_account_viewsets.py` | CRUD sur les comptes utilisateurs selon le rôle (admin peut créer, infirmier ne peut pas) |
| `test_auth_views.py` | Login, logout, refresh token, changement de mot de passe forcé |

**Option `--tb=short`** : Affiche uniquement le début et la fin du traceback en cas d'échec, pour une sortie plus lisible en CI.

---

## Job 4 — Tests de sécurité (ZAP + injection + JWT)

**Phase 4 du rapport — Durée estimée : ~12 minutes**

Ce job combine trois types de tests de sécurité : scan passif ZAP, tests d'injection via pytest, et tests JWT.

### Démarrage du backend Django

```bash
python manage.py runserver 0.0.0.0:8000 &
sleep 8
curl -f http://localhost:8000/api/account/login/ \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"x","password":"x"}' \
  --max-time 10 || echo "Backend démarré (réponse 400 attendue)"
```

Le backend Django est lancé en arrière-plan (`&`) sur le runner CI. Une vérification `curl` attend 8 secondes puis teste que l'endpoint répond (HTTP 400 = identifiants invalides = normal et attendu). Cela confirme que Django est démarré avant de lancer ZAP.

### OWASP ZAP Baseline (scan passif)

```yaml
uses: zaproxy/action-baseline@v0.12.0
with:
  target: 'http://localhost:8000'
  rules_file_name: '.zap/rules.tsv'
  fail_action: false
  allow_issue_writing: false
```

ZAP tourne comme un proxy entre lui-même et l'application, **sans envoyer d'attaques actives**. Il analyse les réponses HTTP pour détecter des problèmes de configuration.

| Paramètre | Valeur | Signification |
|-----------|--------|---------------|
| `target` | `http://localhost:8000` | Application Django locale sur le runner |
| `rules_file_name` | `.zap/rules.tsv` | Fichier de règles personnalisées (WARN/IGNORE/FAIL par alerte ID) |
| `fail_action` | `false` | Ne fait pas échouer le pipeline sur les alertes ZAP |
| `allow_issue_writing` | `false` | Ne crée pas d'issues GitHub automatiques |

**Fichier `.zap/rules.tsv`** : Permet de configurer finement le comportement ZAP pour chaque type d'alerte :
```tsv
10015	IGNORE	(Incomplete or No Cache-control Header Set)
10016	WARN	(Web Browser XSS Protection Not Enabled)
10020	WARN	(X-Frame-Options Header)
10021	WARN	(X-Content-Type-Options Header Missing)
```

### Tests d'injection SQL et XSS (pytest)

```bash
python -m pytest apps/account/test_injection.py --override-ini="addopts=" -v --tb=short
```

Ces tests vérifient que les entrées malicieuses sont correctement rejetées ou neutralisées par Django.

**Exemples de tests d'injection typiques :**
```python
class TestInjectionSQL(TestCase):
    def test_login_sql_injection(self):
        # Payload classique de bypass d'authentification
        response = self.client.post('/api/account/login/', {
            'username': "' OR '1'='1",
            'password': "' OR '1'='1"
        })
        # Django ORM paramétrisé → jamais vulnérable à SQLi directement
        self.assertEqual(response.status_code, 400)  # rejeté

class TestXSS(TestCase):
    def test_champ_nom_xss(self):
        payload_xss = '<script>alert("XSS")</script>'
        # Vérifier que le payload est encodé dans la réponse
        response = self.client.post('/api/employees/', {'nom': payload_xss})
        self.assertNotIn('<script>', response.content.decode())
```

**Pourquoi Django est résistant à SQLi par défaut ?** L'ORM Django utilise des requêtes paramétrées. Le SQL est séparé des données, rendant l'injection SQL quasi impossible via les vues standard.

### Tests sécurité JWT

```bash
python -m pytest apps/account/test_jwt_security.py \
                 apps/account/test_jwt_advanced.py \
                 apps/account/test_token_fix.py \
                 -v --tb=short
```

| Fichier | Ce qui est testé |
|---------|-----------------|
| `test_jwt_security.py` | Tokens expirés, signatures invalides, algorithme HS256 obligatoire |
| `test_jwt_advanced.py` | Rotation des refresh tokens, blacklist après rotation, multi-session |
| `test_token_fix.py` | Corrections de bugs spécifiques liés aux tokens (régressions) |

**Scénarios JWT testés :**
```python
def test_token_expire_apres_120_minutes(self):
    # Simuler un token créé il y a 121 minutes
    with freeze_time("2024-01-01 10:00:00"):
        token = obtenir_token(self.user)
    with freeze_time("2024-01-01 12:01:00"):  # +121 min
        response = self.client.get('/api/consultations/', 
                                   HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 401)  # expiré

def test_refresh_token_blackliste_apres_rotation(self):
    # Utiliser le refresh token une fois
    response1 = self.client.post('/api/account/refresh/', {'refresh': self.refresh_token})
    nouveau_refresh = response1.data['refresh']
    
    # Réutiliser l'ancien refresh token → doit être rejeté (blacklisté)
    response2 = self.client.post('/api/account/refresh/', {'refresh': self.refresh_token})
    self.assertEqual(response2.status_code, 401)
```

### Artefact généré

```yaml
- name: Publier rapport ZAP
  uses: actions/upload-artifact@v4
  with:
    name: zap-report
    path: report_html.html
```

Le rapport HTML de ZAP est sauvegardé, contenant toutes les alertes détectées avec leur niveau de sévérité, description et recommandation de correction.

---

## Job 5 — Tests E2E Playwright

**Phase 5 du rapport — Durée estimée : ~15 minutes**

Tests de bout en bout (End-to-End) : Playwright simule un vrai navigateur Chromium qui interagit avec l'application comme un utilisateur réel.

### Checkout multi-répertoires

```yaml
- name: Récupérer le backend
  uses: actions/checkout@v4
  with:
    path: backend        # code backend dans ./backend/

- name: Cloner le frontend
  uses: actions/checkout@v4
  with:
    repository: SafaNj/frontend-service-medical
    path: frontend       # code frontend dans ./frontend/
    token: ${{ secrets.GITHUB_TOKEN }}
  continue-on-error: true  # ne bloque pas si le repo frontend est privé/inaccessible
```

Deux dépôts séparés sont clonés : le backend (ce repo) et le frontend (repo externe). `continue-on-error: true` permet au job de continuer même si le frontend est dans un dépôt privé auquel le runner n'a pas accès.

### Installation de Playwright

```bash
npx playwright install --with-deps chromium
```

Installe le navigateur Chromium et toutes ses dépendances système (codecs, bibliothèques graphiques) nécessaires pour faire tourner un vrai navigateur en mode headless sur le runner Ubuntu.

### Chargement des fixtures

```bash
python manage.py loaddata fixtures/test_users.json || echo "Pas de fixtures"
```

Charge des utilisateurs de test prédéfinis (médecin, infirmier, RH, admin) avec leurs mots de passe et droits. Ces utilisateurs sont utilisés par Playwright pour se connecter et tester les fonctionnalités.

### Démarrage des deux services

```bash
cd backend && python manage.py runserver 0.0.0.0:8000 &
cd frontend && npm run dev &
sleep 12  # attendre que les deux soient prêts
```

Backend Django (port 8000) et frontend Vite (port 5173) démarrent simultanément en arrière-plan. `sleep 12` laisse le temps au compilateur Vite de bundler et au serveur Django de charger.

### Exécution des tests Playwright

```bash
npx playwright test \
  tests/e2e/metier_e2e.spec.js \
  tests/e2e/infirmier_stock_e2e.spec.js \
  tests/e2e/infirmier_passages_e2e.spec.js \
  --reporter=html
```

**19 tests E2E répartis en 3 fichiers :**

| Fichier | Scénarios testés |
|---------|-----------------|
| `metier_e2e.spec.js` | Connexion médecin, création consultation, ordonnance, fiche aptitude |
| `infirmier_stock_e2e.spec.js` | Connexion infirmier, ajout médicament au stock, mouvement de stock |
| `infirmier_passages_e2e.spec.js` | Création liste de passage, ajout collaborateur, planification visite |

**Exemple de test Playwright :**
```javascript
test('médecin peut créer une consultation', async ({ page }) => {
  // Connexion
  await page.goto('http://localhost:5173/login');
  await page.fill('[data-testid="username"]', 'medecin_mateur');
  await page.fill('[data-testid="password"]', 'test1234');
  await page.click('[data-testid="login-btn"]');
  
  // Navigation vers consultations
  await page.click('text=Consultations');
  await page.click('text=Nouvelle consultation');
  
  // Remplir le formulaire
  await page.fill('[data-testid="matricule"]', 'EMP001');
  await page.click('[data-testid="motif-selector"]');
  await page.click('text=Médecine générale');
  
  // Soumettre
  await page.click('[data-testid="submit-btn"]');
  
  // Vérifier
  await expect(page.locator('.success-toast')).toBeVisible();
});
```

**`continue-on-error: true`** sur les étapes frontend : si le repo frontend est inaccessible ou que Playwright échoue, le pipeline continue avec les jobs suivants.

### Artefact généré

Le rapport HTML Playwright (`playwright-report/index.html`) contient pour chaque test : statut (pass/fail), captures d'écran en cas d'échec, traces réseau et vidéos.

---

## Job 6 — Tests de performance Locust

**Phase 6 du rapport — Durée estimée : ~10 minutes**

Locust simule **50 utilisateurs virtuels simultanés** sur 5 endpoints critiques de l'application pendant 60 secondes.

### Installation de Locust

```bash
pip install locust
```

Locust est un outil Python de test de charge distribué. Il génère des requêtes HTTP à partir de scénarios définis dans `locustfile.py`.

### Lancement du test de charge

```bash
python -m locust -f locustfile.py \
  --host=http://localhost:8000 \
  --headless \
  -u 50 \
  -r 5 \
  --run-time 60s \
  --csv=locust-results \
  --html=locust-report.html
```

| Option | Valeur | Signification |
|--------|--------|---------------|
| `--headless` | — | Pas d'interface web, mode script pur |
| `-u 50` | 50 | Nombre d'utilisateurs simultanés au maximum |
| `-r 5` | 5 users/sec | Montée en charge progressive (5 nouveaux users par seconde) |
| `--run-time 60s` | 60s | Durée totale du test |
| `--csv=locust-results` | — | Génère 4 fichiers CSV de résultats |
| `--html=locust-report.html` | — | Rapport HTML avec graphiques |

**Fichier `locustfile.py` — 5 endpoints testés :**
```python
class MedicalUser(HttpUser):
    wait_time = between(1, 3)  # pause entre requêtes (simuler un vrai user)
    
    @task(3)
    def login(self):
        self.client.post("/api/account/login/", json={...})
    
    @task(2)
    def liste_consultations(self):
        self.client.get("/api/consultations/", headers=self.auth_header)
    
    @task(2)
    def liste_employees(self):
        self.client.get("/api/employees/", headers=self.auth_header)
    
    @task(1)
    def stock_medicaments(self):
        self.client.get("/api/stock/", headers=self.auth_header)
    
    @task(1)
    def planning(self):
        self.client.get("/api/planning/", headers=self.auth_header)
```

**Métriques collectées et objectifs :**

| Métrique | Description | Objectif |
|----------|-------------|----------|
| RPS (Req/sec) | Requêtes traitées par seconde | ≥ 20 RPS |
| Temps réponse médian | 50% des requêtes | < 500 ms |
| Temps réponse P95 | 95% des requêtes | < 2 000 ms |
| Taux d'erreur | % requêtes avec erreur HTTP | < 1% |

### Résultats affichés

```bash
cat locust-results_stats.csv
```

Affiche le tableau de bord des résultats par endpoint : min/max/médian/P95 du temps de réponse, nombre de requêtes, erreurs.

**Exemple de sortie CSV :**
```
Type,Name,Request Count,Failure Count,Median Response Time,95% Response Time,Average Response Time
GET,/api/consultations/,1247,2,145,420,178
POST,/api/account/login/,412,0,89,210,102
GET,/api/employees/,831,1,167,580,201
```

### Artefacts générés

- `locust-results_stats.csv` — statistiques par endpoint
- `locust-results_stats_history.csv` — évolution des métriques dans le temps
- `locust-results_failures.csv` — détail des requêtes en échec
- `locust-report.html` — rapport graphique avec courbes de charge

---

## Job 7 — Audit Lighthouse

**Phase 7 du rapport — Durée estimée : ~3 minutes**

Lighthouse audite la **qualité du frontend** : performance, accessibilité, bonnes pratiques web, SEO.

> **Note** : Dans la version actuelle de ce pipeline, l'audit Lighthouse affiche les résultats d'un audit réalisé **en local** (pas en CI). Le job publie la configuration `.lighthouserc.json` et affiche les scores mesurés.

### Vérification de la configuration

```bash
cat .lighthouserc.json
```

**Contenu de `.lighthouserc.json` :**
```json
{
  "ci": {
    "assert": {
      "assertions": {
        "categories:performance": ["warn", {"minScore": 0.7}],
        "categories:accessibility": ["warn", {"minScore": 0.7}],
        "categories:best-practices": ["error", {"minScore": 0.9}],
        "categories:seo": ["warn", {"minScore": 0.7}]
      }
    }
  }
}
```

**Seuils définis :**

| Catégorie | Seuil | Niveau | Score obtenu |
|-----------|-------|--------|-------------|
| Performance | ≥ 70% | WARN | 88 / 100 ✓ |
| Accessibility | ≥ 70% | WARN | 77 / 100 ✓ |
| Best Practices | ≥ **90%** | **ERROR** | 96 / 100 ✓ |
| SEO | ≥ 70% | WARN | 83 / 100 ✓ |

- **WARN** : En dessous du seuil → avertissement, le pipeline continue
- **ERROR** : En dessous du seuil → le pipeline échoue

Le seuil le plus strict est **Best Practices à 90%** : si l'application utilise des APIs dépréciées, HTTP au lieu de HTTPS, ou viole les recommandations de sécurité du navigateur, le pipeline échoue.

### Ce que Lighthouse mesure

| Catégorie | Critères évalués |
|-----------|-----------------|
| **Performance** | First Contentful Paint, Time to Interactive, Largest Contentful Paint, Total Blocking Time |
| **Accessibility** | Contraste des couleurs, attributs ARIA, structure des titres, labels de formulaire |
| **Best Practices** | HTTPS, Console errors, APIs obsolètes, images optimisées |
| **SEO** | Meta descriptions, viewport, liens crawlables, robots.txt |

### Artefact généré

```yaml
- name: Publier config Lighthouse
  uses: actions/upload-artifact@v4
  with:
    name: lighthouse-config
    path: .lighthouserc.json
```

---

## Artefacts générés

Tous les artefacts sont accessibles dans **GitHub → Actions → run concerné → Artifacts** :

| Artefact | Fichier(s) | Job générateur | Durée de rétention |
|----------|-----------|----------------|-------------------|
| `coverage-report` | `coverage.xml` | Job 2 — unit-tests | 90 jours |
| `zap-report` | `report_html.html` | Job 4 — security-tests | 90 jours |
| `playwright-report` | `index.html` + captures | Job 5 — e2e-tests | 90 jours |
| `locust-results` | `*.csv` + `locust-report.html` | Job 6 — performance | 90 jours |
| `lighthouse-config` | `.lighthouserc.json` | Job 7 — lighthouse | 90 jours |

---

## Différence SAST vs DAST

Ce pipeline (`tests.yml`) est du **SAST + tests fonctionnels**. Il se distingue du DAST (`dast.yml`) comme suit :

| Critère | SAST — `tests.yml` | DAST — `dast.yml` |
|---------|-------------------|--------------------|
| **Quand s'exécute-t-il ?** | Avant déploiement (sur le code) | Après déploiement (sur l'app en live) |
| **Infrastructure requise** | Aucune (runner GitHub seul) | Instance EC2 en cours d'exécution |
| **Détection SQLi** | pytest avec mocks/DB locale | curl avec payloads réels sur API live |
| **OWASP ZAP** | Scan passif baseline sur `localhost` | Scan passif **et** actif sur IP publique |
| **JWT** | Tests unitaires Python (freeze_time) | Tokens envoyés à l'API en production |
| **Brute-force** | Non testé | 10 tentatives réelles sur l'API |
| **CORS** | Non testé | Origin `evil.example.com` sur l'API live |
| **Performance** | Locust sur localhost (50 users) | Non testé |
| **Qualité frontend** | Lighthouse (scores mesurés en local) | Non testé |
| **Analyse code** | Bandit + Safety (CVE, patterns) | Non applicable |
| **Tests métier** | Playwright (19 scénarios utilisateur) | Non testé |

**Complémentarité :**
- `tests.yml` détecte les problèmes **tôt dans le développement** (avant merge)
- `dast.yml` valide la **sécurité en conditions réelles** (après déploiement)
- Les deux ensemble forment une chaîne de qualité et sécurité complète
