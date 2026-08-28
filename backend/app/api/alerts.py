import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_account_id
from app.db import get_db
from app.models.alerts import AlertDelivery, AlertSettings
from app.schemas import AlertDeliveryOut, AlertSettingsIn, AlertSettingsOut
from app.services import jobs as jobs_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


async def _get_or_create_settings(session: AsyncSession, account_id: uuid.UUID) -> AlertSettings:
    settings_row = (
        await session.execute(select(AlertSettings).where(AlertSettings.account_id == account_id))
    ).scalars().first()
    if not settings_row:
        settings_row = AlertSettings(account_id=account_id)
        session.add(settings_row)
        await session.commit()
        await session.refresh(settings_row)
    return settings_row


@router.get("/settings", response_model=AlertSettingsOut)
async def get_alert_settings(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    return await _get_or_create_settings(session, account_id)


@router.patch("/settings", response_model=AlertSettingsOut)
async def update_alert_settings(
    body: AlertSettingsIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    settings_row = await _get_or_create_settings(session, account_id)
    for key, value in body.model_dump().items():
        setattr(settings_row, key, value)
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


@router.get("/preview", response_model=list[AlertDeliveryOut])
async def preview_alerts(
    account_id: uuid.UUID = Depends(get_current_account_id), session: AsyncSession = Depends(get_db)
):
    rows = (
        await session.execute(
            select(AlertDelivery).where(AlertDelivery.account_id == account_id).order_by(AlertDelivery.created_at.desc()).limit(50)
        )
    ).scalars().all()
    return rows


@router.post("/send-test")
async def send_test_alert(
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.email_provider import get_email_provider
    from app.services.email_templates import wrap_email

    alert_settings = await _get_or_create_settings(session, account_id)
    to = alert_settings.email_recipient or settings.email_to
    provider = get_email_provider(settings)
    subject = "Correo de prueba — Radar de Conversaciones"
    html = wrap_email(subject, "<p style='font-size:14px;color:#33403c;'>Esto es una prueba de configuración de alertas.</p>")
    sent = await provider.send(to=to, subject=subject, html=html)
    session.add(
        AlertDelivery(
            account_id=account_id, kind="test", subject=subject, body_html=html, to_address=to,
            provider=settings.email_provider, sent=sent,
        )
    )
    await session.commit()
    return {"sent_externally": sent, "provider": settings.email_provider}
