# GinkAssistant
Help_Human
# Gink  - Quick Run

1. Create virtualenv:
   python -m venv venv
   source venv/bin/activate   # windows: venv\Scripts\activate

2. Install:
   pip install -r requirements.txt

3. Optional: set environment variables:
   - OPENAI_API_KEY (if using GPT features)
   - OPENWEATHER_API_KEY (if implementing weather)

4. Run parts:
   - Full CLI: python assistant_full.py
   - Lite CLI: python assistant_lite.py
   - FastAPI server: uvicorn server:app --reload
   - Desktop GUI: python desktop_app.py

Security: This project includes a security guard: `security_guard.py`. It will refuse unsafe or impossible requests.

