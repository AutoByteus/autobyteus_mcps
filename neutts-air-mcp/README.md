# 🗣️ NeuTTS Air MCP Server

Model Context Protocol (MCP) server wrapping **Neuphonic NeuTTS Air** for local, realistic TTS with **instant voice cloning**.

* Upstream GitHub: `neuphonic/neutts-air`
* Model card: `neuphonic/neutts-air` on Hugging Face
* Runs on **CPU**, **CUDA (NVIDIA)**, or **MPS (Apple Silicon)**

> NeuTTS Air Python usage and examples are documented upstream. This server exposes a small tool surface to integrate with MCP-compatible assistants.

## Features

* `synthesize` tool: text → WAV using a short **reference audio + transcript**
* `text_summary` tool: quick validation/stats for input text
* `health_check` tool: sanity check + defaults
* **Dry-run** mode to preview the synthesis plan without loading models

## Install

### System prerequisite (espeak for phonemizer)

```bash
# macOS (Homebrew)
brew install espeak

# Ubuntu/Debian
sudo apt update && sudo apt install -y espeak
```

> On macOS, if phonemizer cannot find the espeak library, you may need to set the dynamic library path as shown upstream.

### Python environment

Use your preferred manager; examples below use `pip`:

```bash
cd autobyteus_mcps/neutts-air-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .[test]
```

This installs:

* `neuttsair` (from the official Git repository)
* `torch`/`torchaudio` (choose a build matching your GPU/OS)
* `soundfile`, `phonemizer`, and MCP CLI

### GPU notes

* **NVIDIA**: install a CUDA-enabled PyTorch build. `torch.cuda.is_available()` should be `True`.
* **Apple Silicon (M1/M2/M3)**: use the PyTorch nightly or stable with **MPS**; this server auto-selects `mps` when available.
* **CPU-only** works, but generation is slower.

## Run the server

```bash
# stdio transport
python server.py

# or via uv
uv run server.py
```

### Claude Desktop example

```json
{
  "mcpServers": {
    "NeuTTSAir": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/autobyteus_mcps/neutts-air-mcp", "run", "server.py"]
    }
  }
}
```

## Tools

### `health_check()`

Returns basic metadata and defaults.

### `text_summary(text: str)`

Validates non-empty text and returns length stats.

### `synthesize(...)`

**Args**

* `text`: text to speak
* `ref_audio`: path to a short mono WAV (3–15s, 16–44kHz)
* `ref_text`: transcript of the reference audio
* `output_wav`: path to write the synthesized audio (default `outputs/neutts_air_out.wav`)
* `backbone_repo`: default `neuphonic/neutts-air`
* `codec_repo`: default `neuphonic/neucodec`
* `backbone_device`: `auto` (default), `cuda`, `mps`, or `cpu`
* `codec_device`: same choices; default follows backbone
* `sample_rate`: default `24000`
* `dry_run`: when `true`, returns the planned payload without loading models

**Example (dry-run)**

```python
from mcp.client.session import LocalSession
session = LocalSession("uv --directory /abs/path/to/autobyteus_mcps/neutts-air-mcp run server.py")

plan = session.call_tool("synthesize", {
  "text": "Hello from NeuTTS Air.",
  "ref_audio": "samples/dave.wav",
  "ref_text": open("samples/dave.txt").read().strip(),
  "output_wav": "outputs/hello.wav",
  "dry_run": True
})
print(plan)
```

**Example (synthesize)**

```python
result = session.call_tool("synthesize", {
  "text": "This is a cloned voice speaking with NeuTTS Air.",
  "ref_audio": "samples/dave.wav",
  "ref_text": open("samples/dave.txt").read().strip(),
  "output_wav": "outputs/hello.wav",
  "backbone_device": "cuda"  # or "mps" on Apple Silicon, "cpu" otherwise
})
print(result["output_wav"])
```

## References

* NeuTTS Air GitHub and README (usage, examples, dependencies)
* NeuTTS Air Hugging Face model card and collection
* Notes on GGUF / llama-cpp / ONNX alternatives are available upstream.