"""
Gestión de sesión persistente de navegador (JobPilot pattern).

Mantiene sesión de navegador entre aplicaciones:
- Cookies, localStorage, sessionStorage persistentes
- Perfil de usuario reutilizable
- Login único, sesión reutilizable
- Contexto aislado por aplicación si necesario
"""
import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
import logging

logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Gestor de sesión persistente estilo JobPilot.
    
    Características:
    - Directorio de perfil persistente (cookies, storage, certificados)
    - Un solo browser context reutilizado
    - Limpieza automática de páginas huérfanas
    - Screenshots automáticos en checkpoints
    """
    
    def __init__(
        self,
        profile_dir: str = str(Path(__file__).resolve().parent.parent.parent / "browser_profile"),
        headless: bool = False,
        viewport: dict = None,
        screenshots_dir: str = str(Path(__file__).resolve().parent.parent.parent / "screenshots"),
        user_agent: str = None,
    ):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        
        self.headless = headless
        self.viewport = viewport or {"width": 1280, "height": 900}
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: dict[str, Page] = {}  # app_id -> page
        self._initialized = False
    
    async def initialize(self) -> None:
        """Inicializa browser y context persistente."""
        if self._initialized:
            return
            
        self._playwright = await async_playwright().start()
        
        # Usar Chrome real del sistema si existe (pasa detecciones anti-bot
        # mucho mejor que el Chromium bundled de Playwright)
        chrome_bin = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        launch_kwargs = {}
        if chrome_bin:
            launch_kwargs["executable_path"] = chrome_bin
            logger.info(f"Using system Chrome: {chrome_bin}")
        
        # Argumentos: NADA que delate automatización
        # (--disable-web-security y --disable-gpu SON red flags detectables)
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
            **launch_kwargs,
        )
        
        # Context persistente con perfil de usuario
        self._context = await self._browser.new_context(
            viewport=self.viewport,
            user_agent=self.user_agent,
            locale="en-US",
            timezone_id="America/Costa_Rica",
            storage_state=str(self.profile_dir / "storage_state.json") 
                if (self.profile_dir / "storage_state.json").exists() 
                else None,
            accept_downloads=True,
        )
        
        # Anti-detección: parches consistentes con un Chrome real
        await self._context.add_init_script("""
            // webdriver fuera
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // chrome object con estructura real
            window.chrome = {
                runtime: {
                    connect: () => {}, sendMessage: () => {},
                    PlatformOs: {MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd'},
                },
                loadTimes: () => ({requestTime: Date.now() / 1000}),
                csi: () => ({startE: Date.now(), onloadT: Date.now(), pageT: 1000}),
            };
            // plugins con forma real (Chrome desktop tiene 5)
            const pluginData = [
                {name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            ];
            const pluginArr = pluginData.map(p => Object.assign({}, p, {length: 1}));
            Object.defineProperty(navigator, 'plugins', {
                get: () => Object.assign(pluginArr, {
                    item: i => pluginArr[i], namedItem: n => pluginArr.find(p => p.name === n),
                    refresh: () => {}, length: pluginArr.length,
                }),
            });
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => Object.assign([{type: 'application/pdf'}], {
                    item: i => ({type: 'application/pdf'}), length: 1,
                }),
            });
            // languages coherentes con locale
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            // WebGL: vendor/renderer de GPU real (no SwiftShader/llvmpipe)
            const getParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (Intel)';
                if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics (0x000046A8), OpenGL 4.6)';
                return getParam.call(this, param);
            };
            const getParam2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (Intel)';
                if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics (0x000046A8), OpenGL 4.6)';
                return getParam2.call(this, param);
            };
            // permissions.query coherente (notifications prompt por defecto)
            const origQuery = window.Notification && Notification.permission;
            if (window.Notification) {
                window.Notification.permission = 'default';
            }
        """)
        
        self._initialized = True
        logger.info(f"Browser session initialized (headless={self.headless})")
    
    async def get_page(self, app_id: str) -> Page:
        """Obtiene o crea una página para una aplicación."""
        if app_id in self._pages:
            page = self._pages[app_id]
            if not page.is_closed():
                return page
        
        if not self._initialized:
            await self.initialize()
        
        page = await self._context.new_page()
        self._pages[app_id] = page
        
        # Configurar timeouts por defecto
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(60000)
        
        return page
    
    async def close_page(self, app_id: str) -> None:
        """Cierra página de una aplicación."""
        if app_id in self._pages:
            page = self._pages.pop(app_id)
            if not page.is_closed():
                await page.close()
    
    async def take_screenshot(self, app_id: str, name: str) -> str:
        """Toma screenshot y guarda en directorio."""
        page = self._pages.get(app_id)
        if not page or page.is_closed():
            return ""
        
        path = self.screenshots_dir / f"{app_id}_{name}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.debug(f"Screenshot saved: {path}")
        return str(path)
    
    async def save_storage_state(self) -> None:
        """Guarda cookies, localStorage, sessionStorage."""
        if self._context:
            await self._context.storage_state(path=str(self.profile_dir / "storage_state.json"))
            logger.debug("Storage state saved")
    
    async def load_storage_state(self) -> None:
        """Carga estado guardado (se hace en initialize)."""
        pass  # Se carga automáticamente en new_context
    
    async def clear_storage(self) -> None:
        """Limpia almacenamiento (logout)."""
        if self._context:
            await self._context.clear_cookies()
            await self._context.storage_state(path=str(self.profile_dir / "storage_state.json"))
    
    async def wait_for_human(self, app_id: str, message: str, timeout: int = 300) -> dict:
        """
        Espera intervención humana (CAPTCHA, 2FA, campos rotos).
        Returns: {"action": "continue"|"abort"|"retry", "data": {...}}
        """
        page = self._pages.get(app_id)
        if not page:
            return {"action": "abort", "error": "Page not found"}
        
        # Tomar screenshot para revisión
        screenshot = await self.take_screenshot(app_id, "human_intervention")
        
        logger.warning(f"[{app_id}] HUMAN INTERVENTION REQUIRED: {message}")
        logger.warning(f"[{app_id}] Screenshot: {screenshot}")
        
        # Aquí se integraría ntfy.sh para notificación push
        # Por ahora, polling simple
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(2)
            
            # Verificar si la página cambió (submit, error, etc.)
            try:
                current_url = page.url
                # Detectar éxito
                if any(x in current_url.lower() for x in ["/thanks", "/success", "/confirmation", "thank-you"]):
                    return {"action": "continue", "url": current_url}
                
                # Detectar error de validación
                errors = await page.query_selector_all(".error, .field-error, .alert-danger, [role='alert']")
                for err in errors:
                    if await err.is_visible():
                        text = await err.inner_text()
                        if text and "thank" not in text.lower():
                            return {"action": "retry", "error": text[:200]}
            except Exception:
                pass
        
        return {"action": "abort", "error": "Timeout waiting for human"}
    
    async def shutdown(self) -> None:
        """Cierra todo limpiamente."""
        # Guardar estado antes de cerrar
        await self.save_storage_state()
        
        # Cerrar páginas
        for app_id, page in self._pages.items():
            if not page.is_closed():
                await page.close()
        self._pages.clear()
        
        # Cerrar context y browser
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        self._initialized = False
        logger.info("Browser session shutdown complete")


# Instancia global singleton
_global_session: Optional[BrowserSessionManager] = None


async def get_global_session(**kwargs) -> BrowserSessionManager:
    """Obtiene instancia global singleton."""
    global _global_session
    if _global_session is None:
        _global_session = BrowserSessionManager(**kwargs)
        await _global_session.initialize()
    return _global_session


async def shutdown_global_session() -> None:
    """Cierra sesión global."""
    global _global_session
    if _global_session:
        await _global_session.shutdown()
        _global_session = None