"""Interactive TUI for llmwiki - Contextual-style interface."""
from typing import List, Dict, Any, Optional
from pathlib import Path
import typer
import ollama
import os
import sys
import json
import time
import shutil
import re
import base64
import io
import urllib.request
import urllib.error
import subprocess
import tempfile
import pyfiglet
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.text import Text
from rich.rule import Rule
from rich.spinner import Spinner
from rich.live import Live
from rich.console import Group
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.progress import track
from pick import pick
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
from prompt_toolkit.application import get_app

from llmwiki.db.connection import DatabaseConnection
from llmwiki.config import Config
from llmwiki.constants import (
    DEFAULT_config_file,
    DEFAULT_categories_file,
    DEFAULT_sources_dir,
    DEFAULT_wiki_dir,
    DEFAULT_state_dir,
    DEFAULT_cache_dir,
    DEFAULT_db_path,
)

console = Console()
app = typer.Typer(help="Interactive llmwiki TUI")

# --- Multiline input setup ---
session = PromptSession()
bindings = KeyBindings()


@bindings.add("c-d")
def _(event):
    """Exit when Ctrl+D is pressed."""
    event.app.exit()


@bindings.add("escape", "enter")
def _(event):
    """Submit on Meta+Enter or Esc+Enter."""
    event.current_buffer.validate_and_handle()


def get_multiline_input() -> str:
    """Get multi-line input from user."""
    return session.prompt(
        "> ",
        placeholder="Enter your prompt. Press [Meta+Enter] or [Esc]+[Enter] to submit.",
        multiline=True,
        key_bindings=bindings,
        prompt_continuation="... ",
    )


# --- Banner and Help ---
def print_banner():
    """Print colorful figlet banner."""
    console.print("\n\n")
    # Use "LLMWiki CLI" for the figlet header
    banner_text = pyfiglet.figlet_format("LLMWiki CLI", font="4Max", width=int(console.width * 0.9))
    lines = banner_text.split("\n")
    rainbow = ["bold bright_red", "bold bright_yellow", "bold bright_green", "bold bright_cyan", "bold bright_blue", "bold bright_magenta"]
    for i, line in enumerate(lines):
        console.print(Align.center(f"[{rainbow[i % len(rainbow)]}]{line}[/{rainbow[i % len(rainbow)]}]"))
    console.print()
    # Updated tagline with copyright
    tagline = "An LLMWiki CLI Powered by Ollama ©Stafford Lumsden April 2026 v.1.0"
    console.print(
        Align.center(
            Text(tagline, style="white"),
        ),
        highlight=False,
    )
    console.print("\n\n")


def print_help():
    """Print help menu."""
    table = Table(expand=True, padding=(0, 2))
    table.add_column("Command", style="cyan", width=20)
    table.add_column("Description", style="white")

    commands = [
        ("/help", "Show this help message"),
        ("/stats", "Show session statistics"),
        ("/ingest", "Ingest documents via file picker"),
        ("/category", "Manage categories"),
        ("/switch chat|embed", "Switch chat or embedding model"),
        ("/set cold|balanced|warm", "Apply parameter preset"),
        ("/set parameter <name> <value>", "Set Ollama parameter"),
        ("/chunks N", "Set retrieval chunk count (placeholder)"),
        ("/readme", "View README.md"),
        ("/exit | /quit", "Exit interactive mode"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(Panel(table, title="[bold]Available Commands[/bold]", border_style="blue"))


def print_stats(
    start_time: float,
    chat_model: str,
    embed_model: str,
    turns: int,
    input_tokens: int,
    output_tokens: int,
    params: Dict[str, Any],
    sources_count: int,
):
    """Print session statistics."""
    elapsed = time.time() - start_time
    stats_text = f"""Session Time: {elapsed:.1f}s
Turns: {turns}
Input Tokens: {input_tokens}
Output Tokens: {output_tokens}
Sources: {sources_count}
Chat Model: {chat_model}
Embed Model: {embed_model}
"""
    console.print(Panel(stats_text, title="[bold green]Session Stats[/bold green]", border_style="green"))


# --- Model selection ---
def select_chat_model() -> Optional[str]:
    """Select a chat model from available Ollama models."""
    try:
        models_info = ollama.list()
        available = [m["model"] for m in models_info.get("models", []) if "embed" not in m["model"].lower()]
        if not available:
            console.print(Panel("[red]No chat models found. Run 'ollama pull <model>'.[/red]"))
            return None
        options = available + ["Cancel"]
        choice, _ = pick(options, "Select Chat Model", indicator=">")
        return choice if choice != "Cancel" else None
    except Exception as e:
        console.print(Panel(f"[red]Error: {e}[/red]"))
        return None


def select_embedding_model() -> Optional[str]:
    """Select an embedding model."""
    try:
        models_info = ollama.list()
        available = [m["model"] for m in models_info.get("models", []) if "embed" in m["model"].lower()]
        if not available:
            console.print(Panel("[red]No embedding models found. Run 'ollama pull nomic-embed-text'.[/red]"))
            return None
        options = available + ["Cancel"]
        choice, _ = pick(options, "Select Embedding Model", indicator=">")
        return choice if choice != "Cancel" else None
    except Exception as e:
        console.print(Panel(f"[red]Error: {e}[/red]"))
        return None


# --- Parameter handling ---
OLLAMA_PARAMETER_PRESETS = {
    "cold": {"temperature": 0.35, "top_p": 0.85, "num_predict": 1024},
    "balanced": {"temperature": 0.7, "top_p": 0.97, "num_predict": 768},
    "warm": {"temperature": 0.95, "top_p": 0.95, "num_predict": 768},
}


def apply_parameter_preset(params: Dict[str, Any], preset: str):
    """Apply a parameter preset."""
    if preset in OLLAMA_PARAMETER_PRESETS:
        params.update(OLLAMA_PARAMETER_PRESETS[preset])
        console.print(Panel(f"[green]Applied preset: {preset}[/green]"))
    else:
        console.print(Panel(f"[red]Unknown preset: {preset}[/red]"))


def set_parameter(params: Dict[str, Any], name: str, value: str):
    """Set a single parameter."""
    try:
        params[name] = float(value) if "." in value else int(value)
        console.print(Panel(f"[green]Set {name} = {params[name]}[/green]"))
    except ValueError:
        console.print(Panel(f"[red]Invalid value: {value}[/red]"))


# --- Category management ---
def get_categories(db: DatabaseConnection) -> List[Dict]:
    """Get categories from database."""
    try:
        return db.fetchall("SELECT * FROM categories WHERE is_active = 1")
    except Exception:
        return []


def handle_category_management(db: DatabaseConnection):
    """Interactive category management."""
    while True:
        options = ["List categories", "Add category (stub)", "Back"]
        choice, _ = pick(options, "Category Management", indicator=">")
        if choice == "Back":
            return
        elif choice == "List categories":
            cats = get_categories(db)
            if not cats:
                console.print(Panel("[yellow]No categories found.[/yellow]"))
                continue
            table = Table(title="Categories")
            table.add_column("ID", style="cyan")
            table.add_column("Label", style="green")
            table.add_column("Description", style="white")
            for cat in cats:
                table.add_row(str(cat["id"]), cat["label"], cat.get("description", "")[:40])
            console.print(table)
        elif choice == "Add category (stub)":
            console.print(Panel("[yellow]Category addition not yet implemented.[/yellow]"))


# --- Ingestion ---
def get_sources_count(db: DatabaseConnection) -> int:
    """Get count of sources."""
    try:
        row = db.fetchone("SELECT COUNT(*) as cnt FROM sources")
        return row["cnt"] if row else 0
    except Exception:
        return 0


def handle_ingest(db: DatabaseConnection, config: Config):
    """Interactive document ingestion."""
    console.print(Panel("[bold]Ingest Documents[/bold]"))
    options = ["Select file", "Select folder", "Back"]
    choice, _ = pick(options, "Ingestion Mode", indicator=">")
    if choice == "Back":
        return
    elif choice == "Select file":
        # Simple file picker
        path = Prompt.ask("Enter file path")
        if path and os.path.exists(path):
            console.print(Panel(f"[green]Ingesting: {path}[/green]"))
            # Stub: In real impl, call ingestion pipeline
            console.print("[dim]Ingestion stub - full pipeline not yet connected.[/dim]")
        else:
            console.print(Panel("[red]File not found.[/red]"))
    elif choice == "Select folder":
        path = Prompt.ask("Enter folder path")
        if path and os.path.isdir(path):
            console.print(Panel(f"[green]Ingesting folder: {path}[/green]"))
            console.print("[dim]Folder ingestion stub.[/dim]")
        else:
            console.print(Panel("[red]Folder not found.[/red]"))


# --- Retrieval ---
def retrieve_relevant_chunks(db: DatabaseConnection, embed_model: str, query: str, top_k: int = 5) -> List[Dict]:
    """Retrieve relevant chunks using embeddings (stub)."""
    # Stub: In real impl, embed query and search embeddings table
    try:
        # Simple FTS fallback
        rows = db.fetchall("SELECT chunks.id, chunks.text FROM chunks JOIN chunk_fts ON chunks.id = chunk_fts.rowid WHERE chunk_fts MATCH ? LIMIT ?", (query, top_k))
        return [{"text": r["text"], "similarity": 1.0} for r in rows]
    except Exception:
        return []


# --- Chat loop ---
def render_response(response_text: str, citations: Optional[List[Dict]] = None):
    """Render response with citations."""
    md = Markdown(response_text)
    console.print(md)
    if citations:
        table = Table(title="Citations")
        table.add_column("Source", style="cyan")
        table.add_column("Text", style="white")
        for cit in citations[:5]:
            table.add_row(str(cit.get("id", "")), cit.get("text", "")[:60] + "...")
        console.print(table)


def handle_switch_model(chat_model: str, embed_model: str):
    """Switch models interactively."""
    choice, _ = pick(["chat", "embed"], "Switch which model?", indicator=">")
    if choice == "chat":
        new_model = select_chat_model()
        if new_model:
            chat_model = new_model
            console.print(Panel(f"[green]Chat model switched to: {chat_model}[/green]"))
    else:
        new_model = select_embedding_model()
        if new_model:
            embed_model = new_model
            console.print(Panel(f"[green]Embedding model switched to: {embed_model}[/green]"))
    return chat_model, embed_model


def chat_loop(db: DatabaseConnection, config: Config, chat_model: str, embed_model: str):
    """Main chat loop."""
    start_time = time.time()
    turns = 0
    input_tokens = 0
    output_tokens = 0
    params: Dict[str, Any] = {}
    sources_count = get_sources_count(db)

    console.print(Rule("[bold magenta]Interactive llmwiki Session[/bold magenta]"))
    print_help()

    while True:
        user_msg = get_multiline_input()
        if not user_msg.strip():
            continue

        cmd = user_msg.strip().lower()

        if cmd in ("/exit", "/quit"):
            console.print(Panel("[bold red]Exiting.[/bold red]"))
            break
        elif cmd == "/help":
            print_help()
        elif cmd == "/stats":
            print_stats(start_time, chat_model, embed_model, turns, input_tokens, output_tokens, params, sources_count)
        elif cmd.startswith("/switch"):
            chat_model, embed_model = handle_switch_model(chat_model, embed_model)
        elif cmd.startswith("/set "):
            parts = cmd.split()
            if len(parts) == 2 and parts[1] in OLLAMA_PARAMETER_PRESETS:
                apply_parameter_preset(params, parts[1])
            elif len(parts) == 4 and parts[1] == "parameter":
                set_parameter(params, parts[2], parts[3])
            else:
                console.print(Panel("[red]Usage: /set cold|balanced|warm or /set parameter <name> <value>[/red]"))
        elif cmd.startswith("/category"):
            handle_category_management(db)
        elif cmd.startswith("/ingest"):
            handle_ingest(db, config)
            sources_count = get_sources_count(db)
        elif cmd.startswith("/chunks"):
            console.print(Panel("[yellow]/chunks not yet implemented.[/yellow]"))
        elif cmd == "/readme":
            readme_path = Path("README.md")
            if readme_path.exists():
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()
                console.print(Panel(Markdown(content), title="llmwiki README", border_style="cyan", expand=False))
            else:
                console.print(Panel("[red]README.md not found.[/red]"))
        else:
            # Query
            turns += 1
            input_tokens += len(user_msg.split())

            # Retrieve context
            chunks = retrieve_relevant_chunks(db, embed_model, user_msg, top_k=5)
            context = "\n\n".join([c["text"] for c in chunks])

            # Generate response (stub - just echo for now)
            console.print(Panel("[dim]Query processing stub - full generation not yet connected.[/dim]"))
            console.print(f"[yellow]Query: {user_msg}[/yellow]")
            console.print(f"[dim]Context chunks: {len(chunks)}[/dim]")

            # In real impl: call Ollama with context and user_msg
            # For now, simulate response
            response = f"Response to: {user_msg}\n\n(This is a stub response. Full Ollama generation will be connected in the next iteration.)"
            render_response(response, [{"id": i, "text": c["text"]} for i, c in enumerate(chunks)])

            output_tokens += len(response.split())


def main_interactive():
    """Entry point for interactive mode."""
    cfg_path = Path(DEFAULT_config_file)
    if cfg_path.exists():
        config = Config.load_from_file(cfg_path)
    else:
        console.print(Panel("[red]No config found. Run 'llmwiki init' first.[/red]"))
        raise typer.Exit(code=1)

    db_path = Path(DEFAULT_db_path)
    if not db_path.exists():
        console.print(Panel("[red]No database found. Run 'llmwiki init' first.[/red]"))
        raise typer.Exit(code=1)

    db = DatabaseConnection(db_path)
    db.connect()

    # Select models
    chat_model = select_chat_model() or config.models.get("generation", {}).get("name", "llama3")
    embed_model = select_embedding_model() or config.models.get("embeddings", {}).get("name", "nomic-embed-text")

    print_banner()
    chat_loop(db, config, chat_model, embed_model)
    db.close()


@app.command(name="interactive")
def interactive_cmd():
    """Run the interactive llmwiki TUI."""
    main_interactive()
