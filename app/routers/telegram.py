from fastapi import APIRouter, Header, HTTPException, Request

from bot.webhook import SECRET_TOKEN_HEADER, WEBHOOK_PATH, TelegramWebhook


router = APIRouter(tags=["telegram"])


@router.post(WEBHOOK_PATH, include_in_schema=False)
async def receive_telegram_update(
    request: Request,
    secret_token: str | None = Header(default=None, alias=SECRET_TOKEN_HEADER),
) -> dict[str, bool]:
    webhook: TelegramWebhook | None = getattr(request.app.state, "telegram_webhook", None)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not webhook.is_authentic(secret_token):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    await webhook.enqueue(await request.json())
    return {"ok": True}
