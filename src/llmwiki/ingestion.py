"""Document ingestion pipeline for llmwiki."""

import hashlib
from pathlib import Path
from typing import List, Dict, Any
import ollama
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
import re

from llmwiki.db.connection import DatabaseConnection
from llmwiki.config import Config

console = Console()


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """Extract text from PDF with page numbers.
    
    Returns list of dicts with 'text' and 'page' keys.
    """
    from pypdf import PdfReader
    
    reader = PdfReader(str(pdf_path))
    pages = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages.append({
                "text": text,
                "page": i + 1  # 1-indexed
            })
    
    return pages


def chunk_text(text: str, page_number: int, config: Config) -> List[Dict[str, Any]]:
    """Chunk text respecting headings and page boundaries.
    
    Args:
        text: Text to chunk
        page_number: Source page number
        config: Configuration with chunking settings
        
    Returns:
        List of chunk dicts with 'text', 'page_start', 'page_end', 'chunk_index'
    """
    chunking_cfg = config.chunking
    target_chars = chunking_cfg.target_chars
    max_chars = chunking_cfg.max_chars
    overlap_chars = chunking_cfg.overlap_chars
    split_on_headings = chunking_cfg.split_on_headings
    
    chunks = []
    
    # Split on headings if enabled
    if split_on_headings:
        # Match markdown-style headings (##, ###, etc.)
        heading_pattern = r'\n(#+\s+.+?)\n'
        sections = re.split(heading_pattern, text)
        
        # Reconstruct sections with headings
        processed_sections = []
        i = 0
        while i < len(sections):
            if i + 1 < len(sections) and sections[i].startswith('#'):
                # This is a heading, combine with next section
                section_text = sections[i] + '\n' + (sections[i + 1] if i + 1 < len(sections) else '')
                processed_sections.append(section_text)
                i += 2
            elif sections[i].strip():
                processed_sections.append(sections[i])
                i += 1
            else:
                i += 1
    else:
        processed_sections = [text]
    
    # Chunk each section
    chunk_index = 0
    for section in processed_sections:
        if len(section) <= target_chars:
            # Section is small enough, use as-is
            if section.strip():
                chunks.append({
                    "text": section.strip(),
                    "page_start": page_number,
                    "page_end": page_number,
                    "chunk_index": chunk_index
                })
                chunk_index += 1
        else:
            # Need to split section further
            words = section.split()
            current_chunk = []
            current_length = 0
            
            for word in words:
                word_len = len(word) + 1  # +1 for space
                if current_length + word_len > max_chars and current_chunk:
                    # Flush current chunk
                    chunk_text = ' '.join(current_chunk)
                    if chunk_text.strip():
                        chunks.append({
                            "text": chunk_text.strip(),
                            "page_start": page_number,
                            "page_end": page_number,
                            "chunk_index": chunk_index
                        })
                        chunk_index += 1
                    
                    # Start new chunk with overlap
                    overlap_text = ' '.join(current_chunk[-(overlap_chars // 5):]) if current_chunk else ''
                    current_chunk = overlap_text.split() if overlap_text else []
                    current_length = len(overlap_text) if overlap_text else 0
                
                current_chunk.append(word)
                current_length += word_len
            
            # Flush remaining
            if current_chunk:
                chunk_text = ' '.join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        "text": chunk_text.strip(),
                        "page_start": page_number,
                        "page_end": page_number,
                        "chunk_index": chunk_index
                    })
                    chunk_index += 1
    
    return chunks


def generate_embeddings(texts: List[str], model: str, config: Config) -> List[List[float]]:
    """Generate embeddings for texts using Ollama.
    
    Args:
        texts: List of texts to embed
        model: Embedding model name
        config: Configuration
        
    Returns:
        List of embedding vectors
    """
    embeddings = []
    
    # Process each text individually (Ollama embeddings API accepts single prompts)
    for text in texts:
        try:
            response = ollama.embeddings(model=model, prompt=text)
            embeddings.append(response["embedding"])
        except Exception as e:
            console.print(f"[red]Error generating embedding: {e}[/red]")
            # Return zero vector for failed embeddings
            embeddings.append([0.0] * 768)  # Default dimension
    
    return embeddings


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def ingest_file(file_path: str, db: DatabaseConnection, config: Config) -> Dict[str, Any]:
    """Ingest a single file into the database.
    
    Args:
        file_path: Path to file to ingest
        db: Database connection
        config: Configuration
        
    Returns:
        Ingestion result dict with status and stats
    """
    path = Path(file_path)
    
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}
    
    # Check if file already ingested
    file_hash = compute_sha256(path)
    existing = db.fetchone("SELECT * FROM sources WHERE sha256 = ?", (file_hash,))
    
    if existing:
        console.print(f"[yellow]File already ingested: {path.name}[/yellow]")
        return {"status": "skipped", "message": "Already ingested"}
    
    # Create source record
    mime_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/plain"
    
    db.execute(
        "INSERT INTO sources (path, sha256, mime_type, status) VALUES (?, ?, ?, ?)",
        (str(path), file_hash, mime_type, "ingesting")
    )
    source_id = db.fetchone("SELECT last_insert_rowid() as id")["id"]
    
    # Create run and job records
    db.execute(
        "INSERT INTO runs (run_type, profile, status) VALUES (?, ?, ?)",
        ("ingestion", "default", "running")
    )
    run_id = db.fetchone("SELECT last_insert_rowid() as id")["id"]
    
    db.execute(
        "INSERT INTO jobs (run_id, job_type, target_path, status) VALUES (?, ?, ?, ?)",
        (run_id, "ingest_file", str(path), "running")
    )
    
    try:
        # Extract text based on file type
        if path.suffix.lower() == ".pdf":
            pages = extract_text_from_pdf(path)
        else:
            # Plain text fallback
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            pages = [{"text": text, "page": 1}]
        
        # Create source version
        db.execute(
            "INSERT INTO source_versions (source_id, sha256, page_count) VALUES (?, ?, ?)",
            (source_id, file_hash, len(pages))
        )
        source_version_id = db.fetchone("SELECT last_insert_rowid() as id")["id"]
        
        # Process pages and create chunks
        all_chunks = []
        all_texts = []
        chunk_metadata = []
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            extract_task = progress.add_task("Extracting and chunking...", total=len(pages))
            
            for page_data in pages:
                page_num = page_data["page"]
                page_text = page_data["text"]
                
                # Chunk the page text
                page_chunks = chunk_text(page_text, page_num, config)
                
                for chunk in page_chunks:
                    all_chunks.append((
                        source_version_id,
                        chunk["page_start"],
                        chunk["page_end"],
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["text"].lower(),  # normalized_text
                        len(chunk["text"]),
                        len(chunk["text"]) // 4  # rough token estimate
                    ))
                    all_texts.append(chunk["text"])
                    chunk_metadata.append(chunk)
                
                progress.update(extract_task, advance=1)
        
        # Insert chunks (FTS is handled by triggers in schema.sql)
        if all_chunks:
            db.executemany(
                """INSERT INTO chunks 
                   (source_version_id, page_start, page_end, chunk_index, text, normalized_text, char_count, token_estimate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                all_chunks
            )
            # Note: FTS index is automatically updated by triggers defined in schema.sql
            console.print(f"[dim]Inserted {len(all_chunks)} chunks (FTS updated via triggers)[/dim]")

        # Generate and store embeddings with progress
        embed_model = config.models["embeddings"]["name"]
        console.print(f"[dim]Generating embeddings with {embed_model}...[/dim]")
        
        embeddings_created = 0
        if all_texts:
            # Get chunk IDs for the inserted chunks (in order)
            chunk_rows = db.fetchall(
                "SELECT id FROM chunks WHERE source_version_id = ? ORDER BY chunk_index",
                (source_version_id,)
            )
            chunk_ids = [row["id"] for row in chunk_rows]
            
            # Progress for embedding generation
            embed_progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            )
            embed_data = []
            with embed_progress:
                embed_task = embed_progress.add_task("Embedding chunks", total=len(all_texts))
                for i, text in enumerate(all_texts):
                    try:
                        # Ollama embeddings API accepts a single prompt at a time
                        response = ollama.embeddings(model=embed_model, prompt=text)
                        embedding = response.get("embedding")
                    except Exception as e:
                        console.print(f"[red]Error generating embedding: {e}[/red]")
                        embedding = [0.0] * 768
                    
                    # Get the correct chunk_id for this text
                    chunk_id = chunk_ids[i] if i < len(chunk_ids) else chunk_ids[-1]
                    
                    import struct
                    vector_bytes = struct.pack(f'{len(embedding)}f', *embedding)
                    embed_data.append((
                        chunk_id,
                        embed_model,
                        len(embedding),
                        'float32',
                        vector_bytes
                    ))
                    embed_progress.update(embed_task, advance=1)
            
            if embed_data:
                db.executemany(
                    """INSERT INTO embeddings (chunk_id, model_alias, dims, dtype, vector_blob)
                       VALUES (?, ?, ?, ?, ?)""",
                    embed_data
                )
                embeddings_created = len(embed_data)
        
        # Update status
        db.execute(
            "UPDATE sources SET status = ? WHERE id = ?",
            ("ingested", source_id)
        )
        db.execute(
            "UPDATE jobs SET status = ?, completed_at = datetime('now') WHERE run_id = ?",
            ("completed", run_id)
        )
        db.execute(
            "UPDATE runs SET status = ?, ended_at = datetime('now') WHERE id = ?",
            ("completed", run_id)
        )
        
        result = {
            "status": "success",
            "source_id": source_id,
            "source_version_id": source_version_id,
            "chunks_created": len(all_chunks),
            "embeddings_created": embeddings_created,
            "message": f"Successfully ingested {path.name}"
        }
        
        console.print(f"[green]{result['message']} - {len(all_chunks)} chunks created[/green]")
        return result
        
    except Exception as e:
        # Rollback on error
        db.execute(
            "UPDATE sources SET status = ? WHERE id = ?",
            ("failed", source_id)
        )
        db.execute(
            "UPDATE jobs SET status = ?, error_message = ? WHERE run_id = ?",
            ("failed", str(e), run_id)
        )
        db.execute(
            "UPDATE runs SET status = ?, ended_at = datetime('now') WHERE id = ?",
            ("failed", run_id)
        )
        
        console.print(f"[red]Error ingesting {path.name}: {e}[/red]")
        return {"status": "error", "message": str(e)}


def ingest_folder(folder_path: str, db: DatabaseConnection, config: Config) -> Dict[str, Any]:
    """Ingest all documents from a folder.
    
    Args:
        folder_path: Path to folder
        db: Database connection
        config: Configuration
        
    Returns:
        Ingestion summary dict
    """
    path = Path(folder_path)
    
    if not path.is_dir():
        return {"status": "error", "message": f"Not a directory: {folder_path}"}
    
    # Find all supported files
    supported_exts = {".pdf", ".txt", ".md"}
    files = [f for f in path.rglob("*") if f.suffix.lower() in supported_exts]
    
    if not files:
        return {"status": "warning", "message": "No supported files found"}
    
    console.print(f"[dim]Found {len(files)} files to ingest[/dim]")
    
    results = {"success": 0, "skipped": 0, "error": 0, "details": []}
    
    for file_path in files:
        result = ingest_file(str(file_path), db, config)
        results["details"].append({
            "file": str(file_path),
            "result": result
        })
        
        if result["status"] == "success":
            results["success"] += 1
        elif result["status"] == "skipped":
            results["skipped"] += 1
        else:
            results["error"] += 1
    
    summary = f"Ingestion complete: {results['success']} success, {results['skipped']} skipped, {results['error']} errors"
    console.print(f"[green]{summary}[/green]")
    
    results["message"] = summary
    return results
