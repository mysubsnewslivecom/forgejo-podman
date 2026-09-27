#!/usr/bin/env python3
"""
Forgejo Runner Configuration Templating Script

This script generates and templates `runner-config.yml` for Forgejo Actions runner.
It supports reading from CLI flags, environment variables, or a `.env` file,
auto-generates UUIDs, preserves existing runner UUIDs across runs, and validates
the rendered YAML syntax.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import uuid

# Optional PyYAML check for syntax validation
try:
    import yaml  # type: ignore

    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "runner-config.template.yml"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "forgejo-runner" / "runner-config.yml"


def parse_env_file(filepath: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file without external dependencies."""
    env_vars: dict[str, str] = {}
    if not filepath.is_file():
        return env_vars
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                env_vars[key] = val
    return env_vars


def extract_existing_uuid(config_path: Path) -> str | None:
    """Extract existing active runner UUID from an already generated config file."""
    if not config_path.is_file():
        return None
    try:
        if HAVE_YAML:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    server_block = data.get("server") or {}
                    connections = server_block.get("connections") or {}
                    if isinstance(connections, dict):
                        for conn in connections.values():
                            if isinstance(conn, dict) and "uuid" in conn:
                                return str(conn["uuid"])
        # Fallback regex ignoring commented lines
        content = config_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            match = re.match(r"^uuid:\s*([a-f0-9\-]+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    except Exception:
        pass
    return None


def format_yaml_labels(labels: list[str]) -> str:
    """Format a list of label strings as indented YAML list items."""
    formatted = []
    for label in labels:
        label = label.strip()
        if label:
            formatted.append(f'    - "{label}"')
    if not formatted:
        formatted.append('    - "host:host"')
    return "\n".join(formatted)


def render_template(template_str: str, variables: dict[str, str]) -> str:
    """Replace ${VAR_NAME} placeholders with values from variables dictionary."""
    def replace_match(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return variables[var_name]
        # Leave unknown placeholders unchanged
        return match.group(0)

    return re.sub(r"\$\{([A-Z0-9_]+)\}", replace_match, template_str)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Template and generate Forgejo runner configuration (runner-config.yml)."
    )
    parser.add_argument(
        "-t",
        "--token",
        dest="token",
        help="Runner registration token from Forgejo (or set FORGEJO_RUNNER_TOKEN)",
    )
    parser.add_argument(
        "-u",
        "--url",
        dest="url",
        default="http://forgejo:3000/",
        help="Forgejo server instance URL (default: http://forgejo:3000/ or FORGEJO_URL)",
    )
    parser.add_argument(
        "--uuid",
        dest="uuid",
        help="Runner UUID. If not specified, reuses existing UUID in output file or generates a new UUIDv4",
    )
    parser.add_argument(
        "--new-uuid",
        action="store_true",
        dest="new_uuid",
        help="Force generation of a brand-new UUID even if one already exists in the config",
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default="forgejo",
        help="Connection name identifier under server.connections (default: forgejo)",
    )
    parser.add_argument(
        "-l",
        "--labels",
        dest="labels",
        default="host:host",
        help="Comma-separated labels for runner (e.g. 'host:host,docker:docker://node:22-bookworm')",
    )
    parser.add_argument(
        "-c",
        "--capacity",
        dest="capacity",
        type=int,
        default=1,
        help="Task capacity / concurrent job count (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        default="3h",
        help="Maximum timeout for jobs (default: 3h)",
    )
    parser.add_argument(
        "--shutdown-timeout",
        dest="shutdown_timeout",
        default="3h",
        help="Runner shutdown timeout when canceling running jobs (default: 3h)",
    )
    parser.add_argument(
        "--docker-host",
        dest="docker_host",
        default="-",
        help="Docker host override for job containers ('-' disables socket injection) (default: -)",
    )
    parser.add_argument(
        "--container-network",
        dest="container_network",
        default="",
        help="Custom network for job containers (default: '')",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        dest="insecure",
        help="Skip verifying TLS certificate of the Forgejo instance (default: false)",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="info",
        choices=["trace", "debug", "info", "warn", "error", "fatal"],
        help="Runner log level (default: info)",
    )
    parser.add_argument(
        "--job-log-level",
        dest="job_log_level",
        default="info",
        choices=["trace", "debug", "info", "warn", "error", "fatal"],
        help="Job log level sent to Forgejo UI (default: info)",
    )
    parser.add_argument(
        "--template",
        dest="template_file",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Path to template file (default: {DEFAULT_TEMPLATE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--env-file",
        dest="env_file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file to load variables from (default: .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print rendered config to stdout without writing to file",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Load environment variables from .env if present
    env_vars = parse_env_file(args.env_file)

    # 2. Resolve token
    token = (
        args.token
        or os.environ.get("FORGEJO_RUNNER_TOKEN")
        or env_vars.get("FORGEJO_RUNNER_TOKEN")
    )
    if not token:
        print(
            "ERROR: Runner registration token is required.\n"
            "Provide it via '--token <TOKEN>', set FORGEJO_RUNNER_TOKEN in your environment, or in .env",
            file=sys.stderr,
        )
        return 1

    # 3. Resolve URL
    url = (
        args.url
        if args.url != "http://forgejo:3000/"
        else (os.environ.get("FORGEJO_URL") or env_vars.get("FORGEJO_URL") or args.url)
    )

    # 4. Resolve UUID
    resolved_uuid = None
    if not args.new_uuid:
        if args.uuid:
            resolved_uuid = args.uuid
        elif "FORGEJO_RUNNER_UUID" in os.environ:
            resolved_uuid = os.environ["FORGEJO_RUNNER_UUID"]
        elif "FORGEJO_RUNNER_UUID" in env_vars:
            resolved_uuid = env_vars["FORGEJO_RUNNER_UUID"]
        else:
            resolved_uuid = extract_existing_uuid(args.output_file)

    if not resolved_uuid:
        resolved_uuid = str(uuid.uuid4())
        print(f"Generated new runner UUID: {resolved_uuid}")
    else:
        print(f"Using runner UUID: {resolved_uuid}")

    # 5. Resolve labels
    label_list: list[str] = []
    raw_labels = args.labels or env_vars.get("RUNNER_LABELS") or "host:host"
    for item in raw_labels.split(","):
        item = item.strip()
        if item:
            label_list.append(item)

    # 6. Read template
    if not args.template_file.is_file():
        print(
            f"ERROR: Template file '{args.template_file}' does not exist.",
            file=sys.stderr,
        )
        return 1

    template_content = args.template_file.read_text(encoding="utf-8")

    # 7. Prepare replacement map
    replacements: dict[str, str] = {
        "FORGEJO_URL": url,
        "RUNNER_TOKEN": token,
        "RUNNER_UUID": resolved_uuid,
        "CONNECTION_NAME": args.name or "forgejo",
        "CAPACITY": str(args.capacity),
        "TIMEOUT": args.timeout,
        "SHUTDOWN_TIMEOUT": args.shutdown_timeout,
        "INSECURE": "true" if args.insecure else "false",
        "DOCKER_HOST": args.docker_host,
        "CONTAINER_NETWORK": args.container_network,
        "LOG_LEVEL": args.log_level,
        "JOB_LOG_LEVEL": args.job_log_level,
        "LABELS": format_yaml_labels(label_list),
    }

    rendered = render_template(template_content, replacements)

    # 8. Syntax validation
    if HAVE_YAML:
        try:
            yaml.safe_load(rendered)
        except Exception as e:
            print(f"ERROR: Rendered template is not valid YAML: {e}", file=sys.stderr)
            return 1

    # 9. Output
    if args.dry_run:
        print("\n--- Rendered runner-config.yml (dry-run) ---")
        print(rendered)
        return 0

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(rendered, encoding="utf-8")
    print(f"Successfully generated runner config at: {args.output_file.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
