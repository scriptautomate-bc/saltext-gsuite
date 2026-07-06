"""
Naming and type conventions shared by the generator.

Design choices:

* Function names are snake_case: the resource path segments plus the method, e.g.
  ``drive.files.list`` -> ``files_list``; ``gmail.users.messages.send`` ->
  ``users_messages_send``; ``sheets.spreadsheets.values.batchGet`` ->
  ``spreadsheets_values_batch_get``.
* Parameter kwargs keep their **verbatim Discovery names** (usually camelCase such as
  ``fileId``, ``pageSize``). This matches Google's public API reference one-to-one, keeps
  required and optional (``**params``) parameters under a single naming scheme, and avoids an
  error-prone snake<->camel round trip when building the ``--params`` JSON. Names that are not
  valid Python identifiers or collide with Python keywords get a trailing underscore in the
  signature and are mapped back to the original when the request is built.
"""

import keyword
import re

_CAMEL_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")

# Control kwargs consumed by saltext.gsuite._gws; an API parameter sharing one of these names
# would be shadowed, so the generator flags it (see generate_modules.py).
RESERVED_KWARGS = {
    "test",
    "page_all",
    "page_limit",
    "page_delay",
    "output",
    "timeout",
    "body",
    "upload",
}

# Discovery JSON type -> a human-friendly label for docs.
TYPE_LABELS = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def snake(name: str) -> str:
    """Convert a camelCase / PascalCase identifier to snake_case."""
    name = name.replace("-", "_").replace(".", "_")
    name = _CAMEL_1.sub(r"\1_\2", name)
    name = _CAMEL_2.sub(r"\1_\2", name)
    return name.lower()


def function_name(resource_path, method: str) -> str:
    """Build the execution-module function name for a method."""
    parts = [snake(p) for p in resource_path]
    parts.append(snake(method))
    return "_".join(parts)


# Names that would collide with a generated function's own parameters or locals.
SIGNATURE_RESERVED = {"params", "body", "upload", "test", "self", "log", "_params"}


def safe_kwarg(name: str) -> str:
    """Return a valid Python identifier for a parameter, preserving the original where possible."""
    if name.isidentifier() and not keyword.iskeyword(name) and name not in SIGNATURE_RESERVED:
        return name
    candidate = re.sub(r"\W", "_", name)
    if not candidate or candidate[0].isdigit():
        candidate = "p_" + candidate
    if keyword.iskeyword(candidate) or candidate in SIGNATURE_RESERVED:
        candidate += "_"
    return candidate


def safe_function_name(name: str) -> str:
    """Sanitize a generated *function* name (guards keywords/identifiers only)."""
    candidate = re.sub(r"\W", "_", name)
    if not candidate or candidate[0].isdigit():
        candidate = "fn_" + candidate
    if keyword.iskeyword(candidate):
        candidate += "_"
    return candidate


def type_label(param: dict) -> str:
    """Human-friendly type label for a Discovery parameter node."""
    return TYPE_LABELS.get(param.get("type", "string"), param.get("type", "string"))


def clean_description(text: str) -> str:
    """Collapse whitespace in a Discovery description for safe embedding in docstrings."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


_RST_SPECIAL = re.compile(r"([`*|_\\])")


def rst_escape(text: str) -> str:
    """
    Escape reStructuredText inline markup characters in free Discovery text.

    Google descriptions freely use single backticks, asterisks and pipes as Markdown, which
    Sphinx (built with ``-W``) rejects as malformed inline markup. Backslash-escaping keeps the
    prose rendering verbatim. The result is embedded in plain (non-raw) triple-quoted Python
    docstrings, so the backslash itself is doubled: a single ``\\`` before the markup character
    is not a valid Python string escape and trips ``SyntaxWarning: invalid escape sequence``.
    """
    if not text:
        return ""
    return _RST_SPECIAL.sub(lambda m: "\\\\" + m.group(1), text)


def required_params(method) -> list:
    """
    Return the ordered list of required parameters for a method as dicts:
    ``{"py": <signature name>, "orig": <discovery name>, "type": <label>, "desc": <text>}``.

    Ordered by the Discovery ``parameterOrder`` first, then remaining required params alpha.
    """
    params = method.parameters
    ordered = []
    seen = set()
    for name in method.parameter_order:
        if name in params and params[name].get("required"):
            ordered.append(name)
            seen.add(name)
    for name in sorted(params):
        if name not in seen and params[name].get("required"):
            ordered.append(name)
    result = []
    for name in ordered:
        node = params[name]
        result.append(
            {
                "py": safe_kwarg(name),
                "orig": name,
                "type": type_label(node),
                "desc": clean_description(node.get("description", "")),
            }
        )
    return result


def optional_params(method) -> list:
    """Return optional parameters (for documentation), same dict shape as required_params."""
    params = method.parameters
    result = []
    for name in sorted(params):
        node = params[name]
        if node.get("required"):
            continue
        result.append(
            {
                "py": safe_kwarg(name),
                "orig": name,
                "type": type_label(node),
                "desc": clean_description(node.get("description", "")),
                "deprecated": bool(node.get("deprecated")),
            }
        )
    return result
