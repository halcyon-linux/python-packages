"""Steam launch wrappers forcing the latest DLSS presets through DXVK-NVAPI.

Port of dlss-swapper and dlss-swapper-dll (from CachyOS, GPL-3.0). Both
export the DXVK-NVAPI override variables and exec the wrapped command.
dlss-swapper additionally sets PROTON_ENABLE_NGX_UPDATER so the DLSS
DLLs are refreshed from the driver (and takes over their future updates);
dlss-swapper-dll relies on the DLLs that ship with the game.
"""

from __future__ import annotations

import os
import sys

PRESET_ENV = {
    "DXVK_NVAPI_DRS_NGX_DLSS_RR_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_FG_OVERRIDE": "on",
    "DXVK_NVAPI_DRS_NGX_DLSS_RR_OVERRIDE_RENDER_PRESET_SELECTION": "render_preset_latest",
    "DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE_RENDER_PRESET_SELECTION": "render_preset_latest",
}
NGX_UPDATER_ENV = {"PROTON_ENABLE_NGX_UPDATER": "1"}
__version__ = "1.0.0"


def exec_with(environment: dict[str, str], argv: list[str]) -> int:
    """Export the overrides and exec the wrapped command (bash `exec "$@"`)."""
    if not argv:
        return 0
    os.environ.update(environment)
    try:
        os.execvpe(argv[0], argv, os.environ)
    except FileNotFoundError:
        print(f"{argv[0]}: command not found", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"{argv[0]}: permission denied", file=sys.stderr)
        return 126
    # Unreachable after a successful exec; reached only when os.execvpe is
    # replaced (tests).
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    return exec_with({**PRESET_ENV, **NGX_UPDATER_ENV}, args)


def dll_main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    return exec_with(PRESET_ENV, args)
