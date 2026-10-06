"""Strict provider-owned snapshots; model output remains untrusted data."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from agent_reliability_runtime.contracts.domain import Counter, Identifier, Record


class ToolDefinition(Record):
    name: Identifier
    description: str = ""
    parameters: dict[str, JsonValue]

    @model_validator(mode="after")
    def object_schema(self) -> Self:
        if self.parameters.get("type") != "object":
            raise ValueError("tool parameters must describe a JSON object")
        return self


class ToolCall(Record):
    call_id: Identifier | None = None
    name: Identifier
    arguments: dict[str, JsonValue]


class ChatMessage(Record):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: Identifier | None = None

    @model_validator(mode="after")
    def message_shape(self) -> Self:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages can carry tool calls")
        if self.role == "tool" and self.tool_call_id is None:
            raise ValueError("tool response requires tool_call_id")
        if self.role != "tool" and self.tool_call_id is not None:
            raise ValueError("only tool responses carry tool_call_id")
        if self.content is None and not self.tool_calls:
            raise ValueError("message requires content or tool calls")
        return self


class ModelSettings(Record):
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    max_tokens: Annotated[int, Field(gt=0, strict=True)] | None = None
    seed: Counter | None = None


class ChatRequest(Record):
    messages: Annotated[tuple[ChatMessage, ...], Field(min_length=1)]
    tools: tuple[ToolDefinition, ...] = ()
    settings: ModelSettings = Field(default_factory=ModelSettings)
    # Caller context retained locally; B80 owns telemetry/correlation forwarding.
    trace_context: dict[str, str] = Field(default_factory=dict, repr=False)


class Usage(Record):
    input_tokens: Counter | None = None
    output_tokens: Counter | None = None
    total_tokens: Counter | None = None


class ChatResult(Record):
    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: Identifier
    provider_id: Identifier
    model_id: Identifier
    usage: Usage | None = None
    # No raw provider payloads, reasoning, request IDs or secret-bearing metadata.
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EmbeddingRequest(Record):
    inputs: Annotated[tuple[Identifier, ...], Field(min_length=1)]


class EmbeddingResult(Record):
    provider_id: Identifier
    model_id: Identifier
    vectors: Annotated[tuple[tuple[float, ...], ...], Field(min_length=1)]
    input_tokens: Counter | None = None

    @model_validator(mode="after")
    def uniform_dimension(self) -> Self:
        if not self.vectors[0] or any(
            len(vector) != len(self.vectors[0]) for vector in self.vectors
        ):
            raise ValueError("embedding vectors must have equal nonzero dimension")
        return self

    @property
    def dimension(self) -> int:
        return len(self.vectors[0])


class ChatProvider(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResult: ...


class EmbeddingProvider(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
