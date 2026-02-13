#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
from pathlib import Path
import statistics
import sys
import time
import wave

from tts_mcp.config import load_settings
from tts_mcp.runner import run_speak


@dataclass(frozen=True)
class ModelCase:
    preset: str
    model_id: str
    default_instruct: str | None


@dataclass(frozen=True)
class TextCase:
    name: str
    text: str


MODEL_CASES: tuple[ModelCase, ...] = (
    ModelCase("kokoro_fast", "mlx-community/Kokoro-82M-bf16", None),
    ModelCase("qwen_base_hq", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16", None),
    ModelCase(
        "qwen_voicedesign_hq",
        "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
        "A warm calm assistant voice with clear articulation and natural pacing",
    ),
)

TEXT_CASES: tuple[TextCase, ...] = (
    TextCase("short", "Hello, this is a quick model latency check."),
    TextCase(
        "medium",
        (
            "Hello, this is a practical speech benchmark for everyday assistant replies. "
            "We want to measure how long generation takes for a normal sentence length "
            "that users hear many times per session."
        ),
    ),
)


def _audio_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        frame_count = handle.getnframes()
        sample_rate = handle.getframerate()
    return frame_count / float(sample_rate)


def _percentile_95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    index = int(round(0.95 * (len(sorted_values) - 1)))
    return sorted_values[index]


def _run_one(
    model_case: ModelCase,
    text_case: TextCase,
    run_idx: int,
    output_dir: Path,
) -> dict[str, object]:
    output_path = output_dir / f"{model_case.preset}_{text_case.name}_{run_idx}.wav"
    if output_path.exists():
        output_path.unlink()

    settings_env = {
        "TTS_MCP_BACKEND": "mlx_audio",
        "TTS_MCP_TIMEOUT_SECONDS": "1200",
        "TTS_MCP_OUTPUT_DIR": str(output_dir),
        "TTS_MCP_MLX_MODEL_PRESET": model_case.preset,
        "MLX_TTS_MODEL": model_case.model_id,
        # Version checks are intentionally disabled for benchmark consistency.
        "TTS_MCP_ENFORCE_LATEST": "false",
    }
    if model_case.default_instruct:
        settings_env["MLX_TTS_DEFAULT_INSTRUCT"] = model_case.default_instruct

    settings = load_settings(settings_env)

    started = time.perf_counter()
    result = run_speak(
        settings=settings,
        text=text_case.text,
        output_path=str(output_path),
        play=False,
    )
    elapsed = time.perf_counter() - started

    if not result["ok"]:
        raise RuntimeError(
            f"Benchmark run failed for {model_case.preset}/{text_case.name}: "
            f"{result['error_type']} {result['error_message']}"
        )

    duration_s = _audio_duration_seconds(output_path)
    size_bytes = output_path.stat().st_size

    return {
        "elapsed_s": elapsed,
        "audio_duration_s": duration_s,
        "rtf": elapsed / max(duration_s, 1e-9),
        "output_size_bytes": size_bytes,
    }


def _benchmark_model_text_case(
    model_case: ModelCase,
    text_case: TextCase,
    warmup_runs: int,
    measure_runs: int,
    output_dir: Path,
) -> dict[str, object]:
    for warmup_idx in range(warmup_runs):
        _run_one(
            model_case=model_case,
            text_case=text_case,
            run_idx=-(warmup_idx + 1),
            output_dir=output_dir,
        )

    measured_runs: list[dict[str, object]] = []
    for run_idx in range(measure_runs):
        measured_runs.append(
            _run_one(
                model_case=model_case,
                text_case=text_case,
                run_idx=run_idx,
                output_dir=output_dir,
            )
        )

    latencies = [float(item["elapsed_s"]) for item in measured_runs]
    audio_durations = [float(item["audio_duration_s"]) for item in measured_runs]
    rtfs = [float(item["rtf"]) for item in measured_runs]

    return {
        "model_preset": model_case.preset,
        "model_id": model_case.model_id,
        "text_case": text_case.name,
        "text_char_count": len(text_case.text),
        "runs": measure_runs,
        "latency_s": {
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
            "p95_approx": _percentile_95(latencies),
            "min": min(latencies),
            "max": max(latencies),
        },
        "audio_duration_s": {
            "mean": statistics.fmean(audio_durations),
            "median": statistics.median(audio_durations),
        },
        "rtf": {
            "mean": statistics.fmean(rtfs),
            "median": statistics.median(rtfs),
        },
    }


def _build_markdown_summary(results: list[dict[str, object]]) -> str:
    lines = [
        "| Model | Text | Mean Latency (s) | Median (s) | Approx P95 (s) | Mean Audio (s) | Mean RTF |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        latency = row["latency_s"]  # type: ignore[assignment]
        duration = row["audio_duration_s"]  # type: ignore[assignment]
        rtf = row["rtf"]  # type: ignore[assignment]
        lines.append(
            "| "
            f"{row['model_preset']} | {row['text_case']} | "
            f"{latency['mean']:.2f} | {latency['median']:.2f} | {latency['p95_approx']:.2f} | "
            f"{duration['mean']:.2f} | {rtf['mean']:.2f} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark MLX models via tts_mcp.run_speak")
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measure-runs", type=int, default=3)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("benchmark") / "mlx_performance_latest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark") / "audio_outputs",
    )
    args = parser.parse_args()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict[str, object]] = []
    for text_case in TEXT_CASES:
        for model_case in MODEL_CASES:
            result = _benchmark_model_text_case(
                model_case=model_case,
                text_case=text_case,
                warmup_runs=args.warmup_runs,
                measure_runs=args.measure_runs,
                output_dir=args.output_dir,
            )
            all_results.append(result)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_version": sys.version.split()[0],
            "mlx_audio_version": importlib.metadata.version("mlx-audio"),
        },
        "config": {
            "warmup_runs": args.warmup_runs,
            "measure_runs": args.measure_runs,
        },
        "results": all_results,
        "markdown_summary": _build_markdown_summary(all_results),
    }

    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote benchmark results to {args.output_json}")
    print()
    print(payload["markdown_summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
