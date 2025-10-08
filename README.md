# LLM Code Deployment - Student Application

A FastAPI application that receives task requests from IITM server, generates web applications using GPT-4, and deploys them to GitHub Pages.

---

## 📋 Table of Contents

1. [What I Built](#what-i-built)
2. [What You Need](#what-you-need)
3. [Quick Setup](#quick-setup)
4. [Running the Server](#running-the-server)
5. [Testing](#testing)
6. [Deployment](#deployment)
7. [How It Works](#how-it-works)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 What I- [ ] Dependencies installed (`pip install -r requirements.txt`)

- [ ] `.env` file created and configured
- [ ] GitHub token obtained (with `repo` scope)
- [ ] OpenAI key obtained (with payment method)
- [ ] All environment variables set in `.env`
- [ ] Local server starts (`python main.py`)

A complete production-ready FastAPI application with:

### Core Files

- **`main.py`** - FastAPI server with `/api/build` endpoint
- **`config.py`** - Configuration management (loads from `.env`)
- **`models.py`** - Request/response validation using Pydantic
- **`services/llm_generator.py`** - GPT-4 integration for code generation
- **`services/github_service.py`** - GitHub API + Pages deployment
- **`services/notifier.py`** - Evaluation server notification with retry logic

### Configuration Files

- **`requirements.txt`** - Python dependencies
- **`.env.example`** - Environment variables template
- **`test_request.json`** - Sample IITM request for testing

### What It Does

1. ✅ Receives JSON POST requests from IITM server
2. ✅ Validates your secret key
3. ✅ Returns 200 OK immediately
4. ✅ Generates complete web app using GPT-4 (background)
5. ✅ Creates GitHub repository automatically
6. ✅ Deploys to GitHub Pages
7. ✅ Notifies IITM evaluation server with repo details

---

## 💻 What You Need

### Software

- **Python 3.11+** (check: `python --version`)
- **pip** (comes with Python)
- **Git** (for GitHub operations)

### Accounts & Credentials

1. **GitHub Personal Access Token**

   - Go to: https://github.com/settings/tokens
   - Generate new token (classic)
   - Select scope: ✅ `repo` only
   - Copy token (starts with `ghp_`)

2. **OpenAI API Key**

   - Go to: https://platform.openai.com/api-keys
   - Create new secret key
   - Copy key (starts with `sk-`)
   - **IMPORTANT:** Add payment method at https://platform.openai.com/account/billing

3. **Your Secret Key** (that you submitted to IITM)

4. **Your Email** (registered with IITM)

---

## ⚡ Quick Setup

### Step 1: Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs:

- FastAPI (web framework)
- Uvicorn (ASGI server)
- OpenAI (GPT-4 API)
- PyGithub (GitHub API)
- Pydantic (data validation)
- httpx (HTTP client)

### Step 2: Configure Environment

```powershell
# Copy the example file
Copy-Item .env.example .env

# Edit with your actual values
notepad .env
```

**Edit `.env` with these values:**

```ini
STUDENT_EMAIL=your.actual.email@example.com
STUDENT_SECRET=your-secret-that-you-gave-to-iitm
GITHUB_TOKEN=ghp_your_actual_github_token_here
GITHUB_USERNAME=your-github-username
OPENAI_API_KEY=sk-your_actual_openai_key_here
```

### Step 3: Verify Setup

Make sure your `.env` file has all required values:

- `STUDENT_EMAIL`
- `STUDENT_SECRET`
- `GITHUB_TOKEN`
- `GITHUB_USERNAME`
- `OPENAI_API_KEY`

---

## 🚀 Running the Server

### Start the Server

```powershell
python main.py
```

You should see:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Server is now running at:** `http://localhost:8000`

### Keep It Running

- The server must stay running to receive requests
- Press `Ctrl+C` to stop the server
- Check logs to see what's happening

---

## 🧪 Testing

### Test 1: Health Check

```powershell
# In a new terminal (keep server running)
curl http://localhost:8000/health
```

**Expected response:**

```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Test 2: Full Build Test

First, edit `test_request.json` with your email and secret:

```json
{
  "email": "your.email@example.com",
  "secret": "your-actual-secret",
  ...
}
```

Then run:

```powershell
curl -X POST http://localhost:8000/api/build `
  -H "Content-Type: application/json" `
  -d (Get-Content test_request.json -Raw)
```

**Expected response:**

```json
{
  "status": "accepted",
  "message": "Task calculator-test-001 received and processing started"
}
```

**Watch the server logs** - you'll see:

1. ✓ Generating app with LLM...
2. ✓ Creating GitHub repository...
3. ✓ Uploading files...
4. ✓ Enabling GitHub Pages...
5. ✓ Notifying evaluation server...

**Check GitHub** - a new repository should be created!

---

## 🌐 Deployment (Production)

### Option 1: Render.com (Recommended - Free Tier)

#### 1. Push to GitHub

```powershell
# Initialize git (if not done)
git init
git add .
git commit -m "Initial commit"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/iitm-llm-deploy.git
git push -u origin main
```

#### 2. Deploy on Render

1. Go to https://render.com
2. Sign up / Login
3. Click **"New +"** → **"Web Service"**
4. Connect your GitHub repository
5. Configure:

   - **Name:** `iitm-student-api` (or your choice)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** Free

6. **Add Environment Variables** (click "Advanced"):

   ```
   STUDENT_EMAIL=your.email@example.com
   STUDENT_SECRET=your-secret
   GITHUB_TOKEN=ghp_your_token
   GITHUB_USERNAME=your-username
   OPENAI_API_KEY=sk-your_key
   PORT=8000
   ```

7. Click **"Create Web Service"**

8. Wait 5-10 minutes for deployment

9. **Your URL:** `https://iitm-student-api.onrender.com`

#### 3. Test Production

```powershell
curl https://iitm-student-api.onrender.com/health
```

#### 4. Submit to IITM

Submit this URL: `https://iitm-student-api.onrender.com/api/build`

### Option 2: Railway.app

1. Go to https://railway.app
2. New Project → Deploy from GitHub repo
3. Select your repository
4. Add environment variables in "Variables" tab
5. Railway auto-deploys
6. Generate domain in "Settings"

### Option 3: Docker (Advanced)

```powershell
# Build image
docker build -t student-api .

# Run locally
docker run -p 8000:8000 --env-file .env student-api

# Or deploy to any cloud provider supporting Docker
```

---

## 🔄 How It Works

### Request Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. IITM Server → POST /api/build                            │
│    {email, secret, task, brief, checks, attachments...}     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Your API (main.py)                                       │
│    ├─ Validate email matches STUDENT_EMAIL                  │
│    ├─ Validate secret matches STUDENT_SECRET                │
│    └─ Return 200 OK immediately                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Background Task Starts                                   │
│    ├─ LLM Generator (services/llm_generator.py)             │
│    │   ├─ Sends brief to GPT-4                              │
│    │   ├─ GPT-4 generates HTML/CSS/JS                       │
│    │   └─ Creates index.html, LICENSE, README.md            │
│    │                                                         │
│    ├─ GitHub Service (services/github_service.py)           │
│    │   ├─ Creates new public repository                     │
│    │   ├─ Uploads all files                                 │
│    │   ├─ Enables GitHub Pages                              │
│    │   └─ Waits for Pages to deploy (2-5 min)              │
│    │                                                         │
│    └─ Notifier (services/notifier.py)                       │
│        ├─ POSTs to evaluation_url                           │
│        ├─ Sends: repo_url, commit_sha, pages_url            │
│        └─ Retries with exponential backoff (1,2,4,8,16s)    │
└─────────────────────────────────────────────────────────────┘

Total Time: 2-4 minutes per task
```

### API Endpoints

#### `GET /` or `GET /health`

Health check endpoint

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

#### `POST /api/build`

Main endpoint that receives task requests

**Request Body:**

```json
{
  "email": "student@example.com",
  "secret": "your-secret",
  "task": "calculator-abc123",
  "round": 1,
  "nonce": "unique-nonce",
  "brief": "Create a calculator app with Bootstrap 5...",
  "checks": ["Repo has MIT license", "README.md is professional"],
  "evaluation_url": "https://eval.server.com/notify",
  "attachments": [
    {
      "name": "data.csv",
      "url": "data:text/csv;base64,..."
    }
  ]
}
```

**Response (immediate):**

```json
{
  "status": "accepted",
  "message": "Task calculator-abc123 received and processing started"
}
```

**Background Process:** Generates app, creates repo, deploys Pages, notifies server

---

## 🛠️ Troubleshooting

### "ModuleNotFoundError"

```powershell
# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

### "Secret validation failed"

- Check `.env` file
- Ensure `STUDENT_SECRET` matches exactly what you gave IITM
- No extra spaces or quotes

### "GitHub API error"

- Verify token has `repo` permission
- Check token is copied correctly (starts with `ghp_`)
- Try regenerating the token

### "OpenAI rate limit exceeded"

- Add payment method at https://platform.openai.com/account/billing
- Add at least $5 credit
- Check usage at https://platform.openai.com/usage

### "GitHub Pages not deploying"

- This is normal - Pages takes 2-5 minutes to deploy
- The app waits automatically (up to 5 minutes)
- Check: `https://github.com/YOUR_USERNAME/REPO_NAME/settings/pages`

### Server won't start

```powershell
# Check Python version
python --version  # Should be 3.11+

# Check port is not in use
# Try different port:
# Edit config.py and change port: int = 8000 to port: int = 8001
```

### "Can't connect to server"

```powershell
# Make sure server is running
python main.py

# Check in another terminal:
curl http://localhost:8000/health
```

---

## 📊 Project Structure

```
Project 1/
├── main.py                    # FastAPI app (entry point)
├── config.py                  # Configuration management
├── models.py                  # Pydantic request/response models
│
├── services/
│   ├── __init__.py           # Package init
│   ├── llm_generator.py      # GPT-4 code generation
│   ├── github_service.py     # GitHub API + Pages
│   └── notifier.py           # Evaluation notification
│
├── requirements.txt           # Dependencies
├── .env.example              # Environment template
├── .env                      # Your secrets (create this)
├── .gitignore                # Git ignore rules
├── test_request.json         # Sample request
│
└── README.md                 # This file
```

---

## 💰 Cost Estimate

- **Render/Railway:** FREE (free tier)
- **GitHub:** FREE (public repos)
- **OpenAI GPT-4:** ~$0.50-2.00 per task

**Total for 2-3 tasks: $2-5**

---

## 🔐 Security Notes

- ✅ Never commit `.env` file (already in `.gitignore`)
- ✅ Use environment variables for all secrets
- ✅ GitHub token needs only `repo` permission
- ✅ Keep OpenAI usage monitored (set billing alerts)

---

## 📝 Quick Command Reference

```powershell
# Setup
pip install -r requirements.txt

# Verify installation
pip list

# Run server
python main.py

# Test locally (in a new terminal)
curl http://localhost:8000/health

# Test build endpoint
curl -X POST http://localhost:8000/api/build `
  -H "Content-Type: application/json" `
  -d (Get-Content test_request.json -Raw)

# Deploy
git add .
git commit -m "Deploy"
git push
# Then deploy on Render/Railway

# Check production
curl https://your-app.onrender.com/health
```

---

## ✅ Pre-Deployment Checklist

- [ ] Python 3.11+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created and configured
- [ ] GitHub token obtained (with `repo` scope)
- [ ] OpenAI key obtained (with payment method)
- [ ] `.\setup.ps1` passes all checks
- [ ] Local server starts (`python main.py`)
- [ ] Health check works (`curl localhost:8000/health`)
- [ ] Test request succeeds
- [ ] Code pushed to GitHub
- [ ] Deployed to Render/Railway
- [ ] Production health check works
- [ ] Ready to submit endpoint URL to IITM!

---

## 🎯 Summary

**What I built:** Complete FastAPI application for IITM LLM deployment project

**What you need to do:**

1. Get GitHub token and OpenAI key
2. Configure `.env` file
3. Test locally (`python main.py`)
4. Deploy to Render.com
5. Submit your endpoint URL to IITM

**Your endpoint format:** `https://your-app.onrender.com/api/build`

**Expected cost:** ~$2-5 total

**Time to deploy:** ~30 minutes

---

## 📞 Need Help?

1. Check server logs for errors
2. Verify all `.env` values are correct
3. Test health endpoint: `curl http://localhost:8000/health`
4. Test locally before deploying to production
5. Make sure Python 3.11+ is installed: `python --version`

---

**Good luck with your IITM project! 🚀**
