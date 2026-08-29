from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, uuid, threading, subprocess, wave, json, logging, shutil
from datetime import datetime
from deep_translator import GoogleTranslator
from vosk import Model, KaldiRecognizer
from gtts import gTTS

# ------------------------------
# Config / Setup
# ------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel uses a read-only filesystem except for /tmp
IS_VERCEL = os.environ.get('VERCEL') == '1'
WRITE_DIR = "/tmp" if IS_VERCEL else BASE_DIR

UPLOAD_FOLDER = os.path.join(WRITE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(WRITE_DIR, 'outputs')
TEMP_FOLDER = os.path.join(WRITE_DIR, 'temp')
VOSK_MODEL_FOLDER = os.path.join(BASE_DIR, "VoskModel") # Read-only, remains in BASE_DIR

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    os.makedirs(folder, exist_ok=True)

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
app.secret_key = "smart_translator_secure_key"

FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

@app.context_processor
def inject_backend_url():
    return {"backend_url": os.environ.get("BACKEND_URL", "")}

database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

if not database_url:
    if IS_VERCEL:
        raise RuntimeError("DATABASE_URL or POSTGRES_URL is not configured on Vercel")
    else:
        # Fallback to local SQLite for local development
        database_url = 'sqlite:///' + os.path.join(WRITE_DIR, 'app.db')

# SQLAlchemy 2.x requires postgresql:// instead of postgres://
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ------------------------------
# Database Models
# ------------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProjectHistory(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    original = db.Column(db.String(255), nullable=False)
    target = db.Column(db.String(20), nullable=False)
    output = db.Column(db.String(255), nullable=True)
    translated_text = db.Column(db.Text, nullable=True)
    original_text_file = db.Column(db.String(255), nullable=True)
    translated_text_file = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ------------------------------
# Load Vosk Model (with Auto-Download)
# ------------------------------

vosk_model = None

def get_vosk_model():
    global vosk_model
    if vosk_model is not None:
        return vosk_model

    # Check if local model folder exists and is populated
    if not os.path.exists(VOSK_MODEL_FOLDER) or not os.path.exists(os.path.join(VOSK_MODEL_FOLDER, "am")):
        logging.info("Vosk model not found locally. Auto-downloading small English model...")
        import urllib.request, zipfile
        os.makedirs(TEMP_FOLDER, exist_ok=True)
        zip_path = os.path.join(TEMP_FOLDER, "vosk_model.zip")
        url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
        try:
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(TEMP_FOLDER)
            extracted = os.path.join(TEMP_FOLDER, "vosk-model-small-en-us-0.15")
            if os.path.exists(extracted):
                if os.path.exists(VOSK_MODEL_FOLDER):
                    shutil.rmtree(VOSK_MODEL_FOLDER)
                shutil.move(extracted, VOSK_MODEL_FOLDER)
            if os.path.exists(zip_path):
                os.remove(zip_path)
            logging.info("Vosk model downloaded and unpacked successfully")
        except Exception as e:
            logging.error(f"Failed to auto-download Vosk model: {e}")

    if os.path.exists(VOSK_MODEL_FOLDER):
        try:
            vosk_model = Model(VOSK_MODEL_FOLDER)
            logging.info("Vosk model successfully loaded")
        except Exception as e:
            logging.exception(f"Failed loading Vosk model from: {VOSK_MODEL_FOLDER}")

    return vosk_model

# ------------------------------
# Global State for Jobs
# ------------------------------

jobs = {}
jobs_lock = threading.Lock()

# ------------------------------
# Database Helpers for History
# ------------------------------

def update_history(username, original_file, target_lang, output_file, translated_text="", proj_type="video", original_text_file="", translated_text_file=""):
    with app.app_context():
        record_id = uuid.uuid4().hex[:8]
        new_hist = ProjectHistory(
            id=record_id,
            username=username,
            type=proj_type,
            original=original_file,
            target=target_lang,
            output=output_file,
            translated_text=translated_text,
            original_text_file=original_text_file,
            translated_text_file=translated_text_file
        )
        db.session.add(new_hist)
        
        # Keep only last 50 items per user
        user_history = ProjectHistory.query.filter_by(username=username).order_by(ProjectHistory.timestamp.desc()).all()
        if len(user_history) > 50:
            for old_record in user_history[50:]:
                db.session.delete(old_record)
                
        db.session.commit()

# ------------------------------
# Video Processing
# ------------------------------

def process_video(filepath, basename, original_name, target_lang, voice_choice, job_id, username):
    try:
        with jobs_lock:
            jobs[job_id] = {"progress": 0, "output": None, "error": None}

        # 1. Extract audio
        audio_path = os.path.join(TEMP_FOLDER, f"{basename}_audio.wav")
        subprocess.run([
            "ffmpeg","-y","-i", filepath, "-vn", "-acodec","pcm_s16le",
            "-ar","16000", "-ac","1", audio_path
        ], check=True)

        with jobs_lock:
            jobs[job_id]["progress"] = 20

        # 2. Speech Recognition
        v_model = get_vosk_model()
        if v_model is None:
            raise RuntimeError("Vosk model missing on server and could not be downloaded")

        wf = wave.open(audio_path, "rb")
        rec = KaldiRecognizer(v_model, wf.getframerate())
        rec.SetWords(True)  # Enable timestamps

        utterances = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0: break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if res.get("result"):
                    utterances.append({
                        "text": res["text"],
                        "words": res["result"] # List of dicts {word, start, end}
                    })
        final_res = json.loads(rec.FinalResult())
        if final_res.get("result"):
            utterances.append({
                "text": final_res["text"],
                "words": final_res["result"]
            })
        wf.close()

        if not utterances:
            raise RuntimeError("No speech detected in this video")

        full_original_text = " ".join([u["text"] for u in utterances])

        with jobs_lock:
            jobs[job_id]["progress"] = 40

        # 3. Translation
        translated_parts = []
        translator = GoogleTranslator(source="auto", target=target_lang)

        for utt in utterances:
            translated_utt = translator.translate(utt["text"])
            if not translated_utt: translated_utt = utt["text"]
            utt["translated_text"] = translated_utt
            translated_parts.append(translated_utt)

        translated = " ".join(translated_parts)

        with jobs_lock:
            jobs[job_id]["progress"] = 60

        # 4. Neural-TTS using edge-tts (Human-like)
        import asyncio
        import edge_tts
        
        tts_mp3 = os.path.join(TEMP_FOLDER, f"{basename}_tts.mp3")
        
        # Voice Mapping (Language -> Male/Female neural voice codes)
        voice_map = {
            "en": {"male": "en-US-GuyNeural", "female": "en-US-AriaNeural"},
            "hi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
            "ta": {"male": "ta-IN-ValluvarNeural", "female": "ta-IN-PallaviNeural"},
            "te": {"male": "te-IN-MohanNeural", "female": "te-IN-ShrutiNeural"},
            "ml": {"male": "ml-IN-MidhunNeural", "female": "ml-IN-SobhanaNeural"},
            "kn": {"male": "kn-IN-GaganNeural", "female": "kn-IN-SapnaNeural"},
            "zh-cn": {"male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
            "es": {"male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
            "fr": {"male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
            "de": {"male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
        }
        
        # Default fallback logic
        v_data = voice_map.get(target_lang, voice_map["en"])
        selected_voice = v_data.get(voice_choice, v_data["male"])
        if voice_choice == "auto" or voice_choice not in v_data:
            selected_voice = v_data["male"] # Default to male for auto if language matches
            
        async def generate_voice():
            communicate = edge_tts.Communicate(translated, selected_voice)
            await communicate.save(tts_mp3)
            
        asyncio.run(generate_voice())

        # 5. Convert MP3 → WAV (Normal speed 1x)
        tts_wav = os.path.join(TEMP_FOLDER, f"{basename}_tts.wav")
        # No speed-up or filters needed for normal 1x playback.
        subprocess.run([
            "ffmpeg","-y","-i", tts_mp3,
            "-ar","16000", "-ac","1", tts_wav
        ], check=True)

        # 6. Dynamic Duration Matching
        # Get original video duration
        meta_vid = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]).decode("utf-8").strip()
        orig_dur = float(meta_vid)

        # Get AI audio duration (which is now 1.5x faster)
        meta_aud = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", tts_wav
        ]).decode("utf-8").strip()
        aud_dur = float(meta_aud)

        # Scale Factor: How much to stretch/shrink the video to match the audio
        ratio = aud_dur / orig_dur if orig_dur > 0 else 1.0

        # Subtitle generation removed.

        # 8. Merge Video + Audio (Sync matching)
        final_video_name = f"{basename}_translated.mp4"
        final_video_path = os.path.join(OUTPUT_FOLDER, final_video_name)
        
        subprocess.run([
            "ffmpeg","-y","-i", filepath, "-i", tts_wav,
            "-filter:v", f"setpts={ratio}*PTS", "-map","0:v:0", "-map","1:a:0",
            "-shortest", final_video_path
        ], check=True)

        update_history(username, original_name, target_lang, final_video_name, translated)

        with jobs_lock:
            jobs[job_id]["progress"] = 100
            jobs[job_id]["output"] = final_video_name
            jobs[job_id]["translated_text"] = translated

    except Exception as e:
        logging.exception(f"Processing failed for job {job_id}")
        with jobs_lock:
            jobs[job_id]["progress"] = -1
            jobs[job_id]["error"] = str(e)

# ------------------------------
# Audio Processing
# ------------------------------

def process_audio(filepath, basename, original_name, target_lang, voice_choice, job_id, username):
    try:
        with jobs_lock:
            jobs[job_id] = {"progress": 0, "output": None, "error": None, "original_text_file": None, "translated_text_file": None}

        # 1. Standardize audio
        audio_path = os.path.join(TEMP_FOLDER, f"{basename}_std.wav")
        subprocess.run([
            "ffmpeg","-y","-i", filepath, "-acodec","pcm_s16le",
            "-ar","16000", "-ac","1", audio_path
        ], check=True)

        with jobs_lock:
            jobs[job_id]["progress"] = 20

        # 2. Speech Recognition
        v_model = get_vosk_model()
        if v_model is None:
            raise RuntimeError("Vosk model missing on server and could not be downloaded")

        wf = wave.open(audio_path, "rb")
        rec = KaldiRecognizer(v_model, wf.getframerate())
        rec.SetWords(True)

        utterances = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0: break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if res.get("result"):
                    utterances.append({
                        "text": res["text"]
                    })
        final_res = json.loads(rec.FinalResult())
        if final_res.get("result"):
            utterances.append({
                "text": final_res["text"]
            })
        wf.close()

        if not utterances:
            raise RuntimeError("No speech detected in this audio")

        full_original_text = " ".join([u["text"] for u in utterances])
        
        orig_text_file = f"{basename}_original.txt"
        with open(os.path.join(OUTPUT_FOLDER, orig_text_file), "w", encoding="utf-8") as f:
            f.write(full_original_text)

        with jobs_lock:
            jobs[job_id]["progress"] = 40

        # 3. Translation
        translated_parts = []
        translator = GoogleTranslator(source="auto", target=target_lang)

        for utt in utterances:
            translated_utt = translator.translate(utt["text"])
            if not translated_utt: translated_utt = utt["text"]
            translated_parts.append(translated_utt)

        translated = " ".join(translated_parts)
        
        trans_text_file = f"{basename}_translated.txt"
        with open(os.path.join(OUTPUT_FOLDER, trans_text_file), "w", encoding="utf-8") as f:
            f.write(translated)

        with jobs_lock:
            jobs[job_id]["progress"] = 60

        # 4. Neural-TTS using edge-tts
        import asyncio
        import edge_tts
        
        tts_mp3 = os.path.join(OUTPUT_FOLDER, f"{basename}_translated.mp3")
        
        voice_map = {
            "en": {"male": "en-US-GuyNeural", "female": "en-US-AriaNeural"},
            "hi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
            "ta": {"male": "ta-IN-ValluvarNeural", "female": "ta-IN-PallaviNeural"},
            "te": {"male": "te-IN-MohanNeural", "female": "te-IN-ShrutiNeural"},
            "ml": {"male": "ml-IN-MidhunNeural", "female": "ml-IN-SobhanaNeural"},
            "kn": {"male": "kn-IN-GaganNeural", "female": "kn-IN-SapnaNeural"},
            "zh-cn": {"male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
            "es": {"male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
            "fr": {"male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
            "de": {"male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
        }
        
        v_data = voice_map.get(target_lang, voice_map["en"])
        selected_voice = v_data.get(voice_choice, v_data["male"])
        if voice_choice == "auto" or voice_choice not in v_data:
            selected_voice = v_data["male"]
            
        async def generate_voice():
            communicate = edge_tts.Communicate(translated, selected_voice)
            await communicate.save(tts_mp3)
            
        asyncio.run(generate_voice())

        update_history(username, original_name, target_lang, f"{basename}_translated.mp3", translated, proj_type="audio", original_text_file=orig_text_file, translated_text_file=trans_text_file)

        with jobs_lock:
            jobs[job_id]["progress"] = 100
            jobs[job_id]["output"] = f"{basename}_translated.mp3"
            jobs[job_id]["translated_text"] = translated
            jobs[job_id]["original_text_file"] = orig_text_file
            jobs[job_id]["translated_text_file"] = trans_text_file

    except Exception as e:
        logging.exception(f"Processing failed for audio job {job_id}")
        with jobs_lock:
            jobs[job_id]["progress"] = -1
            jobs[job_id]["error"] = str(e)

# ------------------------------
# Routes
# ------------------------------

@app.route("/")
def index():
    if 'user' in session:
        return redirect(url_for("project"))
    return render_template("index.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm = request.form.get("confirm","")

        if password != confirm:
            flash("Passwords do not match","error")
            return redirect(url_for("signup"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists","error")
            return redirect(url_for("signup"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered","error")
            return redirect(url_for("signup"))

        new_user = User(username=username, email=email, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        flash("Account created! You can now log in.","success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        identifier = request.form["identifier"].strip()
        password = request.form["password"]

        # Check if login is via username or email
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
        
        if user and check_password_hash(user.password, password):
            session["user"] = user.username
            flash("Login successful!","success")
            return redirect(url_for("project"))

        flash("Invalid credentials","error")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user",None)
    flash("You have been logged out.","info")
    return redirect(url_for("index"))

@app.route("/project", methods=["GET"])
def project():
    if 'user' not in session:
        return redirect(url_for("login"))

    user = session.get("user")
    history_data = ProjectHistory.query.filter_by(username=user, type='video').order_by(ProjectHistory.timestamp.desc()).limit(5).all()
    return render_template("dashboard.html", history=history_data, user=user, backend_url=BACKEND_URL)

@app.route("/api/upload_video", methods=["POST"])
def upload_video():
    if 'video' not in request.files or request.files['video'].filename=='':
        return jsonify({"error": "No video file"}), 400

    file = request.files["video"]
    original_name = file.filename
    filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex[:8]
    basename = f"{os.path.splitext(filename)[0]}_{unique_id}"
    filepath = os.path.join(UPLOAD_FOLDER, f"{basename}{os.path.splitext(filename)[1]}")
    file.save(filepath)

    target_lang = request.form.get("target","en")
    voice_choice = request.form.get("voice","auto")
    job_id = basename
    username = request.form.get("username", "anonymous")

    threading.Thread(
        target=process_video,
        args=(filepath, basename, original_name, target_lang, voice_choice, job_id, username),
        daemon=True
    ).start()

    redirect_base = FRONTEND_URL if FRONTEND_URL else request.host_url.rstrip('/')
    return redirect(f"{redirect_base}/progress/{job_id}")

@app.route("/progress/<job_id>")
def progress(job_id):
    if 'user' not in session: return redirect(url_for("login"))
    return render_template("progress.html", job_id=job_id, backend_url=BACKEND_URL)

@app.route("/progress_status/<job_id>")
def progress_status(job_id):
    return jsonify(jobs.get(job_id, {"progress":-1, "error":"Job not found"}))

@app.route("/output_video/<filename>")
def output_video(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path)
    return "File not found", 404

@app.route("/subtitles/<filename>")
def subtitles(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="text/vtt")
    return "File not found", 404

@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

@app.route("/download_text/<filename>")
def download_text(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, mimetype="text/plain")
    return "File not found", 404

@app.route("/audio_project", methods=["GET"])
def audio_project():
    if 'user' not in session:
        return redirect(url_for("login"))

    user = session.get("user")
    history_data = ProjectHistory.query.filter_by(username=user, type='audio').order_by(ProjectHistory.timestamp.desc()).limit(5).all()
    return render_template("audio_dashboard.html", history=history_data, user=user, backend_url=BACKEND_URL)

@app.route("/api/upload_audio", methods=["POST"])
def upload_audio():
    if 'audio' not in request.files or request.files['audio'].filename=='':
        return jsonify({"error": "No audio file"}), 400

    file = request.files["audio"]
    original_name = file.filename
    filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex[:8]
    basename = f"{os.path.splitext(filename)[0]}_{unique_id}"
    filepath = os.path.join(UPLOAD_FOLDER, f"{basename}{os.path.splitext(filename)[1]}")
    file.save(filepath)

    target_lang = request.form.get("target","en")
    voice_choice = request.form.get("voice","auto")
    job_id = basename
    username = request.form.get("username", "anonymous")

    threading.Thread(
        target=process_audio,
        args=(filepath, basename, original_name, target_lang, voice_choice, job_id, username),
        daemon=True
    ).start()

    redirect_base = FRONTEND_URL if FRONTEND_URL else request.host_url.rstrip('/')
    return redirect(f"{redirect_base}/audio_progress/{job_id}")

@app.route("/audio_progress/<job_id>")
def audio_progress(job_id):
    if 'user' not in session: return redirect(url_for("login"))
    return render_template("audio_progress.html", job_id=job_id, backend_url=BACKEND_URL)

@app.route("/audio_progress_status/<job_id>")
def audio_progress_status(job_id):
    return jsonify(jobs.get(job_id, {"progress":-1, "error":"Job not found"}))

@app.route("/history")
def history_page():
    if 'user' not in session: return redirect(url_for("login"))
    user = session.get("user")
    history = ProjectHistory.query.filter_by(username=user).order_by(ProjectHistory.timestamp.desc()).all()
    return render_template("history.html", history=history, backend_url=BACKEND_URL)

@app.route("/delete_history/<record_id>")
def delete_history(record_id):
    if 'user' not in session: return redirect(url_for("login"))
    user = session.get("user")
    
    # record_id could be the id or output filename
    record = ProjectHistory.query.filter((ProjectHistory.id == record_id) | (ProjectHistory.output == record_id)).filter_by(username=user).first()
    
    if record:
        if record.output:
            out_path = os.path.join(OUTPUT_FOLDER, record.output)
            if os.path.exists(out_path): os.remove(out_path)
        if record.original_text_file:
            text_path = os.path.join(OUTPUT_FOLDER, record.original_text_file)
            if os.path.exists(text_path): os.remove(text_path)
        if record.translated_text_file:
            text_path = os.path.join(OUTPUT_FOLDER, record.translated_text_file)
            if os.path.exists(text_path): os.remove(text_path)
            
        db.session.delete(record)
        db.session.commit()
        flash("Record deleted successfully.", "success")
        
    return redirect(url_for("history_page"))

@app.route("/downloads")
def downloads():
    if 'user' not in session: return redirect(url_for("login"))
    files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.mp4')]
    return render_template("downloads.html", files=files)

@app.route("/profile")
def profile():
    if 'user' not in session: return redirect(url_for("login"))
    user = session.get("user")
    return render_template("profile.html", user=user)

@app.route("/settings")
def settings():
    if 'user' not in session: return redirect(url_for("login"))
    user = session.get("user")
    return render_template("settings.html", user=user)

@app.route("/test-ffmpeg")
def test_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return {"status": "success", "ffmpeg": path}
    return {"status": "error", "ffmpeg": None}, 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)

