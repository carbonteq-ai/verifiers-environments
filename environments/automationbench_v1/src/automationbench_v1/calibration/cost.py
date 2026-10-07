"""Pre-dispatch cost reservations for the calibration Responses route.

The input bound is the documented *whole model context ceiling*, not an estimate
from visible prompt bytes. Every in-flight call reserves that ceiling at the
maximum applicable input tier plus its output cap at the maximum output tier.
Missing, invalid, cancelled or lost usage keeps the entire reservation charged.
Prices must include every billed token category; this does not protect against a
provider changing its pricing contract. It deliberately rejects paid server tools.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Self

import httpx
from verifiers.v1.clients.client import SESSION_ID_HEADER
from verifiers.v1.clients.eval import EvalClient
from verifiers.v1.configs.client import BaseClientConfig
from verifiers.v1.errors import model_error


@dataclass(frozen=True)
class CostPolicy:
    """Explicit route and pricing contract, persisted in the ledger identity.

    Prices are USD per million tokens; use the maximum applicable tier, including
    reasoning tokens. ``context_token_ceiling`` must be a provider-enforced bound.
    The caller supplies immutable provenance identifying the verified price data.
    Enabling encrypted reasoning input additionally requires provenance that this
    route's reconstructed reasoning is covered by the same provider-enforced
    context ceiling and maximum token prices. Ciphertext is retained unchanged;
    the 8 MiB envelope limit does not estimate its reconstructed token count.
    """

    max_usd: str
    context_token_ceiling: int
    input_usd_per_million: str
    output_usd_per_million: str
    price_provenance: str
    accepted_response_models: tuple[str, ...]
    model: str = "openai/gpt-6-luna"
    url: str = "https://openrouter.ai/api/v1/responses"
    max_output_tokens_per_session: int | None = None
    allow_encrypted_reasoning_input: bool = False

    def __post_init__(self) -> None:
        if type(self.allow_encrypted_reasoning_input) is not bool:
            raise ValueError("encrypted reasoning capability must be boolean")
        for value in (self.max_usd, self.input_usd_per_million, self.output_usd_per_million):
            number = Decimal(value)
            if not number.is_finite() or number <= 0:
                raise ValueError("cost amounts must be finite and positive")
        if type(self.context_token_ceiling) is not int or self.context_token_ceiling <= 0:
            raise ValueError("a documented context ceiling is required")
        if self.max_output_tokens_per_session is not None and (
            type(self.max_output_tokens_per_session) is not int
            or self.max_output_tokens_per_session <= 0
        ):
            raise ValueError("session output ceiling must be a positive integer")
        if not self.price_provenance or not self.accepted_response_models:
            raise ValueError("price provenance and response model identities are required")
        if type(self.accepted_response_models) is not tuple or any(
            type(model) is not str or not model for model in self.accepted_response_models
        ):
            raise ValueError("response model identities must be an immutable tuple of names")
        if len(set(self.accepted_response_models)) != len(self.accepted_response_models):
            raise ValueError("duplicate response model identities")
        if (
            self.model != "openai/gpt-6-luna"
            or self.url != "https://openrouter.ai/api/v1/responses"
        ):
            raise ValueError("this calibration guard supports only the explicit Luna route")

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @property
    def ceiling_nano_usd(self) -> int:
        return int((Decimal(self.max_usd) * 10**9).to_integral_value(rounding="ROUND_FLOOR"))

    def token_cost(self, input_tokens: int, output_tokens: int) -> int:
        cost = (
            Decimal(input_tokens) * Decimal(self.input_usd_per_million)
            + Decimal(output_tokens) * Decimal(self.output_usd_per_million)
        ) * 1000
        return int(cost.to_integral_value(rounding=ROUND_CEILING))

    def validate_request(self, url: str, body: dict) -> int:
        if url != self.url or body.get("model") != self.model or body.get("store") is not False:
            raise ValueError("request differs from the protected model route")
        provider = body.get("provider", {})
        if (
            not isinstance(provider, dict)
            or provider.get("only") != ["openai"]
            or provider.get("order") != ["openai"]
            or provider.get("allow_fallbacks") is not False
            or provider.get("require_parameters") is not True
        ):
            raise ValueError("request must require OpenAI with fallback disabled")
        cap = body.get("max_output_tokens")
        if type(cap) is not int or not 0 < cap <= self.context_token_ceiling:
            raise ValueError("a bounded positive max_output_tokens is required")
        allowed = {
            "model",
            "input",
            "instructions",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "max_output_tokens",
            "reasoning",
            "temperature",
            "top_p",
            "text",
            "store",
            "stream",
            "provider",
            "metadata",
            "truncation",
            "client_metadata",
            "prompt_cache_key",
            "include",
        }
        if set(body) - allowed or body.get("truncation", "disabled") != "disabled":
            raise ValueError("unsupported request fields or automatic truncation")
        if "include" in body:
            include = body["include"]
            if (
                not isinstance(include, list)
                or any(
                    type(item) is not str or item != "reasoning.encrypted_content"
                    for item in include
                )
                or len(include) > 1
            ):
                raise ValueError("unsupported Responses include fields")
            # The actual unpaid Codex fixture requests this output field. Receiving
            # it does not by itself permit sending opaque reasoning back later.
        for field in ("metadata", "client_metadata"):
            if field in body:
                value = body[field]
                if (
                    not isinstance(value, dict)
                    or len(value) > 128
                    or any(
                        type(key) is not str
                        or not 0 < len(key) <= 64
                        or type(item) is not str
                        or len(item) > 1024
                        for key, item in value.items()
                    )
                ):
                    raise ValueError("request metadata must contain bounded string pairs")
        if "prompt_cache_key" in body and (
            type(body["prompt_cache_key"]) is not str
            or not 0 < len(body["prompt_cache_key"]) <= 512
        ):
            raise ValueError("prompt cache key must be a bounded nonempty string")

        def local_tools(tools: object, depth: int = 0) -> None:
            if not isinstance(tools, list) or len(tools) > 512 or depth > 8:
                raise ValueError("invalid local tool list or namespace nesting")
            for tool in tools:
                if (
                    not isinstance(tool, dict)
                    or type(tool.get("type")) is not str
                    or tool.get("type") not in {"function", "namespace"}
                ):
                    raise ValueError("only local function tools and namespaces are supported")
                name = tool.get("name")
                if type(name) is not str or not 0 < len(name) <= 512:
                    raise ValueError("tool name must be a bounded nonempty string")
                if "description" in tool and (
                    type(tool["description"]) is not str or len(tool["description"]) > 16384
                ):
                    raise ValueError("tool description must be a bounded string")
                if tool["type"] == "namespace":
                    if set(tool) - {"type", "name", "description", "tools"}:
                        raise ValueError("unsupported namespace tool fields")
                    local_tools(tool.get("tools"), depth + 1)
                else:
                    if set(tool) - {"type", "name", "description", "parameters", "strict"}:
                        raise ValueError("unsupported local function fields")
                    if "parameters" in tool and not isinstance(tool["parameters"], dict):
                        raise ValueError("local function parameters must be a schema object")
                    if "strict" in tool and type(tool["strict"]) is not bool:
                        raise ValueError("local function strict flag must be boolean")

        local_tools(body.get("tools", []))

        def text_only(value: object) -> None:
            if isinstance(value, dict):
                kind = value.get("type")
                if kind is not None and (
                    type(kind) is not str
                    or kind
                    not in {
                        "message",
                        "input_text",
                        "output_text",
                        "function_call",
                        "function_call_output",
                        "reasoning",
                        "summary_text",
                        "refusal",
                    }
                ):
                    raise ValueError("unsupported input content or hidden provider context")
                if "encrypted_content" in value:
                    if not self.allow_encrypted_reasoning_input or kind != "reasoning":
                        raise ValueError("opaque reasoning context is unsupported")
                    # Opt-in means the caller has verified that reconstructed
                    # reasoning consumes the same bounded, priced model context.
                    # The ciphertext's size is only an envelope/memory limit,
                    # never a token count or an inferred billable-input bound.
                    if set(value) - {"type", "id", "summary", "encrypted_content", "status"}:
                        raise ValueError("unsupported encrypted reasoning envelope fields")
                    identity, encrypted = value.get("id"), value["encrypted_content"]
                    if (
                        type(identity) is not str
                        or not 0 < len(identity) <= 512
                        or type(encrypted) is not str
                        or not encrypted
                        or len(encrypted.encode("utf-8")) > 8 * 2**20
                    ):
                        raise ValueError("invalid or excessive encrypted reasoning envelope")
                    if "status" in value and (
                        type(value["status"]) is not str
                        or value["status"] not in {"completed", "in_progress", "incomplete"}
                    ):
                        raise ValueError("unsupported encrypted reasoning status")
                    summary = value.get("summary")
                    if (
                        not isinstance(summary, list)
                        or len(summary) > 128
                        or any(
                            not isinstance(item, dict)
                            or set(item) != {"type", "text"}
                            or item["type"] != "summary_text"
                            or type(item["text"]) is not str
                            or len(item["text"].encode("utf-8")) > 2**20
                            for item in summary
                        )
                    ):
                        raise ValueError("invalid encrypted reasoning summary")
                for child in value.values():
                    text_only(child)
            elif isinstance(value, list):
                for child in value:
                    text_only(child)

        text_only(body.get("input"))
        return cap


class CostLedger:
    """Exclusive POSIX writer; reservations survive process death and resume.

    Synchronous lock + fsync run before send, so concurrent async calls cannot
    over-admit. An uncertain write poisons the writer; reopen and reconcile.
    This ledger contains accounting only, never prompt bodies or credentials.
    """

    def __init__(self, path: Path, policy: CostPolicy):
        import fcntl

        self.path = path.resolve()
        self.policy = policy
        self.poisoned = False
        self._clients = 0
        self.reservations: dict[str, int] = {}
        self.output_caps: dict[str, int] = {}
        self.session_ids: dict[str, str | None] = {}
        self.observed_outputs: dict[str, int] = {}
        self.settlements: dict[str, int] = {}
        self.events: list[dict] = []
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ownership = Path(str(self.path) + ".lock").open("a+b")  # noqa: SIM115
        try:
            fcntl.flock(self._ownership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists():
                raw = self.path.read_bytes()
                if raw and not raw.endswith(b"\n"):
                    raise ValueError("incomplete cost ledger; reconcile before reuse")
                for line in raw.splitlines():
                    self._accept(json.loads(line))
        except BaseException:
            self._ownership.close()
            raise

    @property
    def charged_nano_usd(self) -> int:
        return sum(self.settlements.get(key, amount) for key, amount in self.reservations.items())

    def charged_output_tokens(self, session_id: str) -> int:
        """Observed output plus full caps of unresolved calls in one native trace.

        The composition must supply trusted native trace IDs. This is an episode
        ceiling only when exactly one solver trace belongs to that episode; it
        does not automatically aggregate multiple agents or distinct trace IDs.
        """
        return sum(
            self.observed_outputs.get(key, cap)
            for key, cap in self.output_caps.items()
            if self.session_ids[key] == session_id
        )

    def _validate(self, event: dict) -> None:
        if set(event) != {
            "sequence",
            "policy",
            "kind",
            "id",
            "nano_usd",
            "output_cap",
            "input_tokens",
            "output_tokens",
            "session_id",
        }:
            raise ValueError("invalid cost ledger record")
        if (
            type(event["sequence"]) is not int
            or event["sequence"] != len(self.events)
            or event["policy"] != self.policy.digest
        ):
            raise ValueError("cost ledger identity or sequence mismatch")
        amount, key, kind = event["nano_usd"], event["id"], event["kind"]
        if type(amount) is not int or amount < 0 or not isinstance(key, str) or not key:
            raise ValueError("invalid reservation amount or identity")
        if kind == "reserved":
            cap = event["output_cap"]
            session_id = event["session_id"]
            if session_id is not None and (type(session_id) is not str or not session_id.strip()):
                raise ValueError("invalid native session identity")
            session_ceiling = self.policy.max_output_tokens_per_session
            if session_ceiling is not None:
                if session_id is None:
                    raise ValueError("trusted native session header required for output budget")
                if (
                    type(cap) is not int
                    or self.charged_output_tokens(session_id) + cap > session_ceiling
                ):
                    raise ValueError("native session output token ceiling reached")
            if event["input_tokens"] is not None or event["output_tokens"] is not None:
                raise ValueError("reservation cannot contain observed usage")
            if type(cap) is not int or not 0 < cap <= self.policy.context_token_ceiling:
                raise ValueError("invalid output cap")
            if amount != self.policy.token_cost(self.policy.context_token_ceiling, cap):
                raise ValueError("reservation differs from policy bound")
            if (
                key in self.reservations
                or self.charged_nano_usd + amount > self.policy.ceiling_nano_usd
            ):
                raise ValueError("cost ceiling or reservation identity violated")
        elif kind == "settled":
            if event["session_id"] != self.session_ids.get(key):
                raise ValueError("settlement session differs from reservation")
            if event["output_cap"] is not None or key not in self.reservations:
                raise ValueError("settlement has no reservation")
            if key in self.settlements or amount > self.reservations[key]:
                raise ValueError("duplicate or excessive settlement")
            inputs, outputs = event["input_tokens"], event["output_tokens"]
            if (
                type(inputs) is not int
                or type(outputs) is not int
                or not 0 <= inputs <= self.policy.context_token_ceiling
                or not 0 <= outputs <= self.output_caps[key]
                or amount != self.policy.token_cost(inputs, outputs)
            ):
                raise ValueError("settlement differs from recorded usage and policy")
        else:
            raise ValueError("unknown cost event")

    def _accept(self, event: dict) -> None:
        self._validate(event)
        destination = self.reservations if event["kind"] == "reserved" else self.settlements
        destination[event["id"]] = event["nano_usd"]
        if event["kind"] == "reserved":
            self.output_caps[event["id"]] = event["output_cap"]
            self.session_ids[event["id"]] = event["session_id"]
        else:
            self.observed_outputs[event["id"]] = event["output_tokens"]
        self.events.append(event)

    def _append(
        self,
        kind: str,
        key: str,
        amount: int,
        cap: int | None,
        inputs: int | None = None,
        outputs: int | None = None,
        session_id: str | None = None,
    ) -> None:
        if self.poisoned or self._ownership.closed:
            raise RuntimeError("cost ledger must be reopened and reconciled")
        event = {
            "sequence": len(self.events),
            "policy": self.policy.digest,
            "kind": kind,
            "id": key,
            "nano_usd": amount,
            "output_cap": cap,
            "input_tokens": inputs,
            "output_tokens": outputs,
            "session_id": session_id,
        }
        self._validate(event)
        try:
            new_file = not self.path.exists()
            with self.path.open("ab") as stream:
                stream.write((json.dumps(event, sort_keys=True) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            if new_file:
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except BaseException:
            self.poisoned = True
            raise
        self._accept(event)

    def reserve(self, output_cap: int, *, session_id: str | None = None) -> str:
        with self._lock:
            key = uuid.uuid4().hex
            self._append(
                "reserved",
                key,
                self.policy.token_cost(self.policy.context_token_ceiling, output_cap),
                output_cap,
                session_id=session_id,
            )
            return key

    def settle(self, key: str, response: object, output_cap: int) -> bool:
        """Release unused reservation only for trustworthy complete usage."""
        if self.output_caps.get(key) != output_cap:
            raise ValueError("settlement output cap differs from persisted reservation")
        if (
            not isinstance(response, dict)
            or response.get("model") not in self.policy.accepted_response_models
        ):
            return False
        if type(response.get("status")) is not str or response.get("status") not in {
            "completed",
            "incomplete",
        }:
            return False
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return False
        inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
        if (
            type(inputs) is not int
            or type(outputs) is not int
            or not 0 <= inputs <= self.policy.context_token_ceiling
            or not 0 <= outputs <= output_cap
            or type(usage.get("total_tokens")) is not int
            or usage.get("total_tokens") != inputs + outputs
        ):
            return False
        with self._lock:
            self._append(
                "settled",
                key,
                self.policy.token_cost(inputs, outputs),
                None,
                inputs,
                outputs,
                session_id=self.session_ids[key],
            )
        return True

    def close(self) -> None:
        if self._clients:
            raise RuntimeError("close guarded clients and their streams before the cost ledger")
        self._ownership.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class _UsageStream(httpx.AsyncByteStream):
    """Observe a bounded copy of SSE; never replace native relay parsing."""

    def __init__(self, inner: httpx.AsyncByteStream, ledger: CostLedger, key: str, cap: int):
        self.inner, self.ledger, self.key, self.cap = inner, ledger, key, cap
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        buffer = bytearray()
        terminal: object = None
        invalid = False
        async for chunk in self.inner:
            buffer.extend(chunk)
            if len(buffer) > 2**20:
                invalid = True
                buffer.clear()
            while b"\n" in buffer:
                line, _, remaining = buffer.partition(b"\n")
                buffer[:] = remaining
                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                        if not isinstance(event, dict):
                            invalid = True
                        elif event.get("type") in {"response.completed", "response.incomplete"}:
                            if terminal is not None:
                                invalid = True
                            terminal = event.get("response")
                        elif event.get("type") in {"error", "response.failed"}:
                            invalid = True
                    except (ValueError, UnicodeDecodeError):
                        invalid = True
            yield chunk
        if buffer.strip():
            invalid = True
        if not invalid and terminal is not None and not self.closed:
            self.ledger.settle(self.key, terminal, self.cap)

    async def aclose(self) -> None:
        self.closed = True
        await self.inner.aclose()


class GuardedEvalClient(EvalClient):
    """Native EvalClient with durable admission at its actual send boundary."""

    def __init__(self, config: BaseClientConfig, *, ledger: CostLedger):
        if ledger._ownership.closed or ledger.poisoned:
            raise RuntimeError("a live reconciled cost ledger is required")
        super().__init__(config)
        self.ledger = ledger
        self._closed = False
        self._streams: list[_UsageStream] = []
        ledger._clients += 1

    async def _request(
        self, url: str, body: dict, headers: httpx.Headers, *, stream: bool = False
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("guarded client is closed")
        try:
            cap = self.ledger.policy.validate_request(url, body)
            # No await separates durable admission from entering the native HTTP path.
            key = self.ledger.reserve(cap, session_id=headers.get(SESSION_ID_HEADER))
        except ValueError as error:
            # Deterministic rejection must not become the native default retryable 502.
            raise model_error(str(error), status_code=400) from error
        response = await super()._request(url, body, headers, stream=stream)
        if self._closed:
            # close() may run while the native send awaits provider headers.
            # Never attach a late stream to a released ledger ownership period.
            await response.aclose()
            raise RuntimeError(
                "guarded client closed during provider dispatch; reservation retained"
            )
        if stream:
            if "text/event-stream" not in response.headers.get("content-type", ""):
                await response.aclose()
                raise ValueError("expected Responses SSE; reservation remains charged")
            if not isinstance(response.stream, httpx.AsyncByteStream):
                raise TypeError("native response stream is not asynchronous")
            observed = _UsageStream(response.stream, self.ledger, key, cap)
            self._streams.append(observed)
            response.stream = observed
        else:
            try:
                raw = response.json()
            except ValueError:
                return response
            if not self._closed:
                self.ledger.settle(key, raw, cap)
        return response

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for stream in self._streams:
            stream.closed = True
        try:
            try:
                for stream in self._streams:
                    await stream.aclose()
            finally:
                await super().close()
        finally:
            # Closed streams cannot release reservations on later iteration.
            self.ledger._clients -= 1
