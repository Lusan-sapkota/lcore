# Contributing to Lcore

## Reporting Bugs

Open a [GitHub Issue](https://github.com/Lusan-sapkota/lcore/issues) with:

- A clear title and description of the bug
- Steps to reproduce (minimal code example)
- Expected vs actual behavior
- Python version and operating system

## Submitting Pull Requests

1. Fork the repository
2. Create a branch for your change
3. Write or update tests for your change
4. Run the test suite and make sure all tests pass
5. Submit a pull request against the `main` branch

## Running Tests

```bash
python -m pytest tests/
```

All 449 tests should pass. The test suite uses only `unittest` from the standard library — no external test dependencies.

## Code Style

- Follow the patterns already established in `lcore.py`
- Use the same naming conventions, docstring style, and formatting
- Keep the code readable and consistent with the rest of the framework

## Constraints

- **No new dependencies.** Lcore imports only from Python's standard library. This is a hard constraint — do not add third-party imports to `lcore.py` or `tests/`.
- **Keep it in one file.** Framework additions go in `lcore.py`. The demo backend (`backend/`) is exempt from this rule.
