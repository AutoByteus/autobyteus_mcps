"""NeuTTS Air MCP server.

Wraps the Neuphonic NeuTTS Air model with MCP tools to synthesize speech
with instant voice cloning using a reference audio + transcript.

References:

* GitHub: [https://github.com/neuphonic/neutts-air](https://github.com/neuphonic/neutts-air)
* HF model card: neuphonic/neutts-air
  """
  from **future** import annotations

import os
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP, Context

# Heavy, optional deps are imported lazily to keep health checks fast

try:
import soundfile as sf  # type: ignore
except ModuleNotFoundError:
sf = None  # type: ignore

DEFAULT_BACKBONE = "neuphonic/neutts-air"
DEFAULT_CODEC = "neuphonic/neucodec"
DEFAULT_SR = 24_000

mcp = FastMCP("NeuTTSAirServer")

def _resolve_path(path: Optional[str]) -> Optional[str]:
if not path:
return None
if os.path.isabs(path):
return path
base = os.getenv("AUTOBYTEUS_AGENT_WORKSPACE")
return os.path.join(base, path) if base else os.path.abspath(path)

def _ensure_runtime(import_model: bool = False) -> None:
"""Raise clear errors if optional deps are missing."""
missing = []
# soundfile is always needed when not dry-running
if sf is None:
missing.append("soundfile")
if import_model:
try:
from neuttsair.neutts import NeuTTSAir  # noqa: F401
except ModuleNotFoundError:
missing.append("neuttsair (pip install 'neuttsair @ git+[https://github.com/neuphonic/neutts-air](https://github.com/neuphonic/neutts-air)')")
# Torch is required for the PyTorch path; ONNX/GGUF paths are optional at runtime.
try:
import torch  # noqa: F401
except ModuleNotFoundError:
missing.append("torch")
if missing:
raise RuntimeError(
"Missing runtime dependencies: "
+ ", ".join(missing)
+ ". Please install the required packages."
)

@mcp.tool()
def health_check() -> Dict[str, str]:
"""Return basic server health and defaults."""
return {
"status": "ok",
"backbone": DEFAULT_BACKBONE,
"codec": DEFAULT_CODEC,
"default_sample_rate": str(DEFAULT_SR),
}

@mcp.tool()
def text_summary(text: str) -> Dict[str, Any]:
"""Validate input text and return simple stats."""
if not text or not text.strip():
raise ValueError("Text to synthesize must be non-empty.")
words = [w for w in text.strip().split() if w]
return {
"chars": len(text),
"words": len(words),
"preview": text.strip()[:120],
}

@mcp.tool()
def synthesize(
text: str,
ref_audio: str,
ref_text: str,
output_wav: str = "outputs/neutts_air_out.wav",
backbone_repo: str = DEFAULT_BACKBONE,
codec_repo: str = DEFAULT_CODEC,
backbone_device: str = "auto",
codec_device: str = "auto",
sample_rate: int = DEFAULT_SR,
dry_run: bool = False,
context: Optional[Context] = None,
) -> Dict[str, Any]:
"""Synthesize speech using NeuTTS Air with instant voice cloning.

```
Args:
    text: Text to synthesize.
    ref_audio: Path to reference .wav file (mono, 16-44kHz, 3-15s).
    ref_text: Transcript of the reference audio (plain text).
    output_wav: Target path for generated audio.
    backbone_repo: HF repo for the backbone (PyTorch or GGUF).
    codec_repo: HF repo for the codec.
    backbone_device: 'cuda', 'mps', 'cpu', or 'auto' to pick best available.
    codec_device: device string for codec (often same as backbone).
    sample_rate: Output sample rate (default 24000 per model docs).
    dry_run: If True, skip model load and return planned actions.

Returns:
    Dict including 'dry_run' flag or 'output_wav' on success and a small summary.
"""
# Basic validation & resolution
if not text or not text.strip():
    raise ValueError("Argument 'text' must be non-empty.")
resolved_ref_audio = _resolve_path(ref_audio)
resolved_output_wav = _resolve_path(output_wav) or os.path.abspath("neutts_air_out.wav")
if not resolved_ref_audio or not os.path.exists(resolved_ref_audio):
    raise FileNotFoundError(f"Reference audio not found: {ref_audio}")

plan = {
    "text": text,
    "ref_audio": resolved_ref_audio,
    "ref_text": ref_text.strip() if ref_text else "",
    "output_wav": resolved_output_wav,
    "backbone_repo": backbone_repo,
    "codec_repo": codec_repo,
    "backbone_device": backbone_device,
    "codec_device": codec_device,
    "sample_rate": sample_rate,
}

# Dry-run path
if dry_run:
    return {"dry_run": True, "plan": plan}

_ensure_runtime(import_model=True)

# Lazy import after checks
from neuttsair.neutts import NeuTTSAir  # type: ignore

# Auto device selection if requested
if backbone_device == "auto":
    dev = "cpu"
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            dev = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dev = "mps"
    except Exception:
        pass
    backbone_device = dev
if codec_device == "auto":
    codec_device = backbone_device

# Initialize model
tts = NeuTTSAir(
    backbone_repo=backbone_repo,
    backbone_device=backbone_device,
    codec_repo=codec_repo,
    codec_device=codec_device,
)

# Encode reference & synthesize
ref_codes = tts.encode_reference(resolved_ref_audio)
wav = tts.infer(text, ref_codes, plan["ref_text"])

# Ensure directory exists and write file
os.makedirs(os.path.dirname(resolved_output_wav), exist_ok=True)
if sf is None:
    raise RuntimeError("soundfile is required to save WAV output.")
sf.write(resolved_output_wav, wav, sample_rate)

return {
    "output_wav": resolved_output_wav,
    "sample_rate": sample_rate,
    "device": backbone_device,
    "summary": {
        "chars": len(text),
        "preview": text[:120],
    },
}
```

if **name** == "**main**":
mcp.run() 