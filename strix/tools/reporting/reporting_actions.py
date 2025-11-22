import csv
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from strix.tools.registry import register_tool


logger = logging.getLogger(__name__)


def _save_vulnerability_to_disk(
    run_dir: Path,
    report_id: str,
    title: str,
    content: str,
    severity: str,
    timestamp: str,
) -> bool:
    """Immediately save vulnerability report to disk (crash-proof)."""
    try:
        # Ensure directories exist
        vuln_dir = run_dir / "vulnerabilities"
        vuln_dir.mkdir(parents=True, exist_ok=True)

        # Write individual vulnerability markdown file
        vuln_file = vuln_dir / f"{report_id}.md"
        with vuln_file.open("w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"**ID:** {report_id}\n")
            f.write(f"**Severity:** {severity.upper()}\n")
            f.write(f"**Found:** {timestamp}\n\n")
            f.write("## Description\n\n")
            f.write(f"{content}\n")

        # Append to CSV index (create header if new file)
        csv_file = run_dir / "vulnerabilities.csv"
        write_header = not csv_file.exists()

        with csv_file.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "title", "severity", "timestamp", "file"]
            )
            if write_header:
                writer.writeheader()
            writer.writerow({
                "id": report_id,
                "title": title,
                "severity": severity.upper(),
                "timestamp": timestamp,
                "file": f"vulnerabilities/{report_id}.md",
            })

        logger.info(f"Vulnerability {report_id} saved to disk: {vuln_file}")
        return True

    except (OSError, IOError) as e:
        logger.error(f"Failed to save vulnerability {report_id} to disk: {e}")
        return False


@register_tool(sandbox_execution=False)
def create_vulnerability_report(
    title: str,
    content: str,
    severity: str,
) -> dict[str, Any]:
    validation_error = None
    if not title or not title.strip():
        validation_error = "Title cannot be empty"
    elif not content or not content.strip():
        validation_error = "Content cannot be empty"
    elif not severity or not severity.strip():
        validation_error = "Severity cannot be empty"
    else:
        valid_severities = ["critical", "high", "medium", "low", "info"]
        if severity.lower() not in valid_severities:
            validation_error = (
                f"Invalid severity '{severity}'. Must be one of: {', '.join(valid_severities)}"
            )

    if validation_error:
        return {"success": False, "message": validation_error}

    try:
        from strix.telemetry.tracer import get_global_tracer

        tracer = get_global_tracer()
        if tracer:
            report_id = tracer.add_vulnerability_report(
                title=title,
                content=content,
                severity=severity,
            )

            # IMMEDIATELY save to disk (crash-proof)
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            run_dir = tracer.get_run_dir()
            disk_saved = _save_vulnerability_to_disk(
                run_dir=run_dir,
                report_id=report_id,
                title=title.strip(),
                content=content.strip(),
                severity=severity.lower().strip(),
                timestamp=timestamp,
            )

            return {
                "success": True,
                "message": f"Vulnerability report '{title}' created successfully",
                "report_id": report_id,
                "severity": severity.lower(),
                "persisted_to_disk": disk_saved,
                "file_path": f"vulnerabilities/{report_id}.md" if disk_saved else None,
            }

        logging.warning("Global tracer not available - vulnerability report not stored")

        return {  # noqa: TRY300
            "success": True,
            "message": f"Vulnerability report '{title}' created successfully (not persisted)",
            "warning": "Report could not be persisted - tracer unavailable",
        }

    except ImportError:
        return {
            "success": True,
            "message": f"Vulnerability report '{title}' created successfully (not persisted)",
            "warning": "Report could not be persisted - tracer module unavailable",
        }
    except (ValueError, TypeError) as e:
        return {"success": False, "message": f"Failed to create vulnerability report: {e!s}"}
