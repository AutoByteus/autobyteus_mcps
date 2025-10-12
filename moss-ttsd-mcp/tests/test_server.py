import os
import pytest

import server


def test_analyze_dialogue_script_counts():
    script = "[S1]Hello there.[S2]Hi![S1]How are you?"
    summary = server.analyze_dialogue_script(script)
    assert summary["unique_speakers"] == ["S1", "S2"]
    assert summary["speaker_histogram"]["S1"] == 2
    assert summary["speaker_histogram"]["S2"] == 1
    assert summary["total_markers"] == 3


def test_generate_dialogue_dry_run(tmp_path):
    output_dir = tmp_path / "dialogue_out"
    result = server.generate_dialogue(
        script="[S1]Hello[S2]Hi",
        output_dir=str(output_dir),
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["analysis"]["unique_speakers"] == ["S1", "S2"]
    assert result["output_dir"] == str(output_dir)
    assert result["data_payload"]["text"] == "[S1]Hello[S2]Hi"


def test_generate_dialogue_missing_prompt_audio(tmp_path):
    missing_file = tmp_path / "missing.wav"
    with pytest.raises(FileNotFoundError):
        server.generate_dialogue(
            script="[S1]Hello[S2]Hi",
            prompt_audio=str(missing_file),
            dry_run=True,
        )


def test_generate_dialogue_requires_speaker_tags():
    with pytest.raises(ValueError):
        server.generate_dialogue(script="Hello world", dry_run=True)


def test_script_summary_matches_helper():
    script = "[S1]Hi[S2]Hello"
    assert server.script_summary(script) == server.analyze_dialogue_script(script)
