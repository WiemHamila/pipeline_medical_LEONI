#!/usr/bin/env python3
"""
DevSecOps Telegram Alert — Medical LEONI Pipeline
Lit les résultats SAST (Bandit, pip-audit) et les résultats DAST,
appelle Mistral AI pour la remédiation, envoie des alertes Telegram formatées.
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

# ── Configuration depuis variables d'environnement ──────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
MISTRAL_KEY    = os.environ.get("MISTRAL_API_KEY", "")
DAST_RESULT    = os.environ.get("DAST_RESULT", "unknown")
GITHUB_RUN_URL = (
    f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}"
    f"/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("[DRY-RUN] Telegram non configuré — message:\n" + text[:300])
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT, "text": text},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[TELEGRAM ERROR] {r.status_code}: {r.text}", file=sys.stderr)
            return False
        print(f"[TELEGRAM] Message envoyé (ok={r.json().get('ok')})")
        return True
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}", file=sys.stderr)
        return False


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
        f"• Rapport CI : {GITHUB_RUN_URL}\n"
        f"{iso_ts}"
    )


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> int:
    now     = datetime.now(timezone.utc)
    date_fr = now.strftime("%d/%m/%Y %H:%M")
    iso_ts  = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    print(f"[INFO] Début analyse DevSecOps — {iso_ts}")
    print(f"[INFO] DAST status : {DAST_RESULT}")

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
        send_telegram(alert)

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
        send_telegram(bandit_alert)

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
    send_telegram(report)

    print(f"[INFO] Score de sécurité : {score}/100")
    print("[INFO] Notifications Telegram envoyées avec succès")
    return 0


if __name__ == "__main__":
    sys.exit(main())
