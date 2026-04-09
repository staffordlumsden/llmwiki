"""CLI command implementations for llmwiki.

This module registers subcommands with the Typer app defined in __main__.py.
It includes the core Phase 1 commands: init, doctor, and stats.
Later phases will add ingest, query, maintenance, etc.
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
app = typer.Typer(help="Portable Ollama-powered LLM Wiki with a Rich CLI")

# Import interactive command and register it with the main app
from llmwiki.interactive import interactive_cmd  # noqa: F401
app.command(name="interactive")(interactive_cmd)

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------

@app.command()
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

@app.command()
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

@app.command()
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
