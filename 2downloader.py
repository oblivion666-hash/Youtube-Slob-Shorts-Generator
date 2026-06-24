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
from heatmap import fetch_heatmap_clips

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")#set color theme for app

#-------Backend---------#




def download_full_video(url, resolution="720p", progress_hook=None):
    if resolution == "1080p":
        fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    elif resolution == "480p":
        fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]"
    else:
        fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"

    ydl_opts = {
        "format": fmt,
        "outtmpl": "%(title)s_source.%(ext)s",
        "merge_output_format": "mp4",
        "overwrites": True,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        for ext in [".webm", ".mkv", ".ytdl"]:
            filename = filename.replace(ext, ".mp4")
        title = info.get("title", "video")
    return filename, title


def cut_clip_from_source(source_path, start_ts, end_ts, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-ss", start_ts,
        "-to", end_ts,
        "-i", source_path,
        "-c", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Clip cut failed: {result.stderr[-500:]}")


















def get_video_duration(filename):
    cmd = [
        "ffprobe", "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        filename
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Failed to parse video duration from ffprobe. stdout: '{result.stdout.strip()}', stderr: '{result.stderr.strip()}'")

def update_status(text, color="white"):
    app.after(0, lambda: status_label.configure(text=text, text_color=color))

def set_button_state(state):
    app.after(0, lambda: download_button.configure(state=state))

whisper_model_cache = None

def get_whisper_model():
    global whisper_model_cache
    if whisper_model_cache is None:
        update_status("Loading transcription model...", "#3b82f6")
        whisper_model_cache = WhisperModel("tiny", device="cpu", compute_type="int8")
    return whisper_model_cache

def generate_srt(video_path, srt_path):
    model = get_whisper_model()
    segments, _ = model.transcribe(video_path, word_timestamps=True)
    all_words = []
    for segment in segments:
        if segment.words is not None:
            for word in segment.words:
                all_words.append(word)

    with open(srt_path, "w") as f:
     i = 1
     idx = 0
     while idx < len(all_words):
        chunk_size = random.randint(1, 5)
        chunk = all_words[idx:idx + chunk_size]
        start = format_srt_time(chunk[0].start)
        end = format_srt_time(chunk[-1].end)
        text = " ".join(w.word.strip() for w in chunk)
        f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        idx += chunk_size
        i += 1

def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def trigger_download():
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
        
    set_controls_state("disabled")
    
    # Safely extract all values in the main thread
    folder = folder_path.get()
    gameplay = quality_var.get()
    resolution = resolution_var.get()
    captions_enabled = caption_var.get()
    custom_name = filename_entry.get().strip()
    multiclip_enabled = multiclip_var.get()
    
    start_ts = get_start_timestamp()
    end_ts = get_end_timestamp()
    
    # Spawn background daemon thread
    threading.Thread(
        target=start_download_thread,
        args=(url, folder, gameplay, resolution, captions_enabled, custom_name, multiclip_enabled, start_ts, end_ts),
        daemon=True
    ).start()

def start_download_thread(url, folder, gameplay, resolution, captions_enabled, custom_name, multiclip_enabled, start_ts, end_ts):
    source_file = None
    try:
        if multiclip_enabled:
            clips = list(clips_list)
        else:
            clips = [(start_ts, end_ts)]

        if not clips:
            raise ValueError("No clips added to the queue!")

        app.after(0, lambda: progress_bar.set(0))
        total_clips = len(clips)

        # Phase 1: download full video once (progress 0% → 40%)
        def ytdl_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    app.after(0, lambda p=downloaded/total*0.4: progress_bar.set(p))
            elif d['status'] == 'finished':
                app.after(0, lambda: progress_bar.set(0.4))

        update_status("Downloading video...", "#3b82f6")
        source_file, video_title = download_full_video(url, resolution, progress_hook=ytdl_hook)

        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Downloaded video file not found: {source_file}")

        # Resolution parameters (used by ffmpeg stack later)
        if resolution == "1080p":
            width, clip_height = 1080, 960
        elif resolution == "480p":
            width, clip_height = 480, 426
        else:
            width, clip_height = 720, 640

        # Phase 2: cut + process each clip (progress 40% → 100%)
        for idx, (start_str, end_str) in enumerate(clips):
            clip_duration = time_to_seconds(end_str) - time_to_seconds(start_str)
            if clip_duration <= 0:
                raise ValueError(f"Clip {idx+1}: End time must be greater than start time")

            clip_base = 0.4 + (idx / total_clips) * 0.6

            update_status(f"[{idx+1}/{total_clips}] Cutting clip...", "#3b82f6")
            raw_filename = f"raw_clip_{idx}.mp4"
            cut_clip_from_source(source_file, normalize_time(start_str), normalize_time(end_str), raw_filename)
            app.after(0, lambda p=clip_base + 0.05/total_clips: progress_bar.set(p))

            if not os.path.exists(raw_filename):
                raise FileNotFoundError(f"Clip file not found after cutting: {raw_filename}")

            update_status(f"[{idx+1}/{total_clips}] Processing gameplay footage...", "#3b82f6")
            gameplay_type, random_start = get_gameplay_with_val(gameplay, clip_duration)

            def sanitize_for_path(name):
                cleaned = re.sub(r"[^\w\s\.-]", "", name)
                cleaned = re.sub(r"\s+", "_", cleaned)
                return cleaned.strip("_")

            if total_clips > 1:
                if custom_name:
                    base_custom = custom_name[:-4] if custom_name.lower().endswith(".mp4") else custom_name
                    final_filename = f"{sanitize_for_path(base_custom)}_{idx+1}.mp4"
                else:
                    final_filename = f"{sanitize_for_path(video_title)}_{idx+1}.mp4"
            else:
                if custom_name:
                    base_custom = custom_name[:-4] if custom_name.lower().endswith(".mp4") else custom_name
                    final_filename = sanitize_for_path(base_custom) + ".mp4"
                else:
                    final_filename = f"{sanitize_for_path(video_title)}_{start_str.replace(':', '_')}_to_{end_str.replace(':', '_')}.mp4"

            raw_basename = os.path.basename(raw_filename)
            safe_base = re.sub(r"[^\w.-]", "_", raw_basename)
            srt_path = safe_base.replace(".mp4", ".srt")

            if captions_enabled:
                update_status(f"[{idx+1}/{total_clips}] Transcribing audio for captions...", "#3b82f6")
                generate_srt(raw_filename, srt_path)

            update_status(f"[{idx+1}/{total_clips}] Combining and rendering video with FFmpeg...", "#eab308")
            output_path = os.path.join(folder, final_filename)

            srt_path_ffmpeg = srt_path.replace("\\", "/").replace(":", "\\:")
            if captions_enabled and os.path.exists(srt_path):
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
                    f"[v0][v1]vstack=inputs=2[v]"
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

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, universal_newlines=True, errors="replace"
            )

            time_pattern = re.compile(r"time=(-?\d{2}):(\d{2}):(\d{2})\.(\d+)")
            stderr_lines = []

            while True:
                line = process.stderr.readline()
                if not line:
                    break
                stderr_lines.append(line)
                match = time_pattern.search(line)
                if match:
                    h, m, s, frac = match.groups()
                    h, m, s = int(h), int(m), int(s)
                    sign = -1 if "-" in match.group(1) else 1
                    current_seconds = sign * (abs(h)*3600 + m*60 + s + float(f"0.{frac}"))
                    if clip_duration > 0:
                        ffmpeg_pct = min(1.0, current_seconds / clip_duration)
                        overall = clip_base + (0.6 / total_clips) * ffmpeg_pct
                        app.after(0, lambda p=overall: progress_bar.set(p))

            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {''.join(stderr_lines[-10:])}")

            if os.path.exists(raw_filename):
                os.remove(raw_filename)
            if os.path.exists(srt_path):
                os.remove(srt_path)

        update_status("Finished! All videos saved successfully.", "#10b981")
        app.after(0, lambda: progress_bar.set(1.0))

    except Exception as e:
        for f in [locals().get('srt_path'), locals().get('raw_filename')]:
            if f and os.path.exists(f):
                try: os.remove(f)
                except Exception: pass
        update_status(f"Error: {str(e)}", "#ef4444")
    finally:
        if source_file and os.path.exists(source_file):
            try: os.remove(source_file)
            except Exception: pass
        set_controls_state("normal")
        app.after(0, update_download_button_state)
        app.after(0, update_add_clip_button_state)





def get_video_clip(url, sections, progress_hook=None, resolution="720p", clip_id=0):
    if resolution == "1080p":
        fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    elif resolution == "480p":
        fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]"
    else:
        fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"

    ydl_opts = {
        "format": fmt,
        "outtmpl": f"%(title)s_clip{clip_id}.%(ext)s",   # unique per clip
        "download_sections": [f"*{start}-{end}" for start, end in sections],
        "merge_output_format": "mp4",
        "continuedl": False,     # never try to resume/reuse a partial from a prior clip
        "overwrites": True,      # always start clean
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


def get_gameplay_with_val(selection, clip_duration):
    gameplay_paths = {
        "Minecraft Jump and run":"gameplay_libary/minecraft_jr",
        "CS-GO Jump and run":"gameplay_libary/csgo_jr",
        "Fortnite Jump and run ":"gameplay_libary/fortnite_jr",
        "Fortnite Battle Royal":"gameplay_libary/fortnite_br",
        "GTA":"gameplay_libary/gta",
    }
    
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

def get_gameplay(clip_duration):
    return get_gameplay_with_val(quality_var.get(), clip_duration)

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
    if 'multiclip_var' in globals() and multiclip_var.get():
        state = "normal" if clips_list else "disabled"
    else:
        state = "normal" if is_timestamp_valid() else "disabled"
    
    if 'download_button' in globals():
        download_button.configure(state=state)

def update_add_clip_button_state():
    state = "normal" if is_timestamp_valid() else "disabled"
    if 'add_clip_button' in globals():
        add_clip_button.configure(state=state)

def update_all_states():
    update_download_button_state()
    update_add_clip_button_state()

def add_clip():
    if not is_timestamp_valid():
        update_status("Error: Invalid timestamp range", "#ef4444")
        return
    try:
        start_ts = get_start_timestamp()
        end_ts = get_end_timestamp()
        
        if (start_ts, end_ts) in clips_list:
            update_status("Clip already in queue!", "#eab308")
            return
            
        clips_list.append((start_ts, end_ts))
        multiclip_var.set(True)
        
        refresh_queue_ui()
        update_all_states()
        update_status(f"Added clip {start_ts} - {end_ts} to queue", "#10b981")
    except Exception as e:
        update_status(f"Error adding clip: {str(e)}", "#ef4444")

def remove_clip(index):
    try:
        if 0 <= index < len(clips_list):
            removed = clips_list.pop(index)
            refresh_queue_ui()
            update_all_states()
            update_status(f"Removed clip {removed[0]} - {removed[1]}", "#f97316")
    except Exception as e:
        update_status(f"Error removing clip: {str(e)}", "#ef4444")

def clear_queue():
    clips_list.clear()
    refresh_queue_ui()
    update_all_states()
    update_status("Queue cleared", "#3b82f6")

def refresh_queue_ui():
    if 'queue_list_frame' not in globals():
        return
    for widget in queue_list_frame.winfo_children():
        widget.destroy()
        
    if not clips_list:
        no_clips_label = ctk.CTkLabel(
            queue_list_frame, 
            text="No clips in queue\n(Single timestamp mode active)", 
            font=("Helvetica", 11), 
            text_color="#64748b"
        )
        no_clips_label.pack(pady=20, fill="both", expand=True)
        return
        
    for idx, (start, end) in enumerate(clips_list):
        clip_item = ctk.CTkFrame(queue_list_frame, fg_color="#1e293b", corner_radius=6)
        clip_item.pack(fill="x", padx=5, pady=3)
        
        clip_lbl = ctk.CTkLabel(
            clip_item, 
            text=f"Clip {idx+1}: {start} - {end}", 
            font=("Helvetica", 11),
            anchor="w"
        )
        clip_lbl.pack(side="left", padx=10, pady=5, fill="x", expand=True)
        
        remove_btn = ctk.CTkButton(
            clip_item, 
            text="✕", 
            width=24, 
            height=24, 
            fg_color="#ef4444", 
            hover_color="#dc2626",
            command=lambda i=idx: remove_clip(i)
        )
        remove_btn.pack(side="right", padx=5, pady=5)




def fetch_heatmap_from_url():
    url = url_entry.get().strip()
    if not url:
        update_status("Error: Please enter a YouTube URL first!", "#ef4444")
        return

    update_status("Fetching heatmap data from YouTube...", "#3b82f6")
    fetch_heatmap_button.configure(state="disabled")

    def _fetch():
        try:
            clips, title = fetch_heatmap_clips(url)

            if not clips:
                app.after(0, lambda: update_status(
                    "No heatmap data available for this video.", "#eab308"
                ))
                return

            added = 0
            for clip in clips:
                if clip not in clips_list:
                    clips_list.append(clip)
                    added += 1

            if added > 0:
                multiclip_var.set(True)
                app.after(0, refresh_queue_ui)
                app.after(0, update_all_states)
                short_title = (title[:35] + "...") if title and len(title) > 35 else (title or "video")
                app.after(0, lambda: update_status(
                    f"Added {added} most-replayed clips from: {short_title}", "#10b981"
                ))
            else:
                app.after(0, lambda: update_status(
                    "All heatmap clips are already in the queue.", "#eab308"
                ))

        except Exception as e:
            app.after(0, lambda err=str(e): update_status(f"Heatmap error: {err}", "#ef4444"))
        finally:
            app.after(0, lambda: fetch_heatmap_button.configure(state="normal"))

    threading.Thread(target=_fetch, daemon=True).start()

def set_controls_state(state):
    url_entry.configure(state=state)
    filename_entry.configure(state=state)
    quality_menu.configure(state=state)
    caption_checkbox.configure(state=state)
    folder_button.configure(state=state)
    resolution_menu.configure(state=state)
    download_button.configure(state=state)
    if 'fetch_heatmap_button' in globals():
        fetch_heatmap_button.configure(state=state)
    
    for entry in [start_h_entry, start_m_entry, start_s_entry, end_h_entry, end_m_entry, end_s_entry]:
        entry.configure(state="disabled" if state == "disabled" else "normal")
        
    if 'add_clip_button' in globals():
        add_clip_button.configure(state=state)
    if 'clear_queue_button' in globals():
        clear_queue_button.configure(state=state)
    if 'multiclip_checkbox' in globals():
        multiclip_checkbox.configure(state=state)

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
    spinbox.configure(command=update_all_states)
    spinbox.bind("<KeyRelease>", lambda event: update_all_states())
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
app.geometry("1050x500")
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=3)
app.grid_columnconfigure(2, weight=1)
app.grid_columnconfigure(3, weight=1)
app.grid_columnconfigure(4, weight=3)
app.iconphoto(False, tk.PhotoImage(file=resource_path('icon.png')))

clips_list = []
multiclip_var = ctk.BooleanVar(value=False)


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
timestamp_frame.grid(row=0, column=2, columnspan=2, rowspan=3, padx=10, pady=10, sticky="nsew")

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

add_clip_button = ctk.CTkButton(timestamp_frame, text="Add Clip to Queue", command=add_clip)
add_clip_button.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="ew")


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



def get_ffmpeg_fonts():
    try:
        # Fragt fontconfig nach allen eindeutigen Schriftfamilien-Namen im System
        result = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            check=True
        )

        # Namen filtern, Duplikate entfernen und alphabetisch sortieren
        fonts = set()
        for line in result.stdout.splitlines():
            # fc-list trennt manchmal alternative Namen mit Kommas
            first_name = line.split(",")[0].strip()
            if first_name:
                fonts.add(first_name)

        return sorted(list(fonts))
    except Exception:
        # Fallback, falls fc-list auf dem System fehlt oder einen Fehler wirft
        return ["Arial", "Impact", "Sans", "Courier New"]

caption_popup = None

def toggle_caption_popup():
    global caption_popup


    if caption_var.get() == 1:

        if caption_popup is None or not caption_popup.winfo_exists():


            caption_popup = ctk.CTkToplevel()
            caption_popup.title("Caption Settings")
            caption_popup.geometry("300x200")
            caption_popup.lift()
            caption_popup.attributes("-topmost", True)


            font_label = ctk.CTkLabel(caption_popup, text="Font")
            font_label.grid(row=1, column=0, padx=10, pady=5)
            # 1. Alle für FFmpeg verfügbaren System-Schriften laden
            available_fonts = get_ffmpeg_fonts()

            # 2. Variable für die ausgewählte Schriftart (Standard: erste aus der Liste oder Arial)
            default_font = "Arial" if "Arial" in available_fonts else available_fonts[0]
            font_var = ctk.StringVar(value=default_font)

            # 3. Das OptionMenu erstellen und die System-Schriften übergeben
            font_menu = ctk.CTkOptionMenu(
                caption_popup,       # Das Pop-up als Master übergeben
                variable=font_var,
                values=available_fonts  # <-- Hier ist Ihre dynamische Liste!
            )
            font_menu.grid(row=1, column=1, padx=10, pady=5)


            caption_popup.protocol("WM_DELETE_WINDOW", close_caption_popup)

    else:

        if caption_popup and caption_popup.winfo_exists():
            caption_popup.destroy()

def close_caption_popup():
    global caption_popup

    caption_checkbox.deselect()
    if caption_popup:
        caption_popup.destroy()





# Caption Checkbox
caption_var = ctk.BooleanVar(value=False)
caption_checkbox = ctk.CTkCheckBox(settings_frame, text="Add Captions", variable=caption_var, command=toggle_caption_popup)
caption_checkbox.grid(row=0, column=1, padx=10, pady=10, sticky="ew")





# Buttons and Resolution Menu
folder_button = ctk.CTkButton(app, text="Download Folder", command=choose_folder)
folder_button.grid(row=3, column=0, padx=20, pady=20, sticky="ew")

resolution_var = ctk.StringVar(value="720p")
resolution_menu = ctk.CTkOptionMenu(app, variable=resolution_var,
                                   values=["1080p", "720p", "480p"])
resolution_menu.grid(row=3, column=1, padx=20, pady=20, sticky="ew")

download_button = ctk.CTkButton(app, text="Download", command=trigger_download, state="disabled")
download_button.grid(row=3, column=2, columnspan=2, padx=20, pady=20, sticky="ew")

# Queue Frame (Multi-clip Display & Controls)
queue_frame = ctk.CTkFrame(app)
queue_frame.grid(row=0, column=4, columnspan=1, rowspan=4, padx=10, pady=10, sticky="nsew")
queue_frame.grid_columnconfigure(0, weight=1)
queue_frame.grid_rowconfigure(2, weight=1)





queue_title = ctk.CTkLabel(queue_frame, text="Clip Queue", font=("Helvetica", 14, "bold"))
queue_title.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

# NEW: heatmap fetch button
fetch_heatmap_button = ctk.CTkButton(
    queue_frame,
    text=" Fetch Most-Replayed Clips",
    command=fetch_heatmap_from_url,
    fg_color="#1d4ed8",
    hover_color="#1e40af"
)
fetch_heatmap_button.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")

queue_list_frame = ctk.CTkScrollableFrame(queue_frame, height=140)
queue_list_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")   # was row=1

multiclip_checkbox = ctk.CTkCheckBox(queue_frame, text="Enable Multi-clip Mode", variable=multiclip_var, command=update_download_button_state)
multiclip_checkbox.grid(row=3, column=0, padx=10, pady=5, sticky="w")    # was row=2

clear_queue_button = ctk.CTkButton(queue_frame, text="Clear Queue", command=clear_queue, fg_color="#374151", hover_color="#4b5563")
clear_queue_button.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")  # was row=3



refresh_queue_ui()
update_all_states()

status_label = ctk.CTkLabel(app, text="Ready", font=("Helvetica", 12))
status_label.grid(row=4, column=0, columnspan=5, padx=20, pady=5, sticky="ew")




#progressbar 
progress_bar = ctk.CTkProgressBar(app, width=1000)
progress_bar.set(0)
progress_bar.grid(row=5, column=0, columnspan=5, padx=20, pady=10, sticky="ew")

app.mainloop()

