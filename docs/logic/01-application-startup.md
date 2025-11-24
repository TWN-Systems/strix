# Application Startup & Initialization

This diagram illustrates the complete startup sequence when a user initiates a Strix scan.

## Overview

The application startup involves:
1. CLI argument parsing and target type detection
2. Environment validation (Docker, LLM API keys)
3. Docker image availability check
4. LLM connection warmup
5. Workspace preparation and sandbox initialization

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant CLI as main.py
    participant ArgParser as Argument Parser
    participant EnvValidator as Environment Validator
    participant Docker
    participant LLM as LLM Service
    participant Workspace as Workspace Manager
    participant StrixAgent
    participant Tracer

    User->>CLI: strix <targets> [options]

    rect rgb(240, 248, 255)
        Note over CLI,ArgParser: Phase 1: Argument Parsing
        CLI->>ArgParser: parse_arguments()
        ArgParser->>ArgParser: Detect target types

        loop For each target
            ArgParser->>ArgParser: infer_target_type(target)
            alt GitHub URL
                ArgParser-->>ArgParser: type = "repository"
            else Local Path
                ArgParser-->>ArgParser: type = "local_code"
            else HTTP(S) URL
                ArgParser-->>ArgParser: type = "web_application"
            else IP Address
                ArgParser-->>ArgParser: type = "ip_address"
            end
        end

        ArgParser-->>CLI: ParsedArgs(targets, instructions, run_name)
    end

    rect rgb(255, 248, 240)
        Note over CLI,EnvValidator: Phase 2: Environment Validation
        CLI->>EnvValidator: validate_environment()
        EnvValidator->>EnvValidator: Check STRIX_LLM env var
        EnvValidator->>EnvValidator: Check LLM_API_KEY env var

        alt Missing required env vars
            EnvValidator-->>CLI: EnvironmentError
            CLI-->>User: Error: Missing configuration
        else Valid environment
            EnvValidator-->>CLI: Environment OK
        end
    end

    rect rgb(240, 255, 240)
        Note over CLI,Docker: Phase 3: Docker Verification
        CLI->>Docker: check_docker_installed()
        Docker->>Docker: docker --version

        alt Docker not installed
            Docker-->>CLI: DockerNotFoundError
            CLI-->>User: Error: Docker required
        else Docker available
            Docker-->>CLI: Docker OK
        end

        CLI->>Docker: pull_docker_image()
        Docker->>Docker: Check if strix-sandbox exists

        alt Image not present
            Docker->>Docker: docker pull ghcr.io/usestrix/strix-sandbox:0.1.10
            Docker-->>CLI: Image pulled
        else Image exists
            Docker-->>CLI: Image ready
        end
    end

    rect rgb(255, 240, 255)
        Note over CLI,LLM: Phase 4: LLM Connection Warmup
        CLI->>LLM: warm_up_llm()
        LLM->>LLM: Initialize LiteLLM client
        LLM->>LLM: Test completion call

        alt Connection failed
            LLM-->>CLI: LLMConnectionError
            CLI-->>User: Error: Cannot reach LLM
        else Connection OK
            LLM-->>CLI: LLM Ready
        end
    end

    rect rgb(255, 255, 240)
        Note over CLI,Workspace: Phase 5: Workspace Preparation
        CLI->>Workspace: assign_workspace_subdirs(targets)

        loop For each target
            alt Repository target
                Workspace->>Workspace: clone_repository(url, workspace_path)
                Workspace->>Docker: git clone <url>
            else Local code target
                Workspace->>Workspace: collect_local_sources(path)
                Workspace->>Workspace: Copy files to workspace
            else Web/IP target
                Workspace->>Workspace: Create target config
            end
        end

        Workspace-->>CLI: Workspace paths configured
    end

    rect rgb(248, 248, 255)
        Note over CLI,StrixAgent: Phase 6: Agent Initialization
        CLI->>Tracer: Initialize tracer(run_name)
        Tracer-->>CLI: Tracer ready

        CLI->>StrixAgent: StrixAgent(llm_config, tracer)
        StrixAgent->>StrixAgent: Load root_agent prompt module
        StrixAgent->>StrixAgent: Register available tools
        StrixAgent-->>CLI: Agent initialized

        CLI->>StrixAgent: execute_scan(targets, instructions)

        alt Interactive mode (--tui)
            CLI->>CLI: Launch TUI interface
        else Non-interactive mode
            CLI->>CLI: Run CLI mode
        end
    end

    StrixAgent-->>User: Scan started...
```

## Key Components

| Component | File Location | Responsibility |
|-----------|---------------|----------------|
| CLI Entry Point | `interface/main.py` | Orchestrates startup sequence |
| Argument Parser | `interface/main.py:parse_arguments()` | Parses CLI arguments and detects target types |
| Environment Validator | `interface/main.py:validate_environment()` | Validates required environment variables |
| Docker Manager | `interface/main.py:check_docker_installed()` | Manages Docker availability and images |
| LLM Warmup | `interface/main.py:warm_up_llm()` | Tests LLM connectivity |
| Workspace Manager | `utils/utils.py` | Prepares target workspaces |
| StrixAgent | `agents/StrixAgent/strix_agent.py` | Main security testing agent |
| Tracer | `telemetry/tracer.py` | Logging and reporting |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `STRIX_LLM` | Yes | LLM model identifier (e.g., `gpt-4`, `claude-3`) |
| `LLM_API_KEY` | Yes | API key for the LLM provider |
| `PERPLEXITY_API_KEY` | No | Enables web search capability |
| `STRIX_IMAGE` | No | Custom sandbox Docker image |

## Target Type Detection Logic

```
Target Input → Type Detection:
├── Starts with "git@" or "github.com" → repository
├── Starts with "http://" or "https://" → web_application
├── Exists as local path → local_code
├── Matches IP regex → ip_address
└── Default → web_application (if contains domain pattern)
```
