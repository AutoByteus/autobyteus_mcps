import os

import pytest

import server

PROMPT_AUDIO_ENV = "MOSS_TTSD_PROMPT_AUDIO"
PROMPT_TEXT_ENV = "MOSS_TTSD_PROMPT_TEXT"
BASE_PATH_ENV = "MOSS_TTSD_BASE_PATH"
SCRIPT_ENV = "MOSS_TTSD_SCRIPT"
MAX_TOKENS_ENV = "MOSS_TTSD_MAX_NEW_TOKENS"


@pytest.mark.skipif(
    PROMPT_AUDIO_ENV not in os.environ or PROMPT_TEXT_ENV not in os.environ,
    reason="Set MOSS_TTSD_PROMPT_AUDIO and MOSS_TTSD_PROMPT_TEXT for integration test",
)
def test_generate_dialogue_integration(tmp_path):
    prompt_audio = os.environ[PROMPT_AUDIO_ENV]
    prompt_text = os.environ[PROMPT_TEXT_ENV]
    base_path = os.environ.get(BASE_PATH_ENV)
    script = os.environ.get(
        SCRIPT_ENV,
        "[S1]Welcome back![S2]Glad to be here.[S1]Let's get started.",
    )
    max_new_tokens = os.environ.get(MAX_TOKENS_ENV)

    kwargs = {
        "script": script,
        "prompt_audio": prompt_audio,
        "prompt_text": prompt_text,
        "output_dir": str(tmp_path),
        "dry_run": False,
    }
    if base_path:
        kwargs["base_path"] = base_path
    if max_new_tokens:
        kwargs["max_new_tokens"] = int(max_new_tokens)

    result = server.generate_dialogue(**kwargs)

    assert result["audio_files"], "Expected at least one generated audio fragment"
    for file_path in result["audio_files"]:
        assert os.path.exists(file_path), f"Missing generated audio file: {file_path}"
    assert result["transcripts"], "Model should return decoded transcript(s)"
    assert "S1" in result["analysis"]["unique_speakers"], "Script analysis missing speaker S1"
    assert "S2" in result["analysis"]["unique_speakers"], "Script analysis missing speaker S2"
