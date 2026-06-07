import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import yt_dlp
import threading
import os
import sys
import random
import subprocess
import re
from faster_whisper import WhisperModel
from tkinterdnd2 import TkinterDnD, DND_TEXT


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")#set color theme for app

#-------Backend---------#






def get_video_duration(filename):
    cmd = [
        "ffprobe", "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        filename
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def update_status(text, color="white"):
    app.after(0, lambda: status_label.configure(text=text, text_color=color))

def set_button_state(state):
    app.after(0, lambda: download_button.configure(state=state))

def generate_srt(video_path, srt_path):
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, word_timestamps=True)
    all_words = []
    for segment in segments:
      for word in segment.words:
        all_words.append(word)

    words_per_chunk = 3
    with open(srt_path, "w") as f:
      for i, chunk_start in enumerate(range(0, len(all_words), words_per_chunk), start=1):
        chunk = all_words[chunk_start:chunk_start + words_per_chunk]
        start = format_srt_time(chunk[0].start)
        end = format_srt_time(chunk[-1].end)
        text = " ".join(w.word.strip() for w in chunk)
        f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def start_download():
    url = url_entry.get().strip()
    if not url:
        update_status("Error: Please enter a YouTube URL!", "#ef4444")
        return
    if not folder_path.get():
        update_status("Error: Please select a download folder first!", "#ef4444")
        return
    if quality_var.get() == "Choose Gameplay":
        update_status("Error: Please select a gameplay type!", "#ef4444")
        return
        
    set_button_state("disabled")
    update_status("Downloading YouTube video clip...", "#3b82f6")
    
    try:
        start_str = get_start_timestamp()
        end_str = get_end_timestamp()
        clip_duration = time_to_seconds(end_str) - time_to_seconds(start_str)
        if clip_duration <= 0:
            raise ValueError("End time must be greater than start time")
            
        sections = [(normalize_time(start_str), normalize_time(end_str))]
        
        # Reset progress bar
        app.after(0, lambda: progress_bar.set(0))
        
        # Define progress hook for yt-dlp (Stage 1: 0% to 50%)
        def ytdl_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    percent = downloaded / total
                    app.after(0, lambda: progress_bar.set(percent * 0.5))
            elif d['status'] == 'finished':
                app.after(0, lambda: progress_bar.set(0.5))
        
        # Get selected resolution parameters
        resolution = resolution_var.get()
        if resolution == "1080p":
            width = 1080
            clip_height = 960
        elif resolution == "480p":
            width = 480
            clip_height = 426
        else: # Default/720p
            width = 720
            clip_height = 640

        # Download clip with the resolution constraint
        raw_filename, video_title = get_video_clip(url, sections, progress_hook=ytdl_hook, resolution=resolution)
        
        if not os.path.exists(raw_filename):
            raise FileNotFoundError(f"Downloaded video file not found: {raw_filename}")
            
        update_status("Processing gameplay footage...", "#3b82f6")
        gameplay_type, random_start = get_gameplay(clip_duration)
        
        # Determine output filename
        def sanitize_for_path(name):
            cleaned = re.sub(r"[^\w\s\.-]", "", name)
            cleaned = re.sub(r"\s+", "_", cleaned)
            return cleaned.strip("_")

        custom_name = filename_entry.get().strip()
        if custom_name:
            if custom_name.lower().endswith(".mp4"):
                custom_name = custom_name[:-4]
            final_filename = sanitize_for_path(custom_name) + ".mp4"
        else:
            sanitized_title = sanitize_for_path(video_title)
            final_filename = f"{sanitized_title}_{start_str.replace(':', '_')}_to_{end_str.replace(':', '_')}.mp4"
            
        # Generate subtitles path - sanitizing the name to make it safe for FFmpeg subtitles filter
        raw_basename = os.path.basename(raw_filename)
        safe_base = re.sub(r"[^\w.-]", "_", raw_basename)
        srt_path = safe_base.replace(".mp4", ".srt")
        
        if caption_var.get():
            update_status("Transcribing audio for captions...", "#3b82f6")
            generate_srt(raw_filename, srt_path)
            
        update_status("Combining and rendering video with FFmpeg...", "#eab308")
        output_path = os.path.join(folder_path.get(), final_filename)
        
        # Run ffmpeg to stack the main clip and gameplay clip
        srt_path_ffmpeg = srt_path.replace("\\", "/").replace(":", "\\:")
        if caption_var.get() and os.path.exists(srt_path):
            filter_complex = (
                f"[0:v]scale=w='max({width},iw*{clip_height}/ih)':h={clip_height},crop={width}:{clip_height}[v0];"
                f"[1:v]scale=w='max({width},iw*{clip_height}/ih)':h={clip_height},crop={width}:{clip_height}[v1];"
                f"[v0][v1]vstack=inputs=2[stacked];"
                f"[stacked]subtitles={srt_path_ffmpeg}:force_style='FontSize=14,Alignment=2,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2'[v]"
            )
        else:
            filter_complex = (
                f"[0:v]scale=w='max({width},iw*{clip_height}/ih)':h={clip_height},crop={width}:{clip_height}[v0];"
                f"[1:v]scale=w='max({width},iw*{clip_height}/ih)':h={clip_height},crop={width}:{clip_height}[v1];"
                "[v0][v1]vstack=inputs=2[v]"
            )
        cmd = [
            "ffmpeg", "-y",
            "-i", raw_filename,
            "-ss", str(random_start),
            "-t", str(clip_duration),
            "-i", gameplay_type,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        
        # Execute command and track progress (Stage 2: 50% to 95%)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        time_pattern = re.compile(r"time=(-?\d{2}):(\d{2}):(\d{2})\.(\d+)")
        stderr_lines = []
        
        while True:
            line = process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line)
            
            # Parse time
            match = time_pattern.search(line)
            if match:
                hours, minutes, seconds, fraction_part = match.groups()
                hours, minutes, seconds = int(hours), int(minutes), int(seconds)
                sign = -1 if hours < 0 or (hours == 0 and "-" in match.group(1)) else 1
                hours = abs(hours)
                fraction = float(f"0.{fraction_part}")
                current_seconds = sign * (hours * 3600 + minutes * 60 + seconds + fraction)
                if clip_duration > 0:
                    ffmpeg_percent = current_seconds / clip_duration
                    percent = 0.5 + 0.45 * min(1.0, ffmpeg_percent)
                    app.after(0, lambda p=percent: progress_bar.set(p))
                    
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {''.join(stderr_lines[-10:])}")
            
        # Cleanup
        if os.path.exists(raw_filename):
            os.remove(raw_filename)
        if 'srt_path' in locals() and os.path.exists(srt_path):
            os.remove(srt_path)
            
        update_status("Finished! Video saved successfully.", "#10b981")
        app.after(0, lambda: progress_bar.set(1.0))
    except Exception as e:
        if 'srt_path' in locals() and os.path.exists(srt_path):
            try:
                os.remove(srt_path)
            except Exception:
                pass
        update_status(f"Error: {str(e)}", "#ef4444")
    finally:
        app.after(0, update_download_button_state)

def get_video_clip(url, sections, progress_hook=None, resolution="720p"):
    if resolution == "1080p":
        fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    elif resolution == "480p":
        fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]"
    else:
        fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"

    ydl_opts = {
        "format": fmt,
        "outtmpl": "%(title)s.%(ext)s",
        "download_sections": [f"*{start}-{end}" for start, end in sections],
        "force_keyframes_at_cuts": True,
        "postprocessor_args": [
            "-ss", sections[0][0],
            "-to", sections[0][1]
        ],
        "merge_output_format": "mp4",
        "verbose": True,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        for ext in [".webm", ".mkv", ".ytdl"]:
            filename = filename.replace(ext, ".mp4")
        video_title = info.get("title", "video_clip")
    return filename, video_title

def get_gameplay(clip_duration):
    gameplay_paths = {
        "Minecraft Jump and run":"gameplay_libary/minecraft_jr",
        "CS-GO Jump and run":"gameplay_libary/csgo_jr",
        "Fortnite Jump and run ":"gameplay_libary/fortnite_jr",
        "Fortnite Battle Royal":"gameplay_libary/fortnite_br",
        "GTA":"gameplay_libary/gta",
    }
    
    selection = quality_var.get()
    if selection not in gameplay_paths:
        raise ValueError("Invalid gameplay selection")
        
    folder = resource_path(gameplay_paths[selection])
    gameplay_type = get_random_gameplay_file(folder)
    
    gameplay_duration = get_video_duration(gameplay_type)
    
    if gameplay_duration <= clip_duration:
        raise ValueError(f"Gameplay clip ({gameplay_duration:.1f}s) is shorter than target duration ({clip_duration:.1f}s)")
        
    max_start = gameplay_duration - clip_duration
    random_start = random.uniform(0, max_start)
    
    return gameplay_type, random_start

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath("")

    return os.path.join(base_path, relative_path)


def time_to_seconds(time_str):
    parts = list(map(int, time_str.split(":")))

    if len(parts) == 2:  # mm:ss
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:  # hh:mm:ss
        return parts[0]*3600 + parts[1]*60 + parts[2]
    else:
        raise ValueError("Invalid time format")

def normalize_time(t):
    parts = t.split(":")
    if len(parts) == 2:
        return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    if len(parts) == 3:
        return ":".join(p.zfill(2) for p in parts)
    raise ValueError("Bad time format")






def get_timestamp_from_fields(hour_entry, minute_entry, second_entry):
    hour = hour_entry.get().strip() or "0"
    minute = minute_entry.get().strip() or "0"
    second = second_entry.get().strip() or "0"

    if not (hour.isdigit() and minute.isdigit() and second.isdigit()):
        raise ValueError("Timestamp fields must contain only digits")

    return f"{int(hour):02d}:{int(minute):02d}:{int(second):02d}"

def get_start_timestamp():
    return get_timestamp_from_fields(start_h_entry, start_m_entry, start_s_entry)

def get_end_timestamp():
    return get_timestamp_from_fields(end_h_entry, end_m_entry, end_s_entry)







def is_timestamp_valid():
    try:
        start_ts = get_start_timestamp()
        end_ts = get_end_timestamp()
        return time_to_seconds(start_ts) < time_to_seconds(end_ts)
    except ValueError:
        return False

def update_download_button_state():
    state = "normal" if is_timestamp_valid() else "disabled"
    download_button.configure(state=state)


def create_timestamp_spinbox(parent, values):
    spinbox = tk.Spinbox(
        parent,
        values=values,
        width=5,
        justify="center",
        font=("Helvetica", 12),
        bg="#1f2937",
        fg="#f8fafc",
        insertbackground="#f8fafc",
        highlightthickness=1,
        highlightbackground="#334155",
        relief="flat",
        bd=0,
    )
    spinbox.configure(command=update_download_button_state)
    spinbox.bind("<KeyRelease>", lambda event: update_download_button_state())
    return spinbox


def get_random_gameplay_file(folder):
    files = [f for f in os.listdir(folder) if f.endswith(".mp4")]

    if not files:
        raise ValueError("No gameplay videos found")

    chosen = random.choice(files)
    return os.path.join(folder, chosen)



#----------UI-----------------

class App(ctk.CTk, TkinterDnD.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

app = App()
app.title("YouTube Slop-Generator")
app.geometry("800x300")
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=3)
app.iconphoto(False, tk.PhotoImage(file=resource_path('icon.png')))


#Takes either url or mp4-file + timestamp/stamps : if url is entered download
# URL
ctk.CTkLabel(app, text="ENTER YouTube URL:").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
url_entry = ctk.CTkEntry(app, width=300)
url_entry._entry.drop_target_register(DND_TEXT)
url_entry._entry.dnd_bind('<<Drop>>', lambda e: (url_entry.delete(0, "end"), url_entry.insert(0, e.data.strip("{}"))))
url_entry.grid(row=0, column=1, padx=5, pady=5)

# Custom Output Name
ctk.CTkLabel(app, text="Custom Output Name:").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
filename_entry = ctk.CTkEntry(app, width=300, placeholder_text="Optional: leave blank for default")
filename_entry.grid(row=1, column=1, padx=5, pady=5)


#Timestampp

timestamp_frame = ctk.CTkFrame(app)
timestamp_frame.grid(row=0, column=2, columnspan=2, rowspan=2, padx=10, pady=10, sticky="ew")

start_label = ctk.CTkLabel(timestamp_frame, text="Start (hh:mm:ss)")
start_label.grid(row=0, column=0, padx=10, pady=5)

start_h_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(24)])
start_h_entry.grid(row=0, column=1, padx=(0, 2), pady=5)

start_m_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(60)])
start_m_entry.grid(row=0, column=2, padx=(0, 2), pady=5)

start_s_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(60)])
start_s_entry.grid(row=0, column=3, padx=(0, 2), pady=5)

end_label = ctk.CTkLabel(timestamp_frame, text="End (hh:mm:ss)")
end_label.grid(row=1, column=0, padx=10, pady=5)

end_h_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(24)])
end_h_entry.grid(row=1, column=1, padx=(0, 2), pady=5)

end_m_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(60)])
end_m_entry.grid(row=1, column=2, padx=(0, 2), pady=5)

end_s_entry = create_timestamp_spinbox(timestamp_frame, [f"{i:02d}" for i in range(60)])
end_s_entry.grid(row=1, column=3, padx=(0, 2), pady=5)


# Folder
folder_path = ctk.StringVar()
def choose_folder():
    folder = filedialog.askdirectory()
    folder_path.set(folder)

# Settings Frame (Gameplay Selection & Captions Checkbox)
settings_frame = ctk.CTkFrame(app)
settings_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
settings_frame.grid_columnconfigure(0, weight=1)
settings_frame.grid_columnconfigure(1, weight=1)

# Get Gameplay type
quality_var = ctk.StringVar(value="Choose Gameplay")
quality_menu = ctk.CTkOptionMenu(settings_frame, variable=quality_var,
                                values=["Minecraft Jump and run",
                                        "CS-GO Jump and run",
                                        "Fortnite Jump and run ",
                                        "Fortnite Battle Royal",
                                        "GTA"])
quality_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

# Caption Checkbox
caption_var = ctk.BooleanVar(value=False)
caption_checkbox = ctk.CTkCheckBox(settings_frame, text="Add Captions", variable=caption_var)
caption_checkbox.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

# Buttons and Resolution Menu
folder_button = ctk.CTkButton(app, text="Download Folder", command=choose_folder)
folder_button.grid(row=3, column=0, padx=20, pady=20, sticky="ew")

resolution_var = ctk.StringVar(value="720p")
resolution_menu = ctk.CTkOptionMenu(app, variable=resolution_var,
                                   values=["1080p", "720p", "480p"])
resolution_menu.grid(row=3, column=1, padx=20, pady=20, sticky="ew")

download_button = ctk.CTkButton(app, text="Download", command=lambda: threading.Thread(target=start_download, daemon=True).start(), state="disabled")
download_button.grid(row=3, column=2, columnspan=2, padx=20, pady=20, sticky="ew")
update_download_button_state()

status_label = ctk.CTkLabel(app, text="Ready", font=("Helvetica", 12))
status_label.grid(row=4, column=0, columnspan=4, padx=20, pady=5, sticky="ew")




#progressbar 
progress_bar = ctk.CTkProgressBar(app, width=800)
progress_bar.set(0)
progress_bar.grid(row=5, column=0, columnspan=4, padx=20, pady=10, sticky="ew")

app.mainloop()

