import ffmpeg
import os
import re
import tempfile
import shutil
import subprocess

from core import mcp, resolve_path, _get_media_properties

@mcp.tool()
def trim_video(video_path: str, output_video_path: str, start_time: str, end_time: str) -> str:
    """Trims a video to the specified start and end times."""
    video_path = resolve_path(video_path)
    output_video_path = resolve_path(output_video_path)
    try:
        input_stream = ffmpeg.input(video_path, ss=start_time, to=end_time)
        output_stream = input_stream.output(output_video_path, c='copy') 
        output_stream.run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"Video trimmed successfully (codec copy) to {output_video_path}"
    except ffmpeg.Error as e:
        error_message_copy = e.stderr.decode('utf8') if e.stderr else str(e)
        try:
            input_stream_recode = ffmpeg.input(video_path, ss=start_time, to=end_time)
            output_stream_recode = input_stream_recode.output(output_video_path)
            output_stream_recode.run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Video trimmed successfully (re-encoded) to {output_video_path}"
        except ffmpeg.Error as e_recode:
            error_message_recode = e_recode.stderr.decode('utf8') if e_recode.stderr else str(e_recode)
            return f"Error trimming video. Copy attempt: {error_message_copy}. Re-encode attempt: {error_message_recode}"
    except FileNotFoundError:
        return f"Error: Input video file not found at {video_path}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@mcp.tool()
def concatenate_videos(video_paths: list[str], output_video_path: str,
                       transition_effect: str = None, transition_duration: float = None) -> str:
    """Concatenates multiple video files into a single output file.
    This tool intelligently handles clips with different resolutions and frame rates.
    Supports optional xfade transition when concatenating exactly two videos.

    Args:
        video_paths: A list of paths to the video files to concatenate.
        output_video_path: The path to save the concatenated video file.
        transition_effect (str, optional): The xfade transition type. Only applied if exactly two videos are provided.
        transition_duration (float, optional): The duration of the xfade transition in seconds. Required if transition_effect is specified.
    
    Returns:
        A status message indicating success or failure.
    """
    video_paths = [resolve_path(p) for p in video_paths]
    output_video_path = resolve_path(output_video_path)
    if not video_paths:
        return "Error: No video paths provided for concatenation."
    if len(video_paths) < 1:
        return "Error: At least one video is required."
    
    for video_path in video_paths:
        if not os.path.exists(video_path):
            return f"Error: Input video file not found at {video_path}"

    if len(video_paths) == 1:
        try:
            ffmpeg.input(video_paths[0]).output(output_video_path, vcodec='libx264', acodec='aac').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            return f"Single video processed and saved to {output_video_path}"
        except ffmpeg.Error as e:
            return f"Error processing single video: {e.stderr.decode('utf8') if e.stderr else str(e)}"

    if transition_effect:
        if len(video_paths) > 2:
            return f"Error: xfade transition is currently only supported for exactly two videos. Found {len(video_paths)} videos."
        if transition_duration is None or transition_duration <= 0:
            return "Error: A positive transition_duration is required when transition_effect is specified."

        temp_dir = tempfile.mkdtemp()
        try:
            prepared_clips_info = []
            max_width = 0
            max_height = 0
            target_sample_rate = 0

            for i, video_path in enumerate(video_paths):
                props = _get_media_properties(video_path)
                if not props['has_video']:
                    return f"Error: Input file at {video_path} does not contain a video stream."

                max_width = max(max_width, props.get('width', 0))
                max_height = max(max_height, props.get('height', 0))
                target_sample_rate = max(target_sample_rate, props.get('sample_rate', 44100))

                final_path = video_path
                if not props.get('has_audio'):
                    temp_path = os.path.join(temp_dir, f"xfade_prepared_{i}.mp4")
                    try:
                        subprocess.run([
                            'ffmpeg', '-i', video_path, '-f', 'lavfi',
                            '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                            '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-y', temp_path
                        ], check=True, capture_output=True)
                        final_path = temp_path
                    except subprocess.CalledProcessError as e:
                        return f"Error adding silent audio to {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}"
                    props = _get_media_properties(final_path)

                prepared_clips_info.append({'path': final_path, 'props': props})

            if len(prepared_clips_info) != 2:
                return "Error: xfade transition requires exactly two valid video clips."
            if max_width == 0 or max_height == 0:
                return "Error: Unable to determine video dimensions for xfade transition."
            if target_sample_rate <= 0:
                target_sample_rate = 44100

            first_clip_duration = float(prepared_clips_info[0]['props'].get('duration', 0.0))
            offset = first_clip_duration - float(transition_duration)
            if offset <= 0:
                return "Error: transition_duration must be shorter than the first video's duration."

            stream_a = ffmpeg.input(prepared_clips_info[0]['path'])
            stream_b = ffmpeg.input(prepared_clips_info[1]['path'])

            def _prepare_video(stream):
                return (
                    stream
                    .filter('scale', width=max_width, height=max_height, force_original_aspect_ratio='decrease')
                    .filter('pad', width=max_width, height=max_height, x='(ow-iw)/2', y='(oh-ih)/2', color='black')
                    .filter('setsar', '1')
                    .filter('format', 'yuv420p')
                )

            def _prepare_audio(stream):
                audio = stream.filter('aresample', sample_rate=target_sample_rate)
                audio = audio.filter('aformat', channel_layouts='stereo', sample_rates=target_sample_rate)
                return audio.filter('asetpts', 'PTS-STARTPTS')

            video_a = _prepare_video(stream_a.video)
            video_b = _prepare_video(stream_b.video)
            audio_a = _prepare_audio(stream_a.audio)
            audio_b = _prepare_audio(stream_b.audio)

            xfade_video = ffmpeg.filter(
                [video_a, video_b],
                'xfade',
                transition=transition_effect,
                duration=transition_duration,
                offset=offset
            )
            cross_audio = ffmpeg.filter(
                [audio_a, audio_b],
                'acrossfade',
                d=transition_duration
            )

            ffmpeg.output(
                xfade_video,
                cross_audio,
                output_video_path,
                vcodec='libx264',
                acodec='aac'
            ).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)

            return f"Videos concatenated successfully with '{transition_effect}' transition to {output_video_path}"

        except ffmpeg.Error as e:
            error_message = e.stderr.decode('utf8') if e.stderr else str(e)
            return f"Error during xfade concatenation: {error_message}"
        except Exception as e:
            return f"An unexpected error occurred during xfade concatenation: {str(e)}"
        finally:
            shutil.rmtree(temp_dir)

    temp_dir = tempfile.mkdtemp()
    try:
        # Step 1: Prepare clips and determine target normalization values
        prepared_clips_info = []
        max_width = 0
        max_height = 0
        target_fps = 0.0
        target_sample_rate = 0

        for i, video_path in enumerate(video_paths):
            props = _get_media_properties(video_path)
            if not props['has_video']:
                continue

            if props['width'] > max_width:
                max_width = props['width']
            if props['height'] > max_height:
                max_height = props['height']
            if props.get('avg_fps', 0):
                target_fps = max(target_fps, float(props['avg_fps']))
            if props.get('sample_rate', 0):
                target_sample_rate = max(target_sample_rate, int(props['sample_rate']))
            
            final_path = video_path
            if not props['has_audio']:
                temp_path = os.path.join(temp_dir, f"prepared_{i}.mp4")
                try:
                    subprocess.run([
                        'ffmpeg', '-i', video_path, '-f', 'lavfi',
                        '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                        '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-y', temp_path
                    ], check=True, capture_output=True)
                    final_path = temp_path
                except subprocess.CalledProcessError as e:
                    return f"Error adding silent audio to {video_path}: {e.stderr.decode('utf8') if e.stderr else str(e)}"
                props = _get_media_properties(temp_path)

            # Refresh normalization metrics after any preprocessing
            if props.get('avg_fps', 0):
                target_fps = max(target_fps, float(props['avg_fps']))
            if props.get('sample_rate', 0):
                target_sample_rate = max(target_sample_rate, int(props['sample_rate']))
            if props['width'] > max_width:
                max_width = props['width']
            if props['height'] > max_height:
                max_height = props['height']
            
            prepared_clips_info.append({'path': final_path})

        if len(prepared_clips_info) < 2:
             return f"Error: Not enough valid video clips to concatenate after preparation."

        if max_width == 0 or max_height == 0:
            return "Error: Unable to determine target resolution for concatenation."

        if target_fps <= 0:
            target_fps = 30.0
        if target_sample_rate <= 0:
            target_sample_rate = 44100

        # Step 2: Create pre-processed input streams with normalized resolution
        processed_streams = []
        for clip in prepared_clips_info:
            stream = ffmpeg.input(clip['path'])
            video_stream = (
                stream.video
                .filter('fps', fps=target_fps)
                .filter('scale', width=max_width, height=max_height, force_original_aspect_ratio='decrease')
                .filter('pad', width=max_width, height=max_height, x='(ow-iw)/2', y='(oh-ih)/2', color='black')
                .filter('setsar', '1')
                .filter('setpts', 'PTS-STARTPTS')
            )
            processed_streams.append(video_stream)
            audio_stream = (
                stream.audio
                .filter('aresample', sample_rate=target_sample_rate)
                .filter('aformat', channel_layouts='stereo', sample_rates=target_sample_rate)
                .filter('asetpts', 'PTS-STARTPTS')
            )
            processed_streams.append(audio_stream)
        
        # Step 3: Concatenate the processed streams
        concatenated_node = ffmpeg.concat(*processed_streams, v=1, a=1).node
        video_out = concatenated_node[0]
        audio_out = concatenated_node[1]

        # Step 4: Output the final video
        ffmpeg.output(video_out, audio_out, output_video_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"Videos concatenated successfully to {output_video_path}"

    except ffmpeg.Error as e:
        error_message = e.stderr.decode('utf8') if e.stderr else str(e)
        return f"Error during concatenation process: {error_message}"
    except Exception as e:
        return f"An unexpected error occurred during standard concatenation: {str(e)}"
    finally:
        shutil.rmtree(temp_dir)

@mcp.tool()
def concatenate_audios(audio_paths: list[str], output_audio_path: str) -> str:
    """Concatenates multiple audio files into a single output file."""
    audio_paths = [resolve_path(p) for p in audio_paths]
    output_audio_path = resolve_path(output_audio_path)
    
    if not audio_paths:
        return "Error: No audio paths provided for concatenation."
        
    for audio_path in audio_paths:
        if not os.path.exists(audio_path):
            return f"Error: Input audio file not found at {audio_path}"

    temp_dir = tempfile.mkdtemp()
    try:
        normalized_clips = []
        for i, path in enumerate(audio_paths):
            normalized_path = os.path.join(temp_dir, f"norm_{i}.wav")
            (
                ffmpeg.input(path)
                .output(normalized_path, ar=48000, ac=2, format='wav')
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
            normalized_clips.append(ffmpeg.input(normalized_path))
        
        concatenated_audio = ffmpeg.concat(*normalized_clips, v=0, a=1)
        
        concatenated_audio.output(output_audio_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        
        return f"Audios concatenated successfully to {output_audio_path}"

    except ffmpeg.Error as e:
        error_message = e.stderr.decode('utf8') if e.stderr else str(e)
        return f"Error concatenating audios: {error_message}"
    except Exception as e:
        return f"An unexpected error occurred during audio concatenation: {str(e)}"
    finally:
        shutil.rmtree(temp_dir)

@mcp.tool()
def change_video_speed(video_path: str, output_video_path: str, speed_factor: float) -> str:
    """Changes the playback speed of a video (and its audio, if present)."""
    video_path = resolve_path(video_path)
    output_video_path = resolve_path(output_video_path)
    if speed_factor <= 0:
        return "Error: Speed factor must be positive."
    if not os.path.exists(video_path):
        return f"Error: Input video file not found at {video_path}"

    try:
        props = _get_media_properties(video_path)
        has_audio = props.get('has_audio', False)

        input_stream = ffmpeg.input(video_path)
        video = input_stream.video.setpts(f"{1.0/speed_factor}*PTS")
        
        output_streams = [video]

        if has_audio:
            atempo_value = speed_factor
            atempo_filters_values = []
            
            if speed_factor < 0.5:
                while atempo_value < 0.5:
                    atempo_filters_values.append(0.5)
                    atempo_value *= 2
                if atempo_value < 0.99:
                    atempo_filters_values.append(atempo_value)
            elif speed_factor > 2.0:
                while atempo_value > 2.0:
                    atempo_filters_values.append(2.0)
                    atempo_value /= 2
                if atempo_value > 1.01:
                    atempo_filters_values.append(atempo_value)
            else:
                atempo_filters_values.append(speed_factor)
            
            audio = input_stream.audio
            for val in atempo_filters_values:
                audio = audio.filter("atempo", val)
            
            output_streams.append(audio)
        
        output = ffmpeg.output(*output_streams, output_video_path)
        output.run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        
        return f"Video speed changed by factor {speed_factor} and saved to {output_video_path}"
    except (ffmpeg.Error, RuntimeError) as e:
        error_message = e.stderr.decode('utf8') if hasattr(e, 'stderr') and e.stderr else str(e)
        return f"Error changing video speed: {error_message}"
    except Exception as e:
        return f"An unexpected error occurred while changing video speed: {str(e)}"

@mcp.tool()
def remove_silence(media_path: str, output_media_path: str, 
                   silence_threshold_db: float = -30.0, 
                   min_silence_duration_ms: int = 500) -> str:
    """Removes silent segments from an audio or video file."""
    media_path = resolve_path(media_path)
    output_media_path = resolve_path(output_media_path)
    if not os.path.exists(media_path):
        return f"Error: Input media file not found at {media_path}"
    if min_silence_duration_ms <= 0:
        return "Error: Minimum silence duration must be positive."

    min_silence_duration_s = min_silence_duration_ms / 1000.0

    try:
        silence_detection_process = (
            ffmpeg
            .input(media_path)
            .filter('silencedetect', n=f'{silence_threshold_db}dB', d=min_silence_duration_s)
            .output('-', format='null')
            .run_async(pipe_stderr=True)
        )
        _, stderr_bytes = silence_detection_process.communicate()
        stderr_str = stderr_bytes.decode('utf8')

        silence_starts = [float(x) for x in re.findall(r"silence_start: (\d+\.?\d*)", stderr_str)]
        silence_ends = [float(x) for x in re.findall(r"silence_end: (\d+\.?\d*)", stderr_str)]

        if not silence_starts:
            try:
                ffmpeg.input(media_path).output(output_media_path, c='copy').run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
                return f"No significant silences detected. Original media copied to {output_media_path}."
            except ffmpeg.Error as e_copy:
                 return f"No significant silences detected, but error copying original file: {e_copy.stderr.decode('utf8') if e_copy.stderr else str(e_copy)}"

        probe = ffmpeg.probe(media_path)
        total_duration = float(probe['format']['duration'])

        sound_segments = []
        current_pos = 0.0
        for i in range(len(silence_starts)):
            start_silence = silence_starts[i]
            end_silence = silence_ends[i] if i < len(silence_ends) else total_duration

            if start_silence > current_pos:
                sound_segments.append((current_pos, start_silence))
            current_pos = end_silence
        
        if current_pos < total_duration:
            sound_segments.append((current_pos, total_duration))
        
        if not sound_segments:
            return f"Error: No sound segments were identified to keep. The media might be entirely silent."

        video_select_filter_parts = [f'between(t,{start},{end})' for start, end in sound_segments]
        audio_select_filter_parts = [f'between(t,{start},{end})' for start, end in sound_segments]
        video_select_expr = "+".join(video_select_filter_parts)
        audio_select_expr = "+".join(audio_select_filter_parts)

        input_media = ffmpeg.input(media_path)
        
        has_video = any(s['codec_type'] == 'video' for s in probe['streams'])
        has_audio = any(s['codec_type'] == 'audio' for s in probe['streams'])

        output_streams = []
        if has_video:
            processed_video = input_media.video.filter('select', video_select_expr).filter('setpts', 'PTS-STARTPTS')
            output_streams.append(processed_video)
        if has_audio:
            processed_audio = input_media.audio.filter('aselect', audio_select_expr).filter('asetpts', 'PTS-STARTPTS')
            output_streams.append(processed_audio)
        
        if not output_streams:
            return "Error: The input media does not have video or audio streams."

        ffmpeg.output(*output_streams, output_media_path).run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        return f"Silent segments removed. Output saved to {output_media_path}"

    except ffmpeg.Error as e:
        error_message = e.stderr.decode('utf8') if e.stderr else str(e)
        return f"Error removing silence: {error_message}"
    except Exception as e:
        return f"An unexpected error occurred while removing silence: {str(e)}"
