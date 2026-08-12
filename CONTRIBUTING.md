# Contributing to pyverge

Thank you for considering contributing to pyverge! This document outlines the
process for contributing code, documentation, and ideas.

## Getting started

1. **Fork the repository** and clone it locally.
2. **Create a virtual environment** and install dependencies:
   ```bash
   uv sync --dev
   ```
3. **Run the tests** to ensure everything works:
   ```bash
   uv run pytest
   ```

## How to contribute

### Reporting issues

- Use the issue tracker to report bugs, request features, or ask questions.
- For bugs, include:
  - A minimal reproducible example
  - Expected vs. actual behavior
  - Python version and pyverge version
  - Stack traces if applicable

### Submitting code

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the existing code style.

3. **Write tests** for new functionality. Aim for high coverage.

4. **Run checks** before committing:
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run pytest
   uv run ty check src/pyverge
   ```

5. **Commit** with a clear message following [Conventional Commits](https://www.conventionalcommits.org/):
   ```bash
   git commit -m "feat: add new migration hook type"
   ```

6. **Push** and open a pull request.

### Documentation

- Documentation lives in `docs/`.
- Use reStructuredText or Markdown consistently.
- Include examples for new features.
- Update the changelog if applicable.

## Code style

- **Formatting**: `ruff format` (Black-compatible)
- **Linting**: `ruff check`
- **Type checking**: `ty check`
- **Testing**: `pytest` with `-vv` for verbose output

Follow existing patterns in the codebase. When in doubt, match the surrounding
code.

## Pull request process

1. **CI must pass** — all checks (ruff, ty, pytest) must be green.
2. **Review** — at least one maintainer must approve.
3. **Squash** — if your branch has multiple commits, squash them into logical
   units before merging.
4. **Merge** — maintainers will merge your PR once approved.

## Release process

Releases are automated via [commitizen](https://commitizen-tools.github.io/commitizen/):

1. Commit messages determine the next version:
   - `feat:` → minor version bump
   - `fix:` → patch version bump
   - `BREAKING CHANGE:` → major version bump

2. Pushing to `main` triggers the release pipeline.

3. The changelog is auto-generated from commit messages.

## Questions?

- Open an issue for discussion.
- Check existing issues and PRs for similar topics.
- Read the [documentation](docs/) for usage guidance.
