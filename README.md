# 🌀 Gink Assistant: Think. Talk. Create.

[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org)
[![PyQt5](https://img.shields.io/badge/PyQt5-%2341CD52.svg?style=for-the-badge&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org)
[![macOS Build](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple&logoColor=white)](#-macos-distribution)

An intelligent, privacy-first desktop assistant built with a **Hybrid AI Engine**, Voice Interaction, and deep macOS integration. 

---

## 🚀 Quick Run

### 1. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

2. Install Dependencies
pip install -r requirements.txt

3. Optional: Set Environment Variables
Create a .env file or export the following:

GROQ_API_KEY: For lightning-fast Llama 3.1 cloud responses.

POLLINATIONS_API: (Optional) For AI image generation.

OPENWEATHER_API_KEY: (If implementing weather features).

🛠️ Running the AssistantModeCommandDescriptionDesktop GUIpython main.pyThe full Glassmorphism interface with sidebar history.Full CLIpython assistant_full.pyComplete command-line experience.Serveruvicorn server:app --reloadFastAPI backend for web/remote access.Build Apppython build_gink.py(macOS) Compiles the project into a versioned .dmg.

Mode,Command,Description
Desktop GUI,python main.py,The full Glassmorphism interface with sidebar history.
Full CLI,python assistant_full.py,Complete command-line experience.
Server,uvicorn server:app --reload,FastAPI backend for web/remote access.
Build App,python build_gink.py,(macOS) Compiles the project into a versioned .dmg.

✨ Key Features
🧠 Hybrid AI Engine: Seamlessly switches between Groq (Cloud) for speed and Llama-CPP (Local) for privacy and offline usage.

📂 Smart History (SQLite): Managed chat history with a "Soft-Delete" system. Clear your view while keeping your data archived safely.

🎙️ Voice & Vision: Natural speech recognition and text-to-speech (pyttsx3) integration.

🌐 App & Web Control: Launch local macOS apps or perform web searches via simple natural language.

🛡️ Security Guard: Includes security_guard.py to intercept and refuse unsafe or impossible system requests.

📦 macOS Distribution
To generate a clean, standalone binary and installer:

Ensure you have create-dmg installed: brew install create-dmg.

Run the build script:
python build_gink.py

💫 About Me
I'm a software developer passionate about creating personal, accessible AI tools.

💻 Tech Stack
📊 GitHub Stats
<p align="left">
<img src="https://www.google.com/search?q=https://github-readme-stats.vercel.app/api%3Fusername%3DAmgib00%26theme%3Ddark%26hide_border%3Dtrue%26show_icons%3Dtrue" width="400" />
<img src="https://nirzak-streak-stats.vercel.app/?user=Amgib00&theme=dark&hide_border=true" width="300" />


<img src="https://www.google.com/search?q=https://github-readme-stats.vercel.app/api/top-langs/%3Fusername%3DAmgib00%26theme%3Ddark%26hide_border%3Dtrue%26layout%3Dcompact" width="400" />
</p>

Proudly created by Amgib00
