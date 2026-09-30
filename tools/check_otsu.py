#!/usr/bin/env python3
"""Static check: every otsu() caller must unpack the (threshold, eta) pair.

otsu() now returns a tuple. A caller that still treats it as a float would
compare an array against a float and either raise or silently misbehave, and
this project has no test runner, so the check is static.

    python3 tools/check_otsu.py [file ...]
"""
import ast
import sys

PATHS = sys.argv[1:] or ["tools/compare_render.py"]


def parents_of(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def main():
    rc = 0
    for path in PATHS:
        src = open(path).read()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            print("SYNTAX ERROR %s line %s: %s" % (path, e.lineno, e.msg))
            rc = 1
            continue
        print("AST_OK  %s" % path)
        par = parents_of(tree)
        n, bad = 0, 0
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "otsu"):
                continue
            n += 1
            p = par.get(node)
            # `tr, eta = otsu(...)` parses with the Tuple on TARGETS, not on
            # value - checking p.value is the natural mistake and reports every
            # correctly-unpacked call as broken
            if isinstance(p, ast.Assign) and isinstance(p.value, ast.Call) \
                    and len(p.targets) == 1 \
                    and isinstance(p.targets[0], ast.Tuple) \
                    and len(p.targets[0].elts) == 2:
                continue
            if isinstance(p, ast.Subscript):
                continue                      # otsu(...)[0]
            if isinstance(p, ast.Tuple):
                continue                      # f(otsu(...), ...)
            bad += 1
            print("  %s line %d: otsu() result not unpacked into 2 names"
                  % (path, node.lineno))
        print("  otsu() call sites: %d, unhandled: %d" % (n, bad))
        rc |= 1 if bad else 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
