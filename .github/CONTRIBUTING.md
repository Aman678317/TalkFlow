# Contributing to GlobalTalk AI

First off, **thank you** for considering contributing to GlobalTalk AI! 🎉  
Every contribution — big or small — helps break language barriers for more people.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Submitting Pull Requests](#submitting-pull-requests)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Commit Message Convention](#commit-message-convention)

---

## Code of Conduct

This project adheres to our [Code of Conduct](CODE_OF_CONDUCT.md).  
By participating, you agree to uphold these standards.  
Report unacceptable behaviour to [open-source@globaltalk.ai](mailto:open-source@globaltalk.ai).

---

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/globaltalk-ai.git
   cd globaltalk-ai
   ```
3. **Set up** the development environment (see [Development Setup](#development-setup)).
4. **Create a feature branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```

---

## How to Contribute

### Reporting Bugs

If you find a bug, please [open an issue](../../issues/new?template=bug-report.md) and include:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Your OS, Python version, Node version, and browser
- Any relevant logs or screenshots

### Suggesting Features

For new feature ideas, [open an issue](../../issues/new?template=suggest-new-feature.md) with:
- A clear description of the proposed feature
- Why this would benefit users
- Any potential implementation ideas

### Submitting Pull Requests

1. **One feature or fix per PR** — keep it focused.
2. **Reference an issue** if one exists (`Fixes #123`).
3. **Write tests** for any new functionality.
4. **Ensure all tests pass** before submitting.
5. **Update documentation** if the API or behavior changes.
6. **Follow the coding standards** below.

Fill out the [pull request template](PULL_REQUEST_TEMPLATE.md) completely.

---

## Development Setup

### Backend

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r services/api/requirements.txt
pip install -r services/api/requirements-dev.txt

# Copy and configure environment
cp .env.example .env

# Run the API server
python run_api.py
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

### Running Tests

```bash
# Backend tests
pytest tests/ -v

# Frontend tests
cd apps/web && npm test
```

---

## Coding Standards

### Python (Backend)

- **Formatter:** `black` (line length 100)
- **Linter:** `ruff`
- **Type hints:** required on all public functions
- **Docstrings:** Google-style for all public modules, classes, and functions
- **No direct model imports** in routes — always use service/AI abstraction layers

### TypeScript (Frontend)

- **Formatter:** Prettier
- **Linter:** ESLint with strict TypeScript rules
- **No `any`** unless explicitly justified with a comment
- **Components:** functional components with explicit prop types
- **State management:** Zustand stores for global state, `useState` for local

### Git Hygiene

- Keep commits atomic and focused
- Rebase onto the latest `main` before opening a PR
- Squash fixup commits before requesting review

---

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

**Examples:**
```
feat(voice): add BCP-47 language code normalization
fix(api): correct cors_origins parsing for comma-separated values
docs(readme): update quick start with Windows instructions
refactor(db): extract normalize_db_url into a utility function
```

---

## Questions?

Open a [GitHub Discussion](../../discussions) or reach out via [open-source@globaltalk.ai](mailto:open-source@globaltalk.ai).

Thank you for helping make GlobalTalk AI better! 🌍
