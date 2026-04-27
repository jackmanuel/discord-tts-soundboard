"""
Soundboard Generator Module

Handles generation and caching of special soundboard sounds:
- "all": All sounds mixed/overlaid simultaneously (with volume boost)
- "seq": All sounds played sequentially (trimmed to N seconds each)

Generated files are stored in soundboard/generated/ with naming like:
  all_10.opus, all_5.opus, all_full.opus, seq_1.opus, seq_2.opus, etc.
"""

import os
import asyncio
import subprocess

from logger_config import bot_logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDBOARD_DIR = os.path.join(BASE_DIR, "soundboard")
GENERATED_DIR = os.path.join(SOUNDBOARD_DIR, "generated")

# Default durations
DEFAULT_ALL_DURATION = 10  # seconds per sound for "all"
DEFAULT_SEQ_DURATION = 1   # seconds per sound for "seq"

# Volume boost for "all" mix (in dB). amix tends to reduce volume heavily.
ALL_VOLUME_BOOST_DB = 6


def get_real_sounds():
    """Get list of real soundboard sound file paths (excluding generated/special ones)."""
    if not os.path.exists(SOUNDBOARD_DIR):
        return []
    
    files = []
    for f in sorted(os.listdir(SOUNDBOARD_DIR)):
        if f.endswith('.opus') and os.path.isfile(os.path.join(SOUNDBOARD_DIR, f)):
            files.append(os.path.join(SOUNDBOARD_DIR, f))
    return files


def get_real_sound_names():
    """Get list of real soundboard sound names (without extension)."""
    return [os.path.splitext(os.path.basename(f))[0].lower() for f in get_real_sounds()]


def _ensure_generated_dir():
    """Ensure the generated directory exists."""
    os.makedirs(GENERATED_DIR, exist_ok=True)


def _get_cached_path(sound_type, duration_key):
    """Get the path for a cached generated sound.
    
    Args:
        sound_type: "all" or "seq"
        duration_key: integer seconds or "full"
    """
    return os.path.join(GENERATED_DIR, f"{sound_type}_{duration_key}.opus")


def get_cached_variants():
    """Get all cached variant files in the generated directory."""
    if not os.path.exists(GENERATED_DIR):
        return []
    return [f for f in os.listdir(GENERATED_DIR) if f.endswith('.opus')]


def is_cached(sound_type, duration_key):
    """Check if a specific variant is already cached."""
    return os.path.exists(_get_cached_path(sound_type, duration_key))


def _generate_all_sound_sync(duration_key):
    """Generate the 'all' sound synchronously (overlay all sounds).
    
    Args:
        duration_key: integer seconds or "full" for no trimming
    """
    _ensure_generated_dir()
    sound_files = get_real_sounds()
    
    if not sound_files:
        bot_logger.warning("SoundboardGenerator: No sounds to mix for 'all'")
        return None
    
    output_path = _get_cached_path("all", duration_key)
    n = len(sound_files)
    
    # Build ffmpeg command with amix
    cmd = ['ffmpeg', '-y']
    
    # Add inputs with optional duration trim
    for f in sound_files:
        if duration_key != "full":
            cmd.extend(['-t', str(duration_key)])
        cmd.extend(['-i', f])
    
    # Build the filter: amix all inputs, then boost volume
    # amix with duration=longest so the full mix plays  
    # Then apply volume boost to compensate for amix attenuation
    filter_parts = []
    filter_parts.append(
        f"amix=inputs={n}:duration=longest:normalize=0,volume={ALL_VOLUME_BOOST_DB}dB"
    )
    
    cmd.extend([
        '-filter_complex', filter_parts[0],
        '-c:a', 'libopus',
        output_path
    ])
    
    bot_logger.info(f"SoundboardGenerator: Generating 'all' (duration={duration_key}) with {n} sounds")
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            bot_logger.error(f"SoundboardGenerator: ffmpeg error generating 'all': {result.stderr.decode()}")
            return None
        bot_logger.info(f"SoundboardGenerator: Successfully generated '{output_path}'")
        return output_path
    except subprocess.TimeoutExpired:
        bot_logger.error("SoundboardGenerator: ffmpeg timed out generating 'all' sound")
        return None
    except Exception as e:
        bot_logger.error(f"SoundboardGenerator: Error generating 'all': {e}")
        return None


def _generate_seq_sound_sync(duration_key):
    """Generate the 'seq' sound synchronously (concatenate all sounds sequentially).
    
    Args:
        duration_key: integer seconds per sound, or "full" for no trimming
    """
    _ensure_generated_dir()
    sound_files = get_real_sounds()
    
    if not sound_files:
        bot_logger.warning("SoundboardGenerator: No sounds to concatenate for 'seq'")
        return None
    
    output_path = _get_cached_path("seq", duration_key)
    n = len(sound_files)
    is_full = (duration_key == "full")
    
    # Build ffmpeg command to concatenate sounds
    cmd = ['ffmpeg', '-y']
    
    # Add all inputs
    for f in sound_files:
        cmd.extend(['-i', f])
    
    # Build filter: optionally trim each, set pts, then concat
    filter_parts = []
    concat_inputs = []
    for i in range(n):
        label = f"a{i}"
        if is_full:
            filter_parts.append(
                f"[{i}:a]asetpts=PTS-STARTPTS[{label}]"
            )
        else:
            per_sound_duration = int(duration_key)
            filter_parts.append(
                f"[{i}:a]atrim=0:{per_sound_duration},asetpts=PTS-STARTPTS[{label}]"
            )
        concat_inputs.append(f"[{label}]")
    
    concat_str = "".join(concat_inputs)
    filter_parts.append(f"{concat_str}concat=n={n}:v=0:a=1[out]")
    
    full_filter = ";".join(filter_parts)
    
    cmd.extend([
        '-filter_complex', full_filter,
        '-map', '[out]',
        '-c:a', 'libopus',
        output_path
    ])
    
    duration_display = "full" if is_full else f"{duration_key}s/sound"
    bot_logger.info(f"SoundboardGenerator: Generating 'seq' (duration={duration_display}) with {n} sounds")
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            bot_logger.error(f"SoundboardGenerator: ffmpeg error generating 'seq': {result.stderr.decode()}")
            return None
        bot_logger.info(f"SoundboardGenerator: Successfully generated '{output_path}'")
        return output_path
    except subprocess.TimeoutExpired:
        bot_logger.error("SoundboardGenerator: ffmpeg timed out generating 'seq' sound")
        return None
    except Exception as e:
        bot_logger.error(f"SoundboardGenerator: Error generating 'seq': {e}")
        return None


async def generate_sound(sound_type, duration_key):
    """Generate a special sound asynchronously.
    
    Args:
        sound_type: "all" or "seq"
        duration_key: integer seconds or "full"
    
    Returns:
        Path to generated file, or None on failure.
    """
    loop = asyncio.get_event_loop()
    
    if sound_type == "all":
        return await loop.run_in_executor(None, _generate_all_sound_sync, duration_key)
    elif sound_type == "seq":
        return await loop.run_in_executor(None, _generate_seq_sound_sync, duration_key)
    else:
        bot_logger.error(f"SoundboardGenerator: Unknown sound type '{sound_type}'")
        return None


async def get_or_generate(sound_type, duration_key, ctx=None):
    """Get a cached sound or generate it. Shows 'Generating...' in Discord if not cached.
    
    Args:
        sound_type: "all" or "seq"
        duration_key: integer seconds or "full"
        ctx: Discord context (optional, for sending status messages)
    
    Returns:
        Tuple of (filepath, status_msg_or_None)
    """
    cached_path = _get_cached_path(sound_type, duration_key)
    status_msg = None
    duration_display = "full" if duration_key == "full" else f"{duration_key}s"

    if os.path.exists(cached_path):
        bot_logger.info(f"SoundboardGenerator: Cache hit for {sound_type}_{duration_key}")
        return cached_path, None

    bot_logger.info(f"SoundboardGenerator: Cache miss for {sound_type}_{duration_key}, generating...")
    if ctx:
        status_msg = await ctx.send(f"Generating {sound_type} sound ({duration_display})...")

    filepath = await generate_sound(sound_type, duration_key)

    if filepath and status_msg:
        await status_msg.edit(content=f"Generated {sound_type} sound ({duration_display})")
    elif not filepath and status_msg:
        await status_msg.edit(content=f"Failed to generate {sound_type} sound")

    return filepath, status_msg


async def regenerate_all_cached():
    """Regenerate all currently cached variants. Called after sounds are added/deleted.
    
    This only regenerates variants that already exist in the cache, not new ones.
    """
    if not os.path.exists(GENERATED_DIR):
        bot_logger.info("SoundboardGenerator: No generated directory, nothing to regenerate")
        return
    
    cached_files = get_cached_variants()
    if not cached_files:
        bot_logger.info("SoundboardGenerator: No cached variants to regenerate")
        return
    
    bot_logger.info(f"SoundboardGenerator: Regenerating {len(cached_files)} cached variants...")
    
    for filename in cached_files:
        # Parse filename: type_duration.opus
        name_no_ext = os.path.splitext(filename)[0]
        parts = name_no_ext.split('_', 1)
        
        if len(parts) != 2:
            bot_logger.warning(f"SoundboardGenerator: Skipping unrecognized cached file '{filename}'")
            continue
        
        sound_type = parts[0]
        duration_key = parts[1]
        
        # Convert duration_key to int if it's not "full"
        if duration_key != "full":
            try:
                duration_key = int(duration_key)
            except ValueError:
                bot_logger.warning(f"SoundboardGenerator: Skipping invalid duration in '{filename}'")
                continue
        
        if sound_type not in ("all", "seq"):
            bot_logger.warning(f"SoundboardGenerator: Skipping unknown type '{sound_type}' in '{filename}'")
            continue
        
        # Delete old file
        old_path = os.path.join(GENERATED_DIR, filename)
        try:
            os.remove(old_path)
        except OSError:
            pass
        
        # Regenerate
        bot_logger.info(f"SoundboardGenerator: Regenerating {sound_type}_{duration_key}...")
        result = await generate_sound(sound_type, duration_key)
        
        if result:
            bot_logger.info(f"SoundboardGenerator: Regenerated {sound_type}_{duration_key} successfully")
        else:
            bot_logger.error(f"SoundboardGenerator: Failed to regenerate {sound_type}_{duration_key}")
    
    bot_logger.info("SoundboardGenerator: Regeneration complete")


def cleanup_generated():
    """Remove all generated sounds (useful for full reset)."""
    if os.path.exists(GENERATED_DIR):
        for f in os.listdir(GENERATED_DIR):
            filepath = os.path.join(GENERATED_DIR, f)
            if os.path.isfile(filepath):
                os.remove(filepath)
        bot_logger.info("SoundboardGenerator: Cleaned up all generated sounds")
