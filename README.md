# YouTube Slop Generator

A desktop app that turns any YouTube clip into a short-form vertical video by automatically mashing it with gameplay footage — with optional auto-generated captions.

---

## What it does

- Downloads a timestamped clip from any YouTube URL via yt-dlp
- Stacks it on top of a randomly selected gameplay background (Minecraft, CS:GO, Fortnite, GTA)
- Optionally transcribes the audio and burns word-by-word captions into the video
- Exports a ready-to-upload vertical MP4

---

## Requirements

### System dependencies
These must be installed and available on your PATH:

**ffmpeg** (required for all video processing)

Linux (Fedora):
```bash
sudo dnf install ffmpeg
```

Linux (Ubuntu/Debian):
```bash
sudo apt install ffmpeg
```

macOS:
```bash
brew install ffmpeg
```

Windows:
Download from https://ffmpeg.org/download.html and add to PATH.

---

### Python dependencies

Python 3.8 or higher required.

Install all dependencies with:
```bash
pip install -r requirements.txt
```

---

## Setup

**1. Clone the repository:**
```bash
git clone https://github.com/yourusername/slop_machine
cd slop_machine
```

**2. Install Python dependencies:**
```bash
pip install -r requirements.txt
```

**3. Add your gameplay footage:**

Create the following folder structure in the project directory and drop your `.mp4` gameplay clips inside the relevant folders:
```
gameplay_libary/
  minecraft_jr/
  csgo_jr/
  fortnite_jr/
  fortnite_br/
  gta/
```

Any resolution or aspect ratio works — the app handles scaling automatically.

**4. Add the app icon:**

Place an `icon.png` file in the project root directory.

**5. Run the app:**
```bash
python downloader.py
```

---

## Usage

1. Paste or drag a YouTube URL into the URL field
2. Set the start and end timestamps for the clip you want
3. Select a gameplay type from the dropdown
4. Choose an output resolution (480p / 720p / 1080p)
5. Optionally tick "Add Captions" for auto-generated word-by-word subtitles
6. Optionally enter a custom output filename
7. Select an output folder
8. Hit Download

---

## Notes

- The first time you use captions, the Whisper tiny model (~75MB) will be downloaded automatically
- Gameplay clips must be longer than the clip you are downloading
- The app picks a random segment from the gameplay library each time
- Captions slow down the process slightly due to transcription

---

## Built with

- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) — GUI
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube downloading
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — audio transcription
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — drag and drop
- [ffmpeg](https://ffmpeg.org/) — video processing
