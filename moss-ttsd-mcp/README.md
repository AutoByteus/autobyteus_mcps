# 🪐 MOSS-TTSD MCP Server

Model Context Protocol (MCP) server that wraps the bilingual dialogue text-to-speech model [`fnlp/MOSS-TTSD-v0.5`](https://huggingface.co/fnlp/MOSS-TTSD-v0.5). The server lets MCP-compatible assistants synthesize expressive two-speaker conversations (Chinese/English) with optional zero-shot voice cloning support.

## Highlights

- **Two-speaker synthesis** with `[S1]`, `[S2]`, … dialogue tags
- **Voice cloning** by providing shared reference audio + transcript
- **Chinese/English bilingual** generation
- **Long-form output (≤960s)** thanks to the underlying codec
- **Lazy model loading** so quick health checks do not trigger downloads

> **Note:** Downloading the model (~multi-GB) and running inference requires a capable GPU. For CPU-only execution you will likely need to use smaller `max_new_tokens` values and expect much longer generation times.

## Installation

```bash
uv sync  # or: pip install -e .[test]
```

Dependencies include `torch`, `torchaudio`, and `transformers`. Ensure your environment has CUDA, ROCm, or a CPU build of PyTorch that matches your hardware.

## Running the Server

```bash
uv run server.py            # stdio transport
python server.py            # alt entry-point
python -c "from server import mcp; mcp.run(transport='stdio')"
```

### Claude Desktop Example

```json
{
  "mcpServers": {
    "MossTTSD": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/moss-ttsd-mcp",
        "run",
        "server.py"
      ]
    }
  }
}
```

## Tools

| Tool | Description |
| --- | --- |
| `health_check` | Returns basic server information. |
| `script_summary` | Validates a dialogue script and reports speaker counts. |
| `generate_dialogue` | Synthesizes dialogue audio using the MOSS-TTSD model. |

### `generate_dialogue` arguments

| Param | Type | Description |
| --- | --- | --- |
| `script` | `str` | Dialogue with speaker markers, e.g. `[S1]Hi[S2]Hello`. |
| `prompt_audio` | `str?` | Optional path to reference WAV containing both speakers. |
| `prompt_text` | `str?` | Transcript aligned with `prompt_audio`. |
| `base_path` | `str?` | Base directory when the script references audio assets. |
| `output_dir` | `str` | Target directory for generated WAV fragments. |
| `filename_prefix` | `str` | Prefix for generated files (default `dialogue`). |
| `sample_rate` | `int` | Output sample rate (default `24000`). |
| `device_map` | `str` | Passed to `AutoModel.from_pretrained` (default `auto`). |
| `codec_path` | `str` | Hugging Face codec repo (default `fnlp/XY_Tokenizer_TTSD_V0_hf`). |
| `torch_dtype` | `str?` | Optional dtype (`float32`, `bfloat16`, …). |
| `max_new_tokens` | `int?` | Cap for generation length. |
| `dry_run` | `bool` | When `true`, returns the planned payload without inference. |

### Example (voice cloning)

```python
from mcp.client.session import LocalSession
session = LocalSession("uv --directory /path/to/moss-ttsd-mcp run server.py")

script = """
[S1]Welcome back to the show![S2]Thanks! It's great to be here.
[S1]Let's dive into today's topic.[S2]Absolutely—where should we start?
""".strip()

session.call_tool(
    "generate_dialogue",
    {
        "script": script,
        "prompt_audio": "/path/to/reference.wav",
        "prompt_text": "[S1]Reference line[S2]Reference line",
        "output_dir": "outputs/moss_podcast",
        "dry_run": True,  # switch to False to synthesize
    }
)
```

When ready to synthesize, set `dry_run=False`. The tool returns transcript text along with paths to generated WAV fragments (one per utterance).

## Testing

```bash
uv run pytest
```

The bundled tests focus on validation and dry-run logic so they can execute without downloading the full model.

## License

This project reuses the `fnlp/MOSS-TTSD-v0.5` model released under Apache-2.0. See the upstream model card for additional usage guidance.
