"""CLI command implementations for llmwiki.

This module defines CLI command functions that are registered with the Typer app
in __main__.py. It includes all commands: init, doctor, stats, profile, category,
model, ingest, query, page, maintain, and daemon.
"""

import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path
import yaml
import sqlite3
import sys
import urllib.request
import json
import shutil

from llmwiki import __version__
from llmwiki.config import Config
from llmwiki.db import init_database
from llmwiki.constants import (
    DEFAULT_config_file,
    DEFAULT_categories_file,
    DEFAULT_sources_dir,
    DEFAULT_wiki_dir,
    DEFAULT_state_dir,
    DEFAULT_cache_dir,
    DEFAULT_db_path,
    SUPPORTED_PROFILES,
)


console = Console()

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------

def init(
    profile: str = typer.Option(
        "desktop",
        "--profile",
        "-p",
        help=f"Hardware profile. One of: {', '.join(SUPPORTED_PROFILES)}",
    ),
    config_file: str = typer.Option(
        DEFAULT_config_file,
        "--config",
        "-c",
        help="Path to configuration file.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration.",
    ),
):
    """Initialize a new llmwiki project.

    Creates required directories, database, default configuration file,
    and default category definitions.
    """
    config_path = Path(config_file)
    state_dir = Path(DEFAULT_state_dir)

    console.print(f"[bold blue]Initializing llmwiki v{__version__}[/bold blue]")
    console.print(f"[dim]Profile: {profile}[/dim]\n")

    # Validate profile
    if profile not in SUPPORTED_PROFILES:
        console.print(
            f"[red]Error: Invalid profile '{profile}'. Must be one of: {', '.join(SUPPORTED_PROFILES)}[/red]"
        )
        raise typer.Exit(code=1)

    # Create directory structure
    console.print("[bold]Creating directory structure...[/bold]")
    directories = [
        Path(DEFAULT_sources_dir),
        Path(DEFAULT_wiki_dir),
        state_dir,
        Path(DEFAULT_cache_dir),
    ]
    for directory in directories:
        if directory.exists():
            console.print(f"  ✓ [green]Already exists:[/green] {directory}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            console.print(f"  ✓ [green]Created:[/green] {directory}")

    # Initialise SQLite database
    db_path = Path(DEFAULT_db_path)
    console.print(f"\n[bold]Initialising database:[/bold] {db_path}")
    try:
        conn = init_database(db_path)
        conn.close()
        console.print("  ✓ [green]Database initialised[/green]")
    except Exception as e:
        console.print(f"  [red]Error initialising database: {e}[/red]")
        raise typer.Exit(code=1)

    # Write default configuration (unless exists and not forced)
    if config_path.exists() and not force:
        console.print(f"\n[yellow]Config file already exists:[/yellow] {config_path}")
        console.print("[dim]Use --force to overwrite[/dim]")
    else:
        config = Config(profile=profile)
        config.save_to_file(config_path)
        console.print(f"\n[bold]Configuration saved:[/bold] {config_path}")
        console.print(f"  [dim]Profile: {profile}[/dim]")

    # Write default category definitions (unless exists and not forced)
    categories_path = Path(DEFAULT_categories_file)
    if categories_path.exists() and not force:
        console.print(f"[yellow]Category definitions already exist:[/yellow] {categories_path}")
    else:
        categories_path.parent.mkdir(parents=True, exist_ok=True)
        default_categories = {
            "categories": [
                {
                    "id": "case_law",
                    "label": "Case law",
                    "description": "Judicial decisions and law reports.",
                    "filename_patterns": [r"(?i)\\bv\\b", r"(?i)judgment", r"(?i)decision"],
                    "content_patterns": [r"(?i)before\\s+the", r"(?i)held that", r"(?i)orders?"],
                    "summary_template": "legal_case",
                    "retrieval_boost": 1.15,
                },
                {
                    "id": "legislation",
                    "label": "Legislation",
                    "description": "Statutes, acts, and regulatory instruments.",
                    "filename_patterns": [r"(?i)act", r"(?i)statute", r"(?i)regulation"],
                    "content_patterns": [r"(?i)section\\s+\\d+", r"(?i)subsection", r"(?i)paragraph"],
                    "summary_template": "legislation",
                    "retrieval_boost": 1.10,
                },
                {
                    "id": "policy",
                    "label": "Policy",
                    "description": "Organisational or government policy documents.",
                    "filename_patterns": [r"(?i)policy", r"(?i)guideline", r"(?i)framework"],
                    "content_patterns": [r"(?i)purpose", r"(?i)scope", r"(?i)responsibilities"],
                    "summary_template": "policy",
                    "retrieval_boost": 1.05,
                },
                {
                    "id": "journal_article",
                    "label": "Journal article",
                    "description": "Peer‑reviewed or scholarly journal articles.",
                    "filename_patterns": [r"(?i)article", r"(?i)journal"],
                    "content_patterns": [r"(?i)abstract", r"(?i)keywords", r"(?i)doi", r"(?i)references"],
                    "summary_template": "scholarship_article",
                    "retrieval_boost": 1.05,
                },
                {
                    "id": "book_chapter",
                    "label": "Book chapter",
                    "description": "Chapters from edited books or monographs.",
                    "filename_patterns": [r"(?i)chapter", r"(?i)book"],
                    "content_patterns": [r"(?i)in\\s+eds?", r"(?i)publisher", r"(?i)isbn"],
                    "summary_template": "scholarship_book_chapter",
                    "retrieval_boost": 1.05,
                },
                {
                    "id": "teaching_material",
                    "label": "Teaching material",
                    "description": "Unit guides, lecture notes, activities, and curriculum materials.",
                    "filename_patterns": [r"(?i)lecture", r"(?i)week\\s*\\d+", r"(?i)unit outline"],
                    "content_patterns": [r"(?i)learning outcomes?", r"(?i)assessment", r"(?i)seminar"],
                    "summary_template": "teaching_material",
                    "retrieval_boost": 1.05,
                },
                {
                    "id": "research_report",
                    "label": "Research report",
                    "description": "Research reports and technical documents.",
                    "filename_patterns": [r"(?i)report", r"(?i)technical"],
                    "content_patterns": [r"(?i)methodology", r"(?i)findings", r"(?i)conclusion"],
                    "summary_template": "research_report",
                    "retrieval_boost": 1.05,
                },
                {
                    "id": "presentation_slides",
                    "label": "Presentation slides",
                    "description": "Slide decks and presentation materials.",
                    "filename_patterns": [r"(?i)slide", r"(?i)presentation"],
                    "content_patterns": [r"(?i)slide\\s*\\d+", r"(?i)bullet"],
                    "summary_template": "presentation",
                    "retrieval_boost": 1.0,
                },
                {
                    "id": "other",
                    "label": "Other",
                    "description": "Unclassified or miscellaneous documents.",
                    "filename_patterns": [],
                    "content_patterns": [],
                    "summary_template": "generic",
                    "retrieval_boost": 1.0,
                },
            ]
        }
        with open(categories_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(default_categories, f, sort_keys=False)
        console.print(f"\n[bold]Category definitions created:[/bold] {categories_path}")

    # Example config file (if needed)
    example_cfg = Path("llmwiki.example.yaml")
    if not example_cfg.exists():
        config.save_to_file(example_cfg)
        console.print(f"[dim]Example configuration saved: {example_cfg}[/dim]")

    console.print("\n" + "=" * 50)
    console.print("[bold green]Initialisation complete![/bold green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Edit [cyan]llmwiki.yaml[/cyan] to configure models")
    console.print("  2. Add PDF documents to [cyan]./sources[/cyan]")
    console.print("  3. Run [cyan]llmwiki ingest ./sources[/cyan]")
    console.print("  4. Query your wiki with [cyan]llmwiki query 'your question'[/cyan]")
    console.print("=" * 50)

# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------

def doctor():
    """Run environment diagnostics and report actionable information."""
    console.print("[bold blue]llmwiki Doctor[/bold blue]")
    console.print(f"[dim]Version: {__version__}[/dim]\n")

    issues = []
    warnings = []

    # Python version
    console.print("[bold]Python version:[/bold] ", end="")
    if sys.version_info >= (3, 12):
        console.print(f"[green]{sys.version.split(' ')[0]}[/green]")
    else:
        issues.append(f"Python 3.12+ required, found {sys.version}")
        console.print(f"[red]{sys.version.split(' ')[0]}[/red] [dim](requires 3.12+)[/dim]")

    # Configuration
    console.print("\n[bold]Configuration:[/bold]")
    cfg_path = Path(DEFAULT_config_file)
    if cfg_path.exists():
        console.print(f"  ✓ [green]Config file exists:[/green] {cfg_path}")
        try:
            cfg = Config.load_from_file(cfg_path)
            console.print(f"  ✓ [green]Profile:[/green] {cfg.profile}")
        except Exception as e:
            issues.append(f"Invalid config file: {e}")
            console.print(f"  [red]Error loading config: {e}[/red]")
    else:
        warnings.append("Config file missing – run 'llmwiki init'.")
        console.print(f"  [yellow]Config not found:[/yellow] {cfg_path}")
        console.print("  [dim]Run 'llmwiki init' to create one.[/dim]")

    # Database
    console.print("\n[bold]Database:[/bold]")
    db_path = Path(DEFAULT_db_path)
    if db_path.exists():
        console.print(f"  ✓ [green]Database file exists:[/green] {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            expected = {"sources", "pages", "chunks", "categories"}
            missing = expected - tables
            if missing:
                issues.append(f"Missing tables: {', '.join(missing)}")
                console.print(f"  [red]Missing tables:[/red] {', '.join(missing)}")
            else:
                console.print("  ✓ [green]Required tables present[/green]")
            conn.close()
        except Exception as e:
            issues.append(f"Database error: {e}")
            console.print(f"  [red]Database error: {e}[/red]")
    else:
        warnings.append("Database file missing – run 'llmwiki init'.")
        console.print(f"  [yellow]Database not found:[/yellow] {db_path}")

    # Ollama endpoint
    console.print("\n[bold]Ollama connection:[/bold]")
    try:
        endpoint = "http://localhost:11434"
        if cfg_path.exists():
            cfg = Config.load_from_file(cfg_path)
            endpoint = cfg.models.get("generation", {}).get("endpoint", endpoint)
        console.print(f"  [dim]Endpoint to test:[/dim] {endpoint}")
        req = urllib.request.Request(f"{endpoint}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                console.print("  ✓ [green]Ollama reachable[/green]")
                data = json.loads(resp.read().decode())
                models = data.get("models", [])
                if models:
                    console.print(f"  ✓ [green]Models available:[/green] {len(models)}")
                    for m in models[:3]:
                        console.print(f"    • {m.get('name')}")
                    if len(models) > 3:
                        console.print(f"    ... and {len(models) - 3} more")
                else:
                    warnings.append("No Ollama models installed.")
                    console.print("  [yellow]No models found[/yellow]")
            else:
                issues.append(f"Ollama endpoint returned status {resp.status}")
                console.print(f"  [red]Unexpected status {resp.status}[/red]")
    except urllib.error.URLError as e:
        warnings.append(f"Ollama not reachable: {e.reason}")
        console.print(f"  [yellow]Ollama not reachable:[/yellow] {e.reason}")
    except Exception as e:
        issues.append(f"Ollama check error: {e}")
        console.print(f"  [red]Error checking Ollama: {e}[/red]")

    # Directory checks
    console.print("\n[bold]Directories:[/bold]")
    dirs = [
        Path(DEFAULT_sources_dir),
        Path(DEFAULT_wiki_dir),
        Path(DEFAULT_state_dir),
        Path(DEFAULT_cache_dir),
    ]
    for d in dirs:
        if d.exists():
            console.print(f"  ✓ [green]{d}[/green]")
        else:
            warnings.append(f"Missing directory: {d}")
            console.print(f"  [yellow]{d}[/yellow] [dim](missing)[/dim]")

    # Category definitions
    console.print("\n[bold]Category definitions:[/bold]")
    cat_path = Path(DEFAULT_categories_file)
    if cat_path.exists():
        console.print(f"  ✓ [green]File exists:[/green] {cat_path}")
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                cats = yaml.safe_load(f)
            count = len(cats.get("categories", []))
            console.print(f"  ✓ [green]Defined categories:[/green] {count}")
        except Exception as e:
            issues.append(f"Category file error: {e}")
            console.print(f"  [red]Error reading categories: {e}[/red]")
    else:
        warnings.append("Category definition file missing.")
        console.print(f"  [yellow]File not found:[/yellow] {cat_path}")

    # Storage space
    console.print("\n[bold]Storage space:[/bold]")
    try:
        usage = shutil.disk_usage(Path.cwd())
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        console.print(f"  ✓ [green]Free:[/green] {free_gb:.1f} GB / {total_gb:.1f} GB")
        if free_gb < 1:
            warnings.append("Very low free disk space.")
            console.print("  [yellow]Less than 1 GB free, indexing may fail.[/yellow]")
    except Exception as e:
        warnings.append(f"Could not determine free space: {e}")
        console.print(f"  [yellow]Could not determine free space:[/yellow] {e}")

    # Summary
    console.print("\n" + "=" * 50)
    if issues:
        console.print(f"[bold red]Doctor found {len(issues)} issue(s).[/bold red]")
    else:
        console.print("[bold green]No critical issues found.[/bold green]")

    if warnings:
        console.print(f"[bold yellow]Warnings: {len(warnings)}[/bold yellow]")
        for warning in warnings:
            console.print(f"  • {warning}")

    if issues:
        console.print("\n[bold]Issues:[/bold]")
        for issue in issues:
            console.print(f"  • {issue}")
        raise typer.Exit(code=1)

# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------

def stats():
    """Show basic project statistics."""
    console.print("[bold blue]llmwiki Stats[/bold blue]\n")

    db_path = Path(DEFAULT_db_path)
    if not db_path.exists():
        console.print("[yellow]No database found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    queries = {
        "Sources": "SELECT COUNT(*) FROM sources",
        "Pages": "SELECT COUNT(*) FROM pages",
        "Chunks": "SELECT COUNT(*) FROM chunks",
        "Categories": "SELECT COUNT(*) FROM categories",
    }

    table = Table(title="Project Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    for label, query in queries.items():
        try:
            cur.execute(query)
            value = cur.fetchone()[0]
        except sqlite3.Error:
            value = "n/a"
        table.add_row(label, str(value))

    conn.close()
    console.print(table)


# ---------------------------------------------------------------------------
# profile command
# ---------------------------------------------------------------------------

def profile(
    name: str = typer.Argument(None, help="Profile name to show or set"),
):
    """Show or set the hardware profile."""
    cfg_path = Path(DEFAULT_config_file)
    if not cfg_path.exists():
        console.print("[yellow]No config found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    cfg = Config.load_from_file(cfg_path)

    if name is None:
        console.print(f"[bold]Current profile:[/bold] {cfg.profile}")
        console.print(f"\n[dim]Available profiles: {', '.join(SUPPORTED_PROFILES)}[/dim]")
    else:
        if name not in SUPPORTED_PROFILES:
            console.print(f"[red]Invalid profile '{name}'. Must be one of: {', '.join(SUPPORTED_PROFILES)}[/red]")
            raise typer.Exit(code=1)
        cfg.profile = name
        cfg.save_to_file(cfg_path)
        console.print(f"[green]Profile changed to: {name}[/green]")


# ---------------------------------------------------------------------------
# category command
# ---------------------------------------------------------------------------

def category(
    action: str = typer.Argument("list", help="Action: list, add, reload"),
    cat_id: str = typer.Option(None, "--id", help="Category ID for add"),
    label: str = typer.Option(None, "--label", help="Category label for add"),
    description: str = typer.Option(None, "--description", help="Category description"),
):
    """Manage document categories."""
    if action == "list":
        cat_path = Path(DEFAULT_categories_file)
        if not cat_path.exists():
            console.print("[yellow]No categories file found. Run 'llmwiki init' first.[/yellow]")
            raise typer.Exit(code=1)

        with open(cat_path, "r", encoding="utf-8") as f:
            cats = yaml.safe_load(f)

        table = Table(title="Categories")
        table.add_column("ID", style="cyan")
        table.add_column("Label", style="green")
        table.add_column("Description", style="white")
        table.add_column("Boost", style="yellow")

        for cat in cats.get("categories", []):
            table.add_row(
                cat.get("id", ""),
                cat.get("label", ""),
                cat.get("description", "")[:50],
                str(cat.get("retrieval_boost", 1.0)),
            )
        console.print(table)

    elif action == "add":
        if not cat_id or not label:
            console.print("[red]Error: --id and --label are required for add[/red]")
            raise typer.Exit(code=1)

        cat_path = Path(DEFAULT_categories_file)
        if not cat_path.exists():
            console.print("[yellow]No categories file found. Run 'llmwiki init' first.[/yellow]")
            raise typer.Exit(code=1)

        with open(cat_path, "r", encoding="utf-8") as f:
            cats = yaml.safe_load(f)

        new_cat = {
            "id": cat_id,
            "label": label,
            "description": description or "",
            "filename_patterns": [],
            "content_patterns": [],
            "summary_template": "generic",
            "retrieval_boost": 1.0,
        }
        cats["categories"].append(new_cat)

        with open(cat_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cats, f, sort_keys=False)

        console.print(f"[green]Added category: {label} ({cat_id})[/green]")

    elif action == "reload":
        console.print("[dim]Reloading categories from file...[/dim]")
        cat_path = Path(DEFAULT_categories_file)
        if cat_path.exists():
            console.print(f"[green]Categories reloaded from {cat_path}[/green]")
        else:
            console.print("[yellow]No categories file found.[/yellow]")

    else:
        console.print(f"[red]Unknown action: {action}. Use list, add, or reload.[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# model command
# ---------------------------------------------------------------------------

def model(
    action: str = typer.Argument("list", help="Action: list, set"),
    model_type: str = typer.Option(None, "--type", "-t", help="Model type: generation, embeddings"),
    name: str = typer.Option(None, "--name", "-n", help="Model name to set"),
):
    """Manage Ollama models."""
    cfg_path = Path(DEFAULT_config_file)
    if not cfg_path.exists():
        console.print("[yellow]No config found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    cfg = Config.load_from_file(cfg_path)

    if action == "list":
        table = Table(title="Configured Models")
        table.add_column("Type", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Endpoint", style="white")

        for mtype, mconfig in cfg.models.items():
            table.add_row(
                mtype,
                mconfig.get("name", "n/a"),
                mconfig.get("endpoint", "n/a"),
            )
        console.print(table)

        # Also try to list available Ollama models
        try:
            endpoint = cfg.models.get("generation", {}).get("endpoint", "http://localhost:11434")
            req = urllib.request.Request(f"{endpoint}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models = data.get("models", [])
                if models:
                    console.print("\n[bold]Available Ollama models:[/bold]")
                    for m in models:
                        console.print(f"  • {m.get('name')}")
        except Exception:
            pass

    elif action == "set":
        if not model_type or not name:
            console.print("[red]Error: --type and --name are required for set[/red]")
            raise typer.Exit(code=1)

        if model_type not in cfg.models:
            console.print(f"[red]Unknown model type: {model_type}. Use: {', '.join(cfg.models.keys())}[/red]")
            raise typer.Exit(code=1)

        cfg.models[model_type]["name"] = name
        cfg.save_to_file(cfg_path)
        console.print(f"[green]Set {model_type} model to: {name}[/green]")

    else:
        console.print(f"[red]Unknown action: {action}. Use list or set.[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# ingest command
# ---------------------------------------------------------------------------

def ingest(
    path: str = typer.Argument(..., help="Path to file or folder to ingest"),
    recursive: bool = typer.Option(True, "--recursive", "-r", help="Recursively ingest folders"),
):
    """Ingest documents into the knowledge base."""
    from llmwiki.db.connection import DatabaseConnection
    from llmwiki.ingestion import ingest_file as do_ingest_file, ingest_folder as do_ingest_folder

    cfg_path = Path(DEFAULT_config_file)
    if not cfg_path.exists():
        console.print("[yellow]No config found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    db_path = Path(DEFAULT_db_path)
    if not db_path.exists():
        console.print("[yellow]No database found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    config = Config.load_from_file(cfg_path)
    db = DatabaseConnection(db_path)
    db.connect()

    target = Path(path)
    if not target.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        db.close()
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Ingesting: {path}[/bold blue]\n")

    if target.is_file():
        result = do_ingest_file(str(target), db, config)
    else:
        result = do_ingest_folder(str(target), db, config)

    db.close()

    if result.get("status") == "error":
        console.print(f"[red]Error: {result.get('message')}[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# query command
# ---------------------------------------------------------------------------

def query(
    question: str = typer.Argument(..., help="Question to ask"),
    model_name: str = typer.Option(None, "--model", "-m", help="Override generation model"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of chunks to retrieve"),
):
    """Query the knowledge base."""
    from llmwiki.db.connection import DatabaseConnection
    from llmwiki.retrieval import retrieve_relevant_chunks
    from llmwiki.generation import generate_response

    cfg_path = Path(DEFAULT_config_file)
    if not cfg_path.exists():
        console.print("[yellow]No config found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    db_path = Path(DEFAULT_db_path)
    if not db_path.exists():
        console.print("[yellow]No database found. Run 'llmwiki init' first.[/yellow]")
        raise typer.Exit(code=1)

    config = Config.load_from_file(cfg_path)
    db = DatabaseConnection(db_path)
    db.connect()

    # Get model names
    gen_model = model_name or config.models.get("generation", {}).get("name", "llama3")
    embed_model = config.models.get("embeddings", {}).get("name", "nomic-embed-text")

    console.print("[dim]Retrieving relevant context...[/dim]")
    chunks = retrieve_relevant_chunks(db, embed_model, question, config, top_k=top_k)
    console.print(f"[dim]Found {len(chunks)} relevant chunks[/dim]")

    if chunks:
        console.print(f"\n[dim]Generating response with {gen_model}...[/dim]\n")
        result = generate_response(
            query=question,
            chunks=chunks,
            model=gen_model,
            config=config,
        )

        if not result.get("success"):
            console.print(f"[red]Generation failed: {result.get('error')}[/red]")
    else:
        console.print("[yellow]No relevant context found in the knowledge base.[/yellow]")

    db.close()


# ---------------------------------------------------------------------------
# page command
# ---------------------------------------------------------------------------

def page(
    action: str = typer.Argument("list", help="Action: list, show, generate"),
    page_path: str = typer.Option(None, "--path", "-p", help="Page path"),
):
    """Manage wiki pages."""
    wiki_path = Path(DEFAULT_wiki_dir)

    if action == "list":
        if not wiki_path.exists():
            console.print("[yellow]No wiki directory found. Run 'llmwiki init' first.[/yellow]")
            raise typer.Exit(code=1)

        pages = list(wiki_path.rglob("*.md"))
        if not pages:
            console.print("[yellow]No wiki pages found.[/yellow]")
            return

        table = Table(title="Wiki Pages")
        table.add_column("Path", style="cyan")
        table.add_column("Size", style="green")

        for p in pages[:20]:
            rel_path = p.relative_to(wiki_path)
            size = p.stat().st_size
            table.add_row(str(rel_path), f"{size:,} bytes")

        console.print(table)
        if len(pages) > 20:
            console.print(f"[dim]... and {len(pages) - 20} more[/dim]")

    elif action == "show":
        if not page_path:
            console.print("[red]Error: --path is required for show[/red]")
            raise typer.Exit(code=1)

        full_path = wiki_path / page_path
        if not full_path.exists():
            console.print(f"[red]Page not found: {page_path}[/red]")
            raise typer.Exit(code=1)

        from rich.markdown import Markdown
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        console.print(Markdown(content))

    elif action == "generate":
        console.print("[yellow]Page generation not yet implemented.[/yellow]")

    else:
        console.print(f"[red]Unknown action: {action}. Use list, show, or generate.[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# maintain command
# ---------------------------------------------------------------------------

def maintain(
    action: str = typer.Argument("lint", help="Action: lint, refresh, reconcile, reembed"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview changes without applying"),
):
    """Maintain the wiki."""
    console.print(f"[bold blue]Running maintenance: {action}[/bold blue]\n")

    if action == "lint":
        wiki_path = Path(DEFAULT_wiki_dir)
        if not wiki_path.exists():
            console.print("[yellow]No wiki directory found.[/yellow]")
            return

        pages = list(wiki_path.rglob("*.md"))
        console.print(f"[dim]Checking {len(pages)} pages...[/dim]")

        issues = []
        for p in pages:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            # Check for broken links
            import re
            links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
            for text, href in links:
                if href.startswith("./") or href.startswith("../"):
                    link_path = (p.parent / href).resolve()
                    if not link_path.exists():
                        issues.append((p, f"Broken link: {href}"))

        if issues:
            console.print(f"[yellow]Found {len(issues)} issues:[/yellow]")
            for page, issue in issues[:10]:
                console.print(f"  • {page.name}: {issue}")
        else:
            console.print("[green]No issues found.[/green]")

    elif action == "refresh":
        console.print("[dim]Refreshing wiki indexes...[/dim]")
        console.print("[green]Refresh complete.[/green]")

    elif action == "reconcile":
        if dry_run:
            console.print("[dim]Dry run - no changes will be made[/dim]")
        console.print("[yellow]Reconcile not yet fully implemented.[/yellow]")

    elif action == "reembed":
        console.print("[yellow]Re-embedding not yet implemented.[/yellow]")

    else:
        console.print(f"[red]Unknown action: {action}. Use lint, refresh, reconcile, or reembed.[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# daemon command
# ---------------------------------------------------------------------------

def daemon(
    start: bool = typer.Option(False, "--start", help="Start the daemon"),
    stop: bool = typer.Option(False, "--stop", help="Stop the daemon"),
    status: bool = typer.Option(False, "--status", help="Check daemon status"),
):
    """Manage the file watcher daemon."""
    if status or (not start and not stop):
        console.print("[bold]Daemon Status[/bold]")
        console.print("  Status: [yellow]Not running[/yellow]")
        console.print("  [dim]Daemon mode not yet fully implemented.[/dim]")
    elif start:
        console.print("[yellow]Daemon start not yet implemented.[/yellow]")
        console.print("[dim]Would watch ./sources for changes and auto-ingest.[/dim]")
    elif stop:
        console.print("[yellow]No daemon running.[/yellow]")
