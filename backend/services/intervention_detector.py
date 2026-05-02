"""Feb 2026 — Detector de Intervenções Curriculares.

Gera e atualiza `intervention_alerts` a partir da mesma lógica de cobertura.
Regra de ouro: só permanece no feed enquanto cobertura < 90%.

Escalonamento (por semanas sem resolução):
  0–1 semana  → nível 1 (coordenador)
  2–3 semanas → nível 2 (diretor)
  ≥4 semanas  → nível 3 (secretaria)

Anti-spam: e-mail/in-app só dispara se last_notified_at > 7 dias.
"""
from __future__ import annotations

import os
import logging
import hashlib
from datetime import datetime, timezone, timedelta, date
from typing import Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alert_key(school_id: Optional[str], class_id: Optional[str],
               component_id: Optional[str], ano: Optional[int], bimestre: Optional[int]) -> str:
    raw = f"{school_id or '_'}::{class_id or '_'}::{component_id or '_'}::{ano or 0}::{bimestre or 0}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


def _weeks_since(iso: Optional[str]) -> int:
    if not iso:
        return 0
    try:
        first = datetime.fromisoformat(iso)
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - first
        return max(delta.days // 7, 0)
    except Exception:
        return 0


def _escalation_level(weeks: int) -> int:
    if weeks >= 4:
        return 3
    if weeks >= 2:
        return 2
    return 1


TARGET_ROLES_BY_LEVEL = {
    1: ['coordenador', 'apoio_pedagogico'],
    2: ['diretor', 'coordenador', 'apoio_pedagogico'],
    3: ['secretario', 'diretor', 'coordenador', 'apoio_pedagogico'],
}


async def _list_targets(db, school_id: Optional[str], level: int) -> list[dict]:
    """Descobre usuários ativos com papéis-alvo para a escola (ou rede)."""
    roles = TARGET_ROLES_BY_LEVEL.get(level, ['coordenador'])
    filt = {"status": "active", "role": {"$in": roles}}
    if school_id:
        filt["school_links.school_id"] = school_id
    cursor = db.users.find(filt, {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1})
    return await cursor.to_list(length=200)


async def _send_email_notification(user: dict, alert: dict, link: str) -> None:
    """Envia e-mail se RESEND_API_KEY configurado. Nunca trava o pipeline."""
    if not os.environ.get('RESEND_API_KEY') or not os.environ.get('RESEND_SENDER_EMAIL'):
        logger.info("RESEND não configurado — pulando e-mail para %s", user.get('email'))
        return
    try:
        from services.email_service import send_email
        subject = "⚠️ Intervenção necessária — Cobertura curricular em risco"
        html = f"""
        <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px">
          <h2 style="color:#b91c1c;margin-bottom:4px">⚠️ Intervenção necessária</h2>
          <p style="color:#374151;font-size:14px">Olá {user.get('full_name') or 'Coordenador(a)'},</p>
          <p style="color:#374151;font-size:14px;margin:0">
            <strong>Turma:</strong> {alert.get('class_name') or '—'}<br>
            <strong>Componente:</strong> {alert.get('componente_codigo') or '—'}<br>
            <strong>Ano/Bimestre:</strong> {alert.get('ano') or '—'}º ano · {alert.get('bimestre') or '—'}º bim.
          </p>
          <p style="background:#fef2f2;border:1px solid #fecaca;padding:8px 12px;border-radius:6px;color:#7f1d1d;font-size:13px">
            <strong>Status:</strong> {alert.get('status_label')}<br>
            <strong>Cobertura atual:</strong> {alert.get('pct')}%<br>
            <strong>Previsão:</strong> {alert.get('forecast_label')}
          </p>
          <p style="color:#374151;font-size:14px">
            Ação recomendada:<br>
            → Revisar pendências<br>
            → Alinhar com professor responsável
          </p>
          <p style="margin-top:20px">
            <a href="{link}" style="background:#7c3aed;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:600">
              Resolver agora
            </a>
          </p>
          <p style="color:#9ca3af;font-size:11px;margin-top:24px">
            Escalonamento nível {alert.get('escalation_level')}.
            Este alerta permanecerá ativo até a cobertura atingir 90%.
          </p>
        </div>
        """
        text = (
            f"⚠️ Intervenção necessária\n\n"
            f"Turma: {alert.get('class_name') or '—'}\n"
            f"Componente: {alert.get('componente_codigo') or '—'}\n"
            f"Ano/Bim: {alert.get('ano')}º / {alert.get('bimestre')}º\n"
            f"Status: {alert.get('status_label')} ({alert.get('pct')}%)\n"
            f"Previsão: {alert.get('forecast_label')}\n\n"
            f"Acessar: {link}\n"
        )
        await send_email(user['email'], subject, html, text=text)
    except Exception as e:
        logger.warning("Falha ao enviar e-mail de intervenção para %s: %s", user.get('email'), e)


async def _build_class_map(db) -> dict:
    """class_id → {name, school_id, academic_year}. Evita N queries."""
    out: dict = {}
    async for c in db.classes.find({}, {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1}):
        out[c['id']] = c
    return out


async def run_intervention_detection(db, academic_year: Optional[int] = None) -> dict:
    """Detecta e atualiza `intervention_alerts` rodando por turma.

    Retorna estatísticas: created / updated / resolved / notified_inapp / notified_email.
    """
    from routers.curriculum_v2 import setup_router  # noqa (reuse)

    # Usa diretamente a lógica do endpoint /coverage: replicamos aqui para rodar
    # sem contexto HTTP e por turma.
    stats = {"classes_scanned": 0, "created": 0, "updated": 0, "resolved": 0,
             "notified_inapp": 0, "notified_email": 0}
    academic_year = academic_year or date.today().year

    class_map = await _build_class_map(db)
    if not class_map:
        return stats

    # Carrega adaptations indexadas por (component_id, ano, bimestre)
    adapt_cache: dict = {}
    async for a in db.curriculum_adaptations.find({"ativo": True}, {"_id": 0}):
        key = (a['component_id'], a.get('ano'), a.get('bimestre'))
        adapt_cache.setdefault(key, []).append(a)

    if not adapt_cache:
        return stats

    comp_map: dict = {}
    async for c in db.curriculum_components.find({}, {"_id": 0, "id": 1, "codigo": 1, "nome": 1}):
        comp_map[c['id']] = c

    cal = await db.calendario_letivo.find_one({"ano_letivo": academic_year}, {"_id": 0})
    bim_windows: dict = {}
    if cal:
        for b in (1, 2, 3, 4):
            s = str(cal.get(f"bimestre_{b}_inicio") or '')[:10]
            e = str(cal.get(f"bimestre_{b}_fim") or '')[:10]
            if s and e:
                bim_windows[b] = (s, e)

    today_ymd = date.today().isoformat()

    def bim_state(b):
        if not b or b not in bim_windows:
            return 'em_andamento'
        s, e = bim_windows[b]
        if today_ymd < s:
            return 'futuro'
        if today_ymd > e:
            return 'fechado'
        return 'em_andamento'

    for class_id, cls in class_map.items():
        stats["classes_scanned"] += 1
        # Numerador por turma
        used_ids: set = set()
        async for lo in db.learning_objects.find(
            {"class_id": class_id, "academic_year": academic_year},
            {"_id": 0, "adaptation_ids": 1}
        ):
            for aid in (lo.get("adaptation_ids") or []):
                used_ids.add(aid)

        for (component_id, ano, bimestre), adapts in adapt_cache.items():
            state = bim_state(bimestre)
            if state == 'futuro':
                continue  # não avaliado ainda
            total = len(adapts)
            covered = sum(1 for a in adapts if a['id'] in used_ids)
            pct = round((covered / total * 100) if total else 0, 1)

            # Regra de gatilho
            trigger = False
            alert_status = None
            if state == 'fechado' and pct < 90:
                trigger = True
                alert_status = 'fechado_critico'
            elif state == 'em_andamento':
                if pct < 70:
                    trigger = True
                    alert_status = 'nao_cumpre'
                elif pct < 90 and bimestre:
                    # Forecast: projeção linear
                    s, e = bim_windows.get(bimestre, (None, None))
                    if s and e:
                        try:
                            d1 = datetime.fromisoformat(s).date()
                            d2 = datetime.fromisoformat(e).date()
                            today = date.today()
                            total_days = max((d2 - d1).days, 1)
                            elapsed = max((today - d1).days, 1)
                            projected = pct / 100 * (total_days / elapsed)
                            if projected < 0.9:
                                trigger = True
                                alert_status = 'em_risco'
                        except Exception:
                            pass

            alert_id = _alert_key(cls.get('school_id'), class_id, component_id, ano, bimestre)
            existing = await db.intervention_alerts.find_one({"id": alert_id}, {"_id": 0})

            if not trigger:
                # Resolvido
                if existing and not existing.get('resolved_at'):
                    await db.intervention_alerts.update_one(
                        {"id": alert_id},
                        {"$set": {"resolved_at": _now_iso(), "last_coverage_pct": pct}}
                    )
                    stats["resolved"] += 1
                continue

            # Upsert
            weeks = _weeks_since((existing or {}).get('first_detected_at'))
            level = _escalation_level(weeks)
            comp = comp_map.get(component_id) or {}
            doc_base = {
                "id": alert_id,
                "mantenedora_id": cls.get('mantenedora_id'),
                "school_id": cls.get('school_id'),
                "class_id": class_id,
                "class_name": cls.get('name'),
                "component_id": component_id,
                "componente_codigo": comp.get('codigo'),
                "componente_nome": comp.get('nome'),
                "ano": ano,
                "bimestre": bimestre,
                "status": alert_status,
                "last_coverage_pct": pct,
                "escalation_level": level,
                "resolved_at": None,
                "updated_at": _now_iso(),
            }
            if not existing:
                doc_base["first_detected_at"] = _now_iso()
                doc_base["last_notified_at"] = None
                doc_base["last_notified_channel"] = None
                await db.intervention_alerts.insert_one(doc_base)
                stats["created"] += 1
            else:
                await db.intervention_alerts.update_one(
                    {"id": alert_id},
                    {"$set": {**doc_base,
                              "first_detected_at": existing.get('first_detected_at') or _now_iso()}}
                )
                stats["updated"] += 1

            # Anti-spam: enviar somente se last_notified_at é None ou > 7 dias
            last_notified = (existing or {}).get('last_notified_at')
            should_notify = True
            if last_notified:
                try:
                    dt = datetime.fromisoformat(last_notified)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - dt) < timedelta(days=7):
                        should_notify = False
                except Exception:
                    pass

            if should_notify:
                targets = await _list_targets(db, cls.get('school_id'), level)
                status_labels = {
                    'em_risco': 'Em risco',
                    'nao_cumpre': 'Não cumprirá no prazo',
                    'fechado_critico': 'Bimestre fechado sem cobertura adequada',
                }
                forecast_labels = {
                    'em_risco': 'Em risco (ritmo atual não fecha o bimestre)',
                    'nao_cumpre': 'Não cumprirá no prazo',
                    'fechado_critico': 'Não foi cumprido',
                }
                enriched = {
                    **doc_base,
                    "status_label": status_labels.get(alert_status, alert_status),
                    "forecast_label": forecast_labels.get(alert_status, '—'),
                    "pct": pct,
                }
                # URL direta para o slot no dashboard
                link = (
                    f"/admin/curriculo/cobertura?class_id={class_id}"
                    f"&component={comp.get('codigo')}&ano={ano or ''}&bim={bimestre or ''}"
                )
                for u in targets:
                    # In-app notification (sempre)
                    await db.intervention_notifications.insert_one({
                        "id": f"{alert_id}_{u['id']}_{int(datetime.now(timezone.utc).timestamp())}",
                        "alert_id": alert_id,
                        "user_id": u['id'],
                        "title": "⚠️ Intervenção necessária",
                        "message": (
                            f"{comp.get('codigo') or '?'} · {cls.get('name')} "
                            f"· {ano or '—'}º / {bimestre or '—'}º bim · "
                            f"{pct}% ({enriched['status_label']})"
                        ),
                        "link": link,
                        "read": False,
                        "created_at": _now_iso(),
                    })
                    stats["notified_inapp"] += 1
                    # E-mail (opcional, fallback silencioso)
                    if os.environ.get('RESEND_API_KEY'):
                        await _send_email_notification(u, enriched, link)
                        stats["notified_email"] += 1

                await db.intervention_alerts.update_one(
                    {"id": alert_id},
                    {"$set": {
                        "last_notified_at": _now_iso(),
                        "last_notified_channel": "inapp+email" if os.environ.get('RESEND_API_KEY') else "inapp",
                    }}
                )

    return stats
