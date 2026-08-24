"""
Auto-apply unificado - Integración de AutoApply + JobPilot + Job Radar + Workday Copilot

Arquitectura multi-agente (Job Radar):
  ANALYZE → NAVIGATE → AUTH → FILL → VALIDATE → REVIEW

Principios:
- Fillers específicos por ATS (no genéricos)
- Review gate: NUNCA submit sin aprobación humana
- Gestión de cuentas: login, crear, verificación email
- Sesión persistente de navegador (JobPilot style)
- Push notifications para intervención humana
- Checkpointing en cada etapa
"""

# Import fillers para que se registren
from . import fillers_greenhouse
from . import fillers_lever
from . import fillers_ashby
from . import fillers_standard
from . import fillers_linkedin

from .orchestrator import ApplicationOrchestrator
from .session import BrowserSessionManager
from .fillers import FILLER_REGISTRY, get_filler
from .account import AccountManager
from .notifications import NotificationManager
from .state import ApplicationState, ApplicationStatus

__all__ = [
    "ApplicationOrchestrator",
    "BrowserSessionManager", 
    "FILLER_REGISTRY",
    "get_filler",
    "AccountManager",
    "NotificationManager",
    "ApplicationState",
    "ApplicationStatus",
]