"""
JARVIS AI — Unified Memory Manager (Phase 6)

Combines Short-term (Context), Long-term (SQLite), and Semantic (FAISS) maps.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

from loguru import logger

from core.context_manager import ContextManager
from memory.long_term import LongTermMemory
from memory.vector_memory import VectorMemory


class MemoryManager:
    """Central interface for short, long, and semantic memories."""

    def __init__(self, storage_dir: str = "logs/memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Short-term conversational context
        self.short_term = ContextManager()
        
        # 2. SQLite structured KV / Facts
        self.long_term = LongTermMemory(db_path=str(self.storage_dir / "long_term.db"))
        
        # 3. FAISS unstructured search
        self.semantic = VectorMemory(storage_dir=str(self.storage_dir / "faiss"))
        
        # Background init lock
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all memory subsystems in the background."""
        if self._initialized: return
        
        # Semantic memory can take a bit to load the HuggingFace model, so load asynchronously
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.semantic.initialize)
        
        self._initialized = True
        logger.info("Unified Memory Subsystem initialized: Short, Long, Semantic models active.")

    # ── Conversational Context Helpers ───────────────────────
    
    def log_interaction(self, user: str, jarvis: str, topic: Optional[str] = None, intent: Optional[str] = None, entities: Optional[dict] = None, success: bool = True):
        """Standard pipeline for recording interaction into all memory types."""
        # Update current context window
        self.short_term.add_exchange(user, jarvis, intent=intent, entities=entities, success=success)
        
        # If there's a topic shift, explicitly set it
        if topic:
            self.short_term.current_topic = topic
            
        # Add to long-term unstructured semantic search asynchronously
        # so we don't block the UI thread
        if len(user.split()) > 3 or len(jarvis.split()) > 3:
            combined = f"User asked/said: {user}. JARVIS replied: {jarvis}."
            asyncio.create_task(self._async_semantic_add(combined))

    async def _async_semantic_add(self, text: str):
        """Background wrapper for FAISS."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.semantic.add_memory, text)

    # ── Full Context Context Builder ─────────────────────────

    def build_llm_context(self, user_prompt: str, max_short_exchanges: int = 5) -> str:
        """
        Merge ContextManager window, active Preferences, and relevant Semantic vectors.
        """
        parts = []
        
        # 1. Short Term (ContextWindow)
        short_context = self.short_term.build_prompt_context(max_short_exchanges)
        parts.append("### SHORT TERM MEMORY (RELEVANT PAST MESSAGES) ###\n" + short_context)
        
        # 2. Key-Value Preferences
        prefs = self.long_term.get_all_preferences()
        if prefs:
            parts.append("\n### USER PREFERENCES ###")
            for k, v in prefs.items():
                parts.append(f"- {k}: {v}")
                
        # 3. Semantic Vector Search (Is JARVIS recalling anything?)
        if self._initialized:
            # Quick semantic lookup
            # Low top_k since it eats into context limits
            sem_results = self.semantic.search(user_prompt, top_k=2)
            if sem_results:
                parts.append("\n### SEMANTIC RECALL (RELATED PAST DISCUSSIONS) ###")
                for doc, dist in sem_results:
                    # Cosine similarity is large if close. 1.0 is exact
                    if dist > 0.5: 
                        parts.append(f"- {doc}")
                        
        return "\n".join(parts)

    def close(self):
        self.long_term.close()
        logger.info("Memory Manager closed successfully.")
