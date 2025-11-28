from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import os
import smtplib
import logging
from email.message import EmailMessage

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class VolunteerIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    phone: Optional[str]
    weekly_service: Optional[str]
    committed_weekly: bool = False

class VolunteerOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: Optional[str]
    weekly_service: Optional[str]
    committed_weekly: bool
    created_at: str

SERVICES: List[str] = []


def send_confirmation_email(to_email: str, name: str, service_name: str, assigned_date: Optional[str]):
    """Send confirmation email to volunteer."""
    logger.info(f"Attempting to send confirmation email to {to_email} for {name}")
    
    # Read SMTP config from environment variables
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASS = os.getenv("SMTP_PASS")
    FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        # SMTP not configured; skip sending
        logger.warning("SMTP not configured. Email sending disabled.")
        return False

    logger.debug(f"SMTP Config - Host: {SMTP_HOST}, Port: {SMTP_PORT}, User: {SMTP_USER}")

    subject = "TamilSchool Volunteer Signup Confirmation"
    body = f"Hi {name},\n\nThank you for signing up for {service_name}."
    if assigned_date:
        body += f" Your assigned date: {assigned_date}."
    body += "\n\nWe will contact you with further details.\n\n— TamilSchool"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)

    try:
        logger.debug(f"Connecting to SMTP server {SMTP_HOST}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            logger.debug("STARTTLS initiated")
            s.login(SMTP_USER, SMTP_PASS)
            logger.debug(f"Logged in as {SMTP_USER}")
            s.send_message(msg)
            logger.info(f"✓ Confirmation email sent successfully to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False
