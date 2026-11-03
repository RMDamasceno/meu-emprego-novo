"""Triagem e rastreamento local de prospecção, sem dependências externas.

Dados reais e comprovantes devem ficar em privado/, fora do controle de versão.
A avaliação não envia mensagens nem substitui confirmação de recrutadores.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENT_STATUSES = {"sent", "applied", "proposal_sent"}
KNOWN_STATUSES = {
    "found", "screened", "ready", "sent", "applied", "proposal_sent",
    "reply", "interview", "offer", "rejected", "withdrawn", "closed",
}
TRACKING_PARAMS = {"fbclid", "gclid", "msclkid", "li_fat_id"}


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def canonical_url(value: str) -> str:
    """Preserva parâmetros funcionais, removendo rastreadores de publicidade."""
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not host:
        return ""
    port = f":{parsed.port}" if parsed.port else ""
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.casefold().startswith("utm_") and k.casefold() not in TRACKING_PARAMS
    ))
    return urlunsplit((parsed.scheme.casefold() or "https", host + port,
                       parsed.path.rstrip("/") or "/", query, ""))


def opportunity_key(item: dict) -> str:
    """A chave por código evita misturar vagas distintas da mesma empresa."""
    kind = normalized(item.get("kind", "job"))
    company = normalized(item.get("company") or item.get("buyer"))
    role = normalized(item.get("title") or item.get("role"))
    if not company or not role:
        raise ValueError("Cada oportunidade exige empresa/contratante e cargo/objeto.")
    identifier = normalized(item.get("job_id") or item.get("notice_id"))
    identity = f"{kind}|{company}|{identifier or role}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def load_events(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Tracker inválido na linha {number}: {error}") from error
        if not isinstance(event, dict):
            raise ValueError(f"Tracker inválido na linha {number}: objeto esperado")
        events.append(event)
    return events


def duplicate_of(item: dict, events: list[dict]) -> dict | None:
    """Verifica envios por chave estável OU URL canônica; não duplica contatos."""
    key = opportunity_key(item)
    url = canonical_url(str(item.get("url", "")))
    for event in reversed(events):
        if event.get("status") not in SENT_STATUSES | {"interview", "offer", "reply"}:
            continue
        if event.get("key") == key:
            return event
        if url and event.get("url") and canonical_url(event["url"]) == url:
            return event
    return None


def screen_job(job: dict, profile: dict, policy: dict,
               events: list[dict] | None = None) -> dict:
    """Triagem conservadora: requisito obrigatório sem evidência bloqueia."""
    if normalized(job.get("kind", "job")) != "job":
        raise ValueError("A triagem técnica aceita kind=job; B2B usa o preflight separado.")
    key = opportunity_key(job)
    events = events or []
    reasons: list[str] = []
    review: list[str] = []
    if duplicate_of(job, events):
        reasons.append("Candidatura prévia identificada no tracker.")

    skills = {normalized(skill) for skill in profile.get("verified_skills", [])}
    required = [str(skill) for skill in job.get("mandatory_skills", [])]
    wanted = [str(skill) for skill in job.get("desired_skills", [])]
    missing = [skill for skill in required if normalized(skill) not in skills]
    proven = [skill for skill in required + wanted if normalized(skill) in skills]
    if missing:
        reasons.append("Requisitos obrigatórios sem evidência: " + ", ".join(missing))

    areas = {normalized(a) for a in policy.get("areas", [])}
    seniorities = {normalized(s) for s in policy.get("seniority", [])}
    modes = {normalized(m) for m in policy.get("modes", [])}
    contracts = {normalized(c) for c in policy.get("contracts", [])}
    role_area = normalized(job.get("area"))
    seniority = normalized(job.get("seniority"))
    mode = normalized(job.get("mode"))
    contract = normalized(job.get("contract"))

    for label, value, allowed in (
        ("área", role_area, areas),
        ("senioridade", seniority, seniorities),
        ("modalidade", mode, modes),
        ("contrato", contract, contracts),
    ):
        if not value:
            review.append(f"{label.capitalize()} não informada.")
        elif allowed and value not in allowed:
            reasons.append(f"{label.capitalize()} incompatível: {value}.")

    if mode == "hybrid_sp" and normalized(job.get("city")) not in {
        "sao paulo", "sao paulo/sp", "sp"
    }:
        if job.get("city"):
            reasons.append("Híbrido fora da cidade de São Paulo.")
        else:
            review.append("Cidade do híbrido não confirmada.")

    english = normalized(job.get("english_level"))
    if english in {"fluent", "advanced", "fluente", "avancado"} and not profile.get("english_fluent", False):
        reasons.append("Inglês avançado/fluente obrigatório sem comprovação.")

    salary = job.get("salary_monthly_brl")
    floors = policy.get("minimum_monthly_brl", {})
    floor = floors.get(contract.upper()) if contract else None
    if salary is None:
        review.append("Remuneração não divulgada; confirmar antes de avançar.")
    elif floor is not None and float(salary) < float(floor):
        reasons.append(f"Remuneração abaixo do piso {contract.upper()}: R$ {floor}.")

    if not job.get("source_verified"):
        review.append("Fonte oficial ou publicação original ainda não verificada.")
    if not job.get("published_at"):
        review.append("Data de publicação não confirmada.")

    total_requirements = len(required) + len(wanted)
    coverage = len(proven) / total_requirements if total_requirements else 0
    score = round(
        55 * coverage
        + (15 if role_area in areas else 0)
        + (10 if seniority in seniorities else 0)
        + (10 if mode in modes else 0)
        + (5 if contract in contracts else 0)
        + (5 if salary is not None and (floor is None or float(salary) >= float(floor)) else 0)
    )
    decision = "blocked" if reasons else ("review" if review else "eligible")
    return {
        "key": key, "score": score, "decision": decision,
        "verified_matches": proven, "unproven_mandatory": missing,
        "blockers": reasons, "pending_checks": review,
        "note": "Pontuação heurística de priorização, não probabilidade de contratação.",
    }


def preflight(item: dict, events: list[dict], *, channel: str,
              source_verified: bool, recipient_verified: bool,
              history_checked: bool, demand_verified: bool = False,
              attachment: str = "", screen_decision: str = "") -> dict:
    """Verifica segurança antes de tentar qualquer ação externa. Não envia."""
    failures = []
    kind = normalized(item.get("kind", "job"))
    if duplicate_of(item, events):
        failures.append("Oportunidade já contatada.")
    if not source_verified:
        failures.append("Origem não verificada.")
    if not history_checked:
        failures.append("Histórico de envios não consultado.")
    if kind == "job":
        if channel != "outlook":
            failures.append("Candidaturas por este fluxo exigem Outlook.")
        if screen_decision != "eligible":
            failures.append("Triagem não aprovada; verificar pendências e lacunas.")
        if not recipient_verified:
            failures.append("Destinatário de recrutamento não verificado.")
        if not attachment or not Path(attachment).is_file():
            failures.append("Currículo anexável não encontrado.")
    elif kind == "b2b":
        if channel != "gmail":
            failures.append("Propostas B2B por este fluxo exigem Gmail.")
        if not recipient_verified or not demand_verified:
            failures.append("Destinatário ou demanda comercial não verificados.")
        if normalized(item.get("origin_type")) in {
            "freelance_platform", "public_procurement"
        }:
            failures.append("Responder somente pelo canal oficial da plataforma ou edital.")
    else:
        failures.append("Tipo de oportunidade não reconhecido.")
    return {"key": opportunity_key(item), "ready": not failures, "blockers": failures,
            "note": "A aprovação do preflight não representa envio nem entrega."}


def record_event(path: str | Path, item: dict, status: str, *,
                 receipt: str = "", attachment: str = "", source: str = "",
                 recipient: str = "") -> dict:
    """Evento de envio exige identificador de confirmação; nunca presume entrega."""
    if status not in KNOWN_STATUSES:
        raise ValueError("Status desconhecido.")
    if status in SENT_STATUSES and not receipt.strip():
        raise ValueError("Registrar envio requer comprovante/identificador de mensagem.")
    kind = normalized(item.get("kind", "job"))
    if status == "proposal_sent" and kind != "b2b":
        raise ValueError("proposal_sent exige kind=b2b.")
    if status in {"sent", "applied"} and kind != "job":
        raise ValueError("Candidatura exige kind=job.")
    if status in {"sent", "applied"} and (not attachment or not Path(attachment).is_file()):
        raise ValueError("Candidatura enviada requer currículo existente para auditoria.")
    path = Path(path)
    events = load_events(path)
    if status in SENT_STATUSES and duplicate_of(item, events):
        raise ValueError("Envio já registrado para esta oportunidade.")
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "key": opportunity_key(item),
        "kind": kind, "company": item.get("company") or item.get("buyer"),
        "title": item.get("title") or item.get("role"),
        "url": canonical_url(str(item.get("url", ""))),
        "status": status,
        "source": source or item.get("source", ""),
        "recipient": recipient,
        "receipt": receipt,
        "attachment_sha256": (
            hashlib.sha256(Path(attachment).read_bytes()).hexdigest() if attachment else ""
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


def metrics(events: list[dict]) -> dict:
    """Taxa de entrevistas sobre oportunidades candidatas únicas, sem dobrar eventos."""
    jobs: dict[str, set[str]] = {}
    b2b: dict[str, set[str]] = {}
    by_source: dict[str, set[str]] = {}
    for event in events:
        key = event.get("key")
        if not key:
            continue
        states = (jobs if event.get("kind") == "job" else b2b).setdefault(key, set())
        states.add(event.get("status", ""))
        if event.get("kind") == "job" and event.get("status") in SENT_STATUSES:
            by_source.setdefault(event.get("source") or "não informada", set()).add(key)
    # Sem comprovante de envio, entrevista isolada não vira candidatura confirmada.
    applied = sum(bool(s & {"applied", "sent"}) for s in jobs.values())
    interviewed = sum("interview" in s or "offer" in s for s in jobs.values())
    proposals = sum("proposal_sent" in s for s in b2b.values())
    replied = sum(bool(s & {"reply", "offer"}) for s in b2b.values())
    return {
        "job_applications": applied, "interviews": interviewed,
        "interview_rate": round(interviewed / applied, 4) if applied else None,
        "b2b_proposals": proposals, "b2b_replies": replied,
        "b2b_reply_rate": round(replied / proposals, 4) if proposals else None,
        "applications_by_source": {k: len(v) for k, v in sorted(by_source.items())},
    }
