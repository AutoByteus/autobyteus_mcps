"""MOSS-TTSD MCP server.

This server exposes a minimal set of tools that wrap the fnlp/MOSS-TTSD-v0.5
bilingual dialogue TTS model so that MCP-compatible clients can synthesize
spoken dialogues. Heavy model components are loaded lazily to keep the process
fast for health checks and validation utilities.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP

try:  # torch/transformers are large optional dependencies
    import torch
    from transformers import AutoModel, AutoProcessor
except ModuleNotFoundError:  # pragma: no cover - exercised only when deps missing
    torch = None  # type: ignore
    AutoModel = None  # type: ignore
    AutoProcessor = None  # type: ignore

try:
    import torchaudio
except ModuleNotFoundError:  # pragma: no cover
    torchaudio = None  # type: ignore

DEFAULT_MODEL_ID = "fnlp/MOSS-TTSD-v0.5"
DEFAULT_CODEC_ID = "fnlp/XY_Tokenizer_TTSD_V0_hf"
DEFAULT_SAMPLE_RATE = 24_000
SPEAKER_TOKEN_PATTERN = re.compile(r"\[S(\d+)\]")

mcp = FastMCP("MossTTSDServer")


def resolve_path(path: Optional[str]) -> Optional[str]:
    """Resolves relative paths against AUTOBYTEUS_AGENT_WORKSPACE when present."""
    if path is None or path == "":
        return None
    if os.path.isabs(path):
        return path
    workspace = os.getenv("AUTOBYTEUS_AGENT_WORKSPACE")
    if workspace:
        return os.path.join(workspace, path)
    return os.path.abspath(path)


def ensure_dependencies() -> None:
    """Raises a helpful error when optional heavy dependencies are missing."""
    missing = []
    if AutoModel is None or AutoProcessor is None:
        missing.append("transformers")
    if torch is None:
        missing.append("torch")
    if torchaudio is None:
        missing.append("torchaudio")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Missing runtime dependencies: "
            f"{joined}. Install them with `uv sync` or `pip install -r requirements`."
        )


def _parse_torch_dtype(dtype_name: Optional[str]) -> Optional[torch.dtype]:
    if dtype_name is None:
        return None
    if torch is None:
        raise RuntimeError("torch is required to set torch_dtype")
    normalized = dtype_name.lower()
    mapping = {
        "float32": torch.float32,
        "fp32": torch.float32,
        "float16": torch.float16,
        "fp16": torch.float16,
        "half": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    if normalized not in mapping:
        raise ValueError(
            "Unsupported torch_dtype requested. Choose one of: "
            + ", ".join(sorted(set(mapping.keys())))
        )
    return mapping[normalized]


@lru_cache(maxsize=4)
def load_processor(model_id: str, codec_path: str) -> Any:
    ensure_dependencies()
    return AutoProcessor.from_pretrained(
        model_id,
        codec_path=codec_path,
        trust_remote_code=True,
    )


@lru_cache(maxsize=2)
def load_model(
    model_id: str,
    device_map: str = "auto",
    torch_dtype: Optional[str] = None,
) -> Any:
    ensure_dependencies()
    dtype = _parse_torch_dtype(torch_dtype) if torch_dtype else None
    model = AutoModel.from_pretrained(
        model_id,
        trust_remote_code=True,
        device_map=device_map,
        torch_dtype=dtype,
    )
    return model.eval()


def analyze_dialogue_script(script: str) -> Dict[str, Any]:
    """Returns basic analytics for a dialogue script with speaker tags."""
    if not script or not script.strip():
        raise ValueError("Dialogue script is empty")
    tokens = SPEAKER_TOKEN_PATTERN.findall(script)
    if not tokens:
        raise ValueError(
            "Dialogue script must include speaker markers like [S1] and [S2]"
        )
    unique_indices = sorted({int(tok) for tok in tokens})
    return {
        "unique_speakers": [f"S{idx}" for idx in unique_indices],
        "total_markers": len(tokens),
        "speaker_histogram": {
            f"S{idx}": sum(1 for tok in tokens if int(tok) == idx)
            for idx in unique_indices
        },
    }


def _normalize_audio_tensor(fragment: Any) -> Any:
    if torch is None or not hasattr(fragment, "dim"):
        return fragment
    tensor = fragment
    if tensor.dim() == 1:
        tensor = tensor.unsqueeze(0)
    return tensor


@mcp.tool()
def health_check() -> Dict[str, str]:
    """Returns basic server health metadata."""
    return {
        "status": "ok",
        "model_id": DEFAULT_MODEL_ID,
    }


@mcp.tool()
def script_summary(script: str) -> Dict[str, Any]:
    """Analyzes a dialogue script and returns speaker statistics."""
    return analyze_dialogue_script(script)


@mcp.tool()
def generate_dialogue(
    script: str,
    prompt_audio: Optional[str] = None,
    prompt_text: Optional[str] = None,
    base_path: Optional[str] = None,
    output_dir: str = "outputs",
    filename_prefix: str = "dialogue",
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    device_map: str = "auto",
    codec_path: str = DEFAULT_CODEC_ID,
    torch_dtype: Optional[str] = None,
    max_new_tokens: Optional[int] = None,
    dry_run: bool = False,
    context: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generates dialogue speech audio for the provided script using MOSS-TTSD.

    Args:
        script: Dialogue content with speaker tags, e.g. ``[S1]Hello[S2]Hi``.
        prompt_audio: Optional reference audio (wav) containing both speakers.
        prompt_text: Optional reference transcript aligned with ``prompt_audio``.
        base_path: Base path for locating prompt audio files referenced in script.
        output_dir: Directory to store generated wav fragments.
        filename_prefix: Prefix for generated wav files, defaults to ``dialogue``.
        sample_rate: Output sample rate, default ``24000`` per model docs.
        device_map: Passed to ``AutoModel.from_pretrained`` device placement.
        codec_path: Hugging Face repo slug for the codec tokenizer.
        torch_dtype: Optional dtype string, e.g. ``"bfloat16"``.
        max_new_tokens: Optional cap for generation length.
        dry_run: When ``True`` skips model loading and returns planned actions.
        context: MCP execution context (unused, injected automatically).
    """
    analysis = analyze_dialogue_script(script)

    resolved_prompt_audio = resolve_path(prompt_audio)
    resolved_base_path = resolve_path(base_path)
    resolved_output_dir = resolve_path(output_dir) or os.getcwd()

    data_payload = {
        "text": script,
    }
    if resolved_base_path:
        data_payload["base_path"] = resolved_base_path
    if resolved_prompt_audio:
        if not os.path.exists(resolved_prompt_audio):
            raise FileNotFoundError(
                f"Prompt audio not found at {resolved_prompt_audio}"
            )
        data_payload["prompt_audio"] = resolved_prompt_audio
    if prompt_text:
        data_payload["prompt_text"] = prompt_text

    if dry_run:
        return {
            "dry_run": True,
            "analysis": analysis,
            "output_dir": resolved_output_dir,
            "data_payload": data_payload,
        }

    ensure_dependencies()

    processor = load_processor(DEFAULT_MODEL_ID, codec_path)
    model = load_model(DEFAULT_MODEL_ID, device_map=device_map, torch_dtype=torch_dtype)

    os.makedirs(resolved_output_dir, exist_ok=True)

    inputs = processor([data_payload])
    model_inputs = {}
    for key, value in inputs.items():
        if hasattr(value, "to") and torch is not None:
            model_inputs[key] = value.to(model.device)  # type: ignore[attr-defined]
        else:
            model_inputs[key] = value

    generate_kwargs: Dict[str, Any] = {}
    if max_new_tokens is not None:
        generate_kwargs["max_new_tokens"] = max_new_tokens

    token_ids = model.generate(**model_inputs, **generate_kwargs)
    decoded_texts, audio_fragments = processor.batch_decode(token_ids)

    saved_files: List[str] = []
    for sample_idx, sample_fragments in enumerate(audio_fragments):
        for fragment_idx, fragment in enumerate(sample_fragments):
            normalized = _normalize_audio_tensor(fragment)
            if torchaudio is None:
                raise RuntimeError("torchaudio is required to save generated audio")
            file_path = os.path.join(
                resolved_output_dir,
                f"{filename_prefix}_{sample_idx}_{fragment_idx}.wav",
            )
            torchaudio.save(file_path, normalized.cpu(), sample_rate)  # type: ignore[union-attr]
            saved_files.append(file_path)

    return {
        "transcripts": decoded_texts,
        "audio_files": saved_files,
        "analysis": analysis,
    }


if __name__ == "__main__":
    mcp.run()
