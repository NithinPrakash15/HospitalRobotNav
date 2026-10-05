#!/usr/bin/env bash
# Phase 0 — Static validation of the HospitalRobotNav ROS 2 workspace.
# Run inside WSL:  bash phase0_static_check.sh
set -u
WS="/mnt/c/Users/nithi/OneDrive/Desktop/Main Project for vs/HospitalRobotNav/hospital_robot_nav_ws"
FAIL=0

echo "=== [0.1] Syntax-check all Python files in the workspace ==="
while IFS= read -r f; do
  if python3 -m py_compile "$f" 2>/dev/null; then
    echo "OK:   $f"
  else
    echo "FAIL: $f"
    FAIL=1
  fi
done < <(find "$WS/src" -name '*.py' -type f)
echo ""

echo "=== [0.2] Verify hospital_robot_nav_core shim imports root modules ==="
cd "$WS"
# The real package lives at src/hospital_robot_nav_core/hospital_robot_nav_core/,
# so its parent (src/hospital_robot_nav_core) is the PYTHONPATH entry.
if PYTHONPATH="$WS/src/hospital_robot_nav_core" python3 - <<'PYEOF' 2>&1
import sys
import hospital_robot_nav_core as core
root = core.__dict__.get("_PROJECT_ROOT")
print("core shim imported OK. Project root =", root)
missing = []
for name in core.__dict__.get("_SUBMODULES", ()):
    try:
        mod = sys.modules.get(f"hospital_robot_nav_core.{name}")
        print(f"  submodule OK: {name} -> {getattr(mod, '__name__', '?')}")
    except Exception as e:
        missing.append(name)
        print(f"  submodule WARN (skipped): {name} ({e})")
if root is None:
    print("core shim FAILED: _PROJECT_ROOT is None (main.py not found up the tree)")
    sys.exit(1)
print("Core shim check passed.")
PYEOF
then
  echo "Core shim check passed."
else
  echo "Core shim check FAILED."
  FAIL=1
fi
echo ""

echo "=== [0.3] Validate .msg/.srv/.action field definitions ==="
cd "$WS"
python3 - <<'PYEOF'
import re, pathlib, sys

root = pathlib.Path("src/hospital_robot_nav_msgs")
builtin_types = {
    "bool","byte","char","float32","float64","int8","uint8","int16","uint16",
    "int32","uint32","int64","uint64","string",
}
ok = True
for p in sorted(root.rglob("*")):
    if p.suffix not in (".msg", ".srv", ".action"):
        continue
    lines = p.read_text().splitlines()
    for i, ln in enumerate(lines, 1):
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln == "---":
            continue
        # ignore constant definitions (UPPER_CASE = value)
        if re.match(r"^[A-Z_][A-Z0-9_]*\s*=", ln):
            continue
        m = re.match(r"^([\w/]+)\s+([\w]+)", ln)
        if not m:
            print(f"  PARSE WARN {p}:{i}: {ln!r}")
            continue
        typ, fld = m.groups()
        base = typ.split("/")[-1]
        if base.endswith("[]"):
            base = base[:-2]
        if base in builtin_types or "/" in typ or base in ("GridPos", "TaskStep",
                "MissionRequest", "Time", "Duration"):
            continue
        print(f"  UNKNOWN TYPE {p}:{i}: {typ} {fld}")
        ok = False
print("Interface definitions:", "ALL OK" if ok else "ISSUES FOUND")
if not ok:
    sys.exit(1)
PYEOF
if [ $? -ne 0 ]; then FAIL=1; fi
echo ""

echo "=== [0.4] Verify setup.py entrypoints match node modules ==="
cd "$WS"
python3 - <<'PYEOF'
import ast, pathlib, sys

nodes_dir = pathlib.Path("src/hospital_robot_nav_nodes/hospital_robot_nav_nodes")
setup_py = pathlib.Path("src/hospital_robot_nav_nodes/setup.py")
modules = {p.stem for p in nodes_dir.glob("*.py") if p.stem != "__init__"}
tree = ast.parse(setup_py.read_text())

def _collect_console_scripts(node):
    """Recursively collect console_scripts from any entry_points dict in the AST."""
    if not isinstance(node, ast.Dict):
        return set()
    eps = set()
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == "console_scripts" and isinstance(v, (ast.List, ast.Tuple)):
            for el in v.elts:
                if isinstance(el, ast.Constant):
                    eps.add(el.value.split("=")[0].strip())
    return eps

eps = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setup":
        for kw in node.keywords:
            if kw.arg == "entry_points":
                eps |= _collect_console_scripts(kw.value)
    if isinstance(node, ast.Dict) and any(
        isinstance(k, ast.Constant) and k.value == "console_scripts" for k in node.keys
    ):
        eps |= _collect_console_scripts(node)

missing = sorted(modules - eps)
extra = sorted(eps - modules)
print("Node modules:", len(modules), "| Entrypoints:", len(eps))
print("Modules missing entrypoint:", missing or "NONE")
print("Entrypoints with no module:", extra or "NONE")
if missing or extra:
    sys.exit(1)
PYEOF
if [ $? -ne 0 ]; then FAIL=1; fi
echo ""

echo "=== [0.5] Check disk space + Python version + network ==="
df -h /mnt/c | tail -1
python3 --version
echo "Checking packages.ros.org reachability..."
# Use a full GET (with --max-time) to validate the TLS handshake + HTTP response;
# HEAD can hang on some mirrors.  The Release file is small (~KB).
if curl -4 -s --max-time 20 -o /dev/null -w "%{http_code}" https://packages.ros.org/ros2/ubuntu/dists/noble/Release >/tmp/ros_http.txt 2>/dev/null && [ "$(cat /tmp/ros_http.txt)" = "200" ]; then
  echo "packages.ros.org: REACHABLE (HTTP $(cat /tmp/ros_http.txt))"
else
  code=$(cat /tmp/ros_http.txt 2>/dev/null || echo "none")
  echo "packages.ros.org: CHECK FAILED (HTTP code '$code') — will re-verify during apt install"
fi
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "=== PHASE 0 STATIC VALIDATION: ALL CHECKS PASSED ==="
else
  echo "=== PHASE 0 STATIC VALIDATION: ISSUES FOUND (see above) ==="
  exit 1
fi

