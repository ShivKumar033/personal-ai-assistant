"""
JARVIS AI — Tests for Phase 6: Memory, Knowledge & Learning
"""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from memory.long_term import LongTermMemory
from memory.vector_memory import VectorMemory
from memory.memory_manager import MemoryManager
from tools.memory_tools import register_memory_tools
from tools.tool_registry import ToolRegistry


@pytest.fixture
def temp_memory_dir(tmp_path):
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    yield mem_dir
    if mem_dir.exists():
        shutil.rmtree(mem_dir)


class TestLongTermMemory:
    
    def test_preferences(self, temp_memory_dir):
        db_path = str(temp_memory_dir / "lt.db")
        mem = LongTermMemory(db_path)
        
        # Test basic set/get
        mem.set_preference("theme", "dark")
        assert mem.get_preference("theme") == "dark"
        
        # Test complex object
        config = {"speed": 10, "auto": True}
        mem.set_preference("config", config)
        
        retrieved = mem.get_preference("config")
        assert retrieved["speed"] == 10
        assert retrieved["auto"] is True
        
        # Test get_all
        all_prefs = mem.get_all_preferences()
        assert len(all_prefs) == 2
        assert all_prefs["theme"] == "dark"
        
        # Test delete
        mem.delete_preference("theme")
        assert mem.get_preference("theme") is None
        
        mem.close()

    def test_facts(self, temp_memory_dir):
        db_path = str(temp_memory_dir / "lt.db")
        mem = LongTermMemory(db_path)
        
        mem.remember_fact("user", "User likes coffee")
        mem.remember_fact("user", "User works as a developer")
        
        mem.remember_fact("os", "Arch Linux")
        
        user_facts = mem.recall_facts("user")
        assert len(user_facts) == 2
        assert "coffee" in user_facts[0]["fact"] or "developer" in user_facts[0]["fact"]
        
        mem.close()


class TestVectorMemory:
    
    def test_faiss_initialization_and_search(self, temp_memory_dir):
        faiss_dir = str(temp_memory_dir / "faiss")
        vec = VectorMemory(faiss_dir)
        vec.initialize()
        
        vec.add_memory("The quick brown fox jumps over the lazy dog.")
        vec.add_memory("Python is a programming language.")
        vec.add_memory("JARVIS is an artificial intelligence assistant.")
        
        # Test semantic search
        results = vec.search("What is Python?", top_k=1)
        
        assert len(results) == 1
        doc, dist = results[0]
        assert "programming language" in doc
        

class TestMemoryManager:
    
    @pytest.mark.asyncio
    async def test_memory_manager_integration(self, temp_memory_dir):
        manager = MemoryManager(str(temp_memory_dir))
        
        # Will start background initialization of FAISS
        await manager.initialize()
        
        # Wait for initialize to ensure model loads for test
        await asyncio.sleep(0.5)
        
        # Add basic interactions
        manager.log_interaction("hello", "Hi there")
        
        # Add a longer semantic interaction that triggers async semantic loading
        manager.log_interaction("I love to program in Python on my laptop.", "That's good to know!")
        
        # Set a preference inside long term
        manager.long_term.set_preference("editor", "vim")
        
        # Give asyncio tasks time to propagate the background _async_semantic_add
        await asyncio.sleep(0.2)
        
        context = manager.build_llm_context("Do you remember my favorite editor?")
        
        assert "vim" in context
        assert "Hi there" in context


class TestMemoryTools:
    
    @pytest.mark.asyncio
    async def test_remember_and_recall_tools(self, temp_memory_dir):
        # Tools need an instantiated manager
        manager = MemoryManager(str(temp_memory_dir))
        registry = ToolRegistry()
        
        register_memory_tools(registry, manager)
        
        # Get tools
        remember_def = registry.get("remember_preference")
        recall_def = registry.get("recall_preference")
        
        # Execute remember
        res1 = await remember_def.handler(key="color", value="blue")
        assert "saved successfully" in res1
        
        # Execute recall
        res2 = await recall_def.handler(key="color")
        assert "blue" in res2
        
        manager.close()
