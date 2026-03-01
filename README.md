# 🛡️ Verifiable Hash Transaction Reader

Explains blockchain transactions in plain English with **cryptographic proof** from [OpenGradient](https://opengradient.ai).

---

## Project Structure

```
verifiable-hash-reader/
├── server.py             ← Python Flask backend + OpenGradient SDK
├── requirements.txt      ← Python dependencies
├── Procfile              ← Render start command
├── .env.example          ← Environment variable template
├── .gitignore
├── public/
│   ├── index.html        ← Frontend UI
│   └── style.css         ← OpenGradient dark green theme
└── README.md
```

---

## Run Locally

```bash
cd verifiable-hash-reader
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit .env with your key
python server.py
```

Open **http://localhost:3000**

---

## Deploy to Render.com

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "verifiable wallet explainer"
git branch -M main
```

Go to **https://github.com/new** → create repo → then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/verifiable-wallet-explainer.git
git push -u origin main
```

### Step 2: Create Render Web Service

1. Go to **https://render.com** → sign up with GitHub
2. Click **New +** → **Web Service**
3. Connect your GitHub repo
4. Fill in the form:

   - **Name**: `verifiable-wallet-explainer`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn server:app --bind 0.0.0.0:$PORT`

5. Under **Environment Variables** → click **Add Environment Variable**:

   - **Key**: `OG_PRIVATE_KEY`
   - **Value**: `0xYourPrivateKeyHere`

6. Click **Deploy Web Service**

Your site will be live at `https://hash-reader.onrender.com` in ~2 minutes.

---

## Available Models

GPT_4_1, O4_MINI, GPT_5, GPT_5_MINI, GPT_5_2, CLAUDE_SONNET_4_5, CLAUDE_SONNET_4_6, CLAUDE_HAIKU_4_5, CLAUDE_OPUS_4_5, CLAUDE_OPUS_4_6, GEMINI_2_5_FLASH, GEMINI_2_5_PRO, GEMINI_3_PRO, GEMINI_3_FLASH, GROK_4, GROK_4_FAST

Change in `server.py` → `og.TEE_LLM.GEMINI_2_5_FLASH`

---

## Links

| Resource | URL |
|----------|-----|
| OpenGradient Docs | https://docs.opengradient.ai |
| $OPG Faucet | https://faucet.opengradient.ai |
| Block Explorer | https://explorer.opengradient.ai |
| Model Hub | https://hub.opengradient.ai |
