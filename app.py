import os
import time
import base64
import threading

from flask import Flask, render_template, Response, request, jsonify
import cv2
import numpy as np

from gestures.gesture_detector import GestureDetector
from utils.helpers import preprocess_frame  # optional preprocessing from your helpers

app = Flask(__name__)

# Ensure snapshots directory
SNAP_DIR = "snapshots"
os.makedirs(SNAP_DIR, exist_ok=True)

# Shared objects
DETECTOR_LOCK = threading.Lock()
# initialize detector with defaults (will be recreated when settings change)
detector = GestureDetector(min_detection_confidence=0.7, min_tracking_confidence=0.5)

# settings (shared state)
settings = {
    "min_detection_confidence": 0.7,
    "min_tracking_confidence": 0.5,
    "show_landmarks": True,
    "show_fps": True,
    # other UI state tracking
    "last_gesture": "No Hand Detected",
    "last_confidence": None,
    "frames_processed": 0
}

# Camera object (single shared capture)
camera = cv2.VideoCapture(0)  # 0 = default webcam


def gen_frames():
    """Video streaming generator (MJPEG)."""
    prev_time = time.time()
    while True:
        success, frame = camera.read()
        if not success or frame is None:
            # yield a placeholder black frame when camera not available
            blank = 255 * np.ones((480, 640, 3), dtype='uint8')
            ret, buffer = cv2.imencode('.jpg', blank)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
            continue

        # mirror like Streamlit version
        frame = cv2.flip(frame, 1)

        # optional preprocessing (slight blur / resize) — use helpers.preprocess_frame
        try:
            frame_proc = preprocess_frame(frame)
        except Exception:
            frame_proc = frame

        # Detect (thread-safe)
        with DETECTOR_LOCK:
            processed_frame, gesture, confidence = detector.detect(
                frame_proc,
                draw_landmarks=settings.get("show_landmarks", True)
            )

        # Update shared status
        settings["last_gesture"] = gesture
        settings["last_confidence"] = confidence
        settings["frames_processed"] = settings.get("frames_processed", 0) + 1

        # FPS overlay
        if settings.get("show_fps", True):
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0.0
            prev_time = curr_time
            cv2.putText(
                processed_frame,
                f"FPS: {int(fps)}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

        # Encode
        ret, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@app.route('/')
def index():
    """Main UI page."""
    return render_template('index.html', settings=settings)


@app.route('/video_feed')
def video_feed():
    """MJPEG stream endpoint."""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/update_settings', methods=['POST'])
def update_settings():
    """Update detection/tracking and visual settings from client."""
    data = request.json or {}
    try:
        d = float(data.get("min_detection_confidence", settings["min_detection_confidence"]))
        t = float(data.get("min_tracking_confidence", settings["min_tracking_confidence"]))
        show_landmarks = bool(data.get("show_landmarks", settings["show_landmarks"]))
        show_fps = bool(data.get("show_fps", settings["show_fps"]))
    except Exception:
        return jsonify({"error": "invalid payload"}), 400

    # clamp values
    settings["min_detection_confidence"] = max(0.0, min(1.0, d))
    settings["min_tracking_confidence"] = max(0.0, min(1.0, t))
    settings["show_landmarks"] = show_landmarks
    settings["show_fps"] = show_fps

    # Recreate detector with new thresholds (thread-safe)
    global detector
    with DETECTOR_LOCK:
        # close previous detector cleanly if possible
        try:
            del detector
        except Exception:
            pass
        detector = GestureDetector(
            min_detection_confidence=settings["min_detection_confidence"],
            min_tracking_confidence=settings["min_tracking_confidence"]
        )

    return jsonify({"status": "ok", "settings": settings})


@app.route('/snapshot', methods=['POST'])
def snapshot():
    """
    Accept base64 image from client (canvas capture) and save to snapshots/.
    Request JSON: {"image": "data:image/png;base64,...."}
    """
    data = request.json or {}
    img_b64 = data.get("image")
    if not img_b64:
        return jsonify({"error": "no image provided"}), 400

    # strip header
    if "," in img_b64:
        img_b64 = img_b64.split(",", 1)[1]

    try:
        img_bytes = base64.b64decode(img_b64)
    except Exception:
        return jsonify({"error": "invalid base64"}), 400

    ts = int(time.time())
    fname = f"snapshot_{ts}.png"
    path = os.path.join(SNAP_DIR, fname)
    with open(path, "wb") as f:
        f.write(img_bytes)

    return jsonify({"status": "saved", "filename": path})


@app.route('/status')
def status():
    """Return last known detection info (lightweight)."""
    return jsonify({
        "last_gesture": settings.get("last_gesture"),
        "last_confidence": settings.get("last_confidence"),
        "frames_processed": settings.get("frames_processed")
    })


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    finally:
        try:
            camera.release()
        except Exception:
            pass
