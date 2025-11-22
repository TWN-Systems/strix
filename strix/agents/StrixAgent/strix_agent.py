from typing import Any

from strix.agents.base_agent import BaseAgent
from strix.llm.config import LLMConfig


class StrixAgent(BaseAgent):
    max_iterations = 300

    def __init__(self, config: dict[str, Any]):
        default_modules = []
        agent_role = None

        state = config.get("state")
        if state is None or (hasattr(state, "parent_id") and state.parent_id is None):
            default_modules = ["root_agent"]
            agent_role = "root"

        self.default_llm_config = LLMConfig(prompt_modules=default_modules, agent_role=agent_role)

        super().__init__(config)

        # Set role on state for runtime enforcement (state may be created by BaseAgent)
        if agent_role and hasattr(self.state, "agent_role"):
            self.state.agent_role = agent_role

    async def execute_scan(self, scan_config: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0912
        user_instructions = scan_config.get("user_instructions", "")
        targets = scan_config.get("targets", [])
        scope_context = scan_config.get("scope_context")
        exclusion_rules = scan_config.get("exclusion_rules")

        repositories = []
        local_code = []
        urls = []
        ip_addresses = []

        for target in targets:
            target_type = target["type"]
            details = target["details"]
            workspace_subdir = details.get("workspace_subdir")
            workspace_path = f"/workspace/{workspace_subdir}" if workspace_subdir else "/workspace"

            if target_type == "repository":
                repo_url = details["target_repo"]
                cloned_path = details.get("cloned_repo_path")
                repositories.append(
                    {
                        "url": repo_url,
                        "workspace_path": workspace_path if cloned_path else None,
                    }
                )

            elif target_type == "local_code":
                original_path = details.get("target_path", "unknown")
                local_code.append(
                    {
                        "path": original_path,
                        "workspace_path": workspace_path,
                    }
                )

            elif target_type == "web_application":
                urls.append(details["target_url"])
            elif target_type == "ip_address":
                ip_addresses.append(details["target_ip"])

        task_parts = []

        if repositories:
            task_parts.append("\n\nRepositories:")
            for repo in repositories:
                if repo["workspace_path"]:
                    task_parts.append(f"- {repo['url']} (available at: {repo['workspace_path']})")
                else:
                    task_parts.append(f"- {repo['url']}")

        if local_code:
            task_parts.append("\n\nLocal Codebases:")
            task_parts.extend(
                f"- {code['path']} (available at: {code['workspace_path']})" for code in local_code
            )

        if urls:
            task_parts.append("\n\nURLs:")
            task_parts.extend(f"- {url}" for url in urls)

        if ip_addresses:
            task_parts.append("\n\nIP Addresses:")
            task_parts.extend(f"- {ip}" for ip in ip_addresses)

        task_description = " ".join(task_parts)

        if user_instructions:
            task_description += f"\n\nSpecial instructions: {user_instructions}"

        # Inject scope context for agent awareness
        if scope_context:
            task_description += "\n\n<scope_context>"
            task_description += f"\nEngagement: {scope_context.get('engagement', {}).get('name', 'Unknown')}"
            task_description += f"\nType: {scope_context.get('engagement', {}).get('type', 'Unknown')}"
            task_description += f"\nMode: {scope_context.get('settings', {}).get('mode', 'poc-only')}"
            task_description += f"\nTargets in scope: {scope_context.get('target_count', 0)}"

            networks = scope_context.get("networks", [])
            if networks:
                task_description += "\nNetworks:"
                for net in networks:
                    task_description += f"\n  - {net.get('name')}: {net.get('cidr', 'N/A')} ({net.get('type')})"

            in_scope_domains = scope_context.get("in_scope_domains", [])
            if in_scope_domains:
                task_description += f"\nIn-scope domains: {', '.join(in_scope_domains)}"

            task_description += "\n</scope_context>"

        # Inject exclusion rules for agents to respect
        if exclusion_rules:
            task_description += "\n\n<exclusion_rules>"
            if exclusion_rules.get("excluded_hosts"):
                task_description += f"\nExcluded hosts: {', '.join(exclusion_rules['excluded_hosts'])}"
            if exclusion_rules.get("excluded_cidrs"):
                task_description += f"\nExcluded CIDRs: {', '.join(exclusion_rules['excluded_cidrs'])}"
            if exclusion_rules.get("excluded_urls"):
                task_description += f"\nExcluded URLs: {', '.join(exclusion_rules['excluded_urls'])}"
            if exclusion_rules.get("excluded_paths"):
                task_description += f"\nExcluded paths: {', '.join(exclusion_rules['excluded_paths'])}"
            if exclusion_rules.get("excluded_ports"):
                task_description += f"\nExcluded ports: {', '.join(map(str, exclusion_rules['excluded_ports']))}"
            if exclusion_rules.get("out_of_scope_domains"):
                task_description += f"\nOut-of-scope domains: {', '.join(exclusion_rules['out_of_scope_domains'])}"
            task_description += "\n</exclusion_rules>"

        return await self.agent_loop(task=task_description)
