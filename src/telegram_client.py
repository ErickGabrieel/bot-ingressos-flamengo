import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramError(RuntimeError):
    """Raised when Telegram rejects or cannot receive a message."""


def _telegram_request(
    token: str,
    method: str,
    parameters: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict:
    token = token.strip()

    if not token:
        raise TelegramError("O token do Telegram é obrigatório.")

    endpoint = f"https://api.telegram.org/bot{token}/{method}"
    body = urlencode(parameters or {}).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise TelegramError(
            "Não foi possível contatar o Telegram."
        ) from exc

    if not payload.get("ok"):
        raise TelegramError("O Telegram rejeitou a solicitação.")

    return payload


def get_latest_chat_id(token: str) -> str:
    payload = _telegram_request(token, "getUpdates")

    for update in reversed(payload.get("result", [])):
        message = (
            update.get("message")
            or update.get("channel_post")
            or update.get("edited_message")
        )

        if message and message.get("chat", {}).get("id") is not None:
            return str(message["chat"]["id"])

    raise TelegramError(
        "Nenhuma conversa encontrada. Envie /start ao bot e tente novamente."
    )


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    timeout: int = 15,
) -> None:
    chat_id = chat_id.strip()

    if not chat_id:
        raise TelegramError("O chat ID é obrigatório.")

    _telegram_request(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
        },
        timeout,
    )
