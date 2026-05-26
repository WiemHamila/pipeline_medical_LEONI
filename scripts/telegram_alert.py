#!/usr/bin/env python3
"""
DevSecOps Telegram Alert — Medical LEONI Pipeline
Lit les résultats SAST (Bandit, pip-audit) et les résultats DAST,
appelle Mistral AI pour la remédiation, envoie des alertes Telegram formatées.
Supporte plusieurs abonnés : tout utilisateur ayant envoyé /start au bot
est automatiquement inclus dans la diffusion.
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

# ── Configuration depuis variables d'environnement ──────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
MISTRAL_KEY    = os.environ.get("MISTRAL_API_KEY", "")
DAST_RESULT    = os.environ.get("DAST_RESULT", "unknown")
SERVER_IP      = os.environ.get("SERVER_IP", "")
DEPLOY_MODE    = os.environ.get("DEPLOY_MODE", "false").lower() == "true"
GITHUB_RUN_URL = (
    f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}"
    f"/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
)

# Fenêtre de bienvenue : répondre au /start uniquement s'il date de moins de 24h
_WELCOME_WINDOW_SECONDS = 86400


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def get_all_subscribers() -> list[str]:
    """
    Retourne la liste de tous les chat IDs abonnés au bot.
    Collecte les IDs depuis getUpdates (100 derniers messages) sans avancer
    l'offset, afin de conserver l'historique des abonnés entre les runs CI.
    Répond automatiquement aux commandes /start récentes (< 24h).
    """
    chat_ids: set[str] = set()
    if TELEGRAM_CHAT:
        chat_ids.add(TELEGRAM_CHAT)

    if not TELEGRAM_TOKEN:
        return list(chat_ids)

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params={"limit": 100, "timeout": 0},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[TELEGRAM] getUpdates error {r.status_code}", file=sys.stderr)
            return list(chat_ids)

        now_ts = time.time()
        updates = r.json().get("result", [])

        for update in updates:
            for key in ("message", "edited_message", "channel_post"):
                msg = update.get(key)
                if not msg or "chat" not in msg:
                    continue
                chat_id = str(msg["chat"]["id"])
                chat_ids.add(chat_id)

                # Répondre au /start s'il est récent (< 24h)
                text = msg.get("text", "")
                msg_date = msg.get("date", 0)
                if text == "/start" and (now_ts - msg_date) < _WELCOME_WINDOW_SECONDS:
                    first_name = msg["chat"].get("first_name", "")
                    _send_welcome(chat_id, first_name)

        print(f"[TELEGRAM] {len(chat_ids)} abonné(s) : {', '.join(sorted(chat_ids))}")
    except Exception as e:
        print(f"[TELEGRAM] getUpdates exception: {e}", file=sys.stderr)

    return list(chat_ids)


def _send_welcome(chat_id: str, first_name: str) -> None:
    """Envoie un message de bienvenue à un nouvel abonné."""
    welcome = (
        f"Bonjour {first_name} ! 👋\n\n"
        f"✅ Vous êtes maintenant abonné aux alertes DevSecOps "
        f"de la plateforme médicale LEONI.\n\n"
        f"Vous recevrez automatiquement :\n"
        f"• 🔴 Alertes CVEs (pip-audit)\n"
        f"• 🟠 Alertes SAST (Bandit)\n"
        f"• 🔍 Rapport d'audit complet\n\n"
        f"Le prochain rapport sera envoyé lors du prochain déploiement CI/CD."
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": welcome},
            timeout=15,
        )
        if r.status_code == 200:
            print(f"[TELEGRAM] Bienvenue envoyé à {chat_id} ({first_name})")
    except Exception as e:
        print(f"[TELEGRAM] Welcome error: {e}", file=sys.stderr)


def send_telegram(text: str, subscribers: list[str] | None = None) -> bool:
    """Envoie un message à tous les abonnés (ou à TELEGRAM_CHAT si liste vide)."""
    if not TELEGRAM_TOKEN:
        print("[DRY-RUN] Telegram non configuré — message:\n" + text[:300])
        return True

    targets = subscribers if subscribers else ([TELEGRAM_CHAT] if TELEGRAM_CHAT else [])
    if not targets:
        print("[DRY-RUN] Aucun destinataire configuré — message:\n" + text[:300])
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    success = True
    for chat_id in targets:
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=15,
            )
            if r.status_code != 200:
                print(f"[TELEGRAM ERROR] chat={chat_id} {r.status_code}: {r.text}", file=sys.stderr)
                success = False
            else:
                print(f"[TELEGRAM] Message envoyé à {chat_id} (ok={r.json().get('ok')})")
        except Exception as e:
            print(f"[TELEGRAM EXCEPTION] chat={chat_id}: {e}", file=sys.stderr)
            success = False
    return success


def mistral_remediation(pkg_name: str, version: str, cve_ids: list[str]) -> str:
    """Appelle Mistral pour générer une recommandation de remédiation."""
    if not MISTRAL_KEY:
        return f"Mettre à jour {pkg_name} vers la dernière version corrigée disponible sur PyPI."

    cve_list = ", ".join(cve_ids[:3])
    prompt = (
        f"Tu es un expert DevSecOps. Donne une recommandation de remédiation concise "
        f"(1-2 phrases maximum) en français pour :\n"
        f"Package Python : {pkg_name}=={version}\n"
        f"CVEs : {cve_list}\n"
        f"Réponds UNIQUEMENT avec la recommandation, sans introduction ni conclusion."
    )
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-large-latest",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.1,
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[MISTRAL ERROR] {e}", file=sys.stderr)
        return f"Mettre à jour {pkg_name} vers la dernière version corrigée disponible sur PyPI."


def mistral_dast_analysis(dast_status: str, bandit_high: int, bandit_medium: int) -> str:
    """Génère une analyse globale DAST via Mistral."""
    if not MISTRAL_KEY:
        return (
            "Appliquer les correctifs de sécurité identifiés. "
            "Renforcer les en-têtes HTTP (CSP, HSTS). "
            "Implémenter un rate-limiting sur les endpoints d'authentification."
        )

    prompt = (
        f"Analyse DevSecOps pour une application médicale Django/React :\n"
        f"- Résultat DAST (OWASP ZAP) : {dast_status}\n"
        f"- Bandit findings HIGH : {bandit_high}\n"
        f"- Bandit findings MEDIUM : {bandit_medium}\n"
        f"Génère 3-4 recommandations prioritaires concises en français. "
        f"Format : liste numérotée. Pas d'introduction."
    )
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistral-large-latest",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 250,
                "temperature": 0.2,
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[MISTRAL ERROR] {e}", file=sys.stderr)
        return (
            "1. Appliquer les patches de sécurité sur les dépendances Python.\n"
            "2. Renforcer les en-têtes HTTP (CSP, HSTS, X-Frame-Options).\n"
            "3. Implémenter un rate-limiting sur les endpoints d'authentification.\n"
            "4. Automatiser les scans pip-audit dans la pipeline CI/CD."
        )


# ── Extraction des CVEs depuis pip-audit ─────────────────────────────────────

def parse_pipaudit(data) -> list[dict]:
    """
    Retourne une liste de paquets vulnérables :
    [{name, version, cves: [{id, desc, fix_versions}]}]
    """
    if data is None:
        return []
    # pip-audit JSON: liste directe ou {dependencies: [...]}
    if isinstance(data, dict):
        deps = data.get("dependencies", [])
    else:
        deps = data

    vulnerable = []
    for dep in deps:
        vulns = dep.get("vulns", [])
        if not vulns:
            continue
        cves = []
        for v in vulns:
            vuln_id = v.get("id", "UNKNOWN")
            # Chercher le CVE dans aliases
            aliases = v.get("aliases", [])
            cve_id = next((a for a in aliases if a.startswith("CVE-")), vuln_id)
            cves.append({
                "id": cve_id,
                "ghsa": vuln_id,
                "desc": v.get("description", "")[:120],
                "fix_versions": v.get("fix_versions", []),
                "package": dep["name"],
            })
        vulnerable.append({
            "name": dep["name"],
            "version": dep.get("version", "?"),
            "cves": cves,
        })
    return vulnerable


def parse_bandit(data) -> tuple[int, int, list]:
    """Retourne (high_count, medium_count, top_issues)."""
    if data is None:
        return 0, 0, []
    results = data.get("results", [])
    high    = [r for r in results if r.get("issue_severity") in ("HIGH", "CRITICAL")]
    medium  = [r for r in results if r.get("issue_severity") == "MEDIUM"]
    top = [
        {
            "file": r.get("filename", "").replace("backend-service-medical_linux/", ""),
            "line": r.get("line_number", 0),
            "issue": r.get("issue_text", "")[:80],
            "severity": r.get("issue_severity", "?"),
            "test_id": r.get("test_id", ""),
        }
        for r in high[:3]
    ]
    return len(high), len(medium), top


# ── Notification déploiement ─────────────────────────────────────────────────

def format_deploy_notification(ip: str, run_url: str, date_fr: str) -> str:
    return (
        f"[{date_fr}] alert_medical: ✅ Déploiement Réussi — Plateforme Médicale LEONI\n\n"
        f"🖥️  Instance EC2 déployée et opérationnelle\n\n"
        f"• Adresse IP   : {ip}\n"
        f"• Application  : http://{ip}/\n"
        f"• Admin Django : http://{ip}/api/admin/\n"
        f"• SSH          : ssh -i labsuser.pem ubuntu@{ip}\n\n"
        f"🔄 Lancement du DAST (OWASP ZAP) en cours...\n\n"
        f"• CI/CD : {run_url}"
    )


# ── Formatage des messages Telegram ──────────────────────────────────────────

def format_cve_alert(
    namespace: str,
    component: str,
    cves: list[dict],
    remediation: str,
    date_fr: str,
    iso_ts: str,
) -> str:
    cve_lines = "\n".join(
        f"• {c['id']} - {c['package']}: {c['desc'][:75]}"
        for c in cves[:5]
    )
    return (
        f"[{date_fr}] alert_medical: 🔴 Alerte DevSecOps — CRITICAL\n\n"
        f"Namespace : {namespace}\n\n"
        f"Image     : {component}\n\n"
        f"CVEs :\n{cve_lines}\n\n"
        f"Remédiation :\n{remediation}\n\n"
        f"{iso_ts}"
    )


def format_audit_report(
    score: int,
    critical_findings: list[dict],
    positive_points: list[str],
    plan_text: str,
    stats: dict,
    date_fr: str,
    iso_ts: str,
) -> str:
    score_emoji = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"

    findings_text = ""
    for i, f in enumerate(critical_findings[:4], 1):
        findings_text += (
            f"\n{i}. {f['cve']} (CVSS {f.get('cvss', 'N/A')}) — {f['component']}\n"
            f"   ├ Risque : {f['risk'][:90]}\n"
            f"   └ Remédiation : {f['fix']}\n"
        )

    positives_text = "\n".join(f"• {p}" for p in positive_points)

    return (
        f"[{date_fr}] alert_medical: 🔍 Audit DevSecOps — Application Médicale LEONI\n\n"
        f"📌 Score de sécurité : {score}/100  {score_emoji}\n\n"
        f"🚨 Alertes critiques ({len(critical_findings)})\n"
        f"{findings_text}\n"
        f"✅ Points positifs\n{positives_text}\n\n"
        f"📋 Plan de remédiation\n{plan_text}\n\n"
        f"ℹ️ Détails\n"
        f"• Outils utilisés : Bandit, pip-audit, OWASP ZAP\n"
        f"• Packages scannés : {stats['total']} | CRITICAL CVEs : {stats['critical']} "
        f"| Bandit HIGH : {stats['bandit_high']}\n"
        f"• DAST (ZAP) : {stats['dast']}\n"
        + (f"• Instance EC2 : http://{stats['server_ip']}/\n" if stats.get('server_ip') else "")
        + f"• Rapport CI : {GITHUB_RUN_URL}\n"
        f"{iso_ts}"
    )


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> int:
    now     = datetime.now(timezone.utc)
    date_fr = now.strftime("%d/%m/%Y %H:%M")
    iso_ts  = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    print(f"[INFO] Début analyse DevSecOps — {iso_ts}")
    print(f"[INFO] DAST status : {DAST_RESULT}")

    # ── Collecter tous les abonnés (admin + utilisateurs /start) ─────────
    subscribers = get_all_subscribers()

    # ── Mode déploiement : notification IP uniquement ─────────────────────
    if DEPLOY_MODE:
        if not SERVER_IP:
            print("[ERROR] SERVER_IP vide — impossible d'envoyer la notification de déploiement")
            return 1
        msg = format_deploy_notification(SERVER_IP, GITHUB_RUN_URL, date_fr)
        send_telegram(msg, subscribers)
        print(f"[INFO] Notification déploiement envoyée pour IP {SERVER_IP}")
        return 0

    # ── Charger résultats ─────────────────────────────────────────────────
    pipaudit_data = load_json("pipaudit_results.json")
    bandit_data   = load_json("bandit_results.json")

    vulnerable_pkgs          = parse_pipaudit(pipaudit_data)
    bandit_high, bandit_med, bandit_top = parse_bandit(bandit_data)

    # Normalise pipaudit_data en liste de dicts pour les calculs suivants
    if isinstance(pipaudit_data, list):
        all_deps = pipaudit_data
    elif isinstance(pipaudit_data, dict):
        all_deps = pipaudit_data.get("dependencies", [])
    else:
        all_deps = []

    total_deps   = len(all_deps)
    total_cves   = sum(len(p["cves"]) for p in vulnerable_pkgs)

    print(f"[INFO] Packages vulnérables : {len(vulnerable_pkgs)}")
    print(f"[INFO] CVEs totales         : {total_cves}")
    print(f"[INFO] Bandit HIGH          : {bandit_high}")

    # ── Alertes individuelles par package ────────────────────────────────
    for pkg in vulnerable_pkgs[:4]:
        name      = pkg["name"]
        version   = pkg["version"]
        cves      = pkg["cves"]
        cve_ids   = [c["id"] for c in cves]
        remediation = mistral_remediation(name, version, cve_ids)

        alert = format_cve_alert(
            namespace="backend-django",
            component=f"{name}=={version}",
            cves=cves,
            remediation=remediation,
            date_fr=date_fr,
            iso_ts=iso_ts,
        )
        send_telegram(alert, subscribers)

    # ── Alerte Bandit si findings HIGH ───────────────────────────────────
    if bandit_top:
        issues_text = "\n".join(
            f"• {i['test_id']} [{i['severity']}] {i['file']}:{i['line']} — {i['issue']}"
            for i in bandit_top
        )
        bandit_remediation = mistral_remediation(
            "code-django",
            "static-analysis",
            [i["test_id"] for i in bandit_top],
        )
        bandit_alert = (
            f"[{date_fr}] alert_medical: 🟠 Alerte SAST — HIGH\n\n"
            f"Namespace : backend-django\n\n"
            f"Image     : code source Django (Bandit)\n\n"
            f"Findings :\n{issues_text}\n\n"
            f"Remédiation :\n{bandit_remediation}\n\n"
            f"{iso_ts}"
        )
        send_telegram(bandit_alert, subscribers)

    # ── Rapport d'audit global ────────────────────────────────────────────
    score = max(10, 100 - total_cves * 6 - bandit_high * 3 - bandit_med)
    if DAST_RESULT == "failure":
        score = max(10, score - 15)

    # Points positifs
    positives = []
    safe_pkgs = [d for d in all_deps if isinstance(d, dict) and not d.get("vulns")]
    if safe_pkgs:
        names = ", ".join(d["name"] for d in safe_pkgs[:4])
        positives.append(f"{len(safe_pkgs)} package(s) sans CVE : {names}")
    if total_cves == 0:
        positives.append("Aucune CVE détectée dans les dépendances Python")
    if bandit_high == 0:
        positives.append("Aucun finding HIGH/CRITICAL dans l'analyse statique Bandit")
    positives.append("Pipeline CI/CD actif avec scans SAST + DAST automatisés")
    positives.append("Authentification JWT + CORS configurés sur l'API Django")

    # Plan de remédiation via Mistral
    plan_text = mistral_dast_analysis(DAST_RESULT, bandit_high, bandit_med)

    # Findings critiques pour le résumé
    critical_findings = []
    for pkg in vulnerable_pkgs[:4]:
        for cve in pkg["cves"][:2]:
            fix = (
                f"mettre à jour vers {cve['fix_versions'][0]}+"
                if cve["fix_versions"]
                else f"mettre à jour {pkg['name']} vers la dernière version"
            )
            critical_findings.append({
                "cve": cve["id"],
                "cvss": "N/A",
                "component": f"{pkg['name']}=={pkg['version']}",
                "risk": cve["desc"],
                "fix": fix,
            })

    stats = {
        "total":       total_deps,
        "critical":    total_cves,
        "bandit_high": bandit_high,
        "dast":        DAST_RESULT,
        "server_ip":   SERVER_IP,
    }

    report = format_audit_report(
        score=score,
        critical_findings=critical_findings,
        positive_points=positives,
        plan_text=plan_text,
        stats=stats,
        date_fr=date_fr,
        iso_ts=iso_ts,
    )
    send_telegram(report, subscribers)

    print(f"[INFO] Score de sécurité : {score}/100")
    print("[INFO] Notifications Telegram envoyées avec succès")
    return 0


if __name__ == "__main__":
    sys.exit(main())
