"""Per-session SLM usage accumulation (tokens, latency, call count)."""

from __future__ import annotations

from pydantic import BaseModel

from framework.slm.client import SLMClient, SLMResponse


class SLMUsageAccumulator(BaseModel):
    """Running totals for one session across planner and executor clients."""

    tokens_total: int = 0
    latency_ms_total: int = 0
    llm_calls: int = 0

    def record(self, response: SLMResponse) -> None:
        """Add one completion's usage metrics."""
        self.llm_calls += 1
        self.tokens_total += max(0, int(response.tokens_used))
        self.latency_ms_total += max(0, int(response.elapsed_ms))


class TrackingSLMClient:
    """Wrap :class:`SLMClient` and record every :meth:`call` into a shared accumulator."""

    def __init__(self, inner: SLMClient, usage: SLMUsageAccumulator) -> None:
        self._inner = inner
        self._usage = usage

    @property
    def profile(self):
        return self._inner.profile

    @property
    def endpoint(self):
        return self._inner.endpoint

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        response = self._inner.call(messages, role=role, json_mode=json_mode)
        self._usage.record(response)
        return response

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> TrackingSLMClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
