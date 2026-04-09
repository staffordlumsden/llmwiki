"""Ollama generation pipeline for llmwiki."""

import ollama
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from llmwiki.config import Config

console = Console()


def format_context_with_citations(chunks: List[Dict], max_chunks: int = 5) -> str:
    """Format context chunks with citation markers.
    
    Args:
        chunks: List of chunk dicts with 'text', 'page_start', 'page_end', etc.
        max_chunks: Maximum number of chunks to include
        
    Returns:
        Formatted context string with citation markers
    """
    formatted_chunks = []
    
    for i, chunk in enumerate(chunks[:max_chunks]):
        text = chunk.get("text", "")
        page_start = chunk.get("page_start", "?")
        page_end = chunk.get("page_end", page_start)
        source_id = chunk.get("source_id", "?")
        
        # Create citation marker
        citation = f"[{i+1}]"
        
        # Format chunk with citation
        formatted = f"""### Source {source_id} (Pages {page_start}-{page_end}) [{citation}]
{text}
"""
        formatted_chunks.append(formatted)
    
    return "\n\n".join(formatted_chunks)


def build_prompt(query: str, context: str) -> str:
    """Build a well-structured prompt for the LLM.
    
    Args:
        query: User's query
        context: Formatted context with citations
        
    Returns:
        Complete prompt string
    """
    system_prompt = """You are a helpful assistant answering questions based on provided context from a knowledge base.

Instructions:
1. Answer the user's question using ONLY the information provided in the context below.
2. If the answer is not in the context, clearly state that you cannot find the answer in the available sources.
3. Include citation markers (e.g., [1], [2]) in your answer to indicate which sources you're using.
4. Be precise and concise in your responses.
5. If multiple sources agree, you can mention that.
6. If sources contradict, note the contradiction.

Format your answer clearly with appropriate structure (paragraphs, bullet points, etc.)."""

    user_prompt = f"""Context from knowledge base sources:
{context}

---

Question: {query}

Please answer the question above using the context provided. Include citation markers where appropriate."""

    return system_prompt, user_prompt


def generate_response(
    query: str,
    chunks: List[Dict],
    model: str,
    config: Config,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate a response using Ollama with context.
    
    Args:
        query: User's query
        chunks: Retrieved context chunks
        model: Generation model name
        config: Configuration
        params: Optional generation parameters
        
    Returns:
        Response dict with 'text', 'input_tokens', 'output_tokens', 'citations'
    """
    # Format context
    context = format_context_with_citations(chunks) if chunks else "No context available."
    
    # Build prompt
    system_prompt, user_prompt = build_prompt(query, context)
    
    # Get generation params
    gen_config = config.models.get("generation", {})
    options = {
        "temperature": params.get("temperature", gen_config.get("temperature", 0.1)),
        "top_p": params.get("top_p", 0.9),
        "num_predict": params.get("num_predict", gen_config.get("num_ctx", 1024)),
    }
    
    # Prepare for streaming
    full_response = ""
    input_tokens = 0
    output_tokens = 0
    
    try:
        # Stream the response
        stream = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options=options,
            stream=True
        )
        
        # Collect and display response
        console.print(Panel("[dim]Generating response...[/dim]", border_style="blue"))
        
        last_stream_chunk = None
        with Live("", console=console, refresh_per_second=10, vertical_overflow="visible") as live:
            for stream_chunk in stream:
                if "message" in stream_chunk and "content" in stream_chunk["message"]:
                    content = stream_chunk["message"]["content"]
                    full_response += content
                    
                    # Render markdown
                    md = Markdown(full_response)
                    live.update(md)
                last_stream_chunk = stream_chunk
        
        # Parse token usage from the last chunk if available
        if last_stream_chunk and "eval_count" in last_stream_chunk:
            input_tokens = last_stream_chunk.get("prompt_eval_count", 0)
            output_tokens = last_stream_chunk.get("eval_count", 0)
        else:
            # Estimate if not provided
            input_tokens = len(user_prompt) // 4
            output_tokens = len(full_response) // 4
        
        # Extract citations from chunks
        citations = []
        for i, ctx_chunk in enumerate(chunks[:5]):
            citations.append({
                "id": i + 1,
                "text": ctx_chunk.get("text", "")[:200] + "..." if len(ctx_chunk.get("text", "")) > 200 else ctx_chunk.get("text", ""),
                "page_start": ctx_chunk.get("page_start", "?"),
                "page_end": ctx_chunk.get("page_end", "?"),
                "source_id": ctx_chunk.get("source_id", "?")
            })
        
        return {
            "text": full_response,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "citations": citations,
            "model": model,
            "success": True
        }
        
    except ollama.ResponseError as e:
        console.print(f"[red]Ollama error: {e}[/red]")
        return {
            "text": f"Error generating response: {e}",
            "input_tokens": 0,
            "output_tokens": 0,
            "citations": [],
            "model": model,
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        return {
            "text": f"Unexpected error: {e}",
            "input_tokens": 0,
            "output_tokens": 0,
            "citations": [],
            "model": model,
            "success": False,
            "error": str(e)
        }


def generate_response_simple(query: str, model: str, config: Config, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate a simple response without context (chat-only mode).
    
    Args:
        query: User's query
        model: Generation model name
        config: Configuration
        params: Optional generation parameters
        
    Returns:
        Response dict
    """
    gen_config = config.models.get("generation", {})
    options = {
        "temperature": params.get("temperature", gen_config.get("temperature", 0.1)),
        "top_p": params.get("top_p", 0.9),
        "num_predict": params.get("num_predict", gen_config.get("num_ctx", 1024)),
    }
    
    full_response = ""
    
    try:
        stream = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": query}],
            options=options,
            stream=True
        )
        
        with Live("", console=console, refresh_per_second=10, vertical_overflow="visible") as live:
            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    full_response += content
                    md = Markdown(full_response)
                    live.update(md)
        
        # Estimate tokens
        input_tokens = len(query) // 4
        output_tokens = len(full_response) // 4
        
        return {
            "text": full_response,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "citations": [],
            "model": model,
            "success": True
        }
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return {
            "text": f"Error: {e}",
            "input_tokens": 0,
            "output_tokens": 0,
            "citations": [],
            "model": model,
            "success": False,
            "error": str(e)
        }
