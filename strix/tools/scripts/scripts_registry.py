"""Custom Scripts Registry for deterministic tool execution.

This module provides a registry for custom bash scripts and tools that can be:
- Written dynamically by agents
- Executed in a deterministic, reproducible manner
- Chained together in automated pipelines

Benefits over generative AI execution:
- Deterministic: Same script, same results
- Efficient: No LLM overhead for routine scans
- Reusable: Scripts persist across sessions
- Auditable: Clear record of what was executed

Usage:
    from strix.tools.scripts import ScriptsRegistry, get_scripts_registry

    registry = get_scripts_registry()

    # Register a custom script
    registry.register_script(
        name="nmap_full_scan",
        content="#!/bin/bash\\nnmap -sV -sC -p- $1",
        description="Full nmap scan with version detection",
        category="reconnaissance",
        parameters=["target"]
    )

    # Execute it
    result = await registry.execute("nmap_full_scan", target="192.168.1.1")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ScriptCategory(str, Enum):
    """Categories for custom scripts."""

    RECONNAISSANCE = "reconnaissance"  # Information gathering
    SCANNING = "scanning"  # Port/vulnerability scanning
    EXPLOITATION = "exploitation"  # Exploit execution
    POST_EXPLOITATION = "post_exploitation"  # Post-exploit actions
    REPORTING = "reporting"  # Report generation
    UTILITY = "utility"  # General utilities
    VALIDATION = "validation"  # Finding validation


class ScriptLanguage(str, Enum):
    """Supported script languages."""

    BASH = "bash"
    PYTHON = "python"
    RUBY = "ruby"
    PERL = "perl"
    POWERSHELL = "powershell"


@dataclass
class ScriptMetadata:
    """Metadata for a registered script."""

    name: str
    description: str
    category: ScriptCategory
    language: ScriptLanguage
    parameters: list[str]  # Parameter names
    parameter_descriptions: dict[str, str] = field(default_factory=dict)
    author: str = "strix"
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = field(default_factory=list)
    timeout: int = 300  # Default 5 minutes
    requires_root: bool = False
    sandbox_safe: bool = True  # Can run in sandbox

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "language": self.language.value,
            "parameters": self.parameters,
            "parameter_descriptions": self.parameter_descriptions,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "timeout": self.timeout,
            "requires_root": self.requires_root,
            "sandbox_safe": self.sandbox_safe,
        }


@dataclass
class ScriptExecutionResult:
    """Result of script execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    script_name: str
    parameters: dict[str, str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "script_name": self.script_name,
            "parameters": self.parameters,
            "error": self.error,
        }


class ScriptsRegistry:
    """Registry for custom scripts and tools.

    Provides:
    - Script registration and storage
    - Parameter validation
    - Secure execution
    - Result caching
    - Version management
    """

    def __init__(self, scripts_dir: Path | None = None):
        """Initialize the scripts registry.

        Args:
            scripts_dir: Directory to store scripts. Defaults to ./strix_scripts
        """
        self.scripts_dir = scripts_dir or Path.cwd() / "strix_scripts"
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

        self._scripts: dict[str, ScriptMetadata] = {}
        self._content_cache: dict[str, str] = {}

        # Load existing scripts
        self._load_existing_scripts()

    def _load_existing_scripts(self) -> None:
        """Load existing scripts from the scripts directory."""
        metadata_dir = self.scripts_dir / "metadata"
        if not metadata_dir.exists():
            metadata_dir.mkdir(parents=True, exist_ok=True)
            return

        import json

        for meta_file in metadata_dir.glob("*.json"):
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                metadata = ScriptMetadata(
                    name=data["name"],
                    description=data["description"],
                    category=ScriptCategory(data["category"]),
                    language=ScriptLanguage(data["language"]),
                    parameters=data["parameters"],
                    parameter_descriptions=data.get("parameter_descriptions", {}),
                    author=data.get("author", "strix"),
                    version=data.get("version", "1.0.0"),
                    created_at=data.get("created_at", datetime.now(UTC).isoformat()),
                    updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
                    tags=data.get("tags", []),
                    timeout=data.get("timeout", 300),
                    requires_root=data.get("requires_root", False),
                    sandbox_safe=data.get("sandbox_safe", True),
                )

                self._scripts[metadata.name] = metadata
                logger.debug(f"Loaded script: {metadata.name}")

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load script metadata {meta_file}: {e}")

    def _get_script_path(self, name: str, language: ScriptLanguage) -> Path:
        """Get the file path for a script."""
        extensions = {
            ScriptLanguage.BASH: ".sh",
            ScriptLanguage.PYTHON: ".py",
            ScriptLanguage.RUBY: ".rb",
            ScriptLanguage.PERL: ".pl",
            ScriptLanguage.POWERSHELL: ".ps1",
        }
        ext = extensions.get(language, ".sh")
        return self.scripts_dir / f"{name}{ext}"

    def _get_interpreter(self, language: ScriptLanguage) -> list[str]:
        """Get the interpreter command for a language."""
        interpreters = {
            ScriptLanguage.BASH: ["/bin/bash"],
            ScriptLanguage.PYTHON: ["python3"],
            ScriptLanguage.RUBY: ["ruby"],
            ScriptLanguage.PERL: ["perl"],
            ScriptLanguage.POWERSHELL: ["pwsh"],
        }
        return interpreters.get(language, ["/bin/bash"])

    def register_script(
        self,
        name: str,
        content: str,
        description: str,
        category: str | ScriptCategory = ScriptCategory.UTILITY,
        language: str | ScriptLanguage = ScriptLanguage.BASH,
        parameters: list[str] | None = None,
        parameter_descriptions: dict[str, str] | None = None,
        tags: list[str] | None = None,
        timeout: int = 300,
        requires_root: bool = False,
        sandbox_safe: bool = True,
    ) -> ScriptMetadata:
        """Register a new script or update an existing one.

        Args:
            name: Unique script name (alphanumeric + underscore)
            content: The script content
            description: Human-readable description
            category: Script category
            language: Script language
            parameters: List of parameter names
            parameter_descriptions: Optional descriptions for parameters
            tags: Optional tags for searching
            timeout: Execution timeout in seconds
            requires_root: Whether script needs root privileges
            sandbox_safe: Whether script can run in sandbox

        Returns:
            ScriptMetadata for the registered script
        """
        import json

        # Validate name
        if not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid script name: {name}. Use alphanumeric and underscore only.")

        # Convert enums if strings passed
        if isinstance(category, str):
            category = ScriptCategory(category)
        if isinstance(language, str):
            language = ScriptLanguage(language)

        # Create metadata
        now = datetime.now(UTC).isoformat()
        existing = self._scripts.get(name)

        metadata = ScriptMetadata(
            name=name,
            description=description,
            category=category,
            language=language,
            parameters=parameters or [],
            parameter_descriptions=parameter_descriptions or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
            tags=tags or [],
            timeout=timeout,
            requires_root=requires_root,
            sandbox_safe=sandbox_safe,
            version=self._increment_version(existing.version) if existing else "1.0.0",
        )

        # Save script content
        script_path = self._get_script_path(name, language)
        with script_path.open("w", encoding="utf-8") as f:
            f.write(content)

        # Make executable
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        # Save metadata
        metadata_dir = self.scripts_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        with (metadata_dir / f"{name}.json").open("w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        # Update registry
        self._scripts[name] = metadata
        self._content_cache[name] = content

        logger.info(f"Registered script: {name} (v{metadata.version})")
        return metadata

    def _increment_version(self, version: str) -> str:
        """Increment patch version."""
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        return version

    def get_script(self, name: str) -> ScriptMetadata | None:
        """Get script metadata by name."""
        return self._scripts.get(name)

    def get_script_content(self, name: str) -> str | None:
        """Get script content by name."""
        if name in self._content_cache:
            return self._content_cache[name]

        metadata = self._scripts.get(name)
        if not metadata:
            return None

        script_path = self._get_script_path(name, metadata.language)
        if script_path.exists():
            content = script_path.read_text(encoding="utf-8")
            self._content_cache[name] = content
            return content

        return None

    def list_scripts(
        self,
        category: ScriptCategory | None = None,
        tags: list[str] | None = None,
    ) -> list[ScriptMetadata]:
        """List registered scripts, optionally filtered.

        Args:
            category: Filter by category
            tags: Filter by tags (any match)

        Returns:
            List of matching script metadata
        """
        scripts = list(self._scripts.values())

        if category:
            scripts = [s for s in scripts if s.category == category]

        if tags:
            scripts = [s for s in scripts if any(t in s.tags for t in tags)]

        return scripts

    def delete_script(self, name: str) -> bool:
        """Delete a script.

        Args:
            name: Script name to delete

        Returns:
            True if deleted, False if not found
        """
        metadata = self._scripts.get(name)
        if not metadata:
            return False

        # Delete script file
        script_path = self._get_script_path(name, metadata.language)
        if script_path.exists():
            script_path.unlink()

        # Delete metadata
        metadata_path = self.scripts_dir / "metadata" / f"{name}.json"
        if metadata_path.exists():
            metadata_path.unlink()

        # Remove from registry
        del self._scripts[name]
        self._content_cache.pop(name, None)

        logger.info(f"Deleted script: {name}")
        return True

    async def execute(
        self,
        name: str,
        **parameters: str,
    ) -> ScriptExecutionResult:
        """Execute a registered script.

        Args:
            name: Script name
            **parameters: Parameter values

        Returns:
            ScriptExecutionResult with output and status
        """
        import time

        start_time = time.monotonic()

        metadata = self._scripts.get(name)
        if not metadata:
            return ScriptExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=0,
                script_name=name,
                parameters=parameters,
                error=f"Script not found: {name}",
            )

        # Validate parameters
        missing = set(metadata.parameters) - set(parameters.keys())
        if missing:
            return ScriptExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=0,
                script_name=name,
                parameters=parameters,
                error=f"Missing required parameters: {', '.join(missing)}",
            )

        script_path = self._get_script_path(name, metadata.language)
        if not script_path.exists():
            return ScriptExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=0,
                script_name=name,
                parameters=parameters,
                error=f"Script file not found: {script_path}",
            )

        # Build command
        interpreter = self._get_interpreter(metadata.language)
        cmd = interpreter + [str(script_path)]

        # Add parameters as positional args (in order)
        for param in metadata.parameters:
            if param in parameters:
                cmd.append(str(parameters[param]))

        # Execute
        try:
            env = os.environ.copy()
            # Add parameters as environment variables too
            for param, value in parameters.items():
                env[f"STRIX_PARAM_{param.upper()}"] = str(value)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=metadata.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return ScriptExecutionResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=-1,
                    duration_ms=duration_ms,
                    script_name=name,
                    parameters=parameters,
                    error=f"Script timed out after {metadata.timeout}s",
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return ScriptExecutionResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                exit_code=process.returncode or 0,
                duration_ms=duration_ms,
                script_name=name,
                parameters=parameters,
            )

        except (OSError, subprocess.SubprocessError) as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return ScriptExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=duration_ms,
                script_name=name,
                parameters=parameters,
                error=str(e),
            )


# Predefined script templates for common operations
SCRIPT_TEMPLATES: dict[str, dict[str, Any]] = {
    "nmap_quick_scan": {
        "content": """#!/bin/bash
# Quick nmap scan with service detection
TARGET="$1"
nmap -sV -T4 --top-ports 1000 -oN /tmp/nmap_quick_$$.txt "$TARGET"
cat /tmp/nmap_quick_$$.txt
""",
        "description": "Quick nmap scan of top 1000 ports with version detection",
        "category": ScriptCategory.RECONNAISSANCE,
        "language": ScriptLanguage.BASH,
        "parameters": ["target"],
        "parameter_descriptions": {"target": "Target IP or hostname"},
        "tags": ["nmap", "ports", "scan"],
    },
    "nmap_full_scan": {
        "content": """#!/bin/bash
# Full nmap scan with scripts
TARGET="$1"
nmap -sV -sC -p- -T4 -oN /tmp/nmap_full_$$.txt "$TARGET"
cat /tmp/nmap_full_$$.txt
""",
        "description": "Full nmap scan of all ports with version detection and scripts",
        "category": ScriptCategory.RECONNAISSANCE,
        "language": ScriptLanguage.BASH,
        "parameters": ["target"],
        "parameter_descriptions": {"target": "Target IP or hostname"},
        "tags": ["nmap", "ports", "scan", "full"],
        "timeout": 1800,  # 30 minutes for full scan
    },
    "nmap_vuln_scan": {
        "content": """#!/bin/bash
# Nmap vulnerability scan
TARGET="$1"
nmap -sV --script=vuln -oN /tmp/nmap_vuln_$$.txt "$TARGET"
cat /tmp/nmap_vuln_$$.txt
""",
        "description": "Nmap vulnerability scanning using NSE scripts",
        "category": ScriptCategory.SCANNING,
        "language": ScriptLanguage.BASH,
        "parameters": ["target"],
        "parameter_descriptions": {"target": "Target IP or hostname"},
        "tags": ["nmap", "vulnerability", "scan"],
        "timeout": 900,
    },
    "nikto_scan": {
        "content": """#!/bin/bash
# Nikto web vulnerability scan
TARGET="$1"
nikto -h "$TARGET" -o /tmp/nikto_$$.txt
cat /tmp/nikto_$$.txt
""",
        "description": "Nikto web server vulnerability scan",
        "category": ScriptCategory.SCANNING,
        "language": ScriptLanguage.BASH,
        "parameters": ["target"],
        "parameter_descriptions": {"target": "Target URL"},
        "tags": ["nikto", "web", "vulnerability"],
        "timeout": 1200,
    },
    "gobuster_dir": {
        "content": """#!/bin/bash
# Gobuster directory enumeration
TARGET="$1"
WORDLIST="${2:-/usr/share/wordlists/dirb/common.txt}"
gobuster dir -u "$TARGET" -w "$WORDLIST" -o /tmp/gobuster_$$.txt
cat /tmp/gobuster_$$.txt
""",
        "description": "Directory enumeration with gobuster",
        "category": ScriptCategory.RECONNAISSANCE,
        "language": ScriptLanguage.BASH,
        "parameters": ["target", "wordlist"],
        "parameter_descriptions": {
            "target": "Target URL",
            "wordlist": "Path to wordlist (optional)",
        },
        "tags": ["gobuster", "directory", "enumeration"],
    },
    "whatweb_scan": {
        "content": """#!/bin/bash
# WhatWeb technology detection
TARGET="$1"
whatweb -a 3 -v "$TARGET"
""",
        "description": "Web technology fingerprinting with WhatWeb",
        "category": ScriptCategory.RECONNAISSANCE,
        "language": ScriptLanguage.BASH,
        "parameters": ["target"],
        "parameter_descriptions": {"target": "Target URL"},
        "tags": ["whatweb", "fingerprint", "technology"],
    },
    "ffuf_fuzz": {
        "content": """#!/bin/bash
# FFUF fuzzing
TARGET="$1"
WORDLIST="${2:-/usr/share/wordlists/dirb/common.txt}"
ffuf -u "${TARGET}/FUZZ" -w "$WORDLIST" -o /tmp/ffuf_$$.json -of json
cat /tmp/ffuf_$$.json
""",
        "description": "Web fuzzing with ffuf",
        "category": ScriptCategory.RECONNAISSANCE,
        "language": ScriptLanguage.BASH,
        "parameters": ["target", "wordlist"],
        "parameter_descriptions": {
            "target": "Target URL (FUZZ will be appended)",
            "wordlist": "Path to wordlist (optional)",
        },
        "tags": ["ffuf", "fuzz", "directory"],
    },
}


# Global registry instance
_global_registry: ScriptsRegistry | None = None


def get_scripts_registry() -> ScriptsRegistry:
    """Get the global scripts registry."""
    global _global_registry  # noqa: PLW0603

    if _global_registry is None:
        _global_registry = ScriptsRegistry()

        # Register predefined templates if not already present
        for name, template in SCRIPT_TEMPLATES.items():
            if _global_registry.get_script(name) is None:
                _global_registry.register_script(name=name, **template)

    return _global_registry


def set_scripts_registry(registry: ScriptsRegistry) -> None:
    """Set the global scripts registry."""
    global _global_registry  # noqa: PLW0603
    _global_registry = registry
