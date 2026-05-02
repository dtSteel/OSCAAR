import structlog
import aiosmtplib
import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path

from app.core.config import settings

log = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "email"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

EMAIL_SUBJECTS = {
    "welcome":        {
        "en": "Welcome to OSCAAR — Your research access is ready",
        "fr": "Bienvenue sur OSCAAR — Votre accès recherche est prêt",
        "de": "Willkommen bei OSCAAR — Ihr Forschungszugang ist bereit",
        "es": "Bienvenido a OSCAAR — Su acceso de investigación está listo",
        "ja": "OSCAARへようこそ — 研究アクセスの準備ができました",
        "zh": "欢迎使用OSCAAR — 您的研究访问权限已准备就绪",
        "pt": "Bem-vindo ao OSCAAR — Seu acesso à pesquisa está pronto",
    },
    "password_reset": {
        "en": "OSCAAR — Password Reset Request",
        "fr": "OSCAAR — Demande de réinitialisation de mot de passe",
        "de": "OSCAAR — Passwort-Zurücksetzungsanfrage",
        "es": "OSCAAR — Solicitud de restablecimiento de contraseña",
        "ja": "OSCAAR — パスワードリセットのリクエスト",
        "zh": "OSCAAR — 密码重置请求",
        "pt": "OSCAAR — Solicitação de redefinição de senha",
    },
    "admin_invite": {
        "en": "You have been invited to OSCAAR",
    },
}


async def send_email(
    to_address: str,
    template: str,
    language: str,
    context: dict,
    user_id: str = None,
):
    lang = language if language in EMAIL_SUBJECTS.get(template, {}) else "en"
    subject = EMAIL_SUBJECTS.get(template, {}).get(lang, "OSCAAR Notification")

    try:
        template_file = f"{template}_{lang}.html"
        if not (TEMPLATE_DIR / template_file).exists():
            template_file = f"{template}_en.html"
        tmpl = jinja_env.get_template(template_file)
        html_body = tmpl.render(**context)
    except Exception as e:
        log.error("template_render_failed", template=template, error=str(e))
        html_body = f"<p>{context.get('message', 'OSCAAR notification')}</p>"

    if settings.EMAIL_BACKEND == "mailpit":
        await _send_via_smtp(to_address, subject, html_body)
    elif settings.EMAIL_BACKEND == "postal":
        await _send_via_postal(to_address, subject, html_body)
    else:
        await _send_via_smtp(to_address, subject, html_body)

    log.info("email_sent", template=template, to=to_address, lang=lang)


async def _send_via_smtp(to_address: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.EMAIL_FROM
    msg["To"]      = to_address
    msg.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.MAILPIT_SMTP_HOST,
        port=settings.MAILPIT_SMTP_PORT,
        start_tls=False,
    )


async def _send_via_postal(to_address: str, subject: str, html_body: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.POSTAL_API_URL}/api/v1/send/message",
            headers={"X-Server-API-Key": settings.POSTAL_API_KEY},
            json={
                "to":       [to_address],
                "from":     settings.EMAIL_FROM,
                "subject":  subject,
                "html_body": html_body,
            },
        )
        response.raise_for_status()


async def send_welcome_email(user_full_name: str, user_email: str, language: str):
    await send_email(
        to_address=user_email,
        template="welcome",
        language=language,
        context={
            "full_name": user_full_name,
            "login_url": "https://www.oscaar.org",
        },
    )


async def send_password_reset_email(user_full_name: str, user_email: str, reset_token: str, language: str):
    reset_url = f"https://www.oscaar.org/reset-password?token={reset_token}"
    await send_email(
        to_address=user_email,
        template="password_reset",
        language=language,
        context={
            "full_name": user_full_name,
            "reset_url": reset_url,
        },
    )
