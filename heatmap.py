import yt_dlp


def seconds_to_hhmmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _find_peaks(times, values, max_clips=10, min_distance_sec=30):
    """Greedy peak selection: highest value first, enforcing min gap between picks."""
    indexed = sorted(zip(times, values), key=lambda x: x[1], reverse=True)
    selected = []
    for t, _ in indexed:
        if not any(abs(t - s) < min_distance_sec for s in selected):
            selected.append(t)
        if len(selected) >= max_clips:
            break
    selected.sort()
    return selected


def fetch_heatmap_clips(url: str, buffer_sec: int = 10, max_clips: int = 10, min_distance_sec: int = 30):
    """
    Returns (clips, title) where clips is a list of ("hh:mm:ss", "hh:mm:ss") tuples.
    Returns ([], title) if no heatmap is available.
    """
    ydl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    raw_heatmap = info.get("heatmap")
    title = info.get("title")

    if not raw_heatmap:
        return [], title

    video_duration = info.get("duration") or float("inf")
    times  = [e["start_time"] for e in raw_heatmap]
    values = [e["value"]      for e in raw_heatmap]

    peak_times = _find_peaks(times, values, max_clips=max_clips, min_distance_sec=min_distance_sec)

    clips = []
    for t in peak_times:
        start = seconds_to_hhmmss(max(0.0, t - buffer_sec))
        end   = seconds_to_hhmmss(min(video_duration, t + buffer_sec))
        clips.append((start, end))

    return clips, title
