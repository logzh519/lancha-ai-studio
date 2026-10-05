"""Anthropic 协议适配：OpenAI chat.completions 格式 ↔ Anthropic messages 格式。"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Mapping

import anthropic
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import (
    Choice as _ChunkChoice,
)
from openai.types.chat.chat_completion_chunk import (
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.completion_usage import CompletionUsage

from platforms.llm.errors import wrap_error

# openai SDK 新版把 function tool call 拆成了独立类型，做兼容导入
try:
    from openai.types.chat import (
        ChatCompletionMessageFunctionToolCall as _ToolCall,
    )
    from openai.types.chat.chat_completion_message_function_tool_call import (
        Function as _Function,
    )
except ImportError:  # 旧版 openai
    from openai.types.chat import ChatCompletionMessageToolCall as _ToolCall
    from openai.types.chat.chat_completion_message_tool_call import (
        Function as _Function,
    )

JSON_MODE_INSTRUCTION = "你必须只输出一个合法的 JSON 对象，不要输出任何其他文字、解释或代码块标记。"

DEFAULT_MAX_TOKENS = 16000

_TOOL_CHOICE_MAP = {"auto": {"type": "auto"}, "required": {"type": "any"},
                    "none": {"type": "none"}}


def _content_text(content) -> str:
    """OpenAI content 可为 str 或 parts 列表，统一取文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content
                       if isinstance(p, dict) and p.get("type") == "text")
    return "" if content is None else str(content)


def _append(messages: list[dict], role: str, blocks: list[dict]) -> None:
    """连续同角色消息合并（Anthropic 要求角色交替）。"""
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(blocks)
    else:
        messages.append({"role": role, "content": blocks})


def convert_request(params: dict) -> dict:
    system_parts: list[str] = []
    out_messages: list[dict] = []

    for m in params["messages"]:
        role = m["role"]
        if role == "system":
            system_parts.append(_content_text(m["content"]))
        elif role == "tool":
            _append(out_messages, "user", [{
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": _content_text(m.get("content")),
            }])
        elif role == "assistant":
            blocks: list[dict] = []
            text = _content_text(m.get("content"))
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or []:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"] or "{}"),
                })
            if blocks:
                _append(out_messages, "assistant", blocks)
        else:  # user
            _append(out_messages, "user",
                    [{"type": "text", "text": _content_text(m["content"])}])

    req: dict = {
        "model": params["model"],
        "max_tokens": params.get("max_tokens") or DEFAULT_MAX_TOKENS,
        "messages": out_messages,
    }

    response_format = params.get("response_format")
    if response_format:
        kind = response_format.get("type")
        if kind == "json_object":
            system_parts.append(JSON_MODE_INSTRUCTION)
        elif kind == "json_schema":
            req["output_config"] = {"format": {
                "type": "json_schema",
                "schema": response_format["json_schema"]["schema"],
            }}

    if system_parts:
        req["system"] = "\n\n".join(system_parts)

    if params.get("tools"):
        req["tools"] = [{
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters")
                            or {"type": "object", "properties": {}},
        } for t in params["tools"]]

    tool_choice = params.get("tool_choice")
    if tool_choice:
        if isinstance(tool_choice, str):
            req["tool_choice"] = _TOOL_CHOICE_MAP[tool_choice]
        else:
            req["tool_choice"] = {"type": "tool",
                                  "name": tool_choice["function"]["name"]}

    for key in ("temperature", "top_p"):
        if params.get(key) is not None:
            req[key] = params[key]

    return req


FINISH_REASON_MAP = {"end_turn": "stop", "max_tokens": "length",
                     "tool_use": "tool_calls", "refusal": "content_filter"}


def convert_response(msg) -> ChatCompletion:
    texts = [b.text for b in msg.content if b.type == "text"]
    tool_calls = [
        _ToolCall(id=b.id, type="function",
                  function=_Function(name=b.name,
                                     arguments=json.dumps(b.input,
                                                          ensure_ascii=False)))
        for b in msg.content if b.type == "tool_use"
    ] or None

    message = ChatCompletionMessage(role="assistant",
                                    content="".join(texts) or None,
                                    tool_calls=tool_calls)
    usage = CompletionUsage(
        prompt_tokens=msg.usage.input_tokens,
        completion_tokens=msg.usage.output_tokens,
        total_tokens=msg.usage.input_tokens + msg.usage.output_tokens,
    )
    return ChatCompletion(
        id=msg.id, object="chat.completion", created=int(time.time()),
        model=msg.model,
        choices=[Choice(index=0, message=message,
                        finish_reason=FINISH_REASON_MAP.get(
                            msg.stop_reason or "end_turn", "stop"))],
        usage=usage,
    )


class _StreamState:
    """逐事件把 Anthropic 流事件转成 OpenAI chunk；同步/异步两个入口复用。"""

    def __init__(self, model: str):
        self.msg_id = "chatcmpl-anthropic"
        self.created = int(time.time())
        self.model = model
        self.tool_index: dict[int, int] = {}  # anthropic block index → openai tool 序号

    def _chunk(self, delta: ChoiceDelta, finish_reason: str | None = None):
        return ChatCompletionChunk(
            id=self.msg_id, object="chat.completion.chunk",
            created=self.created, model=self.model,
            choices=[_ChunkChoice(index=0, delta=delta,
                                  finish_reason=finish_reason)],
        )

    def handle(self, event) -> list[ChatCompletionChunk]:
        etype = event.type
        if etype == "message_start":
            self.msg_id = event.message.id
            self.model = event.message.model
            return [self._chunk(ChoiceDelta(role="assistant", content=""))]
        if etype == "content_block_start" and \
                event.content_block.type == "tool_use":
            openai_idx = len(self.tool_index)
            self.tool_index[event.index] = openai_idx
            return [self._chunk(ChoiceDelta(tool_calls=[ChoiceDeltaToolCall(
                index=openai_idx, id=event.content_block.id, type="function",
                function=ChoiceDeltaToolCallFunction(
                    name=event.content_block.name, arguments=""))]))]
        if etype == "content_block_delta":
            if event.delta.type == "text_delta":
                return [self._chunk(ChoiceDelta(content=event.delta.text))]
            if event.delta.type == "input_json_delta":
                return [self._chunk(ChoiceDelta(tool_calls=[ChoiceDeltaToolCall(
                    index=self.tool_index[event.index],
                    function=ChoiceDeltaToolCallFunction(
                        arguments=event.delta.partial_json))]))]
            return []
        if etype == "message_delta":
            stop_reason = getattr(event.delta, "stop_reason", None)
            return [self._chunk(ChoiceDelta(),
                                finish_reason=FINISH_REASON_MAP.get(
                                    stop_reason or "end_turn", "stop"))]
        return []


def convert_stream(events: Iterable, model: str) -> Iterator[ChatCompletionChunk]:
    state = _StreamState(model)
    for event in events:
        yield from state.handle(event)


async def convert_stream_async(
        events: AsyncIterable, model: str) -> AsyncIterator[ChatCompletionChunk]:
    state = _StreamState(model)
    try:
        async for event in events:
            for chunk in state.handle(event):
                yield chunk
    finally:
        # 无论正常耗尽还是被提前 aclose，都显式释放底层 SDK 流的 HTTP 连接
        closer = getattr(events, "close", None)
        if closer is not None:
            await closer()


class AnthropicProvider:
    def __init__(self, config: Mapping[str, object]):
        self.client = anthropic.Anthropic(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )

    def create(self, **params):
        request = convert_request(params)
        stream = bool(params.get("stream"))
        try:
            if stream:
                events = self.client.messages.create(**request, stream=True)
                return convert_stream(events, model=request["model"])
            message = self.client.messages.create(**request)
        except anthropic.APIError as e:
            raise wrap_error(e) from e
        return convert_response(message)


class AsyncAnthropicProvider:
    """AnthropicProvider 的异步版：同一套请求/响应转换，SDK 客户端换 AsyncAnthropic。"""

    def __init__(self, config: Mapping[str, object]):
        self.client = anthropic.AsyncAnthropic(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )

    async def create(self, **params):
        request = convert_request(params)
        stream = bool(params.get("stream"))
        try:
            if stream:
                events = await self.client.messages.create(**request,
                                                           stream=True)
                return convert_stream_async(events, model=request["model"])
            message = await self.client.messages.create(**request)
        except anthropic.APIError as e:
            raise wrap_error(e) from e
        return convert_response(message)
