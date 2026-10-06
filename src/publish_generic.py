#!/usr/bin/env python3

import argparse
import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="ArgumentsConfig")


@dataclass
class ArgumentsConfig:
    """Configuration for the package to be published."""

    package_name: str
    package_type: str
    version: str
    file: Path

    def __post_init__(self) -> None:
        self.package_name = self.package_name.strip()
        self.package_type = self.package_type.strip()
        self.version = self.version.strip()

        if not self.package_name:
            raise ValueError("package name cannot be empty")

        if not self.package_type:
            raise ValueError("package type cannot be empty")

        if not self.version:
            raise ValueError("version cannot be empty")

        if not self.file.exists():
            raise FileNotFoundError(f"file not found: {self.file}")

        if not self.file.is_file():
            raise ValueError(f"not a file: {self.file}")

    @classmethod
    def create(cls, **kwargs: object) -> T:
        """Create and validate configuration."""
        return cls(**kwargs)  # type: ignore[arg-type]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Publish a generic package to Forgejo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-n",
        "--name",
        help="Name of the package",
        type=str,
        required=True,
    )

    parser.add_argument(
        "-v",
        "--version",
        help="Package version",
        type=str,
        required=True,
    )

    parser.add_argument(
        "-t",
        "--type",
        help="Package type",
        type=str,
        default="tar.gz",
    )

    parser.add_argument(
        "-f",
        "--filename",
        help="Path to the package file",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def get_required_env(name: str) -> str:
    """Get a required environment variable."""

    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"required environment variable is not set: {name}")

    return value


def check_env_variables(keys: list[str]) -> list[str]:
    """Return missing environment variables."""

    return [key for key in keys if not os.environ.get(key)]


def format_size(size: int) -> str:
    """Format a byte count as a human-readable size."""

    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{value:.1f} TiB"


def push_registry(config: ArgumentsConfig) -> None:
    """Upload a generic package to Forgejo."""

    required_env = [
        "FORGEJO_URL",
        "FORGEJO_USERNAME",
        "FORGEJO_TOKEN",
        "FORGEJO_OWNER",
    ]

    missing_env = check_env_variables(required_env)

    if missing_env:
        raise RuntimeError(
            "required environment variables are not set: "
            + ", ".join(missing_env)
        )

    forgejo_url = get_required_env("FORGEJO_URL").rstrip("/")
    username = get_required_env("FORGEJO_USERNAME")
    token = get_required_env("FORGEJO_TOKEN")
    owner = get_required_env("FORGEJO_OWNER")

    url = (
        f"{forgejo_url}/api/packages/"
        f"{quote(owner, safe='')}/generic/"
        f"{quote(config.package_name, safe='')}/"
        f"{quote(config.version, safe='')}/"
        f"{quote(config.file.name, safe='')}"
    )

    credentials = base64.b64encode(
        f"{username}:{token}".encode()
    ).decode("ascii")

    request = Request(
        url=url,
        data=config.file.read_bytes(),
        method="PUT",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/octet-stream",
        },
    )

    logger.debug("Forgejo URL: %s", url)
    logger.debug("Forgejo owner: %s", owner)
    logger.debug("Username: %s", username)

    logger.info("Uploading package to Forgejo")

    try:
        with urlopen(request) as response:
            status = response.status

        if 200 <= status < 300:
            logger.info(
                "Package uploaded successfully: HTTP %d",
                status,
            )
            return

        raise RuntimeError(
            f"Forgejo returned unexpected HTTP status: {status}"
        )

    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()

        message = f"Forgejo upload failed: HTTP {exc.code}"

        if body:
            message += f": {body}"

        raise RuntimeError(message) from exc

    except URLError as exc:
        raise RuntimeError(
            f"could not connect to Forgejo: {exc.reason}"
        ) from exc


def main() -> int:
    """Application entry point."""

    args = parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        config = ArgumentsConfig.create(
            package_name=args.name,
            package_type=args.type,
            version=args.version,
            file=args.filename,
        )

        file_size = config.file.stat().st_size

        logger.info(
            "Publishing name=%s version=%s",
            config.package_name,
            config.version,
        )

        logger.info(
            "File: %s (%s)",
            config.file,
            format_size(file_size),
        )

        logger.debug("Package type: %s", config.package_type)

        push_registry(config)

        logger.info(
            "Published %s %s",
            config.package_name,
            config.version,
        )

        return 0

    except KeyboardInterrupt:
        logger.warning("Upload cancelled")
        return 130

    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())