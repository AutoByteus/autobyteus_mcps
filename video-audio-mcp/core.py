import ffmpeg
import os
from mcp.server.fastmcp import FastMCP

# --- Central MCP Instance ---
# All tools will be registered against this instance.
mcp = FastMCP("VideoAudioServer")

# --- Shared Helper Functions ---

def resolve_path(path: str) -> str:
    """Resolves a path to an absolute path using AUTOBYTEUS_AGENT_WORKSPACE if available."""
    if not isinstance(path, str) or os.path.isabs(path):
        return path
    
    workspace = os.getenv('AUTOBYTEUS_AGENT_WORKSPACE')
    if workspace:
        return os.path.join(workspace, path)
    
    return path

def _run_ffmpeg_with_fallback(input_path: str, output_path: str, primary_kwargs: dict, fallback_kwargs: dict) -> str:
    """Helper to run ffmpeg command with primary kwargs, falling back to other kwargs on ffmpeg.Error."""
    input_path = resolve_path(input_path)
    output_path = resolve_path(output_path)
    try:
        ffmpeg.input(input_path).output(output_path, **primary_kwargs).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"Operation successful (primary method) and saved to {output_path}"
    except ffmpeg.Error as e_primary:
        try:
            ffmpeg.input(input_path).output(output_path, **fallback_kwargs).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Operation successful (fallback method) and saved to {output_path}"
        except ffmpeg.Error as e_fallback:
            err_primary_msg = e_primary.stderr.decode('utf8') if e_primary.stderr else str(e_primary)
            err_fallback_msg = e_fallback.stderr.decode('utf8') if e_fallback.stderr else str(e_fallback)
            return f"Error. Primary method failed: {err_primary_msg}. Fallback method also failed: {err_fallback_msg}"
    except FileNotFoundError:
        return f"Error: Input file not found at {input_path}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

def _parse_time_to_seconds(time_str: str) -> float:
    """Converts HH:MM:SS.mmm or seconds string to float seconds."""
    if isinstance(time_str, (int, float)):
        return float(time_str)
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            raise ValueError(f"Invalid time format: {time_str}")
    return float(time_str)

def _get_media_properties(media_path: str) -> dict:
    """Probes media file and returns key properties."""
    media_path = resolve_path(media_path)
    try:
        probe = ffmpeg.probe(media_path)
        video_stream_info = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
        audio_stream_info = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
        
        props = {
            'duration': float(probe['format'].get('duration', 0.0)),
            'has_video': video_stream_info is not None,
            'has_audio': audio_stream_info is not None,
            'width': int(video_stream_info['width']) if video_stream_info and 'width' in video_stream_info else 0,
            'height': int(video_stream_info['height']) if video_stream_info and 'height' in video_stream_info else 0,
            'avg_fps': 0, # Default, will be calculated if possible
            'sample_rate': int(audio_stream_info['sample_rate']) if audio_stream_info and 'sample_rate' in audio_stream_info else 44100,
            'channels': int(audio_stream_info['channels']) if audio_stream_info and 'channels' in audio_stream_info else 2,
            'channel_layout': audio_stream_info.get('channel_layout', 'stereo') if audio_stream_info else 'stereo'
        }
        if video_stream_info and 'avg_frame_rate' in video_stream_info and video_stream_info['avg_frame_rate'] != '0/0':
            num, den = map(int, video_stream_info['avg_frame_rate'].split('/'))
            if den > 0:
                props['avg_fps'] = num / den
            else:
                props['avg_fps'] = 30 # Default if denominator is 0
        else: # Fallback if avg_frame_rate is not useful
            props['avg_fps'] = 30 # A common default

        return props
    except ffmpeg.Error as e:
        raise RuntimeError(f"Error probing file {media_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error probing file {media_path}: {str(e)}")
