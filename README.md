# LLMWiki CLI
## Build your personal knowledge bases and keep them local
### Powered by Ollama, inspired by Andrej Karpathy

An LLMWiki CLI Powered by Ollama, inspired by [Andrej Karpathy](https://gist.github.com/karpathy) and his [LLM Wiki](https://gist.github.com/karpathy) concept.

**Copyright © Stafford Lumsden April 2026 v.1.0**

A production-minded Python application that maintains a persistent markdown knowledge wiki over a folder of source documents. It features automatic categorisation, hybrid retrieval (FTS5 + embeddings), and runs portably across hardware from tiny ARM boards to desktop Apple Silicon.

## 🎯 Features

- **Portable**: Pure Python, SQLite-based, no Docker or heavy services required
- **Automatic Categorisation**: Sources are classified on ingest using rule-based and LLM-driven methods
- **Hybrid Retrieval**: Combines lexical (FTS5) and semantic (embeddings) search
- **Hardware Profiles**: `tiny`, `edge`, `desktop`, and `custom` profiles with feature degradation
- **Model Routing**: Switch between local and cloud Ollama models seamlessly
- **Interactive TUI**: Contextual-style interface for ingestion, querying, and management
- **Human-Readable Wiki**: Generated markdown pages are editable outside the app
- **Safe Updates**: Dry-run and diff modes for page updates
- **Citations**: Every synthesis includes stable inline citations

## 🚀 Installation

```bash
# Install dependencies
uv sync

# Or install via pip
pip install -e .
```

## 📖 Quick Start

### 1. Initialise a Project

```bash
# Choose a hardware profile: tiny, edge, desktop, custom
llmwiki init --profile desktop
```

This creates:
- `sources/` - Place your PDF documents here
- `wiki/` - Generated markdown knowledge base
- `.llmwiki/` - Database and cache
- `llmwiki.yaml` - Configuration file
- `categories/defaults.yaml` - Category definitions

### 2. Configure Models

Edit `llmwiki.yaml` to set your Ollama endpoints and model names:

```yaml
models:
  generation:
    name: qwen3.5:35b
    endpoint: http://localhost:11434
  embeddings:
    name: nomic-embed-text
    endpoint: http://localhost:11434
```

### 3. Ingest Documents

**CLI Mode:**
```bash
llmwiki ingest ./sources
```

**Interactive Mode:**
```bash
llmwiki interactive
# Then type: /ingest
```

### 4. Query Your Wiki

**CLI Mode:**
```bash
llmwiki query "What are the key themes in my documents?"
```

**Interactive Mode:**
```bash
llmwiki interactive
# Type your question and press Meta+Enter (Esc+Enter)
```

### 5. Maintain the Wiki

```bash
# Check wiki health
llmwiki maintain lint

# Rebuild indexes
llmwiki maintain refresh

# Update pages based on new sources
llmwiki maintain reconcile
```

## 🎨 Interactive TUI

Launch the Contextual-style interface:

```bash
llmwiki interactive
```

**Available Commands:**
- `/help` - Show help menu
- `/stats` - Session statistics
- `/ingest` - Ingest documents via file picker
- `/category` - Manage categories (list, add, reload)
- `/switch chat|embed` - Switch models interactively
- `/set cold|balanced|warm` - Apply parameter presets
- `/set parameter <name> <value>` - Set Ollama runtime parameters
- `/readme` - View this README
- `/exit` or `/quit` - Exit

## 💻 Hardware Profiles

| Profile | Target Hardware | Features |
|---------|----------------|----------|
| `tiny` | Orange Pi Zero 2W | FTS-only, no embeddings, cloud models only |
| `edge` | Raspberry Pi 5 | FTS + small embeddings, optional watcher |
| `desktop` | Mac mini M4 | Full features, local models, daemon mode |
| `custom` | User-defined | Override any parameter |

## 📂 Extending Categories

Categories are data-driven. Add a new category without code changes:

**Option 1: CLI**
```bash
llmwiki category add --id consultancy_report --label "Consultancy Report" --description "Advisory reports"
```

**Option 2: Edit YAML**
Edit `categories/defaults.yaml`:
```yaml
- id: consultancy_report
  label: Consultancy Report
  description: Advisory and consultancy reports
  filename_patterns: ["(?i)consultancy", "(?i)advisory"]
  content_patterns: ["(?i)executive summary", "(?i)recommendations"]
  summary_template: consultancy_report
  retrieval_boost: 1.05
```

Then reload:
```bash
llmwiki category reload
llmwiki maintain recategorise
```

## 🏗️ Architecture

```
sources/              # Raw PDFs (immutable ground truth)
wiki/                 # Generated markdown (maintained knowledge layer)
.llmwiki/
  state.db            # SQLite database (metadata, FTS, embeddings)
  cache/              # Cached text, embeddings, diffs
```

### Page Types
- **Source Summaries**: One page per document
- **Concept Pages**: Synthesis across multiple sources
- **Entity Pages**: People, institutions, statutes
- **Comparison Pages**: Side-by-side analysis
- **Open Questions**: Unresolved tensions
- **Category Pages**: Organised by document type

## ⚙️ Configuration

See `llmwiki.yaml` for full options:
- Model endpoints and aliases
- Retrieval weights (lexical vs semantic)
- Chunking parameters
- Wiki output directories
- Category settings
- Daemon/watch mode

## 🛠️ Advanced Usage

### Model Switching
```bash
# Per-command model override
llmwiki query "Question" --model cloud_writer

# Switch in interactive mode
/switch chat
/switch embed
```

### Dry-Run Updates
```bash
# Preview changes without applying
llmwiki maintain reconcile --dry-run
```

### Re-embed with New Model
```bash
llmwiki maintain reembed --model new-embedding-model
```

## 🙏 Kudos

This project was inspired by **Andrej Karpathy**'s vision of local LLM-powered knowledge systems. Special thanks to his [LLM Wiki gist](https://gist.github.com/karpathy) which sparked the idea of maintaining personal knowledge bases with local models.

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Run tests: `pytest`
4. Lint: `ruff check .`
5. Submit a PR

## 📄 License

MIT License - Copyright © Stafford Lumsden April 2026 v.1.0

See [LICENSE](LICENSE) for full text.

## 🛠️ Built With

- **Typer + Rich** for CLI
- **SQLite FTS5** for lexical search
- **Ollama** for generation and embeddings
- **PyPDF** for document parsing
- **NumPy** for vector operations
- **Prompt Toolkit** for interactive input
- **Pick** for file selection menus

---

**LLMWiki CLI v1.0** | © Stafford Lumsden April 2026
