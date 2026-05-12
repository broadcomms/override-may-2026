"""Alternative LLM-runtime clients implementing the existing protocols.

Hybrid runtime story (per v6 plan task 2.10 + ADR-003):
  - Watsonx is primary for v1.0 OVERRIDE chat (reasoning + Fan Mode).
  - The IBM SkillsBuild TORCS lab container ships granite4:350m via Ollama.
    Keep it available; route OVERRIDE chat to it when
    `OVERRIDE_LLM_RUNTIME=ollama` is set.
  - Guardian (BYOC scoring) and Embedding stay watsonx-only — no equivalent
    in granite4:350m. `WATSONX_API_KEY` is required even in ollama mode.

The OllamaChatClient implements `core.reasoning.WatsonxChatClient` (a
duck-typed Protocol named for the original impl); zero call-site changes
in `core/reasoning.py` or `core/fan_mode.py`.
"""

from .ollama import OllamaChatClient, OllamaChatClientError, probe_ollama_reachable

__all__ = ["OllamaChatClient", "OllamaChatClientError", "probe_ollama_reachable"]
