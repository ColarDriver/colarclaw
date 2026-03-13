"""Platform detection, configuration, security, and diagnostics."""
from .detect import detect_platform, resolve_os_summary
from .config import load_gateway_config
from .doctor import run_doctor_checks
