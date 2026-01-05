"""
Radio Station Builder - GUI Application
Build automated radio shows with voice segments and music.
Features proper audio ducking for professional radio sound.
"""

import os
import sys
import json
import random
import threading
from datetime import datetime
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from typing import Optional

# Import pydub for audio processing
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None

# Import watchdog for file watching
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object


class RadioStationApp:
    """Main GUI Application for Radio Station Builder."""
    
    CONFIG_FILE = "radio_station_config.json"
    
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("🎙️ Radio Station Builder")
        self.root.geometry("800x750")
        self.root.minsize(700, 650)
        
        # Set icon if available
        try:
            self.root.iconbitmap("radio.ico")
        except:
            pass
        
        # Variables
        self.voice_segments_dir = StringVar(value="C:/RadioStation/voice_segments")
        self.songs_dir = StringVar(value="C:/RadioStation/songs")
        self.output_dir = StringVar(value="C:/RadioStation/output")
        self.songs_between = IntVar(value=2)
        self.crossfade_duration = IntVar(value=2000)
        self.song_fade_duration = IntVar(value=3000)
        self.voice_fade_duration = IntVar(value=500)
        
        # Ducking settings
        self.enable_ducking = BooleanVar(value=True)
        self.ducking_db = IntVar(value=-15)  # How much to lower music under voice
        self.duck_fade_duration = IntVar(value=500)  # How fast to duck in/out
        
        # Test mode
        self.test_mode = BooleanVar(value=False)
        
        # Freshness check settings
        self.require_fresh_files = BooleanVar(value=True)
        self.freshness_minutes = IntVar(value=5)  # Files must be created within this many minutes
        
        # Auto-watch settings
        self.auto_watch_enabled = BooleanVar(value=False)
        self.auto_watch_delay = IntVar(value=5)  # Seconds to wait after last file change
        self.is_watching = False
        self.observer = None
        self.last_change_time = None
        self.watch_timer = None
        
        # Default segment order
        self.segments = [
            "001_intro",
            "002_wellness",
            "003_weather",
            "004_national",
            "005_headlines",
            "006_bumper",
            "007_outro"
        ]
        
        # Build status
        self.is_building = False
        
        # Load saved config
        self.load_config()
        
        # Create UI
        self.create_ui()
        
        # Auto-start watcher if enabled
        if self.auto_watch_enabled.get() and WATCHDOG_AVAILABLE:
            self.root.after(1000, self.start_watching)
        
    def create_ui(self):
        """Create the main UI."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="🎙️ Radio Station Builder",
            font=("Segoe UI", 18, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=BOTH, expand=True, pady=(0, 10))
        
        # Tab 1: Folders
        folders_frame = ttk.Frame(notebook, padding="10")
        notebook.add(folders_frame, text="📁 Folders")
        self.create_folders_tab(folders_frame)
        
        # Tab 2: Segments
        segments_frame = ttk.Frame(notebook, padding="10")
        notebook.add(segments_frame, text="🎤 Segments")
        self.create_segments_tab(segments_frame)
        
        # Tab 3: Audio Settings
        audio_frame = ttk.Frame(notebook, padding="10")
        notebook.add(audio_frame, text="🔊 Audio Settings")
        self.create_audio_tab(audio_frame)
        
        # Tab 4: Ducking
        ducking_frame = ttk.Frame(notebook, padding="10")
        notebook.add(ducking_frame, text="🎚️ Ducking")
        self.create_ducking_tab(ducking_frame)
        
        # Tab 5: Auto-Watch
        watch_frame = ttk.Frame(notebook, padding="10")
        notebook.add(watch_frame, text="👁️ Auto-Watch")
        self.create_watch_tab(watch_frame)
        
        # Test mode checkbox and Build button frame
        build_frame = ttk.Frame(main_frame)
        build_frame.pack(pady=10)
        
        ttk.Checkbutton(
            build_frame,
            text="🧪 Test Mode (quick preview)",
            variable=self.test_mode
        ).pack(side=LEFT, padx=(0, 20))
        
        ttk.Checkbutton(
            build_frame,
            text="⏱️ Require fresh files",
            variable=self.require_fresh_files
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Spinbox(
            build_frame,
            from_=1,
            to=30,
            textvariable=self.freshness_minutes,
            width=3,
            font=("Segoe UI", 9)
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Label(build_frame, text="min", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 20))
        
        self.build_btn = ttk.Button(
            build_frame,
            text="🎬 Build Radio Show",
            command=self.start_build,
            style="Accent.TButton"
        )
        self.build_btn.pack(side=LEFT, ipadx=20, ipady=10)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=X, pady=(0, 10))
        
        # Log area
        log_label = ttk.Label(main_frame, text="Build Log:", font=("Segoe UI", 10, "bold"))
        log_label.pack(anchor=W)
        
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=BOTH, expand=True)
        
        self.log_text = Text(log_frame, height=8, wrap=WORD, font=("Consolas", 9))
        scrollbar = ttk.Scrollbar(log_frame, orient=VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # Status bar
        self.status_var = StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=SUNKEN, anchor=W)
        status_bar.pack(fill=X, pady=(10, 0))
        
    def create_folders_tab(self, parent):
        """Create the folders configuration tab."""
        # Voice segments folder
        ttk.Label(parent, text="Voice Segments Folder:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 5))
        voice_frame = ttk.Frame(parent)
        voice_frame.pack(fill=X, pady=(0, 10))
        ttk.Entry(voice_frame, textvariable=self.voice_segments_dir, width=60).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(voice_frame, text="Browse...", command=lambda: self.browse_folder(self.voice_segments_dir)).pack(side=RIGHT, padx=(5, 0))
        
        # Songs folder
        ttk.Label(parent, text="Songs Folder:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 5))
        songs_frame = ttk.Frame(parent)
        songs_frame.pack(fill=X, pady=(0, 10))
        ttk.Entry(songs_frame, textvariable=self.songs_dir, width=60).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(songs_frame, text="Browse...", command=lambda: self.browse_folder(self.songs_dir)).pack(side=RIGHT, padx=(5, 0))
        
        # Output folder
        ttk.Label(parent, text="Output Folder:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 5))
        output_frame = ttk.Frame(parent)
        output_frame.pack(fill=X, pady=(0, 10))
        ttk.Entry(output_frame, textvariable=self.output_dir, width=60).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(output_frame, text="Browse...", command=lambda: self.browse_folder(self.output_dir)).pack(side=RIGHT, padx=(5, 0))
        
        # Folder status
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Button(parent, text="🔄 Refresh Folder Status", command=self.refresh_folder_status).pack()
        
        self.folder_status = ttk.Label(parent, text="", font=("Segoe UI", 9))
        self.folder_status.pack(pady=10)
        self.refresh_folder_status()
        
    def create_segments_tab(self, parent):
        """Create the segments ordering tab."""
        ttk.Label(parent, text="Segment Order:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 5))
        ttk.Label(parent, text="Drag segments to reorder, or use the Up/Down buttons.", font=("Segoe UI", 9)).pack(anchor=W, pady=(0, 10))
        
        # Listbox frame
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=BOTH, expand=True, pady=10)
        
        # Listbox
        self.segment_listbox = Listbox(list_frame, height=10, font=("Segoe UI", 11), selectmode=SINGLE)
        self.segment_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        
        for segment in self.segments:
            self.segment_listbox.insert(END, segment)
        
        # Buttons frame
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(side=RIGHT, padx=(10, 0))
        
        ttk.Button(btn_frame, text="📂 Scan Folder", command=self.scan_voice_folder, width=15).pack(pady=5)
        ttk.Separator(btn_frame, orient=HORIZONTAL).pack(fill=X, pady=10)
        ttk.Button(btn_frame, text="⬆️ Move Up", command=self.move_segment_up, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="⬇️ Move Down", command=self.move_segment_down, width=15).pack(pady=5)
        ttk.Separator(btn_frame, orient=HORIZONTAL).pack(fill=X, pady=10)
        ttk.Button(btn_frame, text="➕ Add Segment", command=self.add_segment, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="➖ Remove", command=self.remove_segment, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="✏️ Rename", command=self.rename_segment, width=15).pack(pady=5)
        
        # Songs between segments
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        
        songs_frame = ttk.Frame(parent)
        songs_frame.pack(fill=X)
        
        ttk.Label(songs_frame, text="Songs between voice segments:", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        ttk.Spinbox(songs_frame, from_=1, to=10, textvariable=self.songs_between, width=5, font=("Segoe UI", 11)).pack(side=LEFT, padx=10)
        
    def create_audio_tab(self, parent):
        """Create the audio settings tab."""
        settings = [
            ("Crossfade Duration (ms):", self.crossfade_duration, 0, 10000, "Smooth transition between tracks"),
            ("Song Fade In/Out (ms):", self.song_fade_duration, 0, 10000, "How long songs fade in and out"),
            ("Voice Fade In/Out (ms):", self.voice_fade_duration, 0, 5000, "How long voice segments fade in and out"),
        ]
        
        for label_text, var, min_val, max_val, description in settings:
            frame = ttk.Frame(parent)
            frame.pack(fill=X, pady=10)
            
            ttk.Label(frame, text=label_text, font=("Segoe UI", 10, "bold"), width=25).pack(side=LEFT)
            ttk.Spinbox(frame, from_=min_val, to=max_val, textvariable=var, width=8, font=("Segoe UI", 11), increment=100).pack(side=LEFT, padx=10)
            ttk.Label(frame, text=description, font=("Segoe UI", 9, "italic"), foreground="gray").pack(side=LEFT, padx=10)
            
        # Presets
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Label(parent, text="Presets:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        
        presets_frame = ttk.Frame(parent)
        presets_frame.pack(fill=X, pady=10)
        
        ttk.Button(presets_frame, text="🎵 Smooth Radio", command=self.preset_smooth).pack(side=LEFT, padx=5)
        ttk.Button(presets_frame, text="⚡ Quick Cuts", command=self.preset_quick).pack(side=LEFT, padx=5)
        ttk.Button(presets_frame, text="🎭 Podcast Style", command=self.preset_podcast).pack(side=LEFT, padx=5)
    
    def create_ducking_tab(self, parent):
        """Create the ducking settings tab."""
        # Enable ducking checkbox
        ttk.Checkbutton(
            parent, 
            text="Enable Music Ducking Under Voice", 
            variable=self.enable_ducking,
            style="TCheckbutton"
        ).pack(anchor=W, pady=(10, 20))
        
        # Explanation
        explanation = ttk.Label(
            parent, 
            text="Ducking lowers the music volume when the DJ is speaking,\n"
                 "creating that classic professional radio sound.",
            font=("Segoe UI", 9, "italic"),
            foreground="gray"
        )
        explanation.pack(anchor=W, pady=(0, 20))
        
        # Ducking amount
        duck_amount_frame = ttk.Frame(parent)
        duck_amount_frame.pack(fill=X, pady=10)
        
        ttk.Label(duck_amount_frame, text="Duck Amount (dB):", font=("Segoe UI", 10, "bold"), width=25).pack(side=LEFT)
        duck_spinbox = ttk.Spinbox(
            duck_amount_frame, 
            from_=-30, 
            to=0, 
            textvariable=self.ducking_db, 
            width=8, 
            font=("Segoe UI", 11),
            increment=1
        )
        duck_spinbox.pack(side=LEFT, padx=10)
        ttk.Label(
            duck_amount_frame, 
            text="Negative = quieter (-15 is typical)", 
            font=("Segoe UI", 9, "italic"), 
            foreground="gray"
        ).pack(side=LEFT, padx=10)
        
        # Duck fade duration
        duck_fade_frame = ttk.Frame(parent)
        duck_fade_frame.pack(fill=X, pady=10)
        
        ttk.Label(duck_fade_frame, text="Duck Fade Duration (ms):", font=("Segoe UI", 10, "bold"), width=25).pack(side=LEFT)
        ttk.Spinbox(
            duck_fade_frame, 
            from_=100, 
            to=2000, 
            textvariable=self.duck_fade_duration, 
            width=8, 
            font=("Segoe UI", 11),
            increment=100
        ).pack(side=LEFT, padx=10)
        ttk.Label(
            duck_fade_frame, 
            text="How fast music fades down/up", 
            font=("Segoe UI", 9, "italic"), 
            foreground="gray"
        ).pack(side=LEFT, padx=10)
        
        # Ducking presets
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Label(parent, text="Ducking Presets:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        
        presets_frame = ttk.Frame(parent)
        presets_frame.pack(fill=X, pady=10)
        
        ttk.Button(presets_frame, text="📻 Classic Radio", command=self.preset_duck_classic).pack(side=LEFT, padx=5)
        ttk.Button(presets_frame, text="🎧 Subtle", command=self.preset_duck_subtle).pack(side=LEFT, padx=5)
        ttk.Button(presets_frame, text="🔇 Heavy Duck", command=self.preset_duck_heavy).pack(side=LEFT, padx=5)
        ttk.Button(presets_frame, text="❌ No Ducking", command=self.preset_duck_none).pack(side=LEFT, padx=5)
        
        # Visual representation
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Label(parent, text="How Ducking Works:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        
        visual = ttk.Label(
            parent,
            text="Music:  ████████▁▁▁▁▁▁▁▁████████▁▁▁▁▁▁▁▁████████\n"
                 "Voice:          ████████████        ████████████\n"
                 "                 (speaking)           (speaking)",
            font=("Consolas", 10),
            justify=LEFT
        )
        visual.pack(anchor=W, pady=10)
        
    def preset_duck_classic(self):
        """Classic radio ducking preset."""
        self.enable_ducking.set(True)
        self.ducking_db.set(-15)
        self.duck_fade_duration.set(500)
        self.log("Applied 'Classic Radio' ducking preset")
        
    def preset_duck_subtle(self):
        """Subtle ducking preset."""
        self.enable_ducking.set(True)
        self.ducking_db.set(-8)
        self.duck_fade_duration.set(300)
        self.log("Applied 'Subtle' ducking preset")
        
    def preset_duck_heavy(self):
        """Heavy ducking preset."""
        self.enable_ducking.set(True)
        self.ducking_db.set(-25)
        self.duck_fade_duration.set(400)
        self.log("Applied 'Heavy Duck' preset")
        
    def preset_duck_none(self):
        """Disable ducking."""
        self.enable_ducking.set(False)
        self.log("Ducking disabled")
    
    def create_watch_tab(self, parent):
        """Create the auto-watch settings tab."""
        # Check if watchdog is available
        if not WATCHDOG_AVAILABLE:
            ttk.Label(
                parent,
                text="⚠️ Auto-Watch requires the 'watchdog' library.\n\n"
                     "Install it with: pip install watchdog",
                font=("Segoe UI", 11),
                foreground="red"
            ).pack(pady=20)
            return
        
        # Enable auto-watch checkbox
        ttk.Checkbutton(
            parent,
            text="Enable Auto-Watch Mode",
            variable=self.auto_watch_enabled,
            command=self.toggle_watch
        ).pack(anchor=W, pady=(10, 5))
        
        # Explanation
        explanation = ttk.Label(
            parent,
            text="When enabled, the app monitors your voice segments folder.\n"
                 "It automatically builds the radio show when all segments are detected.",
            font=("Segoe UI", 9, "italic"),
            foreground="gray"
        )
        explanation.pack(anchor=W, pady=(0, 20))
        
        # Watch delay setting
        delay_frame = ttk.Frame(parent)
        delay_frame.pack(fill=X, pady=10)
        
        ttk.Label(delay_frame, text="Build Delay (seconds):", font=("Segoe UI", 10, "bold"), width=25).pack(side=LEFT)
        ttk.Spinbox(
            delay_frame,
            from_=1,
            to=30,
            textvariable=self.auto_watch_delay,
            width=8,
            font=("Segoe UI", 11)
        ).pack(side=LEFT, padx=10)
        ttk.Label(
            delay_frame,
            text="Wait time after last file change",
            font=("Segoe UI", 9, "italic"),
            foreground="gray"
        ).pack(side=LEFT, padx=10)
        
        # Status display
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Label(parent, text="Watch Status:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        
        self.watch_status_var = StringVar(value="⏹️ Not watching")
        self.watch_status_label = ttk.Label(
            parent,
            textvariable=self.watch_status_var,
            font=("Segoe UI", 12)
        )
        self.watch_status_label.pack(anchor=W, pady=10)
        
        # Expected files display
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)
        ttk.Label(parent, text="Expected Segment Files:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        
        files_text = "\n".join([f"• {seg}.mp3" for seg in self.segments])
        ttk.Label(
            parent,
            text=files_text,
            font=("Consolas", 10),
            justify=LEFT
        ).pack(anchor=W, pady=10)
        
        # Manual check button
        ttk.Button(
            parent,
            text="🔍 Check Files Now",
            command=self.check_segments_exist
        ).pack(anchor=W, pady=10)
        
        self.files_status_var = StringVar(value="")
        ttk.Label(
            parent,
            textvariable=self.files_status_var,
            font=("Segoe UI", 10)
        ).pack(anchor=W)
    
    def toggle_watch(self):
        """Toggle the file watcher on/off."""
        if self.auto_watch_enabled.get():
            self.start_watching()
        else:
            self.stop_watching()
    
    def start_watching(self):
        """Start watching the voice segments folder."""
        if not WATCHDOG_AVAILABLE:
            messagebox.showerror("Error", "watchdog library not installed!")
            self.auto_watch_enabled.set(False)
            return
        
        if self.is_watching:
            return
        
        watch_path = Path(self.voice_segments_dir.get())
        if not watch_path.exists():
            messagebox.showerror("Error", f"Voice segments folder not found:\n{watch_path}")
            self.auto_watch_enabled.set(False)
            return
        
        # Create event handler
        app = self
        
        class SegmentHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory and event.src_path.endswith('.mp3'):
                    app.on_segment_change(event.src_path)
            
            def on_modified(self, event):
                if not event.is_directory and event.src_path.endswith('.mp3'):
                    app.on_segment_change(event.src_path)
        
        self.observer = Observer()
        self.observer.schedule(SegmentHandler(), str(watch_path), recursive=False)
        self.observer.start()
        self.is_watching = True
        
        self.watch_status_var.set("👁️ Watching for new segments...")
        self.log("🔍 Auto-watch started - monitoring voice segments folder")
    
    def stop_watching(self):
        """Stop watching the voice segments folder."""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2)
            self.observer = None
        
        if self.watch_timer:
            self.root.after_cancel(self.watch_timer)
            self.watch_timer = None
        
        self.is_watching = False
        self.watch_status_var.set("⏹️ Not watching")
        self.log("⏹️ Auto-watch stopped")
    
    def on_segment_change(self, filepath):
        """Called when a segment file is created or modified."""
        self.last_change_time = datetime.now()
        filename = Path(filepath).name
        
        # Update status on main thread
        self.root.after(0, lambda: self.watch_status_var.set(f"📥 Detected: {filename}"))
        self.root.after(0, lambda: self.log(f"📥 File detected: {filename}"))
        
        # Cancel any existing timer
        if self.watch_timer:
            self.root.after_cancel(self.watch_timer)
        
        # Start a new timer
        delay_ms = self.auto_watch_delay.get() * 1000
        self.watch_timer = self.root.after(delay_ms, self.check_and_build)
    
    def check_and_build(self):
        """Check if all segments exist AND are fresh, then trigger build."""
        self.watch_timer = None
        
        if self.is_building:
            self.log("⏳ Build already in progress, skipping...")
            return
        
        voice_dir = Path(self.voice_segments_dir.get())
        missing = []
        found = []  # List of (segment_name, segment_path)
        max_age_minutes = self.freshness_minutes.get()
        now = datetime.now()
        
        for segment in self.segments:
            segment_file = None
            for ext in ['.mp3', '.wav', '.m4a', '.ogg']:
                candidate = voice_dir / f"{segment}{ext}"
                if candidate.exists():
                    segment_file = candidate
                    break
            
            if segment_file:
                found.append((segment, segment_file))
            else:
                missing.append(segment)
        
        total_segments = len(self.segments)
        
        if missing:
            self.watch_status_var.set(f"⏳ Waiting... ({len(found)}/{total_segments} segments)")
            self.log(f"⏳ Missing segments: {', '.join(missing)}")
            return
        
        # All segments exist - now check if ALL are fresh
        stale_files = []
        fresh_count = 0
        
        for segment_name, segment_path in found:
            mtime = datetime.fromtimestamp(segment_path.stat().st_mtime)
            age_minutes = (now - mtime).total_seconds() / 60
            
            if age_minutes <= max_age_minutes:
                fresh_count += 1
            else:
                stale_files.append((segment_name, round(age_minutes, 1)))
        
        if stale_files:
            self.watch_status_var.set(f"⏳ Waiting for fresh files... ({fresh_count}/{total_segments} fresh)")
            stale_names = ", ".join([f"{name} ({age}m old)" for name, age in stale_files[:3]])
            if len(stale_files) > 3:
                stale_names += f" +{len(stale_files) - 3} more"
            self.log(f"⏳ Stale segments (>{max_age_minutes}m old): {stale_names}")
        else:
            self.watch_status_var.set(f"✅ All {total_segments} fresh segments found! Building...")
            self.log(f"✅ All {total_segments} fresh segments detected - starting auto-build!")
            self.root.after(500, self.start_build)
    
    def check_segments_exist(self):
        """Manually check which segment files exist and their freshness."""
        voice_dir = Path(self.voice_segments_dir.get())
        
        if not voice_dir.exists():
            self.files_status_var.set("❌ Folder not found!")
            return
        
        found = []  # (segment_name, segment_path)
        missing = []
        max_age_minutes = self.freshness_minutes.get()
        now = datetime.now()
        
        for segment in self.segments:
            segment_file = None
            for ext in ['.mp3', '.wav', '.m4a', '.ogg']:
                candidate = voice_dir / f"{segment}{ext}"
                if candidate.exists():
                    segment_file = candidate
                    break
            
            if segment_file:
                found.append((segment, segment_file))
            else:
                missing.append(segment)
        
        total_segments = len(self.segments)
        
        if missing:
            self.files_status_var.set(f"Found {len(found)}/{total_segments} — Missing: {', '.join(missing)}")
            return
        
        # Check freshness
        fresh_count = 0
        stale_files = []
        
        for segment_name, segment_path in found:
            mtime = datetime.fromtimestamp(segment_path.stat().st_mtime)
            age_minutes = (now - mtime).total_seconds() / 60
            
            if age_minutes <= max_age_minutes:
                fresh_count += 1
            else:
                stale_files.append((segment_name, round(age_minutes, 1)))
        
        if stale_files:
            stale_info = ", ".join([f"{name} ({age}m)" for name, age in stale_files[:2]])
            if len(stale_files) > 2:
                stale_info += f" +{len(stale_files) - 2} more"
            self.files_status_var.set(f"⚠️ {fresh_count}/{total_segments} fresh — Stale: {stale_info}")
        else:
            self.files_status_var.set(f"✅ All {total_segments} segments found & fresh!")
        
    def browse_folder(self, var: StringVar):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory(initialdir=var.get())
        if folder:
            var.set(folder)
            self.refresh_folder_status()
            
    def refresh_folder_status(self):
        """Update folder status display."""
        voice_path = Path(self.voice_segments_dir.get())
        songs_path = Path(self.songs_dir.get())
        
        voice_count = len([f for f in voice_path.iterdir() if f.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg']]) if voice_path.exists() else 0
        songs_count = len([f for f in songs_path.iterdir() if f.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg', '.flac']]) if songs_path.exists() else 0
        
        status = f"📢 Voice segments: {voice_count} files | 🎵 Songs: {songs_count} files"
        self.folder_status.config(text=status)
        
    def move_segment_up(self):
        """Move selected segment up."""
        selection = self.segment_listbox.curselection()
        if selection and selection[0] > 0:
            idx = selection[0]
            item = self.segment_listbox.get(idx)
            self.segment_listbox.delete(idx)
            self.segment_listbox.insert(idx - 1, item)
            self.segment_listbox.selection_set(idx - 1)
            self.update_segments_list()
            
    def move_segment_down(self):
        """Move selected segment down."""
        selection = self.segment_listbox.curselection()
        if selection and selection[0] < self.segment_listbox.size() - 1:
            idx = selection[0]
            item = self.segment_listbox.get(idx)
            self.segment_listbox.delete(idx)
            self.segment_listbox.insert(idx + 1, item)
            self.segment_listbox.selection_set(idx + 1)
            self.update_segments_list()
            
    def add_segment(self):
        """Add a new segment."""
        from tkinter import simpledialog
        name = simpledialog.askstring("Add Segment", "Enter segment name (e.g., 007_news):")
        if name:
            self.segment_listbox.insert(END, name)
            self.update_segments_list()
            
    def remove_segment(self):
        """Remove selected segment."""
        selection = self.segment_listbox.curselection()
        if selection:
            self.segment_listbox.delete(selection[0])
            self.update_segments_list()
            
    def rename_segment(self):
        """Rename selected segment."""
        from tkinter import simpledialog
        selection = self.segment_listbox.curselection()
        if selection:
            old_name = self.segment_listbox.get(selection[0])
            new_name = simpledialog.askstring("Rename Segment", "Enter new name:", initialvalue=old_name)
            if new_name:
                self.segment_listbox.delete(selection[0])
                self.segment_listbox.insert(selection[0], new_name)
                self.update_segments_list()
    
    def scan_voice_folder(self):
        """Scan voice segments folder and import all files, keeping intro first and outro last."""
        voice_path = Path(self.voice_segments_dir.get())
        
        if not voice_path.exists():
            messagebox.showerror("Error", f"Voice segments folder not found:\n{voice_path}")
            return
        
        # Get all audio files
        audio_extensions = ['.mp3', '.wav', '.m4a', '.ogg']
        audio_files = [
            f.stem for f in voice_path.iterdir() 
            if f.suffix.lower() in audio_extensions
        ]
        
        if not audio_files:
            messagebox.showwarning("No Files", "No audio files found in the voice segments folder.")
            return
        
        # Separate intro, outro, and middle segments
        intro_segments = []
        outro_segments = []
        middle_segments = []
        
        for filename in audio_files:
            lower_name = filename.lower()
            if "intro" in lower_name:
                intro_segments.append(filename)
            elif "outro" in lower_name:
                outro_segments.append(filename)
            else:
                middle_segments.append(filename)
        
        # Sort each group alphabetically
        intro_segments.sort()
        middle_segments.sort()
        outro_segments.sort()
        
        # Combine: intro first, then middle segments, then outro last
        new_segments = intro_segments + middle_segments + outro_segments
        
        # Clear and repopulate the listbox
        self.segment_listbox.delete(0, END)
        for segment in new_segments:
            self.segment_listbox.insert(END, segment)
        
        self.update_segments_list()
        
        messagebox.showinfo(
            "Scan Complete", 
            f"Found {len(new_segments)} segments:\n"
            f"• {len(intro_segments)} intro(s)\n"
            f"• {len(middle_segments)} middle segments\n"
            f"• {len(outro_segments)} outro(s)"
        )
                
    def update_segments_list(self):
        """Update internal segments list from listbox."""
        self.segments = list(self.segment_listbox.get(0, END))
        
    def preset_smooth(self):
        """Apply smooth radio preset."""
        self.crossfade_duration.set(3000)
        self.song_fade_duration.set(4000)
        self.voice_fade_duration.set(800)
        self.log("Applied 'Smooth Radio' preset")
        
    def preset_quick(self):
        """Apply quick cuts preset."""
        self.crossfade_duration.set(500)
        self.song_fade_duration.set(1000)
        self.voice_fade_duration.set(200)
        self.log("Applied 'Quick Cuts' preset")
        
    def preset_podcast(self):
        """Apply podcast style preset."""
        self.crossfade_duration.set(1500)
        self.song_fade_duration.set(2000)
        self.voice_fade_duration.set(500)
        self.log("Applied 'Podcast Style' preset")
        
    def log(self, message: str):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{timestamp}] {message}\n")
        self.log_text.see(END)
        self.root.update_idletasks()
        
    def save_config(self):
        """Save configuration to file."""
        config = {
            "voice_segments_dir": self.voice_segments_dir.get(),
            "songs_dir": self.songs_dir.get(),
            "output_dir": self.output_dir.get(),
            "songs_between": self.songs_between.get(),
            "crossfade_duration": self.crossfade_duration.get(),
            "song_fade_duration": self.song_fade_duration.get(),
            "voice_fade_duration": self.voice_fade_duration.get(),
            "enable_ducking": self.enable_ducking.get(),
            "ducking_db": self.ducking_db.get(),
            "duck_fade_duration": self.duck_fade_duration.get(),
            "test_mode": self.test_mode.get(),
            "require_fresh_files": self.require_fresh_files.get(),
            "freshness_minutes": self.freshness_minutes.get(),
            "auto_watch_enabled": self.auto_watch_enabled.get(),
            "auto_watch_delay": self.auto_watch_delay.get(),
            "segments": self.segments
        }
        
        config_path = Path(self.CONFIG_FILE)
        if getattr(sys, 'frozen', False):
            config_path = Path(sys.executable).parent / self.CONFIG_FILE
            
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
    def load_config(self):
        """Load configuration from file."""
        config_path = Path(self.CONFIG_FILE)
        if getattr(sys, 'frozen', False):
            config_path = Path(sys.executable).parent / self.CONFIG_FILE
            
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    
                self.voice_segments_dir.set(config.get("voice_segments_dir", self.voice_segments_dir.get()))
                self.songs_dir.set(config.get("songs_dir", self.songs_dir.get()))
                self.output_dir.set(config.get("output_dir", self.output_dir.get()))
                self.songs_between.set(config.get("songs_between", 2))
                self.crossfade_duration.set(config.get("crossfade_duration", 2000))
                self.song_fade_duration.set(config.get("song_fade_duration", 3000))
                self.voice_fade_duration.set(config.get("voice_fade_duration", 500))
                self.enable_ducking.set(config.get("enable_ducking", True))
                self.ducking_db.set(config.get("ducking_db", -15))
                self.duck_fade_duration.set(config.get("duck_fade_duration", 500))
                self.test_mode.set(config.get("test_mode", False))
                self.require_fresh_files.set(config.get("require_fresh_files", True))
                self.freshness_minutes.set(config.get("freshness_minutes", 5))
                self.auto_watch_enabled.set(config.get("auto_watch_enabled", False))
                self.auto_watch_delay.set(config.get("auto_watch_delay", 5))
                self.segments = config.get("segments", self.segments)
            except Exception as e:
                print(f"Could not load config: {e}")
                
    def start_build(self):
        """Start building the radio show in a separate thread."""
        if self.is_building:
            messagebox.showwarning("Building", "A build is already in progress!")
            return
            
        if AudioSegment is None:
            messagebox.showerror("Error", "pydub is not installed!\n\nRun: pip install pydub")
            return
            
        # Save config
        self.save_config()
        
        # Start build thread
        self.is_building = True
        self.build_btn.config(state=DISABLED)
        self.progress.start()
        self.status_var.set("Building radio show...")
        self.log_text.delete(1.0, END)
        
        thread = threading.Thread(target=self.build_show, daemon=True)
        thread.start()
        
    def build_show(self):
        """Build the radio show (runs in separate thread)."""
        try:
            # Check if test mode is enabled
            if self.test_mode.get():
                self.build_test_show()
                return
            
            self.log("🎙️ Starting radio show build...")
            
            if self.enable_ducking.get():
                self.log(f"🎚️ Ducking enabled: {self.ducking_db.get()} dB")
            else:
                self.log("🎚️ Ducking disabled")
            
            voice_dir = Path(self.voice_segments_dir.get())
            songs_dir = Path(self.songs_dir.get())
            output_dir = Path(self.output_dir.get())
            
            # Validate folders
            if not voice_dir.exists():
                raise FileNotFoundError(f"Voice segments folder not found: {voice_dir}")
            if not songs_dir.exists():
                raise FileNotFoundError(f"Songs folder not found: {songs_dir}")
                
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get voice segments
            self.log("📂 Loading voice segments...")
            voice_segments = self.get_voice_segments(voice_dir)
            self.log(f"   Found {len(voice_segments)} voice segments")
            
            if not voice_segments:
                raise FileNotFoundError("No voice segments found!")
            
            # Check file freshness if enabled
            if self.require_fresh_files.get():
                self.log(f"⏱️ Checking file freshness (max {self.freshness_minutes.get()} minutes)...")
                all_fresh, stale_files = self.check_files_freshness(voice_segments)
                
                if not all_fresh:
                    stale_list = ", ".join([f"{name} ({age}m old)" for name, age in stale_files])
                    raise ValueError(f"Stale files detected! These files are too old:\n{stale_list}\n\nRun your n8n workflow to generate fresh voice segments.")
            
            # Get songs
            self.log("🎵 Loading songs...")
            songs = self.get_songs(songs_dir)
            self.log(f"   Found {len(songs)} songs (shuffled)")
            
            if not songs:
                raise FileNotFoundError("No songs found!")
            
            # Build the show
            self.log("\n🔨 Building radio show...\n")
            
            final_show = None
            song_index = 0
            crossfade = self.crossfade_duration.get()
            songs_between = self.songs_between.get()
            
            # Ducking settings
            ducking_enabled = self.enable_ducking.get()
            duck_db = self.ducking_db.get()
            duck_fade = self.duck_fade_duration.get()
            
            # Keep track of the last song for ducking
            last_song_for_ducking = None
            
            for i, (segment_name, segment_path) in enumerate(voice_segments):
                self.log(f"--- Processing: {segment_name} ---")
                
                # Load voice segment
                voice = AudioSegment.from_file(str(segment_path))
                voice = voice.fade_in(self.voice_fade_duration.get()).fade_out(self.voice_fade_duration.get())
                
                is_intro = "intro" in segment_name.lower()
                is_outro = "outro" in segment_name.lower()
                
                # Apply ducking if enabled and we have a previous song
                if ducking_enabled and last_song_for_ducking is not None and not is_intro:
                    self.log(f"   Applying ducking ({duck_db} dB) under voice...")
                    voice = self.create_ducked_segment(voice, last_song_for_ducking, duck_db, duck_fade)
                
                if is_intro:
                    final_show = voice if final_show is None else final_show.append(voice, crossfade=crossfade)
                    self.log(f"   Adding {songs_between} songs after intro...")
                    song_block, song_index, last_song_for_ducking = self.create_song_block_with_tracking(
                        songs, songs_between, song_index
                    )
                    final_show = final_show.append(song_block, crossfade=crossfade)
                    
                elif is_outro:
                    final_show = final_show.append(voice, crossfade=crossfade)
                    last_song_for_ducking = None
                    
                else:
                    final_show = final_show.append(voice, crossfade=crossfade)
                    
                    # Always add songs after middle segments
                    self.log(f"   Adding {songs_between} songs...")
                    song_block, song_index, last_song_for_ducking = self.create_song_block_with_tracking(
                        songs, songs_between, song_index
                    )
                    final_show = final_show.append(song_block, crossfade=crossfade)
            
            # Export
            self.log("\n💾 Exporting final radio show...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"radio_show_{timestamp}.mp3"
            
            final_show.export(
                str(output_path),
                format="mp3",
                bitrate="192k"
            )
            
            duration_minutes = len(final_show) / 1000 / 60
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            
            self.log(f"\n✅ Radio show complete!")
            self.log(f"   📍 Output: {output_path}")
            self.log(f"   ⏱️  Duration: {duration_minutes:.1f} minutes")
            self.log(f"   📦 File size: {file_size_mb:.1f} MB")
            
            self.root.after(0, lambda: messagebox.showinfo(
                "Success!",
                f"Radio show built successfully!\n\nDuration: {duration_minutes:.1f} minutes\nFile: {output_path.name}"
            ))
            
        except Exception as e:
            self.log(f"\n❌ Error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Build Error", str(e)))
            
        finally:
            self.root.after(0, self.build_complete)
            
    def build_test_show(self):
        """Build a quick test preview: last 30s of song 1 → ducked voice → first 30s of song 2."""
        try:
            self.log("🧪 TEST MODE: Building quick preview...")
            self.log("   Structure: Song 1 (last 30s) → Voice + Ducking → Song 2 (first 30s)")
            
            voice_dir = Path(self.voice_segments_dir.get())
            songs_dir = Path(self.songs_dir.get())
            output_dir = Path(self.output_dir.get())
            
            # Validate folders
            if not voice_dir.exists():
                raise FileNotFoundError(f"Voice segments folder not found: {voice_dir}")
            if not songs_dir.exists():
                raise FileNotFoundError(f"Songs folder not found: {songs_dir}")
                
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get songs (need at least 2)
            songs = self.get_songs(songs_dir)
            if len(songs) < 2:
                raise FileNotFoundError("Need at least 2 songs for test mode!")
            
            # Get first available voice segment
            voice_segments = self.get_voice_segments(voice_dir)
            if not voice_segments:
                raise FileNotFoundError("No voice segments found!")
            
            # Use the first non-intro/outro segment, or just the first one
            voice_segment = None
            for seg_name, seg_path in voice_segments:
                if "intro" not in seg_name.lower() and "outro" not in seg_name.lower():
                    voice_segment = (seg_name, seg_path)
                    break
            if voice_segment is None:
                voice_segment = voice_segments[0]
            
            self.log(f"\n📂 Loading test assets...")
            self.log(f"   Song 1: {songs[0].name}")
            self.log(f"   Voice: {voice_segment[0]}")
            self.log(f"   Song 2: {songs[1].name}")
            
            # Load Song 1 and get last 30 seconds
            self.log("\n🎵 Processing Song 1 (last 30 seconds)...")
            song1 = AudioSegment.from_file(str(songs[0]))
            song1_end = song1[-30000:]  # Last 30 seconds
            
            # Load voice segment
            self.log("🎤 Loading voice segment...")
            voice = AudioSegment.from_file(str(voice_segment[1]))
            voice = voice.fade_in(self.voice_fade_duration.get()).fade_out(self.voice_fade_duration.get())
            
            # Load Song 2 and get first 30 seconds
            self.log("🎵 Processing Song 2 (first 30 seconds)...")
            song2 = AudioSegment.from_file(str(songs[1]))
            song2_start = song2[:30000]  # First 30 seconds
            song2_start = song2_start.fade_in(self.song_fade_duration.get()).fade_out(self.song_fade_duration.get())
            
            # Ducking settings
            duck_db = self.ducking_db.get()
            duck_fade = self.duck_fade_duration.get()
            crossfade = self.crossfade_duration.get()
            
            # Build the test show
            self.log("\n🔨 Assembling test show...")
            
            voice_length = len(voice)
            voice_fade = self.voice_fade_duration.get()
            
            if self.enable_ducking.get():
                self.log(f"   Applying edge ducking ({duck_db} dB) - music only during voice fade in/out...")
                
                # === PART 1: Song 1 ending with ducked tail + voice intro ===
                # Get the last portion of song1 that will overlap with voice start
                overlap_duration = min(duck_fade + voice_fade, len(song1_end) // 2)
                
                # Song 1 main part (before overlap)
                song1_main = song1_end[:-overlap_duration]
                
                # Song 1 tail (will be ducked and overlaid with voice start)
                song1_tail = song1_end[-overlap_duration:]
                song1_tail_ducked = song1_tail + duck_db
                song1_tail_ducked = song1_tail_ducked.fade_out(overlap_duration)
                
                # Voice intro portion
                voice_intro = voice[:overlap_duration]
                
                # Overlay: ducked song1 tail + voice intro
                transition_in = song1_tail_ducked.overlay(voice_intro)
                
                # === PART 2: Voice middle (no music) ===
                voice_middle = voice[overlap_duration:-overlap_duration]
                
                # === PART 3: Voice outro + Song 2 beginning with ducked intro ===
                # Voice outro portion
                voice_outro = voice[-overlap_duration:]
                
                # Song 2 intro (will be ducked and overlaid with voice end)
                song2_intro = song2_start[:overlap_duration]
                song2_intro_ducked = song2_intro + duck_db
                song2_intro_ducked = song2_intro_ducked.fade_in(overlap_duration)
                
                # Overlay: voice outro + ducked song2 intro
                transition_out = song2_intro_ducked.overlay(voice_outro)
                
                # Song 2 main part (after overlap)
                song2_main = song2_start[overlap_duration:]
                
                # === ASSEMBLE ===
                final_show = song1_main + transition_in + voice_middle + transition_out + song2_main
                
            else:
                # No ducking - just crossfade
                song1_end = song1_end.fade_out(crossfade)
                final_show = song1_end.append(voice, crossfade=crossfade)
                final_show = final_show.append(song2_start, crossfade=crossfade)
            
            # Export
            self.log("\n💾 Exporting test preview...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"test_preview_{timestamp}.mp3"
            
            final_show.export(
                str(output_path),
                format="mp3",
                bitrate="192k"
            )
            
            duration_seconds = len(final_show) / 1000
            file_size_kb = output_path.stat().st_size / 1024
            
            self.log(f"\n✅ Test preview complete!")
            self.log(f"   📍 Output: {output_path}")
            self.log(f"   ⏱️  Duration: {duration_seconds:.1f} seconds")
            self.log(f"   📦 File size: {file_size_kb:.1f} KB")
            
            self.root.after(0, lambda: messagebox.showinfo(
                "Test Complete!",
                f"Test preview built successfully!\n\nDuration: {duration_seconds:.1f} seconds\nFile: {output_path.name}"
            ))
            
        except Exception as e:
            self.log(f"\n❌ Error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Build Error", str(e)))
            
        finally:
            self.root.after(0, self.build_complete)
    
    def create_ducked_segment(self, voice: AudioSegment, music_source: AudioSegment, 
                               duck_db: int, duck_fade: int) -> AudioSegment:
        """Create a voice segment with ducked music only at the edges (fade in/out portions).
        
        The structure is:
        1. Ducked music fading out + voice intro (overlaid)
        2. Voice middle plays alone (no music)
        3. Voice outro + ducked music fading in (overlaid)
        """
        try:
            voice_length = len(voice)
            voice_fade = self.voice_fade_duration.get()
            
            # Calculate overlap duration (where music and voice overlap)
            overlap_duration = min(duck_fade + voice_fade, voice_length // 3)
            
            if overlap_duration < 100:
                # Voice too short for proper ducking, return as-is
                return voice
            
            # === PART 1: Ducked music tail + voice intro ===
            # Get music for the intro overlap
            music_for_intro = music_source[-overlap_duration:] if len(music_source) >= overlap_duration else music_source
            if len(music_for_intro) < overlap_duration:
                # Pad with silence if music is too short
                music_for_intro = AudioSegment.silent(duration=overlap_duration - len(music_for_intro)) + music_for_intro
            
            music_intro_ducked = music_for_intro + duck_db
            music_intro_ducked = music_intro_ducked.fade_out(overlap_duration)
            
            voice_intro = voice[:overlap_duration]
            transition_in = music_intro_ducked.overlay(voice_intro)
            
            # === PART 2: Voice middle (no music) ===
            voice_middle = voice[overlap_duration:-overlap_duration] if voice_length > overlap_duration * 2 else AudioSegment.empty()
            
            # === PART 3: Voice outro + ducked music intro ===
            music_for_outro = music_source[:overlap_duration] if len(music_source) >= overlap_duration else music_source
            if len(music_for_outro) < overlap_duration:
                # Pad with silence if music is too short
                music_for_outro = music_for_outro + AudioSegment.silent(duration=overlap_duration - len(music_for_outro))
            
            music_outro_ducked = music_for_outro + duck_db
            music_outro_ducked = music_outro_ducked.fade_in(overlap_duration)
            
            voice_outro = voice[-overlap_duration:]
            transition_out = music_outro_ducked.overlay(voice_outro)
            
            # === ASSEMBLE ===
            result = transition_in + voice_middle + transition_out
            
            return result
            
        except Exception as e:
            self.log(f"   Warning: Ducking failed ({e}), using voice only")
            return voice
            
    def build_complete(self):
        """Called when build is complete."""
        self.is_building = False
        self.build_btn.config(state=NORMAL)
        self.progress.stop()
        self.status_var.set("Ready")
        
    def check_files_freshness(self, voice_segments: list) -> tuple:
        """Check if all voice segment files were created within the freshness window.
        
        Returns:
            tuple: (all_fresh: bool, stale_files: list of (name, age_minutes))
        """
        max_age_minutes = self.freshness_minutes.get()
        now = datetime.now()
        stale_files = []
        
        for segment_name, segment_path in voice_segments:
            # Get file modification time
            mtime = datetime.fromtimestamp(segment_path.stat().st_mtime)
            age_minutes = (now - mtime).total_seconds() / 60
            
            if age_minutes > max_age_minutes:
                stale_files.append((segment_name, round(age_minutes, 1)))
        
        return (len(stale_files) == 0, stale_files)
    
    def get_voice_segments(self, voice_dir: Path) -> list:
        """Get voice segments in configured order."""
        segments = []
        
        for segment_prefix in self.segments:
            for file in voice_dir.iterdir():
                if file.stem.lower().startswith(segment_prefix.lower()) and file.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg']:
                    segments.append((segment_prefix, file))
                    break
                    
        return segments
        
    def get_songs(self, songs_dir: Path) -> list:
        """Get all songs shuffled."""
        songs = [f for f in songs_dir.iterdir() if f.suffix.lower() in ['.mp3', '.wav', '.m4a', '.ogg', '.flac']]
        random.shuffle(songs)
        return songs
        
    def create_song_block(self, songs: list, count: int, song_index: int) -> tuple:
        """Create a block of songs with crossfades."""
        if not songs:
            return AudioSegment.silent(duration=1000), song_index
            
        block = None
        songs_added = 0
        fade = self.song_fade_duration.get()
        crossfade = self.crossfade_duration.get()
        
        while songs_added < count:
            if song_index >= len(songs):
                song_index = 0
                random.shuffle(songs)
                
            song_path = songs[song_index]
            song_index += 1
            
            try:
                self.log(f"      Loading: {song_path.name}")
                song = AudioSegment.from_file(str(song_path))
                song = song.fade_in(fade).fade_out(fade)
                
                block = song if block is None else block.append(song, crossfade=crossfade)
                songs_added += 1
            except Exception as e:
                self.log(f"      Warning: Could not load {song_path.name}: {e}")
                
        return block or AudioSegment.silent(duration=1000), song_index
    
    def create_song_block_with_tracking(self, songs: list, count: int, song_index: int) -> tuple:
        """Create a block of songs and return the last song for ducking."""
        if not songs:
            return AudioSegment.silent(duration=1000), song_index, None
            
        block = None
        songs_added = 0
        fade = self.song_fade_duration.get()
        crossfade = self.crossfade_duration.get()
        last_song = None
        
        while songs_added < count:
            if song_index >= len(songs):
                song_index = 0
                random.shuffle(songs)
                
            song_path = songs[song_index]
            song_index += 1
            
            try:
                self.log(f"      Loading: {song_path.name}")
                song = AudioSegment.from_file(str(song_path))
                song = song.fade_in(fade).fade_out(fade)
                
                block = song if block is None else block.append(song, crossfade=crossfade)
                last_song = song  # Keep track of last song for ducking
                songs_added += 1
            except Exception as e:
                self.log(f"      Warning: Could not load {song_path.name}: {e}")
                
        return block or AudioSegment.silent(duration=1000), song_index, last_song


def main():
    """Main entry point."""
    root = Tk()
    
    # Set theme
    style = ttk.Style()
    try:
        style.theme_use('vista')  # Windows modern theme
    except:
        pass
        
    app = RadioStationApp(root)
    
    # Save config on close
    def on_closing():
        app.stop_watching()
        app.save_config()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
