#!/usr/bin/env python3
import os
import subprocess
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta

# CONFIGURATION
image_dir = Path("/tmp/motion/image")
video_dir = Path("/tmp/motion")  # FIXED: Changed from image_dir
output_dir = Path("/home/motion/files")
confidence_threshold = 0.6
weights_path = "/home/motion/yolov7/yolov7-tiny.pt"
detect_script = "/home/motion/yolov7/detect.py"
project_dir = Path("/tmp")
run_name = "motion_run"
detect_out_dir = project_dir / run_name

# Ensure destination exists
output_dir.mkdir(parents=True, exist_ok=True)

# Step 1: Run YOLOv7 detection
print("[INFO] Running object detection...")
result = subprocess.run([
    "python3", detect_script,
    "--source", str(image_dir),
    "--weights", weights_path,
    "--conf-thres", str(confidence_threshold),
    "--save-txt",
    "--save-conf",
    "--name", run_name,
    "--project", str(project_dir),
    "--classes", "0", "2", "7", "15", "16", "17", "18", "19", "20", "21", "22", "23",
    "--exist-ok"
], cwd="/tmp", capture_output=True, text=True)

print("[INFO] Detection script finished.")
if result.returncode != 0:
    print("[ERROR] Detection failed:\n", result.stderr)
    exit(1)

# Step 2: Parse detections
labels_dir = detect_out_dir / "labels"
images_dir = detect_out_dir  # Annotated image output dir

if not labels_dir.exists() or not any(labels_dir.glob("*.txt")):
    print("[INFO] No detections found (no label files). Cleaning up...")

    for image in image_dir.glob("*.webp"):
        image.unlink()
        print(f"  → Deleted image: {image.name}")

    for video in video_dir.glob("*.mkv"):
        video.unlink()
        print(f"  → Deleted video: {video.name}")

    for label in labels_dir.glob("*.txt"):
        label.unlink()
        print(f"  → Deleted label file: {label.name}")

    for annotated_image in images_dir.glob("*.*"):
        annotated_image.unlink()
        print(f"  → Deleted annotated image: {annotated_image.name}")

    exit(0)

# Regex for filenames like MM-DD-YYYY_HH.MM.SS_Location
filename_pattern = r"(\d{2}-\d{2}-\d{4})_(\d{2})\.(\d{2})\.(\d{2})_([a-zA-Z]+)"
tolerance_seconds = 40

for label_file in labels_dir.glob("*.txt"):
    base_name = label_file.stem
    print(f"[INFO] Processing label: {label_file.name}")

    match = re.match(filename_pattern, base_name)
    if not match:
        print(f"  × Skipping malformed label name: {base_name}")
        label_file.unlink()
        print(f"  → Deleted malformed label file: {label_file.name}")
        continue

    date, hour, minute, second, location = match.groups()
    image_time = datetime.strptime(f"{date} {hour}:{minute}:{second}", "%m-%d-%Y %H:%M:%S")

    # 1. Delete original image
#    original_image = image_dir / f"{base_name}.webp"
#    if original_image.exists():
#        original_image.unlink()
#        print(f"  → Deleted original image: {original_image.name}")
#    else:
#        print(f"  × Image not found to delete: {base_name}")
    # 1. Move original image
    original_image = image_dir / f"{base_name}.webp"
    if original_image.exists():
        shutil.move(str(original_image), output_dir / original_image.name)
        print(f"  → Moved original image: {original_image.name}")
        # Define the full path to the moved image
        dest_image_path = output_dir / original_image.name

        # Send pushover notification with image
        try:
            curl_cmd = [
                "curl", "-s",
                "--form-string", "token=mytoken",
                "--form-string", "user=myuser",
                "--form-string", "message=Motion!",
                "--form", f"attachment=@{dest_image_path}",
                "https://api.pushover.net/1/messages.json"
            ]
            subprocess.run(curl_cmd, check=True)
            print(f"  → Sent Pushover notification with: {original_image.name}")
        except subprocess.CalledProcessError as e:
            print(f"  × Failed to send Pushover notification: {e}")
    else:
        print(f"  × Original image not found to move: {base_name}")
        
    # 2. Move matching videos (within ±40 seconds)
    matching_videos = []
    for video in video_dir.glob("*.mkv"):
        video_match = re.match(filename_pattern, video.stem)
        if not video_match:
            continue

        v_date, v_hour, v_min, v_sec, v_location = video_match.groups()
        if v_location.lower() != location.lower():
            continue

        try:
            video_time = datetime.strptime(f"{v_date} {v_hour}:{v_min}:{v_sec}", "%m-%d-%Y %H:%M:%S")
        except ValueError:
            continue

        time_diff = abs((video_time - image_time).total_seconds())
        if time_diff <= tolerance_seconds:
            matching_videos.append(video)

    if matching_videos:
        for video in matching_videos:
            shutil.move(str(video), output_dir / video.name)
            print(f"  → Moved video: {video.name}")
    else:
        print(f"  × No matching videos for: {base_name}")
        print(f"    ⤷ Looking in: {video_dir}")
        print(f"    ⤷ Files: {[v.name for v in video_dir.glob('*.mkv')]}")

    # 3. Move annotated detection image
    annotated_candidates = [
        images_dir / f"{base_name}.{ext}"
        for ext in ["webp", "jpg", "jpeg", "png"]
    ]
    annotated_files = [f for f in annotated_candidates if f.exists()]

    if annotated_files:
        print(f"  → Annotated image retained: {annotated_files[0].name}")
    else:
        print(f"  × Annotated image not found: {base_name}")

#    if annotated_files:
#        annotated_image = annotated_files[0]
#        shutil.move(str(annotated_image), output_dir / annotated_image.name)
#        print(f"  → Moved annotated image: {annotated_image.name}")
#    else:
#        print(f"  × Annotated image not found: {base_name}")
        print(f"    ⤷ Checked: {[f.name for f in annotated_candidates]}")
        print(f"    ⤷ Files in annotated dir: {[f.name for f in images_dir.iterdir()]}")

    # 4. Delete the label file
    label_file.unlink()
    print(f"  → Deleted label file: {label_file.name}")
