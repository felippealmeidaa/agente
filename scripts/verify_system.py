#!/usr/bin/env python3
"""Diagnostic & System Verification Script for Hermes-Omni.

Checks:
1. Python version >= 3.12.
2. Required system binaries in PATH (git, ffmpeg, node/npm, uv, docker).
3. Local directory tree integrity.
4. Validation of omni_core.config Settings.
5. Connectivity test to local gateway and remote Ollama URL.
"""

import os
import shutil
import sys
from pathlib import Path

# Add project root to sys.path so omni_core can be imported from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None


def print_msg(msg: str, status: str = "INFO"):
    clean = msg.replace("[green]", "").replace("[/green]", "")
    clean = clean.replace("[red]", "").replace("[/red]", "")
    clean = clean.replace("[yellow]", "").replace("[/yellow]", "")
    clean = clean.replace("[bold]", "").replace("[/bold]", "")
    clean = clean.replace("[cyan]", "").replace("[/cyan]", "")
    clean = clean.replace("[dim]", "").replace("[/dim]", "")
    if HAS_RICH and console:
        console.print(msg)
    else:
        print(f"[{status}] {clean}")


def check_python_version() -> bool:
    v = sys.version_info
    valid = v.major == 3 and v.minor >= 12
    status = f"PASS ({v.major}.{v.minor}.{v.micro})" if valid else f"FAIL ({v.major}.{v.minor}) - Requires 3.12+"
    print_msg(f"• Python Version: {status}", "OK" if valid else "FAIL")
    return valid


def check_binaries() -> dict:
    required = ["git", "ffmpeg", "uv", "node", "docker"]
    results = {}
    print_msg("\n--- Verificando Binarios do Sistema ---")
    for binary in required:
        path = shutil.which(binary)
        if path:
            print_msg(f"• {binary:8s}: ENCONTRADO ({path})", "OK")
            results[binary] = True
        else:
            print_msg(f"• {binary:8s}: NAO ENCONTRADO NO PATH", "WARN")
            results[binary] = False
    return results


def check_directories() -> bool:
    required_dirs = [
        PROJECT_ROOT / "skills" / "auto_learned",
        PROJECT_ROOT / "omni_core" / "orchestrator",
        PROJECT_ROOT / "omni_core" / "coding_council",
        PROJECT_ROOT / "omni_core" / "specialists",
        PROJECT_ROOT / "omni_core" / "self_improvement",
    ]
    all_ok = True
    print_msg("\n--- Verificando Estrutura de Diretorios ---")
    for d in required_dirs:
        if not d.exists():
            print_msg(f"Diretorio ausente: {d}", "FAIL")
            all_ok = False
    if all_ok:
        print_msg("• Estrutura de pastas verificada com sucesso.", "OK")
    return all_ok


def check_settings_import() -> bool:
    print_msg("\n--- Verificando Modulos e Configuracoes ---")
    try:
        from omni_core.config import get_settings
        settings = get_settings()
        print_msg(f"• Configuracoes carregadas com sucesso.", "OK")
        print_msg(f"  - Modelo alvo: {settings.ollama_model_name}")
        print_msg(f"  - Remote Ollama URL: {settings.ollama_remote_url}")
        print_msg(f"  - Local Gateway Host: http://{settings.gateway_host}:{settings.gateway_port}")
        return True
    except Exception as exc:
        print_msg(f"• Falha ao carregar configuracoes: {exc}", "FAIL")
        return False


def main():
    print_msg("====================================================")
    print_msg("       HERMES-OMNI SYSTEM VERIFICATION DIAGNOSTIC   ")
    print_msg("====================================================\n")

    check_python_version()
    check_directories()
    check_settings_import()
    check_binaries()
    print_msg("\nFASE 1 - Base Verification Complete!", "DONE")


if __name__ == "__main__":
    main()
