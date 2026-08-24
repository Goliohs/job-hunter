"""
Gestión de notificaciones push (Job Radar pattern - ntfy.sh).

Notificaciones para:
- CAPTCHA detectado
- Verificación de email requerida
- Intervención humana necesaria
- Aplicación enviada exitosamente
- Error irrecuperable
"""
import asyncio
import logging
from typing import Optional
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Notificación a enviar."""
    topic: str
    title: str
    message: str
    priority: int = 3  # 1=urgent, 3=normal, 5=low
    tags: list = None
    actions: list = None  # Botones de acción
    click_url: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.actions is None:
            self.actions = []


class NotificationManager:
    """
    Gestor de notificaciones push via ntfy.sh (Job Radar pattern).
    
    Configuración:
    - NTFY_TOPIC: topic único para notificaciones
    - NTFY_SERVER: servidor ntfy (default: ntfy.sh)
    - NTFY_AUTH: token opcional para topic privado
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.topic = self.config.get("NTFY_TOPIC", "jobhunter-alerts")
        self.server = self.config.get("NTFY_SERVER", "https://ntfy.sh")
        self.auth_token = self.config.get("NTFY_AUTH")
        self.enabled = bool(self.topic)
        self._session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def send(self, notification: Notification) -> bool:
        """Envía notificación push."""
        if not self.enabled:
            logger.debug("Notifications disabled, skipping")
            return False
        
        try:
            session = await self._get_session()
            
            headers = {
                "Title": notification.title,
                "Priority": str(notification.priority),
                "Tags": ",".join(notification.tags) if notification.tags else "",
            }
            if notification.click_url:
                headers["Click"] = notification.click_url
            if notification.actions:
                import json
                headers["Actions"] = json.dumps(notification.actions)
            
            url = f"{self.server}/{self.topic}"
            async with session.post(url, data=notification.message, headers=headers) as resp:
                if resp.status == 200:
                    logger.info(f"Notification sent: {notification.title}")
                    return True
                else:
                    logger.error(f"Notification failed: {resp.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    async def notify_captcha(self, ats: str, job_title: str, url: str) -> bool:
        """Notifica CAPTCHA detectado."""
        return await self.send(Notification(
            topic=self.topic,
            title=f"🤖 CAPTCHA en {ats}",
            message=f"CAPTCHA detectado aplicando a: {job_title}\n{url}",
            priority=1,
            tags=["captcha", ats.lower(), "human_needed"],
            actions=[{"action": "view", "label": "Abrir", "url": url}],
            click_url=url,
        ))
    
    async def notify_email_verification(self, ats: str, job_title: str, url: str) -> bool:
        """Notifica verificación de email requerida."""
        return await self.send(Notification(
            topic=self.topic,
            title=f"📧 Verificación email en {ats}",
            message=f"Se requiere verificación de email para: {job_title}\n{url}",
            priority=1,
            tags=["email", "verification", ats.lower()],
            actions=[{"action": "view", "label": "Abrir", "url": url}],
            click_url=url,
        ))
    
    async def notify_human_needed(self, ats: str, job_title: str, reason: str, url: str) -> bool:
        """Notifica intervención humana requerida."""
        return await self.send(Notification(
            topic=self.topic,
            title=f"👤 Intervención requerida en {ats}",
            message=f"{reason}\nJob: {job_title}\n{url}",
            priority=2,
            tags=["human", ats.lower(), "intervention"],
            actions=[{"action": "view", "label": "Abrir", "url": url}],
            click_url=url,
        ))
    
    async def notify_success(self, ats: str, job_title: str, company: str, url: str) -> bool:
        """Notifica aplicación exitosa."""
        return await self.send(Notification(
            topic=self.topic,
            title=f"✅ Aplicado en {company}",
            message=f"Aplicación exitosa a: {job_title}\nATS: {ats}\n{url}",
            priority=3,
            tags=["success", ats.lower(), company.lower().replace(" ", "_")],
            click_url=url,
        ))
    
    async def notify_failure(self, ats: str, job_title: str, error: str, url: str) -> bool:
        """Notifica fallo de aplicación."""
        return await self.send(Notification(
            topic=self.topic,
            title=f"❌ Fallo en {ats}",
            message=f"Error aplicando a: {job_title}\n{error}\n{url}",
            priority=2,
            tags=["failure", ats.lower(), "error"],
            click_url=url,
        ))
    
    async def notify_broken_form(self, ats: str, job_title: str, broken_fields: list, url: str) -> bool:
        """Notifica formulario roto."""
        fields_str = "\n".join([f"  • {f['label']}: {f.get('sample_options', [])[:3]}" for f in broken_fields])
        return await self.send(Notification(
            topic=self.topic,
            title=f"🔧 Formulario roto en {ats}",
            message=f"Campos rotos detectados en: {job_title}\n{fields_str}\n{url}",
            priority=2,
            tags=["broken_form", ats.lower()],
            actions=[{"action": "view", "label": "Abrir (semi-auto)", "url": url}],
            click_url=url,
        ))
    
    async def close(self):
        """Cierra sesión HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()


# Instancia global
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager(config: dict = None) -> NotificationManager:
    """Obtiene instancia global."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager(config)
    return _notification_manager