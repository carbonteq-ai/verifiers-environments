import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import replace

import httpx
import pytest
from verifiers.v1.clients.client import SESSION_ID_HEADER
from verifiers.v1.configs.client import BaseClientConfig
from verifiers.v1.dialects.responses import ResponsesDialect
from verifiers.v1.errors import ProviderError

from automationbench_v1.calibration.cost import CostLedger, CostPolicy, GuardedEvalClient


def policy(**kwargs):
    return CostPolicy(
        max_usd="0.25",
        context_token_ceiling=1_050_000,
        input_usd_per_million="0.20",
        output_usd_per_million="0.75",
        price_provenance="frozen-test-price-contract",
        accepted_response_models=("gpt-6-luna",),
        **kwargs,
    )


def request():
    return {
        "model": "openai/gpt-6-luna",
        "input": "hello",
        "store": False,
        "max_output_tokens": 2048,
        "provider": {
            "only": ["openai"],
            "order": ["openai"],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
    }


def usage(**kwargs):
    return dict(
        model="gpt-6-luna",
        status="completed",
        usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        **kwargs,
    )


async def client_for(ledger, handler):
    client = GuardedEvalClient(
        BaseClientConfig(base_url="https://openrouter.ai/api/v1", api_key_var="TEST_UNUSED_KEY"),
        ledger=ledger,
    )
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_concurrent_admission_precedes_send_and_resume_keeps_unknown(tmp_path):
    path = tmp_path / "cost.jsonl"

    async def run():
        with CostLedger(path, policy()) as ledger:
            sent = []
            entered = asyncio.Event()
            release = asyncio.Event()

            async def handler(req):
                assert ledger.charged_nano_usd == 211_536_000
                sent.append(req)
                entered.set()
                await release.wait()
                return httpx.Response(200, json={"missing": "usage"})

            client = await client_for(ledger, handler)
            first = asyncio.create_task(client._request(policy().url, request(), httpx.Headers()))
            await entered.wait()
            with pytest.raises(ProviderError, match="ceiling") as rejected:
                await client._request(policy().url, request(), httpx.Headers())
            assert rejected.value.status_code == 400
            release.set()
            await first
            assert len(sent) == 1
            await client.close()
        with CostLedger(path, policy()) as resumed:
            assert resumed.charged_nano_usd == 211_536_000
            with pytest.raises(ValueError, match="ceiling"):
                resumed.reserve(2048)

    asyncio.run(run())


def test_rejected_route_never_sends_and_valid_json_settles(tmp_path):
    async def run():
        with CostLedger(tmp_path / "cost.jsonl", policy()) as ledger:
            calls = []

            async def handler(req):
                calls.append(req)
                return httpx.Response(200, json=usage())

            client = await client_for(ledger, handler)
            for changes in (
                {"model": "other"},
                {"store": True},
                {"max_output_tokens": None},
                {"previous_response_id": "old"},
                {"tools": [{"type": "web_search"}]},
                {"input": [{"type": "input_image"}]},
                {"provider": {}},
            ):
                with pytest.raises(ProviderError) as rejected:
                    await client._request(policy().url, request() | changes, httpx.Headers())
                assert rejected.value.status_code == 400
            assert not calls and not ledger.events
            await client._request(policy().url, request(), httpx.Headers())
            await client._request(policy().url, request(), httpx.Headers())
            assert len(calls) == 2 and ledger.charged_nano_usd == 34_000
            await client.close()

    asyncio.run(run())


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


@pytest.mark.parametrize("mode", ["valid", "malformed", "lost", "cancelled", "wrong_model"])
def test_stream_usage_loss_and_cancellation(tmp_path, mode):
    async def run():
        with CostLedger(tmp_path / "cost.jsonl", policy()) as ledger:
            raw = usage()
            if mode == "wrong_model":
                raw["model"] = "wrong"
            terminal = (
                "data: " + json.dumps({"type": "response.completed", "response": raw}) + "\n\n"
            ).encode()
            chunks = [terminal[:7], terminal[7:]]
            if mode == "malformed":
                chunks.append(b"data: not-json\n\n")
            if mode == "lost":
                chunks = [terminal[:20]]
            error = asyncio.CancelledError() if mode == "cancelled" else None

            async def handler(req):
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=Chunks(chunks, error)
                )

            client = await client_for(ledger, handler)
            response = await client._request(policy().url, request(), httpx.Headers(), stream=True)
            if mode == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await response.aread()
            else:
                result = await response.aread()
                assert result == b"".join(chunks)
            assert ledger.charged_nano_usd == (17_000 if mode == "valid" else 211_536_000)
            await response.aclose()
            await client.close()

    asyncio.run(run())


def test_writer_ownership_replay_policy_and_poison(tmp_path, monkeypatch):
    path = tmp_path / "cost.jsonl"
    ledger = CostLedger(path, policy())
    with pytest.raises(BlockingIOError):
        CostLedger(tmp_path / "sub" / ".." / "cost.jsonl", policy())
    key = ledger.reserve(2048)
    assert ledger.settle(key, usage(), 2048)
    with pytest.raises(ValueError, match="duplicate"):
        ledger.settle(key, usage(), 2048)
    ledger.close()
    with pytest.raises(ValueError, match="identity"):
        CostLedger(path, replace(policy(), max_usd="1"))
    with path.open("ab") as out:
        out.write(b'{"incomplete":')
    with pytest.raises(ValueError, match="incomplete"):
        CostLedger(path, policy())

    with CostLedger(tmp_path / "failed.jsonl", policy()) as failed:

        def fail(_):
            raise OSError("uncertain fsync")

        monkeypatch.setattr("automationbench_v1.calibration.cost.os.fsync", fail)
        with pytest.raises(OSError):
            failed.reserve(2048)
        with pytest.raises(RuntimeError, match="reopened"):
            failed.reserve(2048)


def test_native_relay_retains_bytes_and_early_close_keeps_reservation(tmp_path):
    async def run():
        terminal = (
            "data: " + json.dumps({"type": "response.completed", "response": usage()}) + "\n\n"
        ).encode()
        delta = b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
        with CostLedger(tmp_path / "cost.jsonl", replace(policy(), max_usd="1")) as ledger:

            async def handler(req):
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=Chunks([delta, terminal]),
                )

            client = await client_for(ledger, handler)
            reply = await client.relay(ResponsesDialect(), request())
            assert b"".join([part async for part in reply.chunks]) == delta + terminal
            await reply.close()
            assert ledger.charged_nano_usd == 17_000
            aborted = await client.relay(ResponsesDialect(), request())
            assert await anext(aborted.chunks) == delta
            assert isinstance(aborted.chunks, AsyncGenerator)
            await aborted.chunks.aclose()
            await aborted.close()
            assert ledger.charged_nano_usd == 211_553_000
            await client.close()

    asyncio.run(run())


def test_replay_rejects_underreserved_amount(tmp_path):
    path = tmp_path / "cost.jsonl"
    with CostLedger(path, policy()) as ledger:
        ledger.reserve(2048)
    event = json.loads(path.read_text())
    event["nano_usd"] -= 1
    path.write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="policy bound"):
        CostLedger(path, policy())


@pytest.mark.parametrize(
    "names", ["gpt-6-luna", ["gpt-6-luna"], (), ("",), (1,), ("gpt-6-luna", "gpt-6-luna")]
)
def test_response_model_identity_requires_immutable_exact_names(names):
    with pytest.raises(ValueError):
        replace(policy(), accepted_response_models=names)


@pytest.mark.parametrize("error", [httpx.ConnectError("no response"), asyncio.CancelledError()])
def test_request_error_keeps_reservation_and_ledger_outlives_client(tmp_path, error):
    async def run():
        ledger = CostLedger(tmp_path / "cost.jsonl", policy())

        async def handler(req):
            raise error

        client = await client_for(ledger, handler)
        with pytest.raises(RuntimeError, match="close guarded clients"):
            ledger.close()
        with pytest.raises(type(error) if isinstance(error, asyncio.CancelledError) else Exception):
            await client._request(policy().url, request(), httpx.Headers())
        assert ledger.charged_nano_usd == 211_536_000
        await client.close()
        ledger.close()
        with CostLedger(tmp_path / "cost.jsonl", policy()) as resumed:
            assert resumed.charged_nano_usd == 211_536_000

    asyncio.run(run())


def test_client_close_retires_active_stream_before_ledger(tmp_path):
    async def run():
        ledger = CostLedger(tmp_path / "cost.jsonl", policy())
        terminal = (
            "data: " + json.dumps({"type": "response.completed", "response": usage()}) + "\n\n"
        ).encode()

        async def handler(req):
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Chunks([terminal])
            )

        client = await client_for(ledger, handler)
        response = await client._request(policy().url, request(), httpx.Headers(), stream=True)
        with pytest.raises(RuntimeError):
            ledger.close()
        await client.close()
        ledger.close()
        # The test stream permits reads after close; even then no late settlement occurs.
        await response.aread()
        with CostLedger(tmp_path / "cost.jsonl", policy()) as resumed:
            assert resumed.charged_nano_usd == 211_536_000

    asyncio.run(run())


@pytest.mark.parametrize("streaming", [False, True])
def test_close_during_send_rejects_late_response_without_settlement(tmp_path, streaming):
    async def run():
        path = tmp_path / "cost.jsonl"
        ledger = CostLedger(path, policy())
        entered, release = asyncio.Event(), asyncio.Event()
        replies = []

        async def handler(req):
            entered.set()
            await release.wait()
            reply = (
                httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=Chunks([b"data: [DONE]\n\n"]),
                )
                if streaming
                else httpx.Response(200, json=usage())
            )
            replies.append(reply)
            return reply

        client = await client_for(ledger, handler)
        pending = asyncio.create_task(
            client._request(policy().url, request(), httpx.Headers(), stream=streaming)
        )
        await entered.wait()
        await client.close()
        ledger.close()
        with CostLedger(path, policy()) as resumed:
            release.set()
            with pytest.raises(RuntimeError, match="closed during provider dispatch"):
                await pending
            assert replies[0].is_closed
            assert resumed.charged_nano_usd == 211_536_000
            assert not client._streams

    asyncio.run(run())


@pytest.mark.parametrize("limit", [0, -1, True, 2.5, "8192"])
def test_invalid_session_output_limit(limit):
    with pytest.raises(ValueError, match="positive integer"):
        replace(policy(), max_output_tokens_per_session=limit)


def test_session_output_admission_is_atomic_and_unknown_survives_resume(tmp_path):
    async def run():
        path = tmp_path / "cost.jsonl"
        bounded = replace(policy(), max_usd="4.99", max_output_tokens_per_session=2048)
        with CostLedger(path, bounded) as ledger:
            entered, release = asyncio.Event(), asyncio.Event()
            sent = []

            async def handler(req):
                sent.append(req)
                entered.set()
                await release.wait()
                return httpx.Response(200, json={"unknown": "usage"})

            client = await client_for(ledger, handler)
            with pytest.raises(ProviderError, match="trusted native session"):
                await client._request(bounded.url, request(), httpx.Headers())
            assert not ledger.events and not sent
            headers = httpx.Headers({SESSION_ID_HEADER: "trace-a"})
            pending = asyncio.create_task(client._request(bounded.url, request(), headers))
            await entered.wait()
            with pytest.raises(ProviderError, match="output token ceiling"):
                await client._request(bounded.url, request(), headers)
            release.set()
            await pending
            assert len(sent) == 1 and ledger.charged_output_tokens("trace-a") == 2048
            await client.close()
        with CostLedger(path, bounded) as resumed:
            assert resumed.charged_output_tokens("trace-a") == 2048
            with pytest.raises(ValueError, match="output token ceiling"):
                resumed.reserve(1, session_id="trace-a")
            resumed.reserve(2048, session_id="trace-b")

    asyncio.run(run())


def test_session_settlement_releases_output_but_never_clamps_request(tmp_path):
    async def run():
        path = tmp_path / "cost.jsonl"
        bounded = replace(policy(), max_usd="4.99", max_output_tokens_per_session=2068)
        with CostLedger(path, bounded) as ledger:
            caps = []

            async def handler(req):
                caps.append(json.loads(req.content)["max_output_tokens"])
                return httpx.Response(200, json=usage())

            client = await client_for(ledger, handler)
            headers = httpx.Headers({SESSION_ID_HEADER: "trace-a"})
            await client._request(bounded.url, request(), headers)
            assert ledger.charged_output_tokens("trace-a") == 20
            await client._request(bounded.url, request(), headers)
            assert ledger.charged_output_tokens("trace-a") == 40
            with pytest.raises(ProviderError, match="output token ceiling"):
                await client._request(bounded.url, request(), headers)
            assert caps == [2048, 2048]
            await client.close()
        with CostLedger(path, bounded) as resumed:
            assert resumed.charged_output_tokens("trace-a") == 40
            resumed.reserve(2028, session_id="trace-a")
            assert resumed.charged_output_tokens("trace-a") == 2068

    asyncio.run(run())


def test_namespace_and_client_metadata_preserve_structure_and_deny_paid_leaves(tmp_path):
    async def run():
        with CostLedger(tmp_path / "cost.jsonl", policy()) as ledger:
            sent = []

            async def handler(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, json=usage())

            client = await client_for(ledger, handler)
            namespace = {
                "type": "namespace",
                "name": "functions",
                "tools": [
                    {
                        "type": "function",
                        "name": "execute",
                        "parameters": {"type": "object"},
                        "strict": False,
                    }
                ],
            }
            candidate = request() | {
                "tools": [namespace],
                "client_metadata": {"session": "test"},
                "prompt_cache_key": "fixture-cache",
                "include": ["reasoning.encrypted_content"],
            }
            for leaf in ("web_search", "file_search", "computer", "mcp", "custom"):
                forbidden = namespace | {"tools": [{"type": leaf, "name": "blocked"}]}
                with pytest.raises(ProviderError) as rejected:
                    await client._request(
                        policy().url, candidate | {"tools": [forbidden]}, httpx.Headers()
                    )
                assert rejected.value.status_code == 400
            for changes in (
                {"client_metadata": {"value": {"nested": "bad"}}},
                {"client_metadata": {"value": "x" * 1025}},
                {"prompt_cache_key": ""},
                {"prompt_cache_key": 123},
                {"include": ["file_search_call.results"]},
                {"include": "reasoning.encrypted_content"},
                {"input": [{"type": "reasoning", "encrypted_content": "opaque"}]},
            ):
                with pytest.raises(ProviderError) as rejected:
                    await client._request(policy().url, candidate | changes, httpx.Headers())
                assert rejected.value.status_code == 400
            assert not sent and not ledger.events
            await client._request(policy().url, candidate, httpx.Headers())
            assert sent == [candidate]
            await client.close()

    asyncio.run(run())


def test_encrypted_reasoning_is_explicit_capability_with_typed_bounded_envelope(tmp_path):
    async def run():
        original = policy()
        enabled = replace(original, allow_encrypted_reasoning_input=True)
        assert enabled.digest != original.digest
        with pytest.raises(ValueError, match="boolean"):
            replace(original, allow_encrypted_reasoning_input="yes")
        reasoning = {
            "type": "reasoning",
            "id": "rs_fixture",
            "summary": [],
            "encrypted_content": "opaque-fixture",
        }
        second_turn = request() | {
            "input": [
                {"role": "user", "content": "first"},
                reasoning,
                {"role": "user", "content": "next"},
            ]
        }
        with pytest.raises(ValueError, match="opaque"):
            original.validate_request(original.url, second_turn)
        with CostLedger(tmp_path / "cost.jsonl", enabled) as ledger:
            sent = []

            async def handler(req):
                sent.append(json.loads(req.content))
                return httpx.Response(200, json=usage())

            client = await client_for(ledger, handler)
            await client._request(enabled.url, request(), httpx.Headers())
            await client._request(enabled.url, second_turn, httpx.Headers())
            assert sent == [request(), second_turn]
            bad_items = [
                reasoning | {"type": "message"},
                reasoning | {"id": 1},
                reasoning | {"encrypted_content": []},
                reasoning | {"encrypted_content": "x" * (8 * 2**20 + 1)},
                reasoning | {"remote_context_id": "unsupported"},
                reasoning | {"summary": [{"type": "summary_text", "text": 123}]},
                reasoning | {"summary": [{"type": "input_image", "text": "bad"}]},
                reasoning | {"status": []},
            ]
            for item in bad_items:
                with pytest.raises(ProviderError) as rejected:
                    await client._request(
                        enabled.url, request() | {"input": [item]}, httpx.Headers()
                    )
                assert rejected.value.status_code == 400
            for field in ("previous_response_id", "conversation"):
                with pytest.raises(ProviderError) as rejected:
                    await client._request(
                        enabled.url, second_turn | {field: "remote"}, httpx.Headers()
                    )
                assert rejected.value.status_code == 400
            assert len(sent) == 2
            await client.close()

    asyncio.run(run())
