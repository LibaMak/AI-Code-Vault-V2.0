# Contributing to AI Code Vault 2.0

Welcome, and thank you for considering contributing to **AI Code Vault 2.0**! Whether you're fixing a bug, adding a feature, improving documentation, or suggesting an idea — your contribution is valued and appreciated.

This guide will help you get started quickly and ensure a smooth collaboration for everyone involved.

---

## 🛠 Development Setup

### Prerequisites

- **Python 3.11** or higher
- **Git**
- A GitHub account

### Getting Started

1. **Fork** the repository on GitHub and **clone** your fork locally:

   ```bash
   git clone https://github.com/<your-username>/AI-Code-Vault-V2.0.git
   cd AI-Code-Vault-V2.0
   ```

2. **Create a virtual environment** and activate it:

   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Open `.env` and fill in the required API keys and configuration values.

5. **Run the application:**

   ```bash
   streamlit run streamlit_app.py
   ```

   The app should open in your browser at `http://localhost:8501`.

---

## 🏗 Project Architecture

AI Code Vault 2.0 is a Streamlit-based AI code intelligence platform. Here's a high-level overview of the key modules:

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Main UI entry point (Streamlit) |
| `backend/agent.py` | Multi-agent orchestration — coordinates 10 specialist agents |
| `backend/db_connector.py` | Database models following the Data Vault 2.0 methodology (22 models) |
| `backend/ai_parser.py` | Code parsing using AST analysis combined with LLM intelligence |
| `backend/embeddings.py` | Vector embeddings generation via sentence-transformers |
| `backend/file_processor.py` | File upload handling and content extraction |
| `backend/repo_scanner.py` | Git repository scanning and indexing |

---

## ✏️ Code Style Guidelines

Consistency keeps the codebase readable and maintainable. Please follow these conventions:

- **Follow [PEP 8](https://peps.python.org/pep-0008/)** for all Python code.
- **Use type hints** where possible, especially for function signatures.
- **Add docstrings** to all new functions and classes.
- **Preserve existing comments and documentation** — do not remove them without good reason.
- **Use meaningful variable names** that clearly convey intent.
- **Keep functions focused and single-purpose** — if a function does too much, consider splitting it.

---

## 🔄 Making Changes

1. **Create a feature branch** from `main`:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make focused, atomic commits.** Each commit should represent a single logical change.

3. **Write clear commit messages** that explain *what* changed and *why*:

   ```
   Add PDF extraction support to file_processor

   Adds PyPDF2-based text extraction for uploaded PDF files,
   including error handling for encrypted documents.
   ```

4. **Test your changes locally** — run the app and verify your feature works as expected.

5. **Ensure the app starts without errors:**

   ```bash
   streamlit run streamlit_app.py
   ```

6. **Submit a pull request** when your changes are ready for review.

---

## 📋 Pull Request Guidelines

When submitting a pull request, please:

- **Describe what changed and why.** Provide enough context for reviewers to understand your intent.
- **Reference related issues** using GitHub keywords (e.g., `Closes #42`).
- **Include testing steps** so reviewers can verify the changes.
- **Keep PRs focused on a single concern.** Avoid bundling unrelated changes together — smaller PRs are easier and faster to review.

---

## 🐛 Reporting Issues

Found a bug or have a suggestion? Please [open an issue](https://github.com/LibaMak/AI-Code-Vault-V2.0/issues) on GitHub.

When reporting a bug, include:

- **Steps to reproduce** the issue
- **Expected behavior** vs. **actual behavior**
- **Python version** (`python --version`)
- **Operating system** and version
- **Error messages or logs**, if applicable

The more detail you provide, the faster we can investigate and resolve the issue.

---

## 💡 Areas for Contribution

Not sure where to start? Here are some areas where contributions are especially welcome:

- **New specialist agents** — Extend `agent.py` with additional domain-specific agents.
- **File format support** — Add new parsers in `file_processor.py` for additional file types.
- **Search improvements** — Enhance search algorithms for better accuracy and performance.
- **UI/UX enhancements** — Improve the Streamlit interface for a better user experience.
- **Documentation** — Expand guides, add examples, or improve inline documentation.
- **Bug fixes** — Check open issues for known bugs that need attention.
- **Performance optimizations** — Profile and improve processing speed or memory usage.

---

## 📄 License

This project is licensed under the **MIT License**. By contributing, you agree that your contributions will be licensed under the same terms.

---

Thank you for helping make AI Code Vault 2.0 better!
