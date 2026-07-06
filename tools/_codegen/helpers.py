"""
Parse the curated ``+helper`` commands that ``gws`` exposes but that are not part of the
Discovery surface (e.g. ``drive +upload``, ``gmail +send``, all of ``workflow``).

We drive this straight off ``gws <service> --help`` and ``gws <service> +helper --help`` so
the generated wrappers always match exactly what the shipped binary supports.
"""

import re
import subprocess
from dataclasses import dataclass
from dataclasses import field

from . import naming

# Options handled by the runner / not useful as kwargs.
_SKIP_OPTIONS = {"help", "format", "sanitize", "dry-run", "output"}

_OPTION_RE = re.compile(
    r"^\s+(?:-\w,\s+)?--(?P<long>[a-zA-Z0-9][a-zA-Z0-9-]*)"
    r"(?P<meta>\s+<[^>]+>)?\s{2,}(?P<desc>.*)$"
)
_ARG_RE = re.compile(r"^\s+(?P<name>\[?<[^>]+>\]?)\s{2,}(?P<desc>.*)$")


@dataclass
class HelperOption:
    long: str  # e.g. "json-values"
    py: str  # e.g. "json_values"
    takes_value: bool
    required: bool
    desc: str
    multiple: bool = False


@dataclass
class HelperArg:
    name: str  # discovery-style token, e.g. "file"
    py: str
    required: bool
    desc: str = ""


@dataclass
class Helper:
    cli: str  # service alias, e.g. "drive"
    command: str  # e.g. "+upload"
    py: str  # e.g. "upload"
    description: str
    args: list = field(default_factory=list)  # list[HelperArg]
    options: list = field(default_factory=list)  # list[HelperOption]


def _run_help(binary, cli, *extra):
    proc = subprocess.run(
        [binary, cli, *extra, "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return proc.stdout or proc.stderr or ""


def list_helpers(binary, cli):
    """Return the ``+helper`` command names for a service (e.g. ``["+upload"]``)."""
    text = _run_help(binary, cli)
    helpers = []
    in_commands = False
    for line in text.splitlines():
        if line.startswith("Commands:"):
            in_commands = True
            continue
        if in_commands:
            if not line.strip():
                break
            match = re.match(r"^\s+(\+[a-zA-Z0-9-]+)", line)
            if match:
                helpers.append(match.group(1))
    return helpers


def list_resources(binary, cli):
    """Return the plain (non-helper) sub-commands ``gws`` exposes for a service."""
    text = _run_help(binary, cli)
    resources = set()
    in_commands = False
    for line in text.splitlines():
        if line.startswith("Commands:"):
            in_commands = True
            continue
        if in_commands:
            if not line.strip():
                break
            match = re.match(r"^\s+([a-zA-Z0-9][a-zA-Z0-9-]*)\s", line)
            if match:
                name = match.group(1)
                if name != "help":
                    resources.add(name)
    return resources


def _parse_usage_requirements(text):
    """From the Usage line, return (required_long_opts, required_pos, optional_pos)."""
    required_opts = set()
    required_pos = []
    optional_pos = []
    for line in text.splitlines():
        if line.strip().startswith("Usage:"):
            usage = line.split("Usage:", 1)[1]
            for match in re.finditer(r"--([a-zA-Z0-9-]+)", usage):
                required_opts.add(match.group(1))
            # Strip option tokens (``--opt <META>`` / ``--opt``) so their metavars are not
            # mistaken for positional arguments, then strip [OPTIONS].
            usage = re.sub(r"--[a-zA-Z0-9-]+(\s+<[^>]+>)?", "", usage)
            usage = usage.replace("[OPTIONS]", "")
            for match in re.finditer(r"\[<([^>]+)>\]", usage):
                optional_pos.append(match.group(1))
            stripped = re.sub(r"\[<[^>]+>\]", "", usage)
            for match in re.finditer(r"<([^>]+)>", stripped):
                required_pos.append(match.group(1))
            break
    return required_opts, required_pos, optional_pos


def parse_helper(binary, cli, command):
    """Parse a single ``+helper`` into a :class:`Helper`."""
    text = _run_help(binary, cli, command)
    lines = text.splitlines()

    description = ""
    for line in lines:
        if line.strip():
            description = re.sub(r"^\[Helper\]\s*", "", line.strip())
            break

    required_opts, required_pos, optional_pos = _parse_usage_requirements(text)

    args = []
    seen_args = set()
    for name in required_pos:
        clean = name.strip("<>[]")
        args.append(HelperArg(name=clean, py=naming.safe_kwarg(naming.snake(clean)), required=True))
        seen_args.add(clean)
    for name in optional_pos:
        clean = name.strip("<>[]")
        if clean not in seen_args:
            args.append(
                HelperArg(name=clean, py=naming.safe_kwarg(naming.snake(clean)), required=False)
            )
            seen_args.add(clean)

    # Enrich arg descriptions from the Arguments: section.
    in_args = False
    for line in lines:
        if line.startswith("Arguments:"):
            in_args = True
            continue
        if in_args:
            if not line.strip():
                break
            match = _ARG_RE.match(line)
            if match:
                clean = match.group("name").strip("<>[]")
                for arg in args:
                    if arg.name == clean:
                        arg.desc = match.group("desc").strip()

    options = []
    in_opts = False
    seen_opts = set()
    for line in lines:
        if line.startswith("Options:"):
            in_opts = True
            continue
        if in_opts:
            if not line.strip():
                break
            match = _OPTION_RE.match(line)
            if not match:
                continue
            long = match.group("long")
            if long in _SKIP_OPTIONS or long in seen_opts:
                continue
            seen_opts.add(long)
            desc = match.group("desc").strip()
            options.append(
                HelperOption(
                    long=long,
                    py=naming.safe_kwarg(naming.snake(long)),
                    takes_value=bool(match.group("meta")),
                    required=long in required_opts,
                    desc=desc,
                    multiple="can be specified multiple times" in desc.lower()
                    or "can be repeated" in desc.lower(),
                )
            )

    options.sort(key=lambda o: (not o.required, o.long))
    return Helper(
        cli=cli,
        command=command,
        py=naming.safe_function_name(naming.snake(command.lstrip("+"))),
        description=description,
        args=args,
        options=options,
    )


def parse_service_helpers(binary, cli):
    """Return all parsed helpers for a service."""
    return [parse_helper(binary, cli, cmd) for cmd in list_helpers(binary, cli)]
