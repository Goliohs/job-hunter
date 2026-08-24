"""
Estado y máquina de estados para aplicaciones (Job Radar pattern).
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid


class ApplicationStatus(Enum):
    """Estados de una aplicación (Job Radar state machine)."""
    PENDING = "pending"                    # Encolada, esperando procesamiento
    ANALYZING = "analyzing"                # Detectando ATS, analizando formulario
    NAVIGATING = "navigating"              # Navegando a la URL, esperando carga
    AUTHENTICATING = "authenticating"      # Login / crear cuenta / verificación email
    FILLING = "filling"                    # Llenando campos del formulario
    VALIDATING = "validating"              # Validando campos, detectando errores
    HUMAN_REVIEW = "human_review"          # Esperando aprobación humana (review gate)
    SUBMITTING = "submitting"              # Enviando aplicación (replay aprobado)
    SUBMITTED = "submitted"                # Confirmado exitoso
    FAILED = "failed"                      # Error irrecuperable
    PARKED = "parked"                      # Estacionado - requiere intervención humana
    CAPTCHA_BLOCKED = "captcha_blocked"    # Bloqueado por CAPTCHA


@dataclass
class ApplicationState:
    """Estado completo de una aplicación en progreso."""
    # Identificación
    application_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    job_id: int = 0
    job_url: str = ""
    ats_type: str = ""
    
    # Estado actual
    status: ApplicationStatus = ApplicationStatus.PENDING
    current_step: str = ""
    step_started_at: Optional[datetime] = None
    
    # Datos del job y candidato
    job_data: dict = field(default_factory=dict)
    candidate_data: dict = field(default_factory=dict)
    
    # Sesión de navegador
    browser_session_id: Optional[str] = None
    page_url: str = ""
    page_html: str = ""
    
    # Datos detectados
    ats_detected: str = ""
    form_fields: list = field(default_factory=list)
    required_fields: list = field(default_factory=list)
    optional_fields: list = field(default_factory=list)
    broken_fields: list = field(default_factory=list)
    
    # Campos llenados
    filled_fields: dict = field(default_factory=dict)
    validation_errors: list = field(default_factory=list)
    
    # Review gate
    review_screenshot: Optional[str] = None
    review_data: dict = field(default_factory=dict)
    human_approved: bool = False
    human_edits: dict = field(default_factory=dict)
    
    # Resultado
    success: bool = False
    submit_response: Optional[str] = None
    error_message: Optional[str] = None
    
    # Checkpointing
    checkpoints: dict = field(default_factory=dict)
    last_checkpoint: Optional[str] = None
    
    # Metadatos
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    
    def update_status(self, status: ApplicationStatus, step: str = ""):
        """Actualiza estado con timestamp."""
        self.status = status
        self.current_step = step or status.value
        self.step_started_at = datetime.now()
        self.updated_at = datetime.now()
        self.checkpoints[status.value] = datetime.now().isoformat()
        self.last_checkpoint = status.value
    
    def add_checkpoint(self, name: str, data: dict = None):
        """Añade checkpoint con datos opcionales."""
        self.checkpoints[name] = {
            "timestamp": datetime.now().isoformat(),
            "data": data or {}
        }
        self.last_checkpoint = name
    
    def can_retry(self) -> bool:
        """Verifica si puede reintentar."""
        return self.retry_count < self.max_retries
    
    def increment_retry(self):
        """Incrementa contador de reintentos."""
        self.retry_count += 1
        self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        """Serializa para logging/debug."""
        return {
            "application_id": self.application_id,
            "job_id": self.job_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "ats_type": self.ats_type,
            "filled_fields": len(self.filled_fields),
            "validation_errors": len(self.validation_errors),
            "human_approved": self.human_approved,
            "success": self.success,
            "error": self.error_message,
            "retry_count": self.retry_count,
        }