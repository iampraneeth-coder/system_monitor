#!/usr/bin/env python3

import os
import requests
import subprocess
from flask import Flask, render_template, send_from_directory
import shutil

app = Flask(__name__)

# Configuration
WATERMARK_TEXT = "Your Watermark"  # Customize this!
TEMP_VIDEO_DIR = "temp_videos"
OUTPUT_VIDEO_DIR = "watermarked_videos"
PORT = 5000 # Default port

# Create directories if they don't exist
os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)

def download_video(url, filename):
    """Downloads a video from a URL."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for bad status codes

        filepath = os.path.join(TEMP_VIDEO_DIR, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(response.raw, f) # Use copyfileobj for large files
        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Error downloading video: {e}")
        return None

def add_watermark(input_file, output_file, watermark_text):
    """Adds a text watermark to the video using FFmpeg."""
    try:
        command = [
            "ffmpeg",
            "-i", input_file,
            "-vf", f"drawtext=text='{watermark_text}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=24:x=10:y=10:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5", #Adjust placement and style!
            "-codec:a", "copy",  # Copy audio stream
            output_file
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error adding watermark: {e.stderr}")
        return False

@app.route("/")
def index():
    return render_template("index.html")  # Simple form for URL input

@app.route("/process", methods=["POST"])
def process_video():
    from flask import request
    video_url = request.form["video_url"]

    # Extract filename from URL
    filename = os.path.basename(video_url)
    if not filename:
        return "Error: Could not extract filename from URL."

    input_filepath = download_video(video_url, filename)
    if not input_filepath:
        return "Error: Video download failed."

    output_filepath = os.path.join(OUTPUT_VIDEO_DIR, "watermarked_" + filename)

    if add_watermark(input_filepath, output_filepath, WATERMARK_TEXT):
        return render_template("video.html", video_filename="watermarked_" + filename)
    else:
        return "Error: Watermarking failed."

@app.route("/videos/<path:filename>")
def serve_video(filename):
    """Serves the watermarked video file."""
    return send_from_directory(OUTPUT_VIDEO_DIR, filename)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=PORT) # Accessible from your network
