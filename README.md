# 🎤 Annual Function — Ramp Walk Scoring System

## Project Structure
```
rampwalk/
├── app.py              ← Flask backend (SocketIO)
├── requirements.txt    ← Python dependencies
├── vercel.json         ← Vercel deployment config
└── templates/
    ├── index.html      ← Home / Landing page
    ├── admin.html      ← Admin setup panel
    ├── guest.html      ← Guest scoring panel
    └── anchor.html     ← Anchor live dashboard
```

## How to Run Locally

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

## Vercel Deployment Steps

1. **Upload to GitHub** (or use Vercel CLI):
   ```bash
   git init
   git add .
   git commit -m "Ramp Walk App"
   git remote add origin <your-github-repo>
   git push -u origin main
   ```

2. **Vercel par deploy karein**:
   - https://vercel.com → New Project → Select GitHub repo
   - Framework: Other
   - Deploy!

3. **Note**: There is a limitation for Socket.IO on Vercel — 
   For real-time events to work properly, **Railway.app** or **Render.com** are better suited.
   **Render.com** is recommended for the free tier.

## Render.com Deployment (Recommended for SocketIO)

1. https://render.com → New Web Service
2. GitHub repo connect karein
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python app.py`
5. Free tier select karein → Deploy!

## Usage Guide

1. **Admin** `/admin` → Setup participants, guests, and couple themes.
2. **Admin** → "Save Setup" → Guest links will be generated.
3. **Share** the guest links (via WhatsApp, etc.) to 5-7 guests.
4. **Anchor** `/anchor` → Open the live dashboard.
5. **Admin** → Start Round 1 → Guests give scores → Lives scores appear on Anchor dashboard.
6. **Admin** → Start Round 2 → Couple theme scoring.
7. **Admin** → "Announce Final Results" → A 🏆 Winners pop-up will appear on the Anchor dashboard!
