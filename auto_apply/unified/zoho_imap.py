"""
Zoho IMAP integration for Greenhouse security code retrieval.

Email real de Greenhouse:
- FROM: no-reply@us.greenhouse-mail.io
- Subject: "Security code for your application to {company}"
- Body HTML: código alfanumérico de 8 chars en <h1>CODE</h1>
- Carpeta: suele caer en "Notification" (o Papelera), no siempre INBOX
"""
import imaplib
import email
import re
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ZohoConfig:
    """Zoho IMAP configuration."""
    email: str
    password: str
    imap_server: str = "imap.zoho.com"
    imap_port: int = 993
    # Carpetas donde buscar (Zoho en español + inglés)
    folders: tuple = ("INBOX", "Notification", "Correo no deseado", "Papelera", "Newsletter", "Archive")


class ZohoIMAPClient:
    """Zoho IMAP client for retrieving Greenhouse security codes."""

    def __init__(self, config: ZohoConfig):
        self.config = config
        self.mail = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Zoho IMAP server."""
        try:
            self.mail = imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port)
            self.mail.login(self.config.email, self.config.password)
            self._connected = True
            logger.info(f"[Zoho] Connected to {self.config.imap_server}")
            return True
        except Exception as e:
            logger.error(f"[Zoho] Connection failed: {e}")
            self.mail = None
            return False

    async def disconnect(self):
        """Disconnect from IMAP server."""
        try:
            if self.mail and self._connected:
                self.mail.logout()
            self._connected = False
        except Exception as e:
            logger.debug(f"[Zoho] Disconnect: {e}")

    async def wait_for_security_code(
        self,
        timeout: int = 120,
        poll_interval: int = 8,
        since: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Espera el email de Greenhouse con el security code.
        Busca en todas las carpetas configuradas (Notification, INBOX, Junk...).

        Args:
            timeout: segundos máximos de espera
            poll_interval: segundos entre chequeos
            since: solo emails posteriores a esta fecha (default: hace 10 min)

        Returns:
            Código alfanumérico (ej: "j6Ms1H0j") o None
        """
        if not self.mail:
            await self.connect()
        if not self.mail:
            return None

        if since is None:
            since = datetime.now() - timedelta(minutes=10)

        deadline = datetime.now() + timedelta(seconds=timeout)
        while datetime.now() < deadline:
            try:
                code = self._check_all_folders(since)
                if code:
                    return code
            except Exception as e:
                logger.warning(f"[Zoho] Error checking email: {e}")
            await asyncio.sleep(poll_interval)

        logger.warning("[Zoho] Timeout waiting for security code")
        return None

    def _check_all_folders(self, since: datetime) -> Optional[str]:
        """Busca el código en todas las carpetas, retorna el más reciente."""
        best = None  # (internaldate, code)
        for folder in self.config.folders:
            try:
                status, _ = self.mail.select(folder)
                if status != "OK":
                    continue
                status, messages = self.mail.search(None, 'FROM "greenhouse-mail.io"')
                if status != "OK" or not messages[0]:
                    continue
                for mid in messages[0].split():
                    try:
                        result = self._extract_code_from_email(mid, since)
                        if result:
                            idate_str, code = result
                            if best is None or idate_str > best[0]:
                                best = (idate_str, code)
                    except Exception:
                        continue
            except Exception:
                continue
        if best:
            logger.info(f"[Zoho] Security code found: {best[1]}")
            return best[1]
        return None

    def _extract_code_from_email(self, mid: bytes, since: datetime):
        """Extrae (internaldate, code) de un email. None si no es un security code reciente."""
        status, data = self.mail.fetch(mid, "(INTERNALDATE RFC822)")
        if status != "OK":
            return None

        # Parse internal date (aware - INTERNALDATE viene con offset, normalmente UTC)
        raw_header = data[0][0].decode("utf-8", errors="ignore")
        m = re.search(r'INTERNALDATE "([^"]+)"', raw_header)
        idate_str = m.group(1) if m else ""
        try:
            idate = datetime.strptime(idate_str, "%d-%b-%Y %H:%M:%S %z")
            if since and idate < since:
                return None  # email anterior al submit, ignorar (comparación aware correcta)
        except ValueError:
            pass  # si no se puede parsear la fecha, igual intentamos extraer el código

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
        if "security code" not in subject.lower():
            return None

        # Extraer HTML (el código está en <h1>CODE</h1>)
        html = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html += payload.decode("utf-8", errors="ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                html = payload.decode("utf-8", errors="ignore")

        # Código: alfanumérico 6-10 chars dentro de <h1>...</h1>
        m = re.search(r"<h1[^>]*>\s*([A-Za-z0-9]{6,10})\s*</h1>", html)
        if m:
            return (idate_str, m.group(1))

        # Fallback: texto plano "code ... XXXX"
        text = re.sub(r"<[^>]+>", " ", html)
        m = re.search(r"paste this code[^A-Za-z0-9]*([A-Za-z0-9]{6,10})", text)
        if m:
            return (idate_str, m.group(1))

        return None


async def get_greenhouse_verification_code(
    email: str,
    password: str,
    timeout: int = 120,
    since: Optional[datetime] = None,
) -> Optional[str]:
    """
    Espera el security code de Greenhouse en Zoho.
    Args:
        since: solo emails recibidos después de este momento (default: hace 10 min).
               Pasar el timestamp del submit para ignorar códigos viejos.
    Returns: código alfanumérico (ej "j6Ms1H0j") o None.
    """
    config = ZohoConfig(email=email, password=password)
    client = ZohoIMAPClient(config)
    try:
        await client.connect()
        return await client.wait_for_security_code(timeout=timeout, since=since)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    email_addr = os.getenv("ZOHO_EMAIL")
    password = os.getenv("ZOHO_APP_PASSWORD")

    print("Buscando security codes recientes en Zoho...")
    code = asyncio.run(get_greenhouse_verification_code(email_addr, password, timeout=15))
    print(f"Code: {code}")