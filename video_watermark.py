#!/usr/bin/env python3

import os
import requests
import subprocess
from flask import Flask, render_template, request, Response, send_from_directory, make_response
import shutil
import threading
import time
import re
import uuid  # For generating unique IDs
from werkzeug.utils import secure_filename  # For handling file uploads

app = Flask(__name__)

# Configuration
DEFAULT_WATERMARK_TEXT = "Your Watermark"
TEMP_VIDEO_DIR = "temp_videos"
OUTPUT_VIDEO_DIR = "watermarked_videos"
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
FFMPEG_TIMEOUT = 600  # Seconds (10 minutes)
PORT = 5000

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
os.makedirs(OUTPUT_VIDEO_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

def generate_unique_filename(base_filename):
    """Generates a unique filename with timestamp and UUID."""
    timestamp = str(int(time.time()))
    unique_id = uuid.uuid4().hex
    base, ext = os.path.splitext(base_filename)
    return f"{base}_{timestamp}_{unique_id}{ext}"

def cleanup_files(filepath):
    """Cleans up the specified file or directory."""
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            print(f"Deleted file: {filepath}")
        elif os.path.isdir(filepath):
            shutil.rmtree(filepath)
            print(f"Deleted directory: {filepath}")
        else:
            print(f"Warning: {filepath} not found.")
    except Exception as e:
        print(f"Error cleaning up {filepath}: {e}")

def download_video(url, filename, progress_callback):
    """Downloads a video from a URL with progress updates and error handling."""
    temp_filepath = None
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        total_length = response.headers.get('content-length')
        if total_length is None:
            temp_filepath = os.path.join(TEMP_VIDEO_DIR, filename)
            with open(temp_filepath, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            progress_callback(100)
            return temp_filepath

        total_length = int(total_length)
        chunk_size = 1024 * 1024  # 1MB chunks
        downloaded = 0
        temp_filepath = os.path.join(TEMP_VIDEO_DIR, filename)

        with open(temp_filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int((downloaded / total_length) * 100)
                    progress_callback(percent)

        return temp_filepath

    except requests.exceptions.RequestException as e:
        print(f"Error downloading video: {e}")
        if temp_filepath:
          cleanup_files(temp_filepath)
        return None

    except Exception as e:
        print(f"An unexpected error occurred during download: {e}")
        if temp_filepath:
            cleanup_files(temp_filepath)
        return None

def add_watermark(input_file, output_file, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_path, progress_callback):
    """Adds a text or image watermark to the video with progress updates and enhanced error handling."""
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

        try:
          process.wait(timeout=FFMPEG_TIMEOUT)  # Timeout to prevent hanging
        except subprocess.TimeoutExpired:
          print("FFmpeg process timed out!")
          process.kill() #Kill the process
          return False

        if process.returncode != 0:
            print(f"FFmpeg error: {process.stderr.read()}")
            cleanup_files(output_file) #Clean up output if it failed
            return False

        progress_callback(100)
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error adding watermark: {e}")
        cleanup_files(output_file) #Clean up output if it failed
        return False

    except Exception as e:
        print(f"An unexpected error occurred during watermarking: {e}")
        cleanup_files(output_file)
        return False
    finally:
        # Ensure cleanup even if exceptions occur
        cleanup_files(input_file) #Clean up downloaded file.



def event_stream(video_url, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_filename):
    """Generates progress updates for SSE with robust error handling."""
    try:
        def progress_callback(percent):
            yield f"data: {percent}\n\n"

        unique_video_filename = generate_filename(video_url)
        temp_filename = generate_unique_filename(unique_video_filename) #Use a unique filename for the temp file.
        print(f"Generated filename: {temp_filename}")

        input_filepath = download_video(video_url, temp_filename, progress_callback)
        if not input_filepath:
            yield "data: error:download_failed\n\n"
            return

        unique_watermarked_filename = f"watermarked_{generate_filename(video_url)}" #Unique for the final watermarked
        output_filepath = os.path.join(OUTPUT_VIDEO_DIR, unique_watermarked_filename)

        #Construct the full path to the waternmart
        image_watermark_path = None
        if image_watermark_filename: #If a file was uploaded
            image_watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], image_watermark_filename)

        if not add_watermark(input_filepath, output_filepath, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_path, progress_callback):
            yield "data: error:watermark_failed\n\n"
            return

        yield "data: complete:{unique_watermarked_filename}\n\n" #Also return the filname

    except Exception as e:
        print(f"An unexpected error occurred in event_stream: {e}")
        yield "data: error:general_error\n\n"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process_video():
    try:
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

      return render_template("processing.html", video_url=video_url, watermark_text=watermark_text, watermark_position=watermark_position, watermark_font=watermark_font, watermark_size=watermark_size, watermark_color=watermark_color, watermark_opacity=watermark_opacity, image_watermark_filename=image_watermark_filename)
    except Exception as e:
        print(f"Error in process_video: {e}")
        return f"An error occurred: {e}"  # Display a simple error message

@app.route('/stream/<path:video_url>')
def stream(video_url):
    try:
        watermark_text = request.args.get('watermark_text')
        watermark_position = request.args.get('watermark_position')
        watermark_font = request.args.get('watermark_font')
        watermark_size = int(request.args.get('watermark_size'))
        watermark_color = request.args.get('watermark_color')
        watermark_opacity = float(request.args.get('watermark_opacity'))
        image_watermark_filename = request.args.get('image_watermark_filename') #Get the water mark

        return Response(event_stream(video_url, watermark_text, watermark_position, watermark_font, watermark_size, watermark_color, watermark_opacity, image_watermark_filename), mimetype="text/event-stream")
    except Exception as e:
        print(f"Error in stream: {e}")
        return Response("data: error:general_error\n\n", mimetype="text/event-stream")

@app.route("/videos/<path:filename>")
def serve_video(filename):
    """Serves the watermarked video file with cache-busting headers."""
    try:
        response = make_response(send_from_directory(OUTPUT_VIDEO_DIR, filename))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
      return f"Could not serve the video: {e}"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=PORT)
