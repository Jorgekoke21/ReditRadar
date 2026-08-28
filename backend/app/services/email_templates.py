"""HTML builders for the three email kinds (spec section 17). Kept dependency
free (plain f-strings) since volume is low and a templating engine would be
overkill for a handful of emails."""

from dataclasses import dataclass


@dataclass
class DigestItem:
    id: str
    subreddit: str
    title: str
    score: int
    summary: str
    recommended_action: str
    promotion_risk: str


_ACTION_LABELS = {
    "respond_now": "Responder ahora",
    "review_today": "Revisar hoy",
    "help_without_mentioning": "Aportar sin mencionar Radarin",
    "ask_question": "Preguntar antes de responder",
    "observe": "Observar",
    "discard": "Descartar",
}

_RISK_LABELS = {"low": "Riesgo bajo", "medium": "Riesgo medio", "high": "Riesgo alto"}


def _item_row(item: DigestItem, app_url: str) -> str:
    return f"""
    <tr>
      <td style="padding:12px 0;border-bottom:1px solid #e5e5e5;">
        <div style="font-size:12px;color:#5c6b66;text-transform:uppercase;letter-spacing:.03em;">
          r/{item.subreddit} &middot; puntuación {item.score}
        </div>
        <div style="font-size:15px;font-weight:600;color:#062F25;margin:4px 0;">{item.title}</div>
        <div style="font-size:14px;color:#33403c;margin-bottom:6px;">{item.summary}</div>
        <div style="font-size:12px;color:#0A4638;">
          {_ACTION_LABELS.get(item.recommended_action, item.recommended_action)} &middot;
          {_RISK_LABELS.get(item.promotion_risk, item.promotion_risk)}
        </div>
        <a href="{app_url}/conversations/{item.id}"
           style="display:inline-block;margin-top:8px;padding:6px 14px;background:#062F25;color:#A3FF12;
                  text-decoration:none;border-radius:6px;font-size:13px;">Ver ficha</a>
      </td>
    </tr>"""


def wrap_email(title: str, body: str) -> str:
    return f"""<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;background:#F1F8F5;
      padding:24px;margin:0;">
      <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:10px;padding:24px;">
        <h1 style="font-size:18px;color:#062F25;margin:0 0 12px;">{title}</h1>
        {body}
        <p style="font-size:11px;color:#8a938f;margin-top:24px;">Radar de Conversaciones — Radarin. Este correo
        resume conversaciones públicas detectadas por palabras clave; ninguna respuesta se publica automáticamente.</p>
      </div>
    </body></html>"""


def build_daily_digest(*, total_found: int, urgent_count: int, items: list[DigestItem], app_url: str) -> tuple[str, str]:
    subject = f"{total_found} conversaciones nuevas donde puedes aportar valor"
    rows = "".join(_item_row(i, app_url) for i in items[:10])
    body = f"""
      <p style="color:#33403c;font-size:14px;">Encontradas hoy: <b>{total_found}</b>
      &middot; urgentes: <b>{urgent_count}</b></p>
      <table style="width:100%;border-collapse:collapse;">{rows}</table>
    """
    return subject, wrap_email(subject, body)


def build_urgent_alert(*, item: DigestItem, app_url: str) -> tuple[str, str]:
    subject = f"Urgente: conversación con puntuación {item.score} en r/{item.subreddit}"
    body = f"<table style='width:100%;border-collapse:collapse;'>{_item_row(item, app_url)}</table>"
    return subject, wrap_email(subject, body)


def build_weekly_digest(
    *,
    analyzed: int,
    recommended: int,
    responded: int,
    conversations_started: int,
    best_community: str,
    top_topic: str,
    app_url: str,
) -> tuple[str, str]:
    subject = "Resumen semanal — Radar de Conversaciones"
    body = f"""
      <ul style="font-size:14px;color:#33403c;line-height:1.8;">
        <li>Analizadas: <b>{analyzed}</b></li>
        <li>Recomendadas: <b>{recommended}</b></li>
        <li>Respondidas: <b>{responded}</b></li>
        <li>Conversaciones iniciadas: <b>{conversations_started}</b></li>
        <li>Mejor comunidad: <b>{best_community or "—"}</b></li>
        <li>Tema más frecuente: <b>{top_topic or "—"}</b></li>
      </ul>
      <a href="{app_url}/history" style="display:inline-block;margin-top:8px;padding:8px 16px;background:#062F25;
        color:#A3FF12;text-decoration:none;border-radius:6px;font-size:13px;">Ver historial completo</a>
    """
    return subject, wrap_email(subject, body)
