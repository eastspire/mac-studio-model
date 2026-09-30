#!/usr/bin/env python3
"""Static consistency check between build_mac_studio.py and mac_studio_spec.py.

Blender cannot start in this sandbox - it segfaults in MTLCreateSystemDefaultDevice
before any Python runs - so the build script has never been executed here. That
leaves static checks as the only evidence that the model would be built from the
corrected spec, and it is not a small thing to leave unchecked: the script used
to carry its own copy of the measured constants, so a corrected spec could pass
its own self-test and still never reach the geometry.

Checked here:
  1. every name the builder imports from the spec actually exists there;
  2. the builder defines no module-level numeric constant of its own, so there
     is nothing left that can drift away from the spec;
  3. every name the builder uses is bound - imported, defined, or builtin - so
     a typo fails here rather than at Blender start-up;
  4. the spec's own invariants still hold with the corrected band.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BLENDER = os.path.join(ROOT, "blender")

sys.path.insert(0, BLENDER)
import mac_studio_spec as S  # noqa: E402

BUILDER = os.path.join(BLENDER, "build_mac_studio.py")


def main():
    src = open(BUILDER).read()
    tree = ast.parse(src)
    spec_names = set(dir(S))
    bad = 0

    # 1. every `from mac_studio_spec import ...` name exists
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "mac_studio_spec":
            for a in node.names:
                imported.add(a.asname or a.name)
                if a.name not in spec_names:
                    print("  MISSING from spec: %s" % a.name)
                    bad += 1
    print("1. spec imports: %d names, all present: %s"
          % (len(imported), "yes" if bad == 0 else "NO"))

    # 2. no module-level NUMERIC constant of its own. VIEWS and TARGETS are
    # camera framing, not measured dimensions, so they are allowed to live
    # here; what must not reappear is a bare number that duplicates the spec.
    # "Contains numbers somewhere inside" is not the test - a list of camera
    # positions is full of them - the value itself has to BE a number.
    def is_number(node):
        if isinstance(node, ast.Num):
            return True
        if isinstance(node, ast.UnaryOp):
            return is_number(node.operand)
        if isinstance(node, ast.BinOp):
            return is_number(node.left) and is_number(node.right)
        return False

    own = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and is_number(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    own.append((t.id, node.lineno))
    for n, ln in own:
        print("  module-level NUMERIC constant in the builder: %s (line %d)"
              % (n, ln))
    bad += len(own)
    print("2. module-level numeric constants in the builder: %d (want 0)"
          % len(own))

    # 3. every global name used is bound somewhere
    import builtins
    defined = set(dir(builtins)) | imported | {"__name__", "__file__", "S"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                defined.add(a.asname or a.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.comprehension,)):
            pass
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    missing = sorted(used - defined)
    for m in missing:
        print("  UNBOUND name used in the builder: %s" % m)
    bad += len(missing)
    print("3. unbound names: %d (of %d used)" % (len(missing), len(used)))

    # 4. the spec's own invariants
    print("4. spec self-test:")
    import io
    import contextlib
    buf = io.StringIO()
    glb = {"__name__": "__main__", "__file__": os.path.join(BLENDER,
                                                            "mac_studio_spec.py")}
    with contextlib.redirect_stdout(buf):
        try:
            exec(compile(open(os.path.join(BLENDER, "mac_studio_spec.py")).read(),
                         "mac_studio_spec.py", "exec"), glb)
        except SystemExit as e:
            if e.code in (0, None):
                pass
            else:
                print("   spec self-test exited %s" % e.code)
                bad += 1
        except AssertionError as e:
            print("   spec self-test FAILED: %s" % e)
            bad += 1
    out = buf.getvalue().strip()
    print("   %s" % (out if out else "(no output - the self-test did not run)"))
    if "SPEC_OK" not in out:
        print("   spec self-test did not report SPEC_OK")
        bad += 1

    print("\n%s" % ("STATIC CHECK CLEAN" if bad == 0
                    else "STATIC CHECK FOUND %d PROBLEM(S)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
