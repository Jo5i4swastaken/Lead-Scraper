# Voice / Realtime Mode

Voice mode lets agents communicate via real-time audio using OpenAI's Realtime API. The agent hears the user speak and responds with speech, while still being able to use tools.

## YAML Configuration

Enable voice mode with `realtime_mode: true` and configure the settings:

```yaml
name: Voice Assistant
model: gpt-realtime
instructions: |
  You are a friendly voice assistant. Keep responses brief and conversational.
welcome_text: "Hi there! I'm your voice assistant."
realtime_mode: true
realtime_settings:
  model_name: gpt-realtime
  voice: alloy
  modalities:
    - audio
  input_audio_format: pcm16
  output_audio_format: pcm16
  turn_detection:
    type: server_vad
    threshold: 0.3
    silence_duration_ms: 200
    prefix_padding_ms: 100
  input_audio_transcription:
    model: whisper-1
tools:
  - get_weather
```

## Settings Reference

### realtime_settings fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_name` | str | `"gpt-realtime"` | Realtime model to use |
| `voice` | str | `"alloy"` | Voice for audio output |
| `modalities` | list | `["audio"]` | `["audio"]`, `["text"]`, or `["audio", "text"]` |
| `input_audio_format` | str | `"pcm16"` | Input audio format |
| `output_audio_format` | str | `"pcm16"` | Output audio format |
| `temperature` | float | `0.8` | Sampling temperature (0.0–2.0) |
| `max_output_tokens` | int | `4096` | Max tokens per response |
| `turn_detection` | dict | see below | Voice activity detection config |
| `input_audio_transcription` | dict | `{"model": "whisper-1"}` | STT config for user audio |

### Voices

`alloy`, `echo`, `shimmer`, `ash`, `ballad`, `coral`, `sage`, `verse`

### Audio formats

| Format | Sample Rate | Notes |
|--------|-------------|-------|
| `pcm16` | 24kHz | 16-bit PCM, recommended default |
| `g711_ulaw` | 8kHz | Telephony (North America) |
| `g711_alaw` | 8kHz | Telephony (Europe) |

Input and output formats can differ.

### Turn detection

Controls when the agent detects the user has finished speaking:

```yaml
turn_detection:
  type: server_vad       # "server_vad" or "semantic_vad"
  threshold: 0.3         # Voice activity threshold (0.0–1.0)
  silence_duration_ms: 200   # How long silence triggers end-of-turn
  prefix_padding_ms: 100     # Audio kept before speech starts
```

## Voice backend types

Set with `voice_backend` in YAML (default: `"realtime"`):

| Backend | Description |
|---------|-------------|
| `realtime` | Direct connection to OpenAI Realtime API. Lower latency. Default. |
| `pipeline` | Routes through the standard agent service with separate STT and TTS steps. Shares chat history with text mode. Requires `pip install 'openai-agents[voice]'`. |

```yaml
voice_backend: "pipeline"  # or "realtime" (default)
```

## Running a voice agent

### Web mode (browser UI)

```bash
omniagents run -c agent.yml --mode web
```

The web UI detects `realtime_mode: true` and enables the microphone interface automatically.

### Server mode (programmatic)

```bash
omniagents run -c agent.yml --mode server --port 9494
```

Voice uses a **separate WebSocket endpoint**: `ws://127.0.0.1:9494/ws/realtime` (not `/ws`).

## Server WebSocket API

### RPC methods (client → server)

#### start_session

```json
{
  "jsonrpc": "2.0", "id": "1",
  "method": "start_session",
  "params": {"session_id": "optional-custom-id"}
}
```

Response: `{"session_id": "...", "run_id": "..."}`

#### send_audio

Send base64-encoded audio chunks as they are captured from the microphone:

```json
{
  "jsonrpc": "2.0", "id": "2",
  "method": "send_audio",
  "params": {
    "session_id": "session-123",
    "audio_base64": "SUQzBAAAAAAAI1RTU0U..."
  }
}
```

#### send_text

Send text input (only works if modalities includes `"text"`):

```json
{
  "jsonrpc": "2.0", "id": "3",
  "method": "send_text",
  "params": {
    "session_id": "session-123",
    "text": "What's the weather like?"
  }
}
```

#### interrupt

Stop the agent mid-speech:

```json
{
  "jsonrpc": "2.0", "id": "4",
  "method": "interrupt",
  "params": {"session_id": "session-123"}
}
```

#### stop_session

End the session (audio and history are preserved):

```json
{
  "jsonrpc": "2.0", "id": "5",
  "method": "stop_session",
  "params": {"session_id": "session-123"}
}
```

#### get_session_info / list_sessions

Query active sessions:

```json
{"jsonrpc": "2.0", "id": "6", "method": "get_session_info", "params": {"session_id": "session-123"}}
{"jsonrpc": "2.0", "id": "7", "method": "list_sessions", "params": {}}
```

### Streaming events (server → client)

All events arrive as `realtime_event` notifications:

```json
{
  "jsonrpc": "2.0",
  "method": "realtime_event",
  "params": {
    "type": "realtime_audio",
    ...
  }
}
```

#### Event types

| Event | Description |
|-------|-------------|
| `realtime_turn_started` | Agent started processing a turn |
| `realtime_turn_ended` | Agent finished a turn |
| `realtime_audio` | Audio output chunk (base64, with `delta_ms` duration) |
| `realtime_transcript` | Transcription of user speech (`role: "user"`) or agent speech (`role: "assistant"`) |
| `realtime_tool_called` | Agent is calling a tool (includes `tool_name` and `arguments`) |
| `realtime_tool_completed` | Tool returned a result |
| `realtime_tool_failed` | Tool execution failed |
| `realtime_handoff` | Agent handing off to another agent |
| `realtime_handoff_agent_start` | New agent starting after handoff |
| `realtime_handoff_agent_end` | Previous agent ended after handoff |
| `realtime_guardrail_tripped` | Guardrail triggered (`blocked: true/false`) |
| `realtime_error` | Error during session |

## Tools in voice sessions

Tools work normally during voice conversations. The agent can call any tool listed in the YAML config. The flow is:

1. Agent decides to call a tool → `realtime_tool_called` event
2. Tool executes on the server
3. Result returned → `realtime_tool_completed` event
4. Agent continues speaking with the result

## Instruction tips for voice agents

Voice agents need different instructions than text agents — the output is spoken, not read:

- Keep responses short and conversational
- No markdown, URLs, or special characters
- Use natural transitions ("First...", "Also...", "One more thing...")
- Spell out numbers and abbreviations ("seventy-two degrees" not "72°F")
- Acknowledge the user naturally ("Sure!", "Great question.")

## Dynamic settings with a resolver

For runtime configuration (e.g., choosing voice based on user preferences), use a resolver function in a `.py` file in the agent directory:

```python
from omniagents.core.config.loader import realtime_settings_resolver

@realtime_settings_resolver
def resolve_realtime_settings() -> dict:
    return {
        "model_name": "gpt-realtime",
        "voice": "echo",
        "temperature": 0.6,
    }
```

Reference it in YAML:
```yaml
realtime_settings_resolver: resolve_realtime_settings
```

## Audio storage

Audio is automatically saved during realtime sessions:

- **Files**: `{base_path}/{project_slug}/{agent_slug}/audio/{session_id}/{session_id}_{item_id}_{content_index}.{format}`
- **Metadata**: SQLite table `audio_metadata` with session_id, item_id, content_index, file_path, audio_format, duration_ms
