# 🚀 Proper Deployment Guide for Smart AI Video Translator

To deploy this project successfully, you need to handle three critical things: **FFmpeg** (for video processing), **Vosk Models** (for speech recognition), and **Large File Support**.

---

## 🏗️ Option 1: Docker (Highly Recommended)
Using Docker is the best way because it bundles FFmpeg and all your Python dependencies together in a single "container" that runs anywhere.

### 📜 1. Initial Build
Run this in your terminal:
```powershell
docker build -t video-translator .
```

### 🏃 2. Run Locally to Test
```powershell
docker run -p 5000:5000 video-translator
```

---

## ☁️ Option 2: Render.com (Easiest Cloud Deployment)
Render is a great free/cheap platform that supports Docker deployments.

### 📝 1. Prepare Your Repository
- Create a **Private Repository** on GitHub.
- Push your code: `git init`, `git add .`, `git commit -m "initial commit"`, `git push origin main`.

### 📄 2. Create a "Web Service" on Render
- Connect your GitHub repo.
- Select **Environment**: `Docker`.
- **Instance Type**: Select at least a **Starter Plan** (Small free instances may not have enough RAM/CPU for video processing).

---

## 🏢 Option 3: Cloud VM (AWS EC2 / DigitalOcean Droplet)
If you want full control, use a Virtual Machine.

### 🛠️ 1. Install System Dependencies (Ubuntu example)
```bash
sudo apt update
sudo apt install -y ffmpeg python3-pip
```

### 📦 2. Clone and Setup
```bash
git clone YOUR_REPO_URL
cd YOUR_REPO_NAME
pip install -r requirements.txt
pip install gunicorn
```

### 🚀 3. Run with Gunicorn (Background Process)
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 600 app:app &
```

---

## ⚠️ Critical Deployment Notes

### 📂 1. Vosk Model Storage
The `VoskModel/` folder is very large and usually excluded from `.dockerignore` for efficiency.
- **Proper Way**: Download the model directly in your `Dockerfile` or mount it as an external volume.
- **For Render**: You may need to commit a *lightweight* version of the model (~40MB `vosk-model-small-en-us-0.15`) or use an external URL to download it on startup.

### 💾 2. Persistence (Database & Files)
- **Problem**: Cloud platforms like Render forget files (`app.db`, `outputs/`) whenever you redeploy.
- **Proper Fix**: Attach a **Disk/Volume** to your service and point your `BASE_DIR` there. For the DB, you'd ideally use a managed PostgreSQL database in the future.

### ⏱️ 3. Timeout
Processing videos takes time. Always ensure your server's **Timeout** is set to at least **600 seconds** (10 minutes) so it doesn't kill the task halfway through.
