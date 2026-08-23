<div align="center">

# 🎬🌍 Seamless AI Video Translator & Dubber

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-Web%20Framework-lightgrey.svg)](https://flask.palletsprojects.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Audio%2FVideo-green.svg)](https://ffmpeg.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*An intelligent, multi-threaded web application that instantly translates, syncs, and dubs video and audio content into multiple languages with precision.*

</div>

<br />

## 📖 About the Project

This AI-powered Flask web application automatically translates and dubs videos. It extracts audio, utilizes **Vosk** offline machine learning for precise speech-to-text, translates the text, and synthesizes human-like voiceovers using **Edge Neural TTS**. **FFmpeg** then dynamically synchronizes the audio speed to the video length and auto-generates localized word-level subtitles.

---

## ✨ Key Features

- 🔐 **Secure User Authentication:** Complete signup, login, and secure sessions via Database Mapping.
- 🎙️ **Precise Speech Recognition:** Employs the highly accurate, offline `Vosk` ML model to transcribe audio into text with word-level timestamps.
- 🌐 **Global Translation:** Powered by `deep-translator` to translate transcribed text to target languages instantly.
- 🗣️ **Human-like Neural Dubbing:** Utilizes Microsoft Edge Neural TTS (`edge-tts`) to generate natural voiceovers (Male & Female voices across various languages).
- ⏱️ **Auto-Time Synchronization:** Dynamically calculates duration differences and automatically adjusts the video time scale to seamlessly match the new spoken translation track using `ffmpeg`.
- 📝 **Automated Subtitles:** Accurately maps the translated audio timing to auto-generate `.vtt` format subtitles.
- 📊 **Interactive Dashboard:** Track real-time progress percentages of asynchronous background video rendering and manage historical projects.

---

## 🛠️ Tech Stack & Technologies

- **Backend:** Python, Flask, Flask-SQLAlchemy
- **Media Engine:** FFmpeg (extraction, filtering, scaling, muxing)
- **AI / ML:** Vosk Offline Speech Recognition model
- **Speech Synthesis:** Edge-TTS (Neural Voice generation)
- **Database:** SQLite (Lightweight, robust mapping)

---

## 🚀 Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

### Prerequisites
1. **Python 3.8+**
2. **[FFmpeg](https://ffmpeg.org/download.html)**: Required for all processing & rendering. You must install this system-wide and add it to your System PATH variables.
3. **[Vosk Speech Model](https://alphacephei.com/vosk/models)**: Download a compatible language model (e.g. `vosk-model-en-us-0.22`), extract it into your project root, and explicitly rename the folder to `VoskModel`.

### Installation

1. **Clone the repo**
   ```sh
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name
   ```

2. **Create a Python Virtual Environment**
   ```sh
   python -m venv venv
   
   # Activate on Windows:
   venv\Scripts\activate
   
   # Activate on macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```sh
   pip install -r requirements.txt
   ```

4. **Launch the Application**
   ```sh
   python project1.py
   ```
   > 🌐 The application will be successfully running at `http://localhost:5000`

---

## 🏗️ Architecture & Workflow Pipeline

1. **Upload:** User provides a source `.mp4` video.
2. **Extraction:** Python executes background `FFmpeg` processes to extract a 16kHz mono `.wav` audio track.
3. **Recognition:** The audio stream is digested by `Vosk`, calculating exact start and end millisecond timestamps for every spoken word.
4. **Translation:** Text arrays are natively pushed through a Google Translate wrapper.
5. **Synthesis:** `Edge-TTS` dynamically creates audio tracks containing the translated text.
6. **Muxing & Syncing:** The system analyzes the neural voiceover's duration against the original video duration. Video speed multipliers are automatically created. The video logic, audio track, and subtitle files are perfectly interwoven.
7. **Delivery:** The user is provided with the final translated `.vtt` subtitle block and the dubbed `.mp4` video file!

---

<div align="center">

*Designed & developed by [Your Name]*

</div>
