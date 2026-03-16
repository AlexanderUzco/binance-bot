"""Notification system: email and Telegram."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

import httpx

from .config import NotificationConfig

logger = logging.getLogger("binance_bot.notifications")


class Notifier:
    """Sends notifications via email and/or Telegram."""

    def __init__(self, config: NotificationConfig):
        self.config = config

    async def notify(self, subject: str, message: str, data: dict | None = None):
        """Send notification through all enabled channels."""
        if self.config.telegram_enabled:
            await self._send_telegram(subject, message)
        if self.config.email_enabled and self.config.email_to:
            self._send_email(subject, message)

    async def notify_trade(self, trade_data: dict):
        """Send trade notification."""
        side = trade_data.get("side", "TRADE")
        symbol = trade_data.get("symbol", "")
        price = trade_data.get("fill_price", trade_data.get("price", 0))
        quantity = trade_data.get("quantity", trade_data.get("fill_quantity", 0))
        profit = trade_data.get("profit")
        reason = trade_data.get("reason", "")

        subject = f"[BinBot] {side} {symbol}"

        lines = [
            f"Side: {side}",
            f"Symbol: {symbol}",
            f"Price: {price}",
            f"Quantity: {quantity}",
        ]
        if profit is not None:
            lines.append(f"Profit: {profit}")
        if reason:
            lines.append(f"Reason: {reason}")

        await self.notify(subject, "\n".join(lines))

    async def notify_shutdown(self, reason: str, stats: dict):
        """Send bot shutdown notification."""
        subject = f"[BinBot] Shutdown: {reason}"
        lines = [
            f"Reason: {reason}",
            f"Total trades: {stats.get('total_trades', 0)}",
            f"Win rate: {stats.get('win_rate', 0):.1f}%",
            f"Total profit: {stats.get('total_profit', 0)}",
        ]
        await self.notify(subject, "\n".join(lines))

    async def _send_telegram(self, subject: str, message: str):
        """Send Telegram message."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self.config.telegram_chat_id,
                    "text": f"*{subject}*\n\n{message}",
                    "parse_mode": "Markdown",
                })
            logger.debug(f"Telegram notification sent: {subject}")
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")

    def _send_email(self, subject: str, body: str):
        """Send email notification (via local sendmail or SMTP)."""
        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["To"] = self.config.email_to
            msg.attach(MIMEText(body, "plain"))

            # Use local sendmail
            with smtplib.SMTP("localhost") as smtp:
                smtp.send_message(msg)
            logger.debug(f"Email sent: {subject}")
        except Exception as e:
            logger.warning(f"Email notification failed: {e}")
