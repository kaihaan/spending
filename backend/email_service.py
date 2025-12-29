"""
Email service for sending password reset and notification emails.

Uses SMTP for email delivery with HTML template support.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailService:
    """SMTP-based email service for password reset and notifications.

    Configuration via environment variables:
        SMTP_SERVER: SMTP server hostname (default: smtp.gmail.com)
        SMTP_PORT: SMTP port (default: 587 for TLS)
        SMTP_USER: SMTP username/email
        SMTP_PASSWORD: SMTP password (use app-specific password for Gmail)
        FROM_EMAIL: Sender email address (default: SMTP_USER)
    """

    def __init__(self):
        """Initialize email service with SMTP configuration."""
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)

        # Validate configuration
        if not self.smtp_user or not self.smtp_password:
            print(
                "⚠️  WARNING: SMTP_USER and SMTP_PASSWORD not configured. "
                "Password reset emails will fail."
            )

    def send_password_reset(
        self, to_email: str, reset_token: str, reset_url: str
    ) -> bool:
        """Send password reset email with token link.

        Args:
            to_email: Recipient email address
            reset_token: Password reset token (URL-safe)
            reset_url: Base URL for password reset page (e.g., http://localhost:5173/reset-password)

        Returns:
            True if email sent successfully, False otherwise

        Example:
            email_service.send_password_reset(
                "user@example.com",
                "abc123...",
                "http://localhost:5173/reset-password"
            )
            # Sends email with link: http://localhost:5173/reset-password?token=abc123...
        """
        if not self.smtp_user or not self.smtp_password:
            print(
                f"❌ Cannot send password reset email to {to_email}: SMTP not configured"
            )
            return False

        subject = "Password Reset Request - Spending App"

        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2563eb;">Password Reset Request</h2>
                    <p>You requested a password reset for your Spending App account.</p>
                    <p>Click the button below to reset your password. This link is valid for <strong>1 hour</strong>.</p>
                    <div style="margin: 30px 0;">
                        <a href="{reset_url}?token={reset_token}"
                           style="background-color: #2563eb; color: white; padding: 12px 24px;
                                  text-decoration: none; border-radius: 6px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    <p style="color: #666; font-size: 14px;">
                        Or copy and paste this link into your browser:<br>
                        <a href="{reset_url}?token={reset_token}" style="color: #2563eb; word-break: break-all;">
                            {reset_url}?token={reset_token}
                        </a>
                    </p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    <p style="color: #666; font-size: 14px;">
                        If you didn't request this password reset, please ignore this email.
                        Your password will remain unchanged.
                    </p>
                    <p style="color: #999; font-size: 12px;">
                        This is an automated message from Spending App. Please do not reply to this email.
                    </p>
                </div>
            </body>
        </html>
        """

        text_body = f"""
Password Reset Request - Spending App

You requested a password reset for your Spending App account.

Click this link to reset your password (valid for 1 hour):
{reset_url}?token={reset_token}

If you didn't request this password reset, please ignore this email.
Your password will remain unchanged.

---
This is an automated message from Spending App.
        """.strip()

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # Attach both plain text and HTML versions
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send email via SMTP with TLS
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Upgrade to TLS
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"✅ Password reset email sent to {to_email}")
            return True

        except Exception as e:
            print(f"❌ Failed to send password reset email to {to_email}: {e}")
            return False

    def send_welcome_email(self, to_email: str, username: str | None = None) -> bool:
        """Send welcome email to new user.

        Args:
            to_email: Recipient email address
            username: User's display name (optional)

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.smtp_user or not self.smtp_password:
            print(f"❌ Cannot send welcome email to {to_email}: SMTP not configured")
            return False

        greeting = f"Hello {username}" if username else "Hello"
        subject = "Welcome to Spending App!"

        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2563eb;">Welcome to Spending App!</h2>
                    <p>{greeting},</p>
                    <p>Your account has been successfully created. You can now start tracking your spending and managing your finances.</p>
                    <p>Get started by:</p>
                    <ul>
                        <li>Connecting your bank accounts via TrueLayer</li>
                        <li>Syncing receipts from Gmail</li>
                        <li>Linking Amazon orders for detailed transaction matching</li>
                    </ul>
                    <p>If you have any questions, please don't hesitate to reach out.</p>
                    <p style="margin-top: 30px;">Best regards,<br>Spending App Team</p>
                </div>
            </body>
        </html>
        """

        text_body = f"""
Welcome to Spending App!

{greeting},

Your account has been successfully created. You can now start tracking your spending and managing your finances.

Get started by:
- Connecting your bank accounts via TrueLayer
- Syncing receipts from Gmail
- Linking Amazon orders for detailed transaction matching

If you have any questions, please don't hesitate to reach out.

Best regards,
Spending App Team
        """.strip()

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"✅ Welcome email sent to {to_email}")
            return True

        except Exception as e:
            print(f"❌ Failed to send welcome email to {to_email}: {e}")
            return False


# Singleton instance
email_service = EmailService()
