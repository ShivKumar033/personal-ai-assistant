"""
JARVIS AI — AI Brain

The reasoning engine of JARVIS. Provides a unified interface to
multiple LLM backends (Ollama local, OpenAI cloud) with async support,
structured output parsing, and JARVIS persona prompting.

Usage:
    from ai.brain import AIBrain
    brain = AIBrain(settings.ai)
    response = await brain.think("open my pentesting workspace")
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger


# ══════════════════════════════════════════════════════════════
#  Data Models
# ══════════════════════════════════════════════════════════════

@dataclass
class Message:
    """A single chat message."""
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM backend."""
    text: str
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    raw: Optional[dict] = None

    def __str__(self) -> str:
        return self.text


@dataclass
class BrainResponse:
    """Structured response from the AI Brain."""
    text: str
    intent: Optional[str] = None
    entities: Optional[dict] = None
    tool_calls: Optional[list[dict]] = None
    confidence: float = 0.0
    model_used: str = ""
    thinking_time_ms: float = 0.0


# ══════════════════════════════════════════════════════════════
#  JARVIS System Prompt
# ══════════════════════════════════════════════════════════════

JARVIS_SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant inspired by Iron Man's AI companion.

Personality:
- Professional, confident, and slightly witty
- Address the user respectfully (use "sir" occasionally)
- Be concise but thorough
- When executing tasks, explain what you're doing

Capabilities:
- You can control the computer (open apps, manage files, system operations)
- You can search the web and gather information
- You can automate repetitive tasks
- You can answer questions using your knowledge

Guidelines:
- Always be helpful and proactive
- If a task seems dangerous, warn the user
- Explain your reasoning when making decisions
- Keep responses focused and actionable
- You are bilingual: respond in English or Hindi based on the user's preference or language used.
"""



# ══════════════════════════════════════════════════════════════
#  Abstract LLM Backend
# ══════════════════════════════════════════════════════════════

class BaseLLM(ABC):
    """Abstract base class for LLM backends."""

    def __init__(self, model_name: str, **kwargs) -> None:
        self.model_name = model_name
        self._available = False

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate a response from a single prompt."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate a response from a conversation."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if this backend is available."""
        ...

    @property
    def is_available(self) -> bool:
        return self._available

    def __repr__(self) -> str:
        status = "✅" if self._available else "❌"
        return f"{self.__class__.__name__}({self.model_name}) {status}"


# ══════════════════════════════════════════════════════════════
#  Ollama Backend (Local LLM)
# ══════════════════════════════════════════════════════════════

class OllamaLLM(BaseLLM):
    """
    Ollama local LLM backend.

    Communicates with the Ollama REST API at localhost:11434.
    Supports any model installed via `ollama pull <model>`.
    """

    def __init__(
        self,
        model_name: str = "llama3",
        host: str = "http://localhost:11434",
        timeout: float = 60.0,
    ) -> None:
        # Strip "ollama/" prefix if present
        clean_name = model_name.replace("ollama/", "")
        super().__init__(clean_name)
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._host,
            timeout=httpx.Timeout(timeout),
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate using Ollama /api/generate endpoint."""
        import time
        start = time.monotonic()

        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if json_mode:
            payload["format"] = "json"

        try:
            resp = await self._client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

            elapsed = (time.monotonic() - start) * 1000
            return LLMResponse(
                text=data.get("response", "").strip(),
                model=self.model_name,
                tokens_used=data.get("eval_count", 0),
                latency_ms=round(elapsed, 1),
                raw=data,
            )
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Chat using Ollama /api/chat endpoint."""
        import time
        start = time.monotonic()

        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": msg_dicts,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_mode:
            payload["format"] = "json"

        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

            elapsed = (time.monotonic() - start) * 1000
            msg = data.get("message", {})
            return LLMResponse(
                text=msg.get("content", "").strip(),
                model=self.model_name,
                tokens_used=data.get("eval_count", 0),
                latency_ms=round(elapsed, 1),
                raw=data,
            )
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()

            available_models = [
                m.get("name", "").split(":")[0]
                for m in data.get("models", [])
            ]
            self._available = self.model_name in available_models

            if not self._available:
                logger.warning(
                    f"Ollama is running but model '{self.model_name}' not found. "
                    f"Available: {available_models}"
                )
            else:
                logger.info(f"Ollama model '{self.model_name}' is available")

            return self._available
        except httpx.ConnectError:
            logger.warning("Ollama is not running (connection refused)")
            self._available = False
            return False
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            self._available = False
            return False

    async def list_models(self) -> list[str]:
        """List all available Ollama models."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# ══════════════════════════════════════════════════════════════
#  OpenAI Backend (Cloud LLM)
# ══════════════════════════════════════════════════════════════

class OpenAILLM(BaseLLM):
    """
    OpenAI cloud LLM backend.

    Uses the official openai Python SDK with async support.
    Supports GPT-4o, GPT-4, GPT-3.5-turbo, etc.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        super().__init__(model_name)
        self._api_key = api_key
        self._timeout = timeout
        self._client = None  # Lazy init

    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    timeout=self._timeout,
                )
            except ImportError:
                logger.error(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )
                raise
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate using OpenAI chat completions (single prompt)."""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        return await self.chat(messages, temperature, max_tokens, json_mode)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Chat using OpenAI chat completions."""
        import time
        start = time.monotonic()

        client = self._get_client()
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": msg_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await client.chat.completions.create(**kwargs)
            elapsed = (time.monotonic() - start) * 1000

            choice = response.choices[0]
            usage = response.usage

            return LLMResponse(
                text=choice.message.content.strip(),
                model=self.model_name,
                tokens_used=usage.total_tokens if usage else 0,
                latency_ms=round(elapsed, 1),
                raw=response.model_dump() if hasattr(response, "model_dump") else None,
            )
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        if not self._api_key:
            logger.info("OpenAI API key not configured")
            self._available = False
            return False

        try:
            client = self._get_client()
            # Use a minimal request to verify the key works
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            self._available = True
            logger.info(f"OpenAI model '{self.model_name}' is available")
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            self._available = False
            return False

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None


# ══════════════════════════════════════════════════════════════
#  AI Brain — The Orchestrator
# ══════════════════════════════════════════════════════════════

class AIBrain:
    """
    The central reasoning engine of JARVIS.

    Orchestrates LLM backends, manages conversation context,
    and provides high-level thinking capabilities:

    - think()     → Understand user intent + decide actions
    - respond()   → Generate natural language responses
    - analyze()   → Parse and extract structured data
    - summarize() → Condense information
    """

    def __init__(self, ai_config, model_router=None) -> None:
        self._config = ai_config
        self._router = model_router
        self._initialized = False
        self._backends: dict[str, BaseLLM] = {}
        self._default_backend: Optional[BaseLLM] = None
        self._fallback_backend: Optional[BaseLLM] = None

    async def initialize(self) -> None:
        """
        Initialize LLM backends and check availability.
        Must be called before using the brain.
        """
        if self._initialized:
            return

        logger.info("Initializing AI Brain...")

        # ── Set up Ollama (local) ─────────────────────
        default_model = self._config.default_model
        ollama_model = default_model.replace("ollama/", "")

        ollama = OllamaLLM(
            model_name=ollama_model,
            host=self._config.ollama_host,
            timeout=self._config.timeout_seconds,
        )
        self._backends["ollama"] = ollama

        # ── Set up Fallback Ollama model ──────────────
        fallback_model = self._config.fallback_model
        if fallback_model and fallback_model != default_model:
            fallback_ollama_model = fallback_model.replace("ollama/", "")
            fallback = OllamaLLM(
                model_name=fallback_ollama_model,
                host=self._config.ollama_host,
                timeout=self._config.timeout_seconds,
            )
            self._backends["ollama_fallback"] = fallback

        # ── Set up OpenAI (cloud) ─────────────────────
        if self._config.openai_api_key:
            openai_llm = OpenAILLM(
                model_name="gpt-4o-mini",
                api_key=self._config.openai_api_key,
                timeout=self._config.timeout_seconds,
            )
            self._backends["openai"] = openai_llm

        # ── Health checks ─────────────────────────────
        available_backends = []
        for name, backend in self._backends.items():
            is_up = await backend.health_check()
            if is_up:
                available_backends.append(name)

        # ── Select default and fallback ───────────────
        if "ollama" in available_backends:
            self._default_backend = self._backends["ollama"]
        elif "openai" in available_backends:
            self._default_backend = self._backends["openai"]
        elif "ollama_fallback" in available_backends:
            self._default_backend = self._backends["ollama_fallback"]

        # Set fallback (different from default)
        for name in ["openai", "ollama_fallback", "ollama"]:
            if (
                name in available_backends
                and self._backends[name] != self._default_backend
            ):
                self._fallback_backend = self._backends[name]
                break

        if self._default_backend:
            logger.info(
                f"AI Brain online → default: {self._default_backend.model_name}"
                f"{f', fallback: {self._fallback_backend.model_name}' if self._fallback_backend else ''}"
            )
        else:
            logger.warning(
                "No LLM backends available! AI Brain running in offline mode. "
                "Start Ollama with `ollama serve` and pull a model with "
                "`ollama pull llama3`."
            )

        self._initialized = True

    @property
    def is_online(self) -> bool:
        """Check if at least one LLM backend is available."""
        return self._default_backend is not None

    @property
    def active_model(self) -> str:
        """Get the active model name."""
        if self._default_backend:
            return self._default_backend.model_name
        return "offline"

    # ── High-Level API ────────────────────────────────────

    async def think(
        self,
        user_input: str,
        context: str = "",
        available_tools: Optional[list[dict]] = None,
    ) -> BrainResponse:
        """
        Process user input and produce a structured understanding.

        This is the main entry point. It:
        1. Builds a context-aware prompt
        2. Sends to LLM with structured output request
        3. Parses the response into BrainResponse

        Args:
            user_input: What the user said
            context: Conversation context string
            available_tools: Tool schemas for function selection

        Returns:
            BrainResponse with intent, entities, and response text
        """
        import time
        start = time.monotonic()

        if not self.is_online:
            return BrainResponse(
                text=(
                    "I'm currently in offline mode — no AI model is connected.\n"
                    "Please start Ollama (`ollama serve`) or configure an OpenAI API key.\n"
                    "I can still execute built-in tools directly (type `tools` to list them)."
                ),
                intent="offline_notice",
                confidence=1.0,
                model_used="offline",
            )

        # ── Build intent extraction prompt ────────────
        tool_descriptions = ""
        if available_tools:
            tool_lines = []
            for t in available_tools:
                params_str = ", ".join(
                    f"{k}: {v}" for k, v in t.get("parameters", {}).items()
                )
                tool_lines.append(
                    f"  - {t['name']}({params_str}): {t['description']}"
                )
            tool_descriptions = "Available tools:\n" + "\n".join(tool_lines)

        analysis_prompt = f"""Analyze the following user input and respond with a JSON object.

{tool_descriptions}

User input: "{user_input}"

{f"Conversation context:{chr(10)}{context}" if context else ""}

Respond ONLY with a valid JSON object in this exact format:
{{
    "intent": "<the primary intent/action the user wants>",
    "entities": {{<relevant extracted entities as key-value pairs>}},
    "tool_name": "<name of the best matching tool to use, or null if conversational>",
    "tool_params": {{<parameters to pass to the tool, or {{}}>}},
    "response": "<a natural JARVIS-style response to the user>",
    "confidence": <0.0 to 1.0 confidence score>,
    "is_conversational": <true if this is just a question/chat, false if it requires action>
}}

Important rules:
- If the user wants to execute an action and a matching tool exists, set tool_name to that tool's name
- If no tool matches, set tool_name to null and provide a helpful response
- Extract relevant entities (app names, file paths, search queries, etc.)
- Keep the response concise and in character as JARVIS
"""

        try:
            llm_response = await self._generate_with_fallback(
                prompt=analysis_prompt,
                system_prompt=JARVIS_SYSTEM_PROMPT,
                temperature=0.3,  # Lower temp for structured output
                json_mode=True,
            )

            elapsed = (time.monotonic() - start) * 1000

            # Parse the JSON response
            parsed = self._parse_json_response(llm_response.text)

            # Build tool_calls list if a tool was selected
            tool_calls = None
            if parsed.get("tool_name"):
                tool_calls = [{
                    "tool": parsed["tool_name"],
                    "params": parsed.get("tool_params", {}),
                }]

            return BrainResponse(
                text=parsed.get("response", llm_response.text),
                intent=parsed.get("intent", "unknown"),
                entities=parsed.get("entities", {}),
                tool_calls=tool_calls,
                confidence=float(parsed.get("confidence", 0.5)),
                model_used=llm_response.model,
                thinking_time_ms=round(elapsed, 1),
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(f"Brain.think() error: {e}")
            return BrainResponse(
                text=f"I encountered an error while processing: {e}",
                intent="error",
                confidence=0.0,
                model_used=self.active_model,
                thinking_time_ms=round(elapsed, 1),
            )

    async def respond(
        self,
        user_input: str,
        context: str = "",
    ) -> str:
        """
        Generate a conversational response (no tool selection).

        Use this for pure Q&A / chat interactions.
        """
        if not self.is_online:
            return (
                "I'm in offline mode. Please start Ollama or configure OpenAI."
            )

        messages = [
            Message(role="system", content=JARVIS_SYSTEM_PROMPT),
        ]

        if context:
            messages.append(Message(
                role="system",
                content=f"Previous conversation context:\n{context}",
            ))

        messages.append(Message(role="user", content=user_input))

        try:
            response = await self._chat_with_fallback(messages)
            return response.text
        except Exception as e:
            logger.error(f"Brain.respond() error: {e}")
            return f"I encountered an error: {e}"

    async def summarize(self, text: str, max_length: int = 200) -> str:
        """Summarize a piece of text."""
        if not self.is_online:
            # Fallback: crude truncation
            return text[:max_length] + "..." if len(text) > max_length else text

        prompt = (
            f"Summarize the following text concisely in {max_length} characters or less. "
            f"Be direct and factual.\n\nText:\n{text}"
        )

        try:
            response = await self._generate_with_fallback(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Brain.summarize() error: {e}")
            return text[:max_length] + "..."

    # ── Internal Methods ──────────────────────────────────

    async def _generate_with_fallback(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate with automatic fallback to secondary backend."""
        try:
            return await self._default_backend.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as e:
            if self._fallback_backend:
                logger.warning(
                    f"Primary backend failed ({e}), falling back to "
                    f"{self._fallback_backend.model_name}"
                )
                return await self._fallback_backend.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            raise

    async def _chat_with_fallback(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Chat with automatic fallback."""
        try:
            return await self._default_backend.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as e:
            if self._fallback_backend:
                logger.warning(
                    f"Primary backend failed ({e}), falling back to "
                    f"{self._fallback_backend.model_name}"
                )
                return await self._fallback_backend.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            raise

    def _parse_json_response(self, text: str) -> dict:
        """
        Parse JSON from LLM response, handling common formatting issues.
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(
            r'```(?:json)?\s*\n?(.*?)\n?\s*```',
            text,
            re.DOTALL,
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        # Give up — return text as response
        logger.warning(f"Could not parse JSON from LLM response: {text[:200]}")
        return {
            "intent": "conversation",
            "response": text,
            "confidence": 0.3,
            "is_conversational": True,
        }

    # ── Status ────────────────────────────────────────────

    def status(self) -> dict:
        """Return brain status for display."""
        backends = {}
        for name, backend in self._backends.items():
            backends[name] = {
                "model": backend.model_name,
                "available": backend.is_available,
            }

        return {
            "online": self.is_online,
            "active_model": self.active_model,
            "backends": backends,
            "initialized": self._initialized,
        }

    async def close(self) -> None:
        """Close all backends."""
        for backend in self._backends.values():
            await backend.close()
        logger.info("AI Brain shut down")
