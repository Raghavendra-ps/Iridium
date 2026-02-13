from typing import List
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings
from pydantic import EmailStr

conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER,
    MAIL_PASSWORD=settings.SMTP_PASSWORD,
    MAIL_FROM=settings.SMTP_USER if settings.SMTP_USER else "noreply@example.com",
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST,
    MAIL_TLS=True,
    MAIL_SSL=False,
    USE_CREDENTIALS=True,
    # VALIDATE_CERTS=True # Optional
)

async def send_verification_email(email_to: EmailStr, code: str):
    """
    Sends a verification email with the 8-digit code.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print("WARNING: SMTP credentials not set. Email not sent.")
        return

    html = f"""
    <html>
        <body>
            <div style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Welcome to Gretis DataPort!</h2>
                <p>Please use the following code to verify your email address:</p>
                <h1 style="background: #f1f5f9; padding: 10px; display: inline-block; border-radius: 8px;">{code}</h1>
                <p>If you did not request this, please ignore this email.</p>
            </div>
        </body>
    </html>
    """

    message = MessageSchema(
        subject="Verify your Gretis DataPort Account",
        recipients=[email_to],
        body=html,
        subtype="html"
    )

    fm = FastMail(conf)
    await fm.send_message(message)
