#!/usr/bin/env python3

import os
import requests
import subprocess
from flask import Flask, render_template, request, Response, send_from_directory
import shutil
import threading
import time
import re
from werkzeug.utils import secure_filename  # For handling file uploads

app = Flask(__name__)

# Configuration
DEFAULT_WATERMARK_TEXT = "Your Watermark"
TEMP_VIDEO_DIR = "temp_videos"
OUTPUT_VIDEO_DIR = "watermarked_videos"
UPLOAD_FOLDER = 'uploads' #For storing uploaded images
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} # Allowed image extensions
PORT = 5000

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True) #Create upload directory

#Utility function to test valid image extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_filename(url):
    filename = os.path.basename(url)
    filename = filename.split('?')[0]
    filename = re.sub(r'[^\w\.]', '_', filename)
    if not filename:
        filename = "default_video.mp4"
    base, ext = os.path.splitext(filename)
    if not ext:
        return filename + '.mp4'
    return filename

def download_video(url, filename, progress_callback):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_length = response.headers.get('content-length')
        if total_length is None:
            filepath = os.path.join(TEMP_VIDEO_DIR, filename)
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            progress_callback(100)
            return filepath

        total_length = int(total_length)
        chunk_size = 1024 * 1024
        downloaded = 0
        filepath = os.path.join(TEMP_VIDEO_DIR, filename)

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int((downloaded / total_length) * 100)
                    progress_callback(percent)

        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Error downloading video: {e}")
        return None


def add_watermark(input_file, output_file, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_path, progress_callback):
    try:
        # Build the drawtext filter string
        drawtext = f"text='{watermark_text}':fontfile=/usr/share/fonts/truetype/dejavu/{watermark_font}:fontsize={watermark_size}:fontcolor={watermark_color}@{watermark_opacity}"

        # Position the watermark
        if watermark_position == "top-left":
            x = "10"
            y = "10"
        elif watermark_position == "top-right":
            x = "w-tw-10"  # w = video width, tw = text width
            y = "10"
        elif watermark_position == "bottom-left":
            x = "10"
            y = "h-th-10"  # h = video height, th = text height
        elif watermark_position == "bottom-right":
            x = "w-tw-10"
            y = "h-th-10"
        else:  # center
            x = "(w-tw)/2"
            y = "(h-th)/2"

        drawtext += f":x={x}:y={y}"
        filter_complex = f"[0:v]drawtext={drawtext}[text];[text]"

        # Handle Image Overlay
        if image_watermark_path:
            #Ensure the watermark is scaled to a sensible size
            overlay = f"[1:v]scale=100:100[overlay];[0:v][overlay]overlay=10:10"  #Scale the image to 100x100

            filter_complex = f"[0:v][1:v]overlay=10:10[out]" #Simple image overlay
        else:
            filter_complex = f"[0:v]drawtext={drawtext}[out]"


        command = [
            "ffmpeg",
            "-i", input_file,
        ]

        if image_watermark_path:
            command.extend(["-i", image_watermark_path]) #Add the second input, the logo

        command.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]", #Map the output of the filter graph
            "-codec:a", "copy",
            output_file
        ])


        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        duration = None
        progress = 0

        while True:
            line = process.stderr.readline()
            if not line:
                break
            print(line.strip())

            if duration is None:
                match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
                if match:
                    hours, minutes, seconds = map(float, match.groups())
                    duration = hours * 3600 + minutes * 60 + seconds

            match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
            if match and duration:
                hours, minutes, seconds = map(float, match.groups())
                time_elapsed = hours * 3600 + minutes * 60 + seconds
                progress = int((time_elapsed / duration) * 100)
                progress_callback(progress)

        process.wait()
        if process.returncode != 0:
            print(f"FFmpeg error: {process.stderr.read()}")
            return False

        progress_callback(100)
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error adding watermark: {e}")
        return False

def event_stream(video_url, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_filename):
    """Generates progress updates for SSE."""
    def progress_callback(percent):
        yield f"data: {percent}\n\n"

    filename = generate_filename(video_url)
    print(f"Generated filename: {filename}")

    input_filepath = download_video(video_url, filename, progress_callback)
    if not input_filepath:
        yield "data: error\n\n"
        return

    output_filepath = os.path.join(OUTPUT_VIDEO_DIR, "watermarked_" + filename)

    #Construct the full path to the waternmart
    image_watermark_path = None
    if image_watermark_filename: #If a file was uploaded
      image_watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], image_watermark_filename)

    if not add_watermark(input_filepath, output_filepath, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_path, progress_callback):
        yield "data: error\n\n"
        return

    yield "data: complete\n\n"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    video_url = request.form["video_url"]
    watermark_text = request.form["watermark_text"]
    watermark_position = request.form["watermark_position"]
    watermark_font = request.form["watermark_font"]
    watermark_size = int(request.form["watermark_size"])
    watermark_color = request.form["watermark_color"]
    watermark_opacity = float(request.form["watermark_opacity"])

    #Handle Image upload
    image_watermark = request.files['image_watermark']

    image_watermark_filename = None #Store the filename, or None if nothing

    if image_watermark and allowed_file(image_watermark.filename):
        filename = secure_filename(image_watermark.filename)
        image_watermark.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_watermark_filename = filename # Store the filename
    #else:
    #  return 'Invalid image file'

    return render_template("processing.html", video_url=video_url, watermark_text=watermark_text)

@app.route('/stream', methods=['POST'])
def stream():
    video_url = request.form["video_url"]
    watermark_text = request.form["watermark_text"]
    watermark_position = request.form["watermark_position"]
    watermark_font = request.form["watermark_font"]
    watermark_size = int(request.form["watermark_size"])
    watermark_color = request.form["watermark_color"]
    watermark_opacity = float(request.form["watermark_opacity"])
    image_watermark_filename = request.form.get("image_watermark_filename") #Get the water mark

    return Response(event_stream(video_url, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_filename), mimetype="text/event-stream")

@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(OUTPUT_VIDEO_DIR, filename)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=PORT)
