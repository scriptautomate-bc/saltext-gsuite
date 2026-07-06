"""
Validate that every hand-written module under modules/ or states/ has a docs/ref page.

tools/generate_modules.py owns docs/ref/{modules,states}/**: it writes a page for every
generated module and, per tools/_codegen/hand_written.toml, for every registered hand-written
module too (see that file's comment header). This hook does not generate anything itself -- two
tools writing the same files in different templates is exactly the drift bug this replaced. It
only checks that the registry and the generator's own manifest agree with what's actually on
disk, so a new hand-written module can't silently ship without docs.
"""

import json
import sys
import tomllib
from pathlib import Path

repo_path = Path(__file__).resolve().parent.parent
src_dir = repo_path / "src" / "saltext" / "gsuite"
manifest_path = src_dir / "metadata" / "generated_manifest.json"
registry_path = repo_path / "tools" / "_codegen" / "hand_written.toml"

with manifest_path.open(encoding="utf-8") as handle:
    generated_files = set(json.load(handle)["files"])

with registry_path.open("rb") as handle:
    registry = tomllib.load(handle)["module"]
registered_paths = {
    "src/saltext/gsuite/" + entry["path"].replace(".", "/") + ".py" for entry in registry
}

errors = []
for kind in ("modules", "states"):
    for path in sorted((src_dir / kind).glob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = str(path.relative_to(repo_path))
        if rel in generated_files:
            continue
        if rel not in registered_paths:
            errors.append(
                f"{rel}: hand-written module has no docs/ref page. Register it in "
                f"{registry_path.relative_to(repo_path)} and run `just generate`."
            )

for entry in registry:
    rst_name = f"docs/ref/{'states' if entry['path'].startswith('states.') else 'modules'}/{entry['name']}.rst"
    if rst_name not in generated_files:
        errors.append(
            f"{registry_path.relative_to(repo_path)}: entry {entry['name']!r} is not reflected "
            f"in {manifest_path.relative_to(repo_path)}. Run `just generate`."
        )

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
