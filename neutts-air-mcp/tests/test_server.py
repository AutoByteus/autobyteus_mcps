import os
import io
import pytest

import server


def test_health_check_ok():
    hc = server.health_check()
    assert hc["status"] == "ok"
    assert "backbone" in hc
    assert "codec" in hc


def test_text_summary_counts():
    text = "Hello NeuTTS Air, make my day."
    s = server.text_summary(text)
    assert s["chars"] == len(text)
    assert s["words"] == len(text.split())
    assert s["preview"].startswith("Hello")


def test_synthesize_dry_run(tmp_path):
    # Create a dummy reference "wav" file (content not used in dry_run)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFFxxxxWAVEfmt ")  # minimal placeholder bytes

    out = tmp_path / "out.wav"
    plan = server.synthesize(
        text="Clone this voice, please.",
        ref_audio=str(ref),
        ref_text="Clone this voice, please.",
        output_wav=str(out),
        dry_run=True,
    )
    assert plan["dry_run"] is True
    p = plan["plan"]
    assert p["ref_audio"] == str(ref)
    assert p["output_wav"] == str(out)
    assert p["text"].startswith("Clone this voice")


def test_synthesize_missing_ref_audio(tmp_path):
    missing = tmp_path / "nope.wav"
    with pytest.raises(FileNotFoundError):
        server.synthesize(
            text="Hi",
            ref_audio=str(missing),
            ref_text="Hi",
            dry_run=True,
        )