#!/usr/bin/env python3

import os
import requests
import subprocess
from flask import Flask, render_template, request, Response
import shutil
import threading
import time
import re  # For extracting file extension

app = Flask(__name__)

# Configuration
WATERMARK_TEXT = "Your Watermark"  # Customize this!
TEMP_VIDEO_DIR = "temp_videos"
OUTPUT_VIDEO_DIR = "watermarked_videos"
PORT = 5000  # Default port

# Create directories if they don't exist
os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)

def generate_filename(url):
    """Generates a filename from a URL, handling edge cases."""
    filename = os.path.basename(url)
    # Remove query parameters (everything after the '?')
    filename = filename.split('?')[0]
    # Remove any characters that are not alphanumeric, dots, or underscores
    filename = re.sub(r'[^\w\.]', '_', filename)

    # If the filename is empty after processing (very unlikely but possible), use a default name
    if not filename:
        filename = "default_video.mp4"  # Or any default name you prefer

    # Extract the file extension (if any)
    base, ext = os.path.splitext(filename)
    if not ext: # If no extension, assume mp4
        return filename + '.mp4'  # Append a default extension

    return filename

def download_video(url, filename, progress_callback):
    """Downloads a video from a URL with progress updates."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_length = response.headers.get('content-length')
        if total_length is None:  # no content length header
            filepath = os.path.join(TEMP_VIDEO_DIR, filename)
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            progress_callback(100) #Report completion since we can't track progress
            return filepath

        total_length = int(total_length)
        chunk_size = 1024 * 1024  # 1MB chunks
        downloaded = 0
        filepath = os.path.join(TEMP_VIDEO_DIR, filename)

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int((downloaded / total_length) * 100)
                    progress_callback(percent)

        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Error downloading video: {e}")
        return None

def add_watermark(input_file, output_file, watermark_text, progress_callback):
    """Adds a text watermark to the video with progress updates."""
    try:
        command = [
            "ffmpeg",
            "-i", input_file,
            "-vf", f"drawtext=text='{watermark_text}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=24:x=10:y=10:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5",
            "-codec:a", "copy",
            output_file
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Parse FFmpeg output for progress (this is tricky and might need adjustment)
        duration = None
        progress = 0

        while True:
            line = process.stderr.readline()
            if not line:
                break
            print(line.strip())  # Print FFmpeg output for debugging

            # Get duration (only needs to be done once)
            if duration is None:
                match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
                if match:
                    hours, minutes, seconds = map(float, match.groups())
                    duration = hours * 3600 + minutes * 60 + seconds

            # Get progress
            match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
            if match and duration:
                hours, minutes, seconds = map(float, match.groups())
                time_elapsed = hours * 3600 + minutes * 60 + seconds
                progress = int((time_elapsed / duration) * 100)
                progress_callback(progress)

        process.wait() # Wait for the process to complete
        if process.returncode != 0:
            print(f"FFmpeg error: {process.stderr.read()}")
            return False

        progress_callback(100)  # Report 100% when done
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error adding watermark: {e}")
        return False

def event_stream(video_url):
    """Generates progress updates for SSE."""
    def progress_callback(percent):
        yield f"data: {percent}\n\n"

    # Extract filename from URL
    filename = generate_filename(video_url)
    print(f"Generated filename: {filename}")

    input_filepath = download_video(video_url, filename, progress_callback)
    if not input_filepath:
        yield "data: error\n\n"
        return

    output_filepath = os.path.join(OUTPUT_VIDEO_DIR, "watermarked_" + filename)
    if not add_watermark(input_filepath, output_filepath, WATERMARK_TEXT, progress_callback):
        yield "data: error\n\n"
        return

    yield "data: complete\n\n"  # Signal completion


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    video_url = request.form["video_url"]
    return render_template("processing.html", video_url=video_url)

@app.route('/stream/<path:video_url>')
def stream(video_url):
    return Response(event_stream(video_url), mimetype="text/event-stream")

@app.route("/videos/<path:filename>")
def serve_video(filename):
    """Serves the watermarked video file."""
    return send_from_directory(OUTPUT_VIDEO_DIR, filename)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=PORT)
