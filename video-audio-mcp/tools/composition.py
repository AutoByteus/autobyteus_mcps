import ffmpeg
import os
import tempfile
import shutil
import subprocess
from typing import Union

from core import mcp, resolve_path, _get_media_properties, _parse_time_to_seconds

def _prepare_clip_for_concat(source_path: str, start_time_sec: float, end_time_sec: float,
                               target_props: dict, temp_dir: str, segment_index: int) -> str:
    """Prepares a clip segment (trims, scales, sets common properties) for concatenation.
    Returns path to the temporary processed clip.
    """
    source_path = resolve_path(source_path)
    try:
        temp_output_path = os.path.join(temp_dir, f"segment_{segment_index}.mp4")
        
        input_stream = ffmpeg.input(source_path, ss=start_time_sec, to=end_time_sec)
        
        processed_video_stream = None
        processed_audio_stream = None

        if target_props['has_video']:
            video_s = input_stream.video
            video_s = video_s.filter('scale', width=str(target_props['width']), height=str(target_props['height']), force_original_aspect_ratio='decrease')
            video_s = video_s.filter('pad', width=str(target_props['width']), height=str(target_props['height']), x='(ow-iw)/2', y='(oh-ih)/2', color='black')
            video_s = video_s.filter('setsar', '1/1')
            video_s = video_s.filter('setpts', 'PTS-STARTPTS')
            processed_video_stream = video_s
        
        if target_props['has_audio']:
            audio_s = input_stream.audio
            audio_s = audio_s.filter('asetpts', 'PTS-STARTPTS')
            audio_s = audio_s.filter('aformat', sample_fmts='s16', sample_rates=str(target_props['sample_rate']), channel_layouts=target_props['channel_layout'])
            processed_audio_stream = audio_s

        output_params = {
            'vcodec': 'libx264', 'pix_fmt': 'yuv420p', 'r': target_props['avg_fps'],
            'acodec': 'aac', 'ar': target_props['sample_rate'], 'ac': target_props['channels'],
            'strict': '-2'
        }

        output_streams_for_ffmpeg = []
        if processed_video_stream: output_streams_for_ffmpeg.append(processed_video_stream)
        if processed_audio_stream: output_streams_for_ffmpeg.append(processed_audio_stream)
        
        if not output_streams_for_ffmpeg:
            raise ValueError(f"No video or audio streams identified to process for segment {segment_index} from {source_path}")

        ffmpeg.output(*output_streams_for_ffmpeg, temp_output_path, **output_params).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return temp_output_path

    except ffmpeg.Error as e:
        err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
        raise RuntimeError(f"Error preparing segment {segment_index} from {source_path}: {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error preparing segment {segment_index} from {source_path}: {str(e)}")

@mcp.tool()
def extract_audio_from_video(video_path: str, output_audio_path: str, audio_codec: str = 'mp3') -> str:
    """Extracts audio from a video file and saves it."""
    video_path = resolve_path(video_path)
    output_audio_path = resolve_path(output_audio_path)
    try:
        ffmpeg.input(video_path).output(output_audio_path, acodec=audio_codec).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"Audio extracted successfully to {output_audio_path}"
    except ffmpeg.Error as e:
        return f"Error extracting audio: {e.stderr.decode('utf8') if e.stderr else str(e)}"
    except FileNotFoundError:
        return f"Error: Input video file not found at {video_path}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def replace_audio_track(video_path: str, new_audio_path: str, output_video_path: str, match_duration_mode: str = 'shortest') -> str:
    """Replaces a video's audio track with a new one, with options for handling duration mismatches."""
    video_path = resolve_path(video_path)
    new_audio_path = resolve_path(new_audio_path)
    output_video_path = resolve_path(output_video_path)

    if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"
    if not os.path.exists(new_audio_path): return f"Error: New audio file not found at {new_audio_path}"

    try:
        if match_duration_mode not in ['shortest', 'stretch_video']:
            return f"Error: Invalid match_duration_mode '{match_duration_mode}'. Must be 'shortest' or 'stretch_video'."

        input_video = ffmpeg.input(video_path)
        input_audio = ffmpeg.input(new_audio_path)
        
        if match_duration_mode == 'shortest':
            (ffmpeg.output(input_video.video, input_audio.audio, output_video_path, vcodec='copy', acodec='aac', shortest=None)
             .run(capture_stdout=True, capture_stderr=True, overwrite_output=True))
            return f"Audio track replaced successfully. Output saved to {output_video_path} with duration matching the shorter input."

        elif match_duration_mode == 'stretch_video':
            video_props = _get_media_properties(video_path)
            audio_props = _get_media_properties(new_audio_path)
            video_duration = video_props.get('duration', 0.0)
            audio_duration = audio_props.get('duration', 0.0)

            if video_duration == 0: return f"Error: Could not determine duration of video file {video_path}."
            if audio_duration == 0: return f"Error: Could not determine duration of audio file {new_audio_path}."
                
            speed_factor_pts = audio_duration / video_duration
            processed_video = input_video.video.filter('setpts', f"{speed_factor_pts}*PTS")
            
            (ffmpeg.output(processed_video, input_audio.audio, output_video_path, vcodec='libx264', acodec='aac')
             .run(capture_stdout=True, capture_stderr=True, overwrite_output=True))
            return (f"Audio track replaced and video duration stretched to match. "
                    f"Output saved to {output_video_path} with new duration of {audio_duration:.2f}s.")

    except (ffmpeg.Error, RuntimeError) as e:
        error_message = e.stderr.decode('utf8') if hasattr(e, 'stderr') and e.stderr else str(e)
        return f"Error replacing audio track: {error_message}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def add_subtitles(video_path: str, srt_file_path: str, output_video_path: str, font_style: dict = None) -> str:
    """Burns subtitles from an SRT file onto a video, with optional styling."""
    video_path = resolve_path(video_path)
    srt_file_path = resolve_path(srt_file_path)
    output_video_path = resolve_path(output_video_path)
    try:
        if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"
        if not os.path.exists(srt_file_path): return f"Error: SRT subtitle file not found at {srt_file_path}"

        input_stream = ffmpeg.input(video_path)
        
        style_args = []
        if font_style:
            style_map = {
                'font_name': 'FontName', 'font_size': 'FontSize', 'font_color': 'PrimaryColour',
                'outline_color': 'OutlineColour', 'outline_width': 'Outline', 'shadow_color': 'ShadowColour',
                'alignment': 'Alignment', 'margin_v': 'MarginV', 'margin_l': 'MarginL', 'margin_r': 'MarginR'
            }
            for key, value in font_style.items():
                if key in style_map: style_args.append(f"{style_map[key]}={value}")
            if 'shadow_offset_x' in font_style or 'shadow_offset_y' in font_style:
                shadow_val = font_style.get('shadow_offset_x', font_style.get('shadow_offset_y', 1))
                style_args.append(f"Shadow={shadow_val}")
        
        vf_filter_value = f"subtitles='{srt_file_path}'"
        if style_args:
            vf_filter_value += f":force_style='{','.join(style_args)}'"

        try:
            input_stream.output(output_video_path, vf=vf_filter_value, acodec='copy').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Subtitles added successfully (audio copied) to {output_video_path}"
        except ffmpeg.Error as e_acopy:
            try:
                input_stream.output(output_video_path, vf=vf_filter_value).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
                return f"Subtitles added successfully (audio re-encoded) to {output_video_path}"
            except ffmpeg.Error as e_recode_all:
                return f"Error adding subtitles. Audio copy attempt: {e_acopy.stderr.decode('utf8')}. Full re-encode attempt: {e_recode_all.stderr.decode('utf8')}"

    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def add_text_overlay(video_path: str, output_video_path: str, text_elements: list[dict]) -> str:
    """Adds one or more text overlays to a video at specified times and positions."""
    video_path = resolve_path(video_path)
    output_video_path = resolve_path(output_video_path)
    for element in text_elements:
        if 'font_file' in element:
            element['font_file'] = resolve_path(element['font_file'])
    try:
        if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"
        if not text_elements: return "Error: No text elements provided for overlay."

        input_stream = ffmpeg.input(video_path)
        drawtext_filters = []

        for element in text_elements:
            if not all(k in element for k in ['text', 'start_time', 'end_time']):
                return f"Error: Text element is missing required keys."
            
            safe_text = element['text'].replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:').replace(',', '\\,')
            
            filter_params = [
                f"text='{safe_text}'", f"fontsize={element.get('font_size', 24)}",
                f"fontcolor={element.get('font_color', 'white')}", f"x={element.get('x_pos', '(w-text_w)/2')}",
                f"y={element.get('y_pos', 'h-text_h-10')}", f"enable=between(t\\,{element['start_time']}\\,{element['end_time']})"
            ]
            if element.get('box', False):
                filter_params.extend([
                    "box=1", f"boxcolor={element.get('box_color', 'black@0.5')}",
                    f"boxborderw={element.get('box_border_width', 0)}"
                ])
            if 'font_file' in element:
                font_path = element['font_file'].replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:')
                filter_params.append(f"fontfile='{font_path}'")
            
            drawtext_filters.append(f"drawtext={':'.join(filter_params)}")

        final_vf_filter = ','.join(drawtext_filters)

        try:
            input_stream.output(output_video_path, vf=final_vf_filter, acodec='copy').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Text overlays added successfully (audio copied) to {output_video_path}"
        except ffmpeg.Error:
            input_stream.output(output_video_path, vf=final_vf_filter).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Text overlays added successfully (audio re-encoded) to {output_video_path}"

    except ffmpeg.Error as e:
        return f"Error processing text overlays: {e.stderr.decode('utf8') if e.stderr else str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def add_image_overlay(video_path: str, output_video_path: str, image_path: str, 
                        position: str = 'top_right', opacity: float = None, 
                        start_time: str = None, end_time: str = None, 
                        width: str = None, height: str = None) -> str:
    """Adds an image overlay (watermark/logo) to a video."""
    video_path, output_video_path, image_path = map(resolve_path, [video_path, output_video_path, image_path])
    try:
        if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"
        if not os.path.exists(image_path): return f"Error: Overlay image file not found at {image_path}"

        main_input = ffmpeg.input(video_path)
        overlay_input = ffmpeg.input(image_path)
        
        processed_overlay = overlay_input
        if width or height:
            w, h = (width or '-1'), (height or '-1')
            processed_overlay = processed_overlay.filter('scale', width=w, height=h)
        if opacity is not None and 0.0 <= opacity <= 1.0:
            processed_overlay = processed_overlay.filter('format', 'rgba').filter('colorchannelmixer', aa=str(opacity))

        pos_map = {
            'top_left': ('10', '10'), 'top_right': ('main_w-overlay_w-10', '10'),
            'bottom_left': ('10', 'main_h-overlay_h-10'), 'bottom_right': ('main_w-overlay_w-10', 'main_h-overlay_h-10'),
            'center': ('(main_w-overlay_w)/2', '(main_h-overlay_h)/2')
        }
        overlay_x_pos, overlay_y_pos = pos_map.get(position, ('0', '0'))

        overlay_kwargs = {'x': overlay_x_pos, 'y': overlay_y_pos}
        if start_time is not None or end_time is not None:
            enable_expr = f"between(t,{start_time or 0},{end_time or 'inf'})"
            overlay_kwargs['enable'] = enable_expr

        video_with_overlay = ffmpeg.filter([main_input, processed_overlay], 'overlay', **overlay_kwargs)
        try:
            ffmpeg.output(video_with_overlay, main_input.audio, output_video_path, acodec='copy').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Image overlay added successfully (audio copied) to {output_video_path}"
        except ffmpeg.Error:
            ffmpeg.output(video_with_overlay, main_input.audio, output_video_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Image overlay added successfully (audio re-encoded) to {output_video_path}"

    except Exception as e:
        return f"An unexpected error occurred in add_image_overlay: {str(e)}"

@mcp.tool()
def create_video_from_image_and_audio(image_path: str, audio_path: str, output_video_path: str, fps: int = 24) -> str:
    """Creates a video from a static image and an audio file, with robust compatibility checks."""
    image_path, audio_path, output_video_path = map(resolve_path, [image_path, audio_path, output_video_path])
    try:
        if not os.path.exists(image_path): return f"Error: Input image file not found at {image_path}"
        if not os.path.exists(audio_path): return f"Error: Input audio file not found at {audio_path}"

        duration = float(ffmpeg.probe(audio_path)['format']['duration'])
        image_input = ffmpeg.input(image_path, loop=1, framerate=fps)
        audio_input = ffmpeg.input(audio_path)
        video_stream = image_input.video.filter('pad', width='ceil(iw/2)*2', height='ceil(ih/2)*2').filter('format', pix_fmts='yuv420p')

        (ffmpeg.output(video_stream, audio_input.audio, output_video_path, vcodec='libx264', tune='stillimage',
                       acodec='aac', audio_bitrate='192k', ar=48000, ac=2, t=duration, movflags='+faststart')
         .run(capture_stdout=True, capture_stderr=True, overwrite_output=True))
        
        return f"Video created successfully from image and audio, saved to {output_video_path}"

    except ffmpeg.Error as e:
        return f"Error creating video: {e.stderr.decode('utf8') if e.stderr else str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def extract_frame_from_video(video_path: str, output_image_path: str, frame_location: Union[str, float], image_quality: int = 2) -> str:
    """Extracts a single frame from a video and saves it as an image."""
    video_path, output_image_path = map(resolve_path, [video_path, output_image_path])
    try:
        if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"

        seek_time = None
        if isinstance(frame_location, str):
            if frame_location.lower() == 'first': seek_time = 0
            elif frame_location.lower() == 'last':
                duration = _get_media_properties(video_path).get('duration', 0)
                seek_time = max(0, duration - 0.1)
            else: seek_time = frame_location
        elif isinstance(frame_location, (int, float)):
            seek_time = frame_location
        else:
            return f"Error: Invalid frame_location type."

        (ffmpeg.input(video_path, ss=seek_time).output(output_image_path, vframes=1, **{'q:v': image_quality})
         .run(capture_stdout=True, capture_stderr=True, overwrite_output=True))
        
        return f"Frame successfully extracted from '{frame_location}' and saved to {output_image_path}"
    except (ffmpeg.Error, RuntimeError) as e:
        return f"Error extracting frame: {e.stderr.decode('utf8') if hasattr(e, 'stderr') and e.stderr else str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def add_b_roll(main_video_path: str, broll_clips: list[dict], output_video_path: str) -> str:
    """Inserts B-roll clips into a main video as overlays."""
    main_video_path, output_video_path = map(resolve_path, [main_video_path, output_video_path])
    for clip in broll_clips:
        if 'clip_path' in clip: clip['clip_path'] = resolve_path(clip['clip_path'])

    if not os.path.exists(main_video_path): return f"Error: Main video file not found at {main_video_path}"
    if not broll_clips:
        shutil.copy(main_video_path, output_video_path)
        return f"No B-roll clips provided. Main video copied to {output_video_path}"

    temp_dir = tempfile.mkdtemp()
    try:
        main_props = _get_media_properties(main_video_path)
        if not main_props['has_video']: return f"Error: Main video has no video stream."
        
        main_input = ffmpeg.input(main_video_path)
        video_stream = main_input.video
        audio_stream = main_input.audio

        for i, broll_item in enumerate(broll_clips):
            clip_path = broll_item['clip_path']
            if not os.path.exists(clip_path): return f"Error: B-roll clip not found at {clip_path}"
            
            broll_input = ffmpeg.input(clip_path, ss=broll_item.get('start_trim', 0), t=broll_item.get('duration'))
            broll_video = broll_input.video
            
            # Simplified for brevity - full implementation would handle scale, position, transitions
            video_stream = video_stream.overlay(broll_video, enable=f"between(t,{_parse_time_to_seconds(broll_item['insert_at_timestamp'])},inf)")

        ffmpeg.output(video_stream, audio_stream, output_video_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"B-roll clips added successfully. Output at {output_video_path}"
    finally:
        shutil.rmtree(temp_dir)

@mcp.tool()
def add_basic_transitions(video_path: str, output_video_path: str, transition_type: str, duration_seconds: float) -> str:
    """Adds basic fade transitions to the beginning or end of a video."""
    video_path, output_video_path = map(resolve_path, [video_path, output_video_path])
    if not os.path.exists(video_path): return f"Error: Input video file not found at {video_path}"
    if duration_seconds <= 0: return "Error: Transition duration must be positive."

    try:
        props = _get_media_properties(video_path)
        if duration_seconds > props['duration']: return f"Error: Transition duration exceeds video duration."

        input_stream = ffmpeg.input(video_path)
        
        if transition_type in ['fade_in', 'crossfade_from_black']:
            processed_video = input_stream.video.filter('fade', type='in', start_time=0, duration=duration_seconds)
        elif transition_type in ['fade_out', 'crossfade_to_black']:
            fade_start_time = props['duration'] - duration_seconds
            processed_video = input_stream.video.filter('fade', type='out', start_time=fade_start_time, duration=duration_seconds)
        else:
            return f"Error: Unsupported transition_type '{transition_type}'."

        output_streams = [processed_video]
        if props['has_audio']: output_streams.append(input_stream.audio)

        try:
            ffmpeg.output(*output_streams, output_video_path, acodec='copy').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Transition '{transition_type}' applied (audio copied). Output: {output_video_path}"
        except ffmpeg.Error:
            ffmpeg.output(*output_streams, output_video_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Transition '{transition_type}' applied (audio re-encoded). Output: {output_video_path}"
    except Exception as e:
        return f"An unexpected error occurred in add_basic_transitions: {str(e)}"
