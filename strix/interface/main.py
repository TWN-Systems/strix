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
from strix.scope import (
    ScopeParseError,
    TargetType as ScopeTargetType,
    load_scope,
    validate_scope,
)
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

  # Custom instructions (inline)
  strix --target example.com --instruction "Focus on authentication vulnerabilities"

  # Custom instructions (from file)
  strix --target example.com --instruction ./instructions.txt
  strix --target https://app.com --instruction /path/to/detailed_instructions.md

  # Using scope files
  strix --scope ./scope.yaml
  strix --scope ./scope.yaml --filter "tags:critical"
  strix --scope ./scope.yaml --validate
        """,
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        action="append",
        help="Target to test (URL, repository, local directory path, domain name, or IP address). "
        "Can be specified multiple times for multi-target scans. "
        "Required unless --scope is provided.",
    )

    parser.add_argument(
        "-s",
        "--scope",
        type=str,
        help="Path to a scope configuration file (YAML, JSON, or CSV). "
        "Defines targets, networks, credentials, and exclusions for the engagement.",
    )

    parser.add_argument(
        "-f",
        "--filter",
        type=str,
        action="append",
        help="Filter targets from scope file. Format: 'field:value'. "
        "Examples: 'tags:critical', 'type:web_application', 'network:DMZ'. "
        "Can be specified multiple times for multiple filters.",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the scope file and exit without running tests. "
        "Useful for checking scope configuration before an engagement.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output with additional details.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed logging.",
    )

    parser.add_argument(
        "--instruction",
        type=str,
        help="Custom instructions for the penetration test. This can be "
        "specific vulnerability types to focus on (e.g., 'Focus on IDOR and XSS'), "
        "testing approaches (e.g., 'Perform thorough authentication testing'), "
        "test credentials (e.g., 'Use the following credentials to access the app: "
        "admin:password123'), "
        "or areas of interest (e.g., 'Check login API endpoint for security issues'). "
        "You can also provide a path to a file containing detailed instructions "
        "(e.g., '--instruction ./instructions.txt').",
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

    if args.instruction:
        instruction_path = Path(args.instruction)
        if instruction_path.exists() and instruction_path.is_file():
            try:
                with instruction_path.open(encoding="utf-8") as f:
                    args.instruction = f.read().strip()
                    if not args.instruction:
                        parser.error(f"Instruction file '{instruction_path}' is empty")
            except Exception as e:  # noqa: BLE001
                parser.error(f"Failed to read instruction file '{instruction_path}': {e}")

    # Initialize scope context
    args.scope_config = None
    args.scope_context = None

    # Process scope file if provided
    if args.scope:
        try:
            args.scope_config = load_scope(args.scope)
            args.scope_context = {
                "metadata": args.scope_config.metadata.model_dump(),
                "settings": args.scope_config.settings.model_dump(),
                "networks": [n.model_dump() for n in args.scope_config.networks],
                "exclusions": args.scope_config.exclusions.model_dump(),
                "domains": args.scope_config.domains.model_dump(),
                "test_focus": args.scope_config.test_focus.model_dump(),
            }
        except ScopeParseError as e:
            parser.error(f"Failed to parse scope file: {e}")

    args.targets_info = []

    # Process scope targets if scope file provided
    if args.scope_config:
        targets = args.scope_config.targets

        # Apply filters if specified
        if args.filter:
            targets = _apply_scope_filters(targets, args.filter)

        for target in targets:
            target_info = _scope_target_to_target_info(target)
            args.targets_info.append(target_info)

    # Process command-line targets
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


def _apply_scope_filters(
    targets: list, filters: list[str]
) -> list:
    """Apply filters to scope targets."""
    result = targets

    for filter_str in filters:
        if ":" not in filter_str:
            continue

        field, value = filter_str.split(":", 1)
        field = field.strip().lower()
        value = value.strip()

        if field == "tags":
            result = [t for t in result if value in t.tags]
        elif field == "type":
            try:
                target_type = ScopeTargetType(value)
                result = [t for t in result if t.type == target_type]
            except ValueError:
                pass
        elif field == "network":
            result = [t for t in result if t.network == value]
        elif field == "critical":
            is_critical = value.lower() in ("true", "1", "yes")
            result = [t for t in result if t.critical == is_critical]
        elif field == "name":
            result = [t for t in result if value.lower() in t.name.lower()]

    return result


def _scope_target_to_target_info(target) -> dict:
    """Convert a scope TargetDefinition to target_info dict."""
    # Determine target type string
    type_mapping = {
        ScopeTargetType.INFRASTRUCTURE: "infrastructure",
        ScopeTargetType.WEB_APPLICATION: "web_application",
        ScopeTargetType.API: "api",
        ScopeTargetType.REPOSITORY: "repository",
        ScopeTargetType.LOCAL_CODE: "local_code",
    }
    target_type = type_mapping.get(target.type, "infrastructure")

    # Build details dict based on target type
    details = {}
    original = target.name

    if target.host:
        details["target_ip"] = target.host
        original = target.host
    elif target.url:
        details["target_url"] = target.url
        original = target.url
    elif target.repo:
        details["target_repo"] = target.repo
        original = target.repo
    elif target.path:
        details["target_path"] = str(Path(target.path).resolve())
        original = target.path

    # Add ports for infrastructure targets
    if target.ports:
        details["ports"] = target.ports

    # Add credentials info (env var references, not actual values)
    if target.credentials:
        details["credentials"] = [
            {
                "username": c.username,
                "password_env": c.password_env,
                "token_env": c.token_env,
                "access_level": c.access_level.value,
            }
            for c in target.credentials
        ]

    # Add token env
    if target.token_env:
        details["token_env"] = target.token_env

    # Add technologies
    if target.technologies:
        details["technologies"] = target.technologies

    # Add focus areas
    if target.focus_areas:
        details["focus_areas"] = target.focus_areas

    # Add modules
    if target.modules:
        details["modules"] = target.modules

    # Add tags
    if target.tags:
        details["tags"] = target.tags

    # Add services
    if target.services:
        details["services"] = [
            {
                "port": s.port,
                "service": s.service,
                "version": s.version,
            }
            for s in target.services
        ]

    return {
        "type": target_type,
        "details": details,
        "original": original,
        "name": target.name,
        "scope_target": target.model_dump(),
    }


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


def _run_scope_validation(args: argparse.Namespace) -> None:
    """Run scope validation and display results."""
    console = Console()

    if not args.scope_config:
        console.print("[bold red]Error:[/] No scope file provided for validation")
        sys.exit(1)

    console.print()
    console.print("[bold cyan]Validating scope configuration...[/]")
    console.print()

    result = validate_scope(args.scope_config)

    # Display results
    if result.is_valid:
        status_text = Text()
        status_text.append("PASSED", style="bold green")
    else:
        status_text = Text()
        status_text.append("FAILED", style="bold red")

    summary_text = Text()
    summary_text.append("Validation Status: ", style="bold")
    summary_text.append(status_text)
    summary_text.append(f"\n\nErrors: {result.errors_count}", style="red" if result.errors_count else "dim")
    summary_text.append(f"\nWarnings: {result.warnings_count}", style="yellow" if result.warnings_count else "dim")

    # Show issues
    if result.issues:
        summary_text.append("\n\n")
        summary_text.append("Issues Found:", style="bold")

        for issue in result.issues:
            if issue.severity.value == "error":
                style = "red"
                prefix = "ERROR"
            elif issue.severity.value == "warning":
                style = "yellow"
                prefix = "WARN"
            else:
                style = "dim"
                prefix = "INFO"

            summary_text.append(f"\n  [{prefix}] ", style=style)
            if issue.location:
                summary_text.append(f"{issue.location}: ", style="dim")
            summary_text.append(issue.message)
            if issue.suggestion:
                summary_text.append(f"\n         Suggestion: {issue.suggestion}", style="dim")

    # Show scope summary
    config = args.scope_config
    scope_info = Text()
    scope_info.append("\n\nScope Summary:", style="bold")
    scope_info.append(f"\n  Engagement: {config.metadata.engagement_name}")
    scope_info.append(f"\n  Type: {config.metadata.engagement_type.value}")
    scope_info.append(f"\n  Networks: {len(config.networks)}")
    scope_info.append(f"\n  Targets: {len(config.targets)}")
    scope_info.append(f"\n  Mode: {config.settings.operational_mode.value}")

    panel = Panel(
        Text.assemble(summary_text, scope_info),
        title="[bold cyan]Scope Validation Results",
        border_style="green" if result.is_valid else "red",
        padding=(1, 2),
    )

    console.print(panel)
    console.print()

    sys.exit(0 if result.is_valid else 1)


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    args = parse_arguments()

    # Set up logging based on flags
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Handle validation-only mode
    if args.validate:
        _run_scope_validation(args)
        return

    check_docker_installed()
    pull_docker_image()

    validate_environment()
    asyncio.run(warm_up_llm())

    if not args.run_name:
        if args.scope_config:
            # Use engagement name from scope for run name
            args.run_name = generate_run_name(args.targets_info)
        else:
            args.run_name = generate_run_name(args.targets_info)

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

    results_path = Path("strix_runs") / args.run_name
    display_completion_message(args, results_path)

    if args.non_interactive:
        tracer = get_global_tracer()
        if tracer and tracer.vulnerability_reports:
            sys.exit(2)


if __name__ == "__main__":
    main()
