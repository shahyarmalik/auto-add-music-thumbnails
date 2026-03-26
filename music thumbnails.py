import os
import re
import stat
import subprocess
import requests
from urllib.parse import quote
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, APIC
from mutagen import File as MutagenFile

MUSIC_FOLDER = r"D:\New folder\music"

SUPPORTED_EXTENSIONS = (".mp3", ".m4a", ".wav", ".wma", ".flac", ".ogg")


def remove_bitrate(text):
    return re.sub(r"\(\s*\d+\s*(k|kbps)?\s*\)", "", text, flags=re.IGNORECASE).strip()


def clean_for_youtube(text):
    text = remove_bitrate(text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"[^a-zA-Z0-9\s$&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    noise_patterns = [
        r"\b\d{2,4}[kKmM]\s*(subs?|subscribers?|views?|special)?\b",
        r"\bvol\w*\s*\d+\b",
        r"\bep\s*\d+\b",
        r"\bpart\s*\d+\b",
        r"\bspecial\b",
        r"\btype beats?\b",
        r"\bmix\b",
        r"\bcompilation\b",
        r"\bplaylist\b",
        r"\bofficial\b",
        r"\blyrics?\b",
        r"\baudio\b",
        r"\bvideo\b",
        r"\bft\b",
        r"\bfeat\b",
        r"\bremix\b",
        r"\bprod\b",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def search_youtube(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(
            f"https://www.youtube.com/results?search_query={quote(query)}",
            headers=headers,
            timeout=10
        )

        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
        if match:
            video_id = match.group(1)
            print(f"   -> Found video ID: {video_id}")

            for quality in ["maxresdefault", "sddefault", "hqdefault", "mqdefault", "default"]:
                thumb_url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
                check = requests.get(thumb_url, timeout=10)
                if check.status_code == 200 and len(check.content) > 1000:
                    print(f"   -> Using thumbnail quality: {quality}")
                    return thumb_url

            print("   -> No valid thumbnail found for this video")
        else:
            print("   -> Could not extract video ID from search page")

    except Exception as e:
        print("YouTube search error:", e)

    return None


def convert_wma_to_m4a(wma_path):
    m4a_path = os.path.splitext(wma_path)[0] + ".m4a"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", wma_path, "-c:a", "aac", "-q:a", "2", m4a_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0 and os.path.exists(m4a_path):
            os.remove(wma_path)
            print(f"   -> Converted to .m4a: {os.path.basename(m4a_path)}")
            return m4a_path
        else:
            print("   -> ffmpeg conversion failed. Is ffmpeg installed?")
            return None
    except FileNotFoundError:
        print("   -> ffmpeg not found. Install it from https://ffmpeg.org/download.html")
        return None


def unlock_file(file_path):
    """Remove read-only flag from file."""
    try:
        os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
    except Exception as e:
        print(f"   -> Could not unlock file: {e}")


def embed_artwork(file_path, image_url):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return False

        image_data = response.content
        ext = os.path.splitext(file_path)[1].lower()

        # Convert WMA to M4A first
        if ext == ".wma":
            unlock_file(file_path)
            file_path = convert_wma_to_m4a(file_path)
            if file_path is None:
                return False
            ext = ".m4a"

        # Unlock the file before writing
        unlock_file(file_path)

        if ext in (".m4a", ".mp4", ".aac"):
            audio = MP4(file_path)
            audio["covr"] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
            return True

        elif ext == ".mp3":
            audio = MP3(file_path, ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(
                APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=image_data)
            )
            audio.save(v2_version=3)
            return True

        elif ext in (".wav", ".flac", ".ogg"):
            audio = MutagenFile(file_path)
            if audio is None:
                print(f"   -> Unsupported format: {ext}")
                return False
            if not audio.tags:
                audio.add_tags()
            if hasattr(audio.tags, "add"):
                audio.tags.delall("APIC")
                audio.tags.add(
                    APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=image_data)
                )
                audio.save()
                return True
            else:
                print(f"   -> Cannot embed cover in {ext} files")
                return False

    except Exception as e:
        print("Embed error:", e)
        return False


def process_music(folder):
    print(f"Scanning folder: {folder}")

    if not os.path.exists(folder):
        print("ERROR: Folder does not exist! Check your MUSIC_FOLDER path.")
        return

    all_files = []
    for root, _, files in os.walk(folder):
        for f in files:
            all_files.append(os.path.join(root, f))

    music_files = [f for f in all_files if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS]

    print(f"   Total files found:  {len(all_files)}")
    print(f"   Music files found:  {len(music_files)}")

    if not music_files:
        print("No supported music files found.")
        return

    for file_path in music_files:
        filename = os.path.basename(file_path)
        original_name = os.path.splitext(filename)[0]
        query = clean_for_youtube(original_name)

        print(f"\nSearching: {query}")

        artwork_url = search_youtube(query)

        if artwork_url:
            success = embed_artwork(file_path, artwork_url)
            if success:
                print(f"OK: {filename}")
            else:
                print(f"FAILED to embed: {filename}")
        else:
            print(f"No result: {filename}")


if __name__ == "__main__":
    process_music(MUSIC_FOLDER)