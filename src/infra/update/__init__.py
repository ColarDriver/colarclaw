"""Update checking, install flows, and startup update logic."""
from .check import (
    UpdateCheckResult,
    check_update_status,
    run_gateway_update,
)
from .install import (
    InstallTarget,
    InstallFlowResult,
    parse_install_spec,
    run_install_flow,
)
from .startup import check_startup_update
