"""
Fetch and walk Google Discovery REST documents (build-time input for the generator).

The Discovery doc is the source of truth for parameters and request-body schemas. We fetch
the standard URL, falling back to the ``$discovery`` endpoint used by newer APIs (forms, keep,
meet, workspaceevents, modelarmor). Responses are cached on disk (ETag-aware would need the
network anyway; here we cache the body and reuse it within the same run / re-runs).
"""

import json
import os
import urllib.request
from dataclasses import dataclass
from dataclasses import field

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

STD_URL = "https://www.googleapis.com/discovery/v1/apis/{api}/{version}/rest"
ALT_URL = "https://{api}.googleapis.com/$discovery/rest?version={version}"


@dataclass
class Method:
    """A single Discovery method resolved to what the generator needs."""

    resource_path: tuple  # e.g. ("users", "messages")
    name: str  # e.g. "send"
    http_method: str
    description: str
    parameters: dict  # name -> param node
    parameter_order: list
    has_body: bool
    body_ref: str | None
    supports_media_upload: bool
    scopes: list
    path: str

    @property
    def dotted(self):
        return ".".join(self.resource_path + (self.name,))


@dataclass
class ServiceSchema:
    """A whole service's resolved surface."""

    api: str
    version: str
    title: str
    description: str
    revision: str
    root_url: str
    service_path: str
    methods: list = field(default_factory=list)  # list[Method]
    schemas: dict = field(default_factory=dict)  # request-body schemas snapshot


def fetch_document(api: str, version: str, use_cache: bool = True) -> dict:
    """Return the raw Discovery document, using an on-disk cache when available."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{api}_{version}.json")
    if use_cache and os.path.isfile(cache_file):
        with open(cache_file, encoding="utf-8") as handle:
            return json.load(handle)

    body = None
    last_error = None
    for template in (STD_URL, ALT_URL):
        url = template.format(api=api, version=version)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8")
                    break
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
    if body is None:
        raise RuntimeError(f"Could not fetch Discovery doc for {api}/{version}: {last_error}")

    with open(cache_file, "w", encoding="utf-8") as handle:
        handle.write(body)
    return json.loads(body)


def _walk_resources(resources: dict, prefix: tuple, out: list) -> None:
    for resource_name in sorted(resources):
        node = resources[resource_name]
        path = prefix + (resource_name,)
        for method_name in sorted(node.get("methods", {})):
            mnode = node["methods"][method_name]
            request = mnode.get("request") or {}
            out.append(
                Method(
                    resource_path=path,
                    name=method_name,
                    http_method=mnode.get("httpMethod", "GET"),
                    description=(mnode.get("description") or "").strip(),
                    parameters=mnode.get("parameters") or {},
                    parameter_order=list(mnode.get("parameterOrder") or []),
                    has_body=bool(request),
                    body_ref=request.get("$ref"),
                    supports_media_upload=bool(mnode.get("supportsMediaUpload")),
                    scopes=list(mnode.get("scopes") or []),
                    path=mnode.get("path", ""),
                )
            )
        sub = node.get("resources")
        if sub:
            _walk_resources(sub, path, out)


def load_service(api: str, version: str, use_cache: bool = True) -> ServiceSchema:
    """Fetch and parse a service into a :class:`ServiceSchema`."""
    doc = fetch_document(api, version, use_cache=use_cache)
    methods: list = []
    _walk_resources(doc.get("resources", {}), (), methods)
    methods.sort(key=lambda m: (m.resource_path, m.name))
    return ServiceSchema(
        api=api,
        version=version,
        title=doc.get("title", api),
        description=(doc.get("description") or "").strip(),
        revision=doc.get("revision", ""),
        root_url=doc.get("rootUrl", ""),
        service_path=doc.get("servicePath", ""),
        methods=methods,
        schemas=doc.get("schemas", {}),
    )


def top_level_resources(api: str, version: str, use_cache: bool = True) -> set:
    """Return the set of top-level resource names in a service's Discovery doc."""
    doc = fetch_document(api, version, use_cache=use_cache)
    return set(doc.get("resources", {}).keys())
