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
from strix.telemetry.run_plan import RunPlan
from strix.telemetry.tracer import Tracer, get_global_tracer, set_global_tracer


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

  # Continue a previous run
  strix --continue my-scan-830a
  strix --continue "webapp_analysis_abc123" --non-interactive
        """,
    )

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        action="append",
        help="Target to test (URL, repository, local directory path, domain name, or IP address). "
        "Can be specified multiple times for multi-target scans.",
    )
    parser.add_argument(
        "-c",
        "--continue",
        dest="continue_run",
        type=str,
        metavar="RUN_NAME",
        help="Continue a previous run by its name (e.g., 'my-scan-830a'). "
        "Loads the run plan and state from the previous run and resumes execution. "
        "Use with --non-interactive for headless continuation.",
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

    if not args.continue_run and not args.target:
        parser.error("Either --target or --continue is required")

    if args.continue_run and args.target:
        parser.error("Cannot use --continue with --target. Use --continue alone to resume a run.")

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

    args.targets_info = []
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

        assign_workspace_subdirs(args.targets_info)

    return args


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


def load_previous_run(run_name: str) -> tuple[dict, RunPlan | None] | None:
    """Load a previous run's state and plan for continuation."""
    console = Console()
    runs_dir = Path.cwd() / "strix_runs"
    run_dir = runs_dir / run_name

    if not run_dir.exists():
        available_runs = [d.name for d in runs_dir.iterdir() if d.is_dir()] if runs_dir.exists() else []

        error_text = Text()
        error_text.append("❌ ", style="bold red")
        error_text.append(f"Run '{run_name}' not found\n\n", style="bold red")

        if available_runs:
            error_text.append("Available runs:\n", style="white")
            for r in sorted(available_runs)[-10:]:
                error_text.append(f"  • {r}\n", style="cyan")
            if len(available_runs) > 10:
                error_text.append(f"  ... and {len(available_runs) - 10} more\n", style="dim")
        else:
            error_text.append("No previous runs found in strix_runs/\n", style="dim")

        panel = Panel(
            error_text,
            title="[bold red]RUN NOT FOUND",
            border_style="red",
            padding=(1, 2),
        )
        console.print(panel)
        return None

    run_state = Tracer.load_run_state(run_dir)
    plan = RunPlan.load(run_dir)

    if run_state is None:
        error_text = Text()
        error_text.append("❌ ", style="bold red")
        error_text.append(f"Could not load state for run '{run_name}'\n", style="bold red")
        error_text.append("The run directory exists but run_state.json is missing or corrupted.\n", style="white")

        panel = Panel(
            error_text,
            title="[bold red]INVALID RUN STATE",
            border_style="red",
            padding=(1, 2),
        )
        console.print(panel)
        return None

    return run_state, plan


def display_continuation_info(run_name: str, run_state: dict, plan: RunPlan | None) -> None:
    """Display information about the run being continued."""
    console = Console()

    info_text = Text()
    info_text.append("🔄 ", style="bold blue")
    info_text.append("CONTINUING PREVIOUS RUN\n\n", style="bold blue")
    info_text.append(f"Run Name: ", style="white")
    info_text.append(f"{run_name}\n", style="cyan")
    info_text.append(f"Started: ", style="white")
    info_text.append(f"{run_state.get('start_time', 'Unknown')}\n", style="dim")

    if plan:
        progress = plan.get_progress()
        info_text.append(f"\nPlan Progress: ", style="white")
        info_text.append(f"{progress['completed']}/{progress['total']} tasks ", style="green")
        info_text.append(f"({progress['percent_complete']}%)\n", style="dim")

        if progress['in_progress'] > 0:
            info_text.append(f"In Progress: ", style="white")
            info_text.append(f"{progress['in_progress']} task(s)\n", style="yellow")

        if progress['failed'] > 0:
            info_text.append(f"Failed: ", style="white")
            info_text.append(f"{progress['failed']} task(s)\n", style="red")

        current_task = plan.get_current_task()
        if current_task:
            info_text.append(f"\nResuming from: ", style="white")
            info_text.append(f"{current_task.title}\n", style="bold cyan")

    panel = Panel(
        info_text,
        title="[bold blue]📋 RUN CONTINUATION",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)
    console.print()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    args = parse_arguments()

    check_docker_installed()
    pull_docker_image()

    validate_environment()
    asyncio.run(warm_up_llm())

    if args.continue_run:
        result = load_previous_run(args.continue_run)
        if result is None:
            sys.exit(1)

        run_state, plan = result
        args.run_name = args.continue_run
        args.is_continuation = True

        display_continuation_info(args.continue_run, run_state, plan)

        tracer = Tracer(run_name=args.run_name)
        tracer.scan_config = run_state.get("scan_config")
        tracer.run_metadata = run_state.get("run_metadata", {})
        tracer.mark_as_continuation({
            "previous_state": run_state,
            "resumed_at": None,
        })

        if plan:
            tracer.set_plan(plan)
            if plan.is_paused:
                plan.resume()

        set_global_tracer(tracer)

        args.targets_info = run_state.get("run_metadata", {}).get("targets", [])
        if isinstance(args.targets_info, list) and args.targets_info:
            if isinstance(args.targets_info[0], str):
                args.targets_info = [{"type": "unknown", "details": {}, "original": t} for t in args.targets_info]

        args.local_sources = []

    else:
        args.is_continuation = False

        if not args.run_name:
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
