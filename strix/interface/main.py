#!/usr/bin/env python3
"""
Strix Agent Interface
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

import litellm
from docker.errors import DockerException
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from strix.interface.cli import run_cli
from strix.interface.tui import run_tui
from strix.interface.utils import (
    assign_workspace_subdirs,
    build_llm_stats_text,
    build_stats_text,
    check_docker_connection,
    clone_repository,
    collect_local_sources,
    generate_run_name,
    image_exists,
    infer_target_type,
    process_pull_line,
    validate_llm_response,
)
from strix.runtime.docker_runtime import STRIX_IMAGE
from strix.telemetry.tracer import get_global_tracer


logging.getLogger().setLevel(logging.ERROR)


def validate_environment() -> None:  # noqa: PLR0912, PLR0915
    console = Console()
    missing_required_vars = []
    missing_optional_vars = []

    if not os.getenv("STRIX_LLM"):
        missing_required_vars.append("STRIX_LLM")

    has_base_url = any(
        [
            os.getenv("LLM_API_BASE"),
            os.getenv("OPENAI_API_BASE"),
            os.getenv("LITELLM_BASE_URL"),
            os.getenv("OLLAMA_API_BASE"),
        ]
    )

    if not os.getenv("LLM_API_KEY"):
        if not has_base_url:
            missing_required_vars.append("LLM_API_KEY")
        else:
            missing_optional_vars.append("LLM_API_KEY")

    if not has_base_url:
        missing_optional_vars.append("LLM_API_BASE")

    if not os.getenv("PERPLEXITY_API_KEY"):
        missing_optional_vars.append("PERPLEXITY_API_KEY")

    if missing_required_vars:
        error_text = Text()
        error_text.append("❌ ", style="bold red")
        error_text.append("MISSING REQUIRED ENVIRONMENT VARIABLES", style="bold red")
        error_text.append("\n\n", style="white")

        for var in missing_required_vars:
            error_text.append(f"• {var}", style="bold yellow")
            error_text.append(" is not set\n", style="white")

        if missing_optional_vars:
            error_text.append("\nOptional environment variables:\n", style="dim white")
            for var in missing_optional_vars:
                error_text.append(f"• {var}", style="dim yellow")
                error_text.append(" is not set\n", style="dim white")

        error_text.append("\nRequired environment variables:\n", style="white")
        for var in missing_required_vars:
            if var == "STRIX_LLM":
                error_text.append("• ", style="white")
                error_text.append("STRIX_LLM", style="bold cyan")
                error_text.append(
                    " - Model name to use with litellm (e.g., 'openai/gpt-5')\n",
                    style="white",
                )
            elif var == "LLM_API_KEY":
                error_text.append("• ", style="white")
                error_text.append("LLM_API_KEY", style="bold cyan")
                error_text.append(
                    " - API key for the LLM provider (required for cloud providers)\n",
                    style="white",
                )

        if missing_optional_vars:
            error_text.append("\nOptional environment variables:\n", style="white")
            for var in missing_optional_vars:
                if var == "LLM_API_KEY":
                    error_text.append("• ", style="white")
                    error_text.append("LLM_API_KEY", style="bold cyan")
                    error_text.append(" - API key for the LLM provider\n", style="white")
                elif var == "LLM_API_BASE":
                    error_text.append("• ", style="white")
                    error_text.append("LLM_API_BASE", style="bold cyan")
                    error_text.append(
                        " - Custom API base URL if using local models (e.g., Ollama, LMStudio)\n",
                        style="white",
                    )
                elif var == "PERPLEXITY_API_KEY":
                    error_text.append("• ", style="white")
                    error_text.append("PERPLEXITY_API_KEY", style="bold cyan")
                    error_text.append(
                        " - API key for Perplexity AI web search (enables real-time research)\n",
                        style="white",
                    )

        error_text.append("\nExample setup:\n", style="white")
        error_text.append("export STRIX_LLM='openai/gpt-5'\n", style="dim white")

        if "LLM_API_KEY" in missing_required_vars:
            error_text.append("export LLM_API_KEY='your-api-key-here'\n", style="dim white")

        if missing_optional_vars:
            for var in missing_optional_vars:
                if var == "LLM_API_KEY":
                    error_text.append(
                        "export LLM_API_KEY='your-api-key-here'  # optional with local models\n",
                        style="dim white",
                    )
                elif var == "LLM_API_BASE":
                    error_text.append(
                        "export LLM_API_BASE='http://localhost:11434'  "
                        "# needed for local models only\n",
                        style="dim white",
                    )
                elif var == "PERPLEXITY_API_KEY":
                    error_text.append(
                        "export PERPLEXITY_API_KEY='your-perplexity-key-here'\n", style="dim white"
                    )

        panel = Panel(
            error_text,
            title="[bold red]🛡️  STRIX CONFIGURATION ERROR",
            title_align="center",
            border_style="red",
            padding=(1, 2),
        )

        console.print("\n")
        console.print(panel)
        console.print()
        sys.exit(1)


def check_docker_installed() -> None:
    if shutil.which("docker") is None:
        console = Console()
        error_text = Text()
        error_text.append("❌ ", style="bold red")
        error_text.append("DOCKER NOT INSTALLED", style="bold red")
        error_text.append("\n\n", style="white")
        error_text.append("The 'docker' CLI was not found in your PATH.\n", style="white")
        error_text.append(
            "Please install Docker and ensure the 'docker' command is available.\n\n", style="white"
        )

        panel = Panel(
            error_text,
            title="[bold red]🛡️  STRIX STARTUP ERROR",
            title_align="center",
            border_style="red",
            padding=(1, 2),
        )
        console.print("\n", panel, "\n")
        sys.exit(1)


async def warm_up_llm() -> None:
    console = Console()

    try:
        model_name = os.getenv("STRIX_LLM", "openai/gpt-5")
        api_key = os.getenv("LLM_API_KEY")

        if api_key:
            litellm.api_key = api_key

        api_base = (
            os.getenv("LLM_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("LITELLM_BASE_URL")
            or os.getenv("OLLAMA_API_BASE")
        )
        if api_base:
            litellm.api_base = api_base

        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with just 'OK'."},
        ]

        llm_timeout = int(os.getenv("LLM_TIMEOUT", "600"))

        response = litellm.completion(
            model=model_name,
            messages=test_messages,
            timeout=llm_timeout,
        )

        validate_llm_response(response)

    except Exception as e:  # noqa: BLE001
        error_text = Text()
        error_text.append("❌ ", style="bold red")
        error_text.append("LLM CONNECTION FAILED", style="bold red")
        error_text.append("\n\n", style="white")
        error_text.append("Could not establish connection to the language model.\n", style="white")
        error_text.append("Please check your configuration and try again.\n", style="white")
        error_text.append(f"\nError: {e}", style="dim white")

        panel = Panel(
            error_text,
            title="[bold red]🛡️  STRIX STARTUP ERROR",
            title_align="center",
            border_style="red",
            padding=(1, 2),
        )

        console.print("\n")
        console.print(panel)
        console.print()
        sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strix Multi-Agent Cybersecurity Penetration Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Web application penetration test
  strix --target https://example.com

  # GitHub repository analysis
  strix --target https://github.com/user/repo
  strix --target git@github.com:user/repo.git

  # Local code analysis
  strix --target ./my-project

  # Domain penetration test
  strix --target example.com

  # IP address penetration test
  strix --target 192.168.1.42

  # Multiple targets (e.g., white-box testing with source and deployed app)
  strix --target https://github.com/user/repo --target https://example.com
  strix --target ./my-project --target https://staging.example.com --target https://prod.example.com

  # Custom instructions
  strix --target example.com --instruction "Focus on authentication vulnerabilities"

  # Using scope file
  strix --scope scope.yaml
  strix --scope scope.yaml --filter "tags:critical"
  strix --scope scope.yaml --validate
        """,
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        required=False,
        action="append",
        help="Target to test (URL, repository, local directory path, domain name, or IP address). "
        "Can be specified multiple times for multi-target scans.",
    )
    parser.add_argument(
        "--scope",
        type=str,
        help="Path to scope configuration file (YAML or JSON). "
        "Defines targets, networks, exclusions, and settings.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        action="append",
        help="Filter scope targets by criteria. Format: 'key:value'. "
        "Supported keys: tags, network, type. Can be specified multiple times.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate scope file and exit without running scan.",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        help="Custom instructions for the penetration test. This can be "
        "specific vulnerability types to focus on (e.g., 'Focus on IDOR and XSS'), "
        "testing approaches (e.g., 'Perform thorough authentication testing'), "
        "test credentials (e.g., 'Use the following credentials to access the app: "
        "admin:password123'), "
        "or areas of interest (e.g., 'Check login API endpoint for security issues')",
    )

    parser.add_argument(
        "--run-name",
        type=str,
        help="Custom name for this penetration test run",
    )

    parser.add_argument(
        "-n",
        "--non-interactive",
        action="store_true",
        help=(
            "Run in non-interactive mode (no TUI, exits on completion). "
            "Default is interactive mode with TUI."
        ),
    )

    args = parser.parse_args()

    # Require either --target or --scope
    if not args.target and not args.scope:
        parser.error("Either --target or --scope is required")

    args.targets_info = []
    args.scope_config = None

    # Handle scope file
    if args.scope:
        args.scope_config = _load_scope_file(args.scope, args.filter, args.validate, parser)
        if args.validate:
            return args  # Early return for validation-only mode

        # Get targets from scope
        scope_targets = args.scope_config.to_targets_info()
        args.targets_info.extend(scope_targets)

        # Add scope-derived instruction context
        scope_instruction = args.scope_config.get_instruction_context()
        if scope_instruction:
            if args.instruction:
                args.instruction = f"{scope_instruction}. {args.instruction}"
            else:
                args.instruction = scope_instruction

    # Handle individual --target arguments
    if args.target:
        for target in args.target:
            try:
                target_type, target_dict = infer_target_type(target)

                if target_type == "local_code":
                    display_target = target_dict.get("target_path", target)
                else:
                    display_target = target

                args.targets_info.append(
                    {"type": target_type, "details": target_dict, "original": display_target}
                )
            except ValueError:
                parser.error(f"Invalid target '{target}'")

    if not args.targets_info:
        parser.error("No valid targets found")

    assign_workspace_subdirs(args.targets_info)

    return args


def _load_scope_file(
    scope_path: str,
    filters: list[str] | None,
    validate_only: bool,
    parser: argparse.ArgumentParser,
) -> Any:
    """Load and validate scope file."""
    from strix.scope import ScopeConfig, validate_scope

    console = Console()

    try:
        scope_config = ScopeConfig.from_file(Path(scope_path))
    except FileNotFoundError:
        parser.error(f"Scope file not found: {scope_path}")
    except ValueError as e:
        parser.error(f"Invalid scope file: {e}")
    except Exception as e:
        parser.error(f"Error loading scope file: {e}")

    # Validate scope
    result = validate_scope(scope_config.model)

    if validate_only:
        # Print validation results and exit
        if result.valid:
            console.print(f"\n[bold green]Scope file is valid:[/] {scope_path}\n")
        else:
            console.print(f"\n[bold red]Scope file has errors:[/] {scope_path}\n")

        if result.errors:
            console.print("[bold red]Errors:[/]")
            for error in result.errors:
                console.print(f"  [red]- {error}[/]")

        if result.warnings:
            console.print("\n[bold yellow]Warnings:[/]")
            for warning in result.warnings:
                console.print(f"  [yellow]- {warning}[/]")

        # Print summary
        console.print(f"\n[bold cyan]Scope Summary:[/]")
        console.print(f"  Engagement: {scope_config.metadata.engagement_name}")
        console.print(f"  Type: {scope_config.metadata.engagement_type}")
        console.print(f"  Mode: {scope_config.settings.operational_mode}")
        console.print(f"  Networks: {len(scope_config.networks)}")
        console.print(f"  Targets: {len(scope_config.targets)}")
        console.print()

        if not result.valid:
            sys.exit(1)
        sys.exit(0)

    # Show warnings but continue
    if result.warnings:
        for warning in result.warnings:
            console.print(f"[yellow]Warning:[/] {warning}")

    if not result.valid:
        console.print("\n[bold red]Scope file has errors:[/]")
        for error in result.errors:
            console.print(f"  [red]- {error}[/]")
        parser.error("Invalid scope file")

    # Apply filters if specified
    if filters:
        _apply_scope_filters(scope_config, filters, parser)

    return scope_config


def _apply_scope_filters(
    scope_config: Any, filters: list[str], parser: argparse.ArgumentParser
) -> None:
    """Apply filters to scope targets."""
    tags_filter: list[str] = []
    network_filter: str | None = None
    type_filter: str | None = None

    for f in filters:
        if ":" not in f:
            parser.error(f"Invalid filter format: {f}. Use 'key:value'")

        key, value = f.split(":", 1)
        key = key.lower().strip()
        value = value.strip()

        if key == "tags":
            tags_filter.extend(v.strip() for v in value.split(","))
        elif key == "network":
            network_filter = value
        elif key == "type":
            type_filter = value
        else:
            parser.error(f"Unknown filter key: {key}. Supported: tags, network, type")

    # Filter targets in place
    filtered = scope_config.filter_targets(
        tags=tags_filter if tags_filter else None,
        network=network_filter,
        target_type=type_filter,
    )

    # Replace targets with filtered list
    scope_config.model.targets = filtered


def display_completion_message(args: argparse.Namespace, results_path: Path) -> None:
    console = Console()
    tracer = get_global_tracer()

    scan_completed = False
    if tracer and tracer.scan_results:
        scan_completed = tracer.scan_results.get("scan_completed", False)

    has_vulnerabilities = tracer and len(tracer.vulnerability_reports) > 0

    completion_text = Text()
    if scan_completed:
        completion_text.append("🦉 ", style="bold white")
        completion_text.append("AGENT FINISHED", style="bold green")
        completion_text.append(" • ", style="dim white")
        completion_text.append("Penetration test completed", style="white")
    else:
        completion_text.append("🦉 ", style="bold white")
        completion_text.append("SESSION ENDED", style="bold yellow")
        completion_text.append(" • ", style="dim white")
        completion_text.append("Penetration test interrupted by user", style="white")

    stats_text = build_stats_text(tracer)
    llm_stats_text = build_llm_stats_text(tracer)

    target_text = Text()
    if len(args.targets_info) == 1:
        target_text.append("🎯 Target: ", style="bold cyan")
        target_text.append(args.targets_info[0]["original"], style="bold white")
    else:
        target_text.append("🎯 Targets: ", style="bold cyan")
        target_text.append(f"{len(args.targets_info)} targets\n", style="bold white")
        for i, target_info in enumerate(args.targets_info):
            target_text.append("   • ", style="dim white")
            target_text.append(target_info["original"], style="white")
            if i < len(args.targets_info) - 1:
                target_text.append("\n")

    panel_parts = [completion_text, "\n\n", target_text]

    if stats_text.plain:
        panel_parts.extend(["\n", stats_text])

    if llm_stats_text.plain:
        panel_parts.extend(["\n", llm_stats_text])

    if scan_completed or has_vulnerabilities:
        results_text = Text()
        results_text.append("📊 Results Saved To: ", style="bold cyan")
        results_text.append(str(results_path), style="bold yellow")
        panel_parts.extend(["\n\n", results_text])

    panel_content = Text.assemble(*panel_parts)

    border_style = "green" if scan_completed else "yellow"

    panel = Panel(
        panel_content,
        title="[bold green]🛡️  STRIX CYBERSECURITY AGENT",
        title_align="center",
        border_style=border_style,
        padding=(1, 2),
    )

    console.print("\n")
    console.print(panel)
    console.print()


def pull_docker_image() -> None:
    console = Console()
    client = check_docker_connection()

    if image_exists(client, STRIX_IMAGE):
        return

    console.print()
    console.print(f"[bold cyan]🐳 Pulling Docker image:[/] {STRIX_IMAGE}")
    console.print("[dim yellow]This only happens on first run and may take a few minutes...[/]")
    console.print()

    with console.status("[bold cyan]Downloading image layers...", spinner="dots") as status:
        try:
            layers_info: dict[str, str] = {}
            last_update = ""

            for line in client.api.pull(STRIX_IMAGE, stream=True, decode=True):
                last_update = process_pull_line(line, layers_info, status, last_update)

        except DockerException as e:
            console.print()
            error_text = Text()
            error_text.append("❌ ", style="bold red")
            error_text.append("FAILED TO PULL IMAGE", style="bold red")
            error_text.append("\n\n", style="white")
            error_text.append(f"Could not download: {STRIX_IMAGE}\n", style="white")
            error_text.append(str(e), style="dim red")

            panel = Panel(
                error_text,
                title="[bold red]🛡️  DOCKER PULL ERROR",
                title_align="center",
                border_style="red",
                padding=(1, 2),
            )
            console.print(panel, "\n")
            sys.exit(1)

    success_text = Text()
    success_text.append("✅ ", style="bold green")
    success_text.append("Successfully pulled Docker image", style="green")
    console.print(success_text)
    console.print()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    args = parse_arguments()

    # Validation-only mode exits in parse_arguments via _load_scope_file
    # This is a safety check in case the flow changes
    if args.validate:
        return

    check_docker_installed()
    pull_docker_image()

    validate_environment()
    asyncio.run(warm_up_llm())

    if not args.run_name:
        args.run_name = generate_run_name()

    for target_info in args.targets_info:
        if target_info["type"] == "repository":
            repo_url = target_info["details"]["target_repo"]
            dest_name = target_info["details"].get("workspace_subdir")
            cloned_path = clone_repository(repo_url, args.run_name, dest_name)
            target_info["details"]["cloned_repo_path"] = cloned_path

    args.local_sources = collect_local_sources(args.targets_info)

    if args.non_interactive:
        asyncio.run(run_cli(args))
    else:
        asyncio.run(run_tui(args))

    results_path = Path("agent_runs") / args.run_name
    display_completion_message(args, results_path)

    if args.non_interactive:
        tracer = get_global_tracer()
        if tracer and tracer.vulnerability_reports:
            sys.exit(2)


if __name__ == "__main__":
    main()
