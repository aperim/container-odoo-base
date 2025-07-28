#!/usr/bin/env python3
"""Verify that the fixes to the entrypoint script were applied correctly."""

import ast
import sys
from pathlib import Path

def check_no_duplicate_code():
    """Check that duplicate code blocks were removed."""
    entrypoint_path = Path(__file__).parent.parent / "entrypoint.py"
    content = entrypoint_path.read_text()
    
    # Check for duplicate ODOO_SKIP_CHOWN
    skip_chown_count = content.count('env.get("ODOO_SKIP_CHOWN") and env["ODOO_SKIP_CHOWN"].lower()')
    if skip_chown_count > 1:
        print(f"❌ Found {skip_chown_count} ODOO_SKIP_CHOWN checks (expected ≤ 1)")
        return False
    
    # Check for duplicate package module lookups in runtime_housekeeping_impl
    impl_start = content.find("def _runtime_housekeeping_impl")
    impl_end = content.find("\ndef", impl_start + 1)
    impl_content = content[impl_start:impl_end] if impl_end > 0 else content[impl_start:]
    
    pkg_mod_count = impl_content.count('_sys.modules.get("entrypoint")')
    if pkg_mod_count > 2:  # Allow up to 2 for legitimate uses
        print(f"❌ Found {pkg_mod_count} package module lookups in runtime_housekeeping_impl (expected ≤ 2)")
        return False
    
    # Check for duplicate Redis/PostgreSQL wait logic
    duplicate_wait_pattern = "wait_for_redis()  # blocks until Redis replies to PING"
    wait_count = impl_content.count(duplicate_wait_pattern)
    if wait_count > 0:
        print(f"❌ Found duplicate Redis wait logic in runtime_housekeeping_impl")
        return False
    
    print("✅ No duplicate code blocks found")
    return True

def check_header_updated():
    """Check that the header reflects completed status."""
    entrypoint_path = Path(__file__).parent.parent / "entrypoint.py"
    content = entrypoint_path.read_text()
    
    # Check that "ongoing port" is removed
    if "ongoing port" in content[:2000]:
        print("❌ Header still mentions 'ongoing port'")
        return False
    
    # Check that v0.5 TODO section is updated
    if "Open issues / TODO (v0.5)" in content:
        print("❌ Header still contains TODO v0.5 section")
        return False
    
    # Check for production-ready mention
    if "production-ready" in content[:2000]:
        print("✅ Header mentions production-ready status")
        return True
    
    print("⚠️  Header doesn't explicitly mention production-ready status")
    return True

def check_function_signatures():
    """Verify key functions still have correct signatures."""
    entrypoint_path = Path(__file__).parent.parent / "entrypoint.py"
    content = entrypoint_path.read_text()
    
    # Parse the AST
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"❌ Syntax error in entrypoint.py: {e}")
        return False
    
    # Find key functions
    expected_functions = {
        "wait_for_dependencies": ["env"],
        "runtime_housekeeping": ["env"],
        "_runtime_housekeeping_impl": ["env"],
        "main": ["argv"],
    }
    
    found_functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in expected_functions:
            args = [arg.arg for arg in node.args.args]
            found_functions[node.name] = args
    
    # Verify signatures
    all_good = True
    for func_name, expected_args in expected_functions.items():
        if func_name not in found_functions:
            print(f"❌ Function {func_name} not found")
            all_good = False
        elif found_functions[func_name][:len(expected_args)] != expected_args:
            print(f"❌ Function {func_name} has unexpected signature: {found_functions[func_name]}")
            all_good = False
    
    if all_good:
        print("✅ All function signatures are correct")
    
    return all_good

def main():
    """Run all verification checks."""
    print("Verifying entrypoint fixes...\n")
    
    checks = [
        ("Duplicate code removal", check_no_duplicate_code),
        ("Header update", check_header_updated),
        ("Function signatures", check_function_signatures),
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        if not check_func():
            all_passed = False
    
    print("\n" + "="*50)
    if all_passed:
        print("✅ All checks passed! The fixes were applied correctly.")
        return 0
    else:
        print("❌ Some checks failed. Please review the entrypoint.py file.")
        return 1

if __name__ == "__main__":
    sys.exit(main())