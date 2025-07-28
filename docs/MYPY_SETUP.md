# MyPy Type Checking Setup

This document describes the setup for static type checking with mypy, addressing TODO #8.

## Configuration

A `mypy.ini` configuration file has been created in the repository root with the following settings:

- Python version: 3.11
- Strict mode enabled for better type safety
- Ignores missing imports for `tools.*`, `redis.*`, and `psycopg2.*` packages

## Running MyPy

To run mypy locally:

```bash
mypy entrypoint/entrypoint.py
```

## CI Integration

To add mypy to the CI pipeline:

1. Copy `.github/workflows/mypy.yml.example` to `.github/workflows/mypy.yml`
2. The workflow will run on all pushes and pull requests to the main branch
3. It will fail the build if type errors are detected

## Current Status

As of the latest check, there are some unused type: ignore comments and a few no-redef warnings in the entrypoint.py file. These are primarily due to:

1. Dynamic imports from the tools package
2. Variable redefinitions in different scopes
3. Legacy code patterns that are difficult to type strictly

## Recommendations

1. Gradually remove unused type: ignore comments
2. Consider refactoring code to avoid variable redefinitions
3. Add type stubs for the tools package if needed
4. Enable mypy in CI to prevent regression of type safety