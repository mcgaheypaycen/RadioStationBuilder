"""
Automated Radio Show Builder
Combines voice segments and songs with proper ducking and crossfades.

Folder structure:
- voice_segments/  (001_intro.mp3, 002_weather.mp3, etc.)
- songs/           (your music library)
- output/          (final radio show output)

Usage:
    python build_radio_show.py
"""

import os
import random
from datetime import datetime
from pathlib import Path
from pydub import AudioSegment

# =============================================================================
# CONFIGURATION
# =============================================================================

# Folders
VOICE_SEGMENTS_DIR = Path("C:/RadioStation/voice_segments")
SONGS_DIR = Path("C:/RadioStation/songs")
OUTPUT_DIR = Path("C:/RadioStation/output")

# Audio settings
CROSSFADE_DURATION = 2000      # ms - crossfade between tracks
VOICE_FADE_IN = 500            # ms - voice segment fade in
VOICE_FADE_OUT = 500           # ms - voice segment fade out
SONG_FADE_IN = 3000            # ms - song fade in
SONG_FADE_OUT = 3000           # ms - song fade out
SONG_DUCK_DB = -12             # dB - how much to lower music under voice (for ducking)

# How many songs to play between voice segments
SONGS_BETWEEN_SEGMENTS = 2

# Voice segment order (by filename prefix or exact name)
# Files should be named: 001_intro.mp3, 002_weather.mp3, etc.
VOICE_SEGMENT_ORDER = [
    "001_intro",
    "002_weather",
    "003_traffic",
    "004_headlines",
    "005_bumper",
    "006_outro"
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_audio(file_path: Path) -> AudioSegment:
    """Load an audio file and return AudioSegment."""
    print(f"  Loading: {file_path.name}")
    return AudioSegment.from_file(str(file_path))


def get_voice_segments() -> list[tuple[str, Path]]:
    """Get voice segments in order."""
    segments = []
    
    for segment_prefix in VOICE_SEGMENT_ORDER:
        # Find file matching this prefix
        for file in VOICE_SEGMENTS_DIR.iterdir():
            if file.stem.lower().startswith(segment_prefix.lower()) and file.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg']:
                segments.append((segment_prefix, file))
                break
    
    return segments


def get_songs() -> list[Path]:
    """Get all songs and shuffle them."""
    songs = [
        f for f in SONGS_DIR.iterdir() 
        if f.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg', '.flac']
    ]
    random.shuffle(songs)
    return songs


def apply_fade(audio: AudioSegment, fade_in_ms: int, fade_out_ms: int) -> AudioSegment:
    """Apply fade in and fade out to audio."""
    return audio.fade_in(fade_in_ms).fade_out(fade_out_ms)


def create_song_block(songs: list[Path], count: int, song_index: int) -> tuple[AudioSegment, int]:
    """
    Create a block of songs with crossfades.
    Returns the combined audio and the new song index.
    """
    if not songs:
        return AudioSegment.silent(duration=1000), song_index
    
    block = None
    songs_added = 0
    
    while songs_added < count and song_index < len(songs):
        song_path = songs[song_index]
        song_index += 1
        
        try:
            song = load_audio(song_path)
            song = apply_fade(song, SONG_FADE_IN, SONG_FADE_OUT)
            
            if block is None:
                block = song
            else:
                # Crossfade with previous
                block = block.append(song, crossfade=CROSSFADE_DURATION)
            
            songs_added += 1
        except Exception as e:
            print(f"  Warning: Could not load {song_path.name}: {e}")
    
    # If we ran out of songs, loop back
    if songs_added < count and songs:
        song_index = 0
        while songs_added < count:
            song_path = songs[song_index % len(songs)]
            song_index += 1
            
            try:
                song = load_audio(song_path)
                song = apply_fade(song, SONG_FADE_IN, SONG_FADE_OUT)
                
                if block is None:
                    block = song
                else:
                    block = block.append(song, crossfade=CROSSFADE_DURATION)
                
                songs_added += 1
            except Exception as e:
                print(f"  Warning: Could not load {song_path.name}: {e}")
                break
    
    return block or AudioSegment.silent(duration=1000), song_index


def build_radio_show():
    """Build the complete radio show."""
    print("\n" + "="*60)
    print("🎙️  AUTOMATED RADIO SHOW BUILDER")
    print("="*60 + "\n")
    
    # Get voice segments and songs
    print("📂 Loading voice segments...")
    voice_segments = get_voice_segments()
    if not voice_segments:
        print("❌ No voice segments found! Add files to voice_segments/ folder.")
        return
    print(f"   Found {len(voice_segments)} voice segments")
    
    print("\n🎵 Loading songs...")
    songs = get_songs()
    if not songs:
        print("❌ No songs found! Add music files to songs/ folder.")
        return
    print(f"   Found {len(songs)} songs (shuffled)")
    
    # Build the show
    print("\n🔨 Building radio show...\n")
    
    final_show = None
    song_index = 0
    
    for i, (segment_name, segment_path) in enumerate(voice_segments):
        print(f"\n--- Processing: {segment_name} ---")
        
        # Load voice segment
        voice = load_audio(segment_path)
        voice = apply_fade(voice, VOICE_FADE_IN, VOICE_FADE_OUT)
        
        # Determine if we need songs before/after this segment
        is_intro = "intro" in segment_name.lower()
        is_outro = "outro" in segment_name.lower()
        
        if is_intro:
            # Intro: just the voice, then songs
            if final_show is None:
                final_show = voice
            else:
                final_show = final_show.append(voice, crossfade=CROSSFADE_DURATION)
            
            # Add songs after intro
            print(f"\n  Adding {SONGS_BETWEEN_SEGMENTS} songs after intro...")
            song_block, song_index = create_song_block(songs, SONGS_BETWEEN_SEGMENTS, song_index)
            final_show = final_show.append(song_block, crossfade=CROSSFADE_DURATION)
            
        elif is_outro:
            # Outro: just append voice at the end
            final_show = final_show.append(voice, crossfade=CROSSFADE_DURATION)
            
        else:
            # Middle segments: voice, then songs
            final_show = final_show.append(voice, crossfade=CROSSFADE_DURATION)
            
            # Add songs after this segment (unless it's the last before outro)
            next_is_outro = (i + 1 < len(voice_segments) and "outro" in voice_segments[i + 1][0].lower())
            
            if not next_is_outro:
                print(f"\n  Adding {SONGS_BETWEEN_SEGMENTS} songs...")
                song_block, song_index = create_song_block(songs, SONGS_BETWEEN_SEGMENTS, song_index)
                final_show = final_show.append(song_block, crossfade=CROSSFADE_DURATION)
    
    # Export
    print("\n\n💾 Exporting final radio show...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"radio_show_{timestamp}.mp3"
    
    final_show.export(
        str(output_path),
        format="mp3",
        bitrate="192k",
        tags={
            "title": f"Radio Show - {datetime.now().strftime('%Y-%m-%d')}",
            "artist": "Automated Radio Station",
            "album": "Daily Broadcast"
        }
    )
    
    # Show stats
    duration_seconds = len(final_show) / 1000
    duration_minutes = duration_seconds / 60
    
    print(f"\n✅ Radio show complete!")
    print(f"   📍 Output: {output_path}")
    print(f"   ⏱️  Duration: {duration_minutes:.1f} minutes ({duration_seconds:.0f} seconds)")
    print(f"   📦 File size: {output_path.stat().st_size / (1024*1024):.1f} MB")
    print("\n" + "="*60 + "\n")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    build_radio_show()

