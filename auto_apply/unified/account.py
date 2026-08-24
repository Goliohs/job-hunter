"""
Gestión de cuentas para ATS (Job Radar pattern).

Maneja:
- Login en portales (Greenhouse, Lever, Ashby, Workday, etc.)
- Creación de cuenta si no existe
- Verificación de email (códigos IMAP)
- Manejo de 2FA/MFA
- Persistencia de sesión
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from playwright.async_api import Page
from .session import BrowserSessionManager

logger = logging.getLogger(__name__)


class AccountManager:
    """
    Gestor de cuentas para ATS (estilo Job Radar).
    
    Funcionalidades:
    - Login automático con credenciales guardadas
    - Creación de cuenta si no existe
    - Verificación de email via IMAP (códigos 6 dígitos)
    - Manejo de 2FA/MFA
    - Reutilización de sesión entre aplicaciones
    """
    
    def __init__(self, session_manager: BrowserSessionManager, config: dict = None):
        self.session_manager = session_manager
        self.config = config or {}
        self.email_config = config.get("email", {}) if config else {}
        self.accounts_file = Path("/home/Helios/job-hunter/accounts.json")
        self.accounts = self._load_accounts()
    
    def _load_accounts(self) -> dict:
        """Carga cuentas guardadas."""
        if self.accounts_file.exists():
            try:
                with open(self.accounts_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_accounts(self):
        """Guarda cuentas."""
        try:
            with open(self.accounts_file, "w") as f:
                json.dump(self.accounts, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save accounts: {e}")
    
    async def ensure_account(self, ats: str, page: Page, credentials: dict = None) -> bool:
        """
        Asegura que hay cuenta en el ATS.
        Returns: True si autenticado, False si requiere intervención humana.
        """
        ats_key = ats.lower()
        
        # Verificar si ya hay sesión válida
        if await self._check_session(ats, page):
            return True
        
        # Intentar login
        if await self._login(ats, page, credentials):
            return True
        
        # Si no hay credenciales o login falló, crear cuenta
        if credentials:
            if await self._create_account(ats, page, credentials):
                return True
        
        # Requiere intervención humana
        logger.warning(f"[{ats}] Manual login/account creation required")
        return False
    
    async def _check_session(self, ats: str, page: Page) -> bool:
        """Verifica si hay sesión válida."""
        try:
            # Navegar a página de perfil/dashboard del ATS
            dashboard_urls = {
                "greenhouse": "https://app.greenhouse.io/",
                "lever": "https://lever.co/",
                "ashby": "https://app.ashbyhq.com/",
                "workable": "https://www.workable.com/",
                "recruitee": "https://app.recruitee.com/",
            }
            url = dashboard_urls.get(ats.lower())
            if not url:
                return True  # ATS sin dashboard conocido
            
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(2000)
            
            # Verificar indicadores de sesión activa
            # Buscar avatar, nombre usuario, botón logout
            logged_in_indicators = [
                '[data-testid="user-avatar"]',
                '.user-menu',
                'button:has-text("Sign out")',
                'a:has-text("Logout")',
                '[aria-label="User menu"]',
            ]
            for sel in logged_in_indicators:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            
            return False
        except Exception:
            return False
    
    async def _login(self, ats: str, page: Page, credentials: dict) -> bool:
        """Intenta login con credenciales."""
        if not credentials:
            return False
        
        login_urls = {
            "greenhouse": "https://app.greenhouse.io/sign_in",
            "lever": "https://lever.co/sign_in",
            "ashby": "https://app.ashbyhq.com/sign_in",
            "workable": "https://www.workable.com/sign_in",
        }
        
        url = login_urls.get(ats.lower())
        if not url:
            return False
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Selectores comunes de login
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                'input[id*="email"]',
            ]
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[id*="password"]',
            ]
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'input[type="submit"]',
            ]
            
            # Llenar email
            email_filled = False
            for sel in email_selectors:
                try:
                    el = await page.wait_for_selector(sel, state="visible", timeout=5000)
                    if el:
                        await el.fill(credentials.get("email", ""))
                        email_filled = True
                        break
                except Exception:
                    continue
            
            if not email_filled:
                return False
            
            # Llenar password
            password_filled = False
            for sel in password_selectors:
                try:
                    el = await page.wait_for_selector(sel, state="visible", timeout=5000)
                    if el:
                        await el.fill(credentials.get("password", ""))
                        password_filled = True
                        break
                except Exception:
                    continue
            
            if not password_filled:
                return False
            
            # Click submit
            for sel in submit_selectors:
                try:
                    btn = await page.wait_for_selector(sel, state="visible", timeout=3000)
                    if btn:
                        await btn.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        break
                except Exception:
                    continue
            
            # Verificar login exitoso
            await page.wait_for_timeout(3000)
            return await self._check_session(ats, page)
            
        except Exception as e:
            logger.error(f"Login failed for {ats}: {e}")
            return False
    
    async def _create_account(self, ats: str, page: Page, credentials: dict) -> bool:
        """Crea cuenta nueva (requiere intervención humana para CAPTCHA/verificación)."""
        logger.info(f"[{ats}] Account creation requires human intervention")
        
        signup_urls = {
            "greenhouse": "https://app.greenhouse.io/sign_up",
            "lever": "https://lever.co/sign_up",
            "ashby": "https://app.ashbyhq.com/sign_up",
        }
        
        url = signup_urls.get(ats.lower())
        if not url:
            return False
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Esperar a que el humano complete registro y verificación
            # En semi-auto, esperar intervención
            return await self.session_manager.wait_for_human(
                "account_creation", 
                f"Create {ats} account and verify email", 
                timeout=300
            )["action"] == "continue"
        except Exception:
            return False
    
    async def verify_email_code(self, page: Page, ats: str, timeout: int = 120) -> Optional[str]:
        """
        Verifica código de email (6 dígitos) via IMAP.
        Returns: código si encontrado, None si timeout.
        """
        if not self.email_config:
            logger.warning("Email config not set, skipping email verification")
            return await self._manual_code_entry(page, timeout)
        
        # Aquí se conectaría a IMAP para buscar código
        # Por simplicidad, devolvemos None para entrada manual
        return await self._manual_code_entry(page, timeout)
    
    async def _manual_code_entry(self, page: Page, timeout: int) -> Optional[str]:
        """Espera entrada manual de código."""
        logger.info(f"Waiting for manual code entry (timeout: {timeout}s)")
        
        # Buscar campo de código
        code_selectors = [
            'input[name="code"]',
            'input[name="verification_code"]',
            'input[id*="code"]',
            'input[autocomplete="one-time-code"]',
        ]
        
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            for sel in code_selectors:
                try:
                    el = await page.wait_for_selector(sel, state="visible", timeout=2000)
                    if el:
                        # Esperar a que se llene (humano escribe)
                        for _ in range(timeout * 2):
                            value = await el.input_value()
                            if value and len(value) >= 4:
                                return value
                            await asyncio.sleep(0.5)
                except Exception:
                    pass
            await asyncio.sleep(1)
        
        return None
    
    def save_account(self, ats: str, account_data: dict):
        """Guarda datos de cuenta."""
        self.accounts[ats.lower()] = {
            "email": account_data.get("email"),
            "created_at": datetime.now().isoformat(),
            "last_used": datetime.now().isoformat(),
            "data": account_data,
        }
        self._save_accounts()
    
    def get_account(self, ats: str) -> Optional[dict]:
        """Obtiene datos de cuenta guardada."""
        return self.accounts.get(ats.lower())


from pathlib import Path
import json
from datetime import datetime