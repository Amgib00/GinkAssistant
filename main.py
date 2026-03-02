import os
import requests
from llama_cpp import Llama

# -------------------------------
# Configuration
# -------------------------------
MODEL_DIR = "models"
MODEL_CHOICE = "7B"  # Change to "5B" if you want the 5B model

# Replace <your_token_here> with your Hugging Face token or set environment variable HF_TOKEN
HF_TOKEN = os.getenv("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")

MODEL_PATHS = {
    "5B": os.path.join(MODEL_DIR, "tinyllama-5b.gguf"),
    "7B": os.path.join(MODEL_DIR, "tinyllama-7b.gguf"),
}

MODEL_URLS = {
    "5B": "https://huggingface.co/TheBloke/tinyllama-5B-GGUF/resolve/main/tinyllama-5b.gguf",
    "7B": "https://huggingface.co/TheBloke/tinyllama-7B-GGUF/resolve/main/tinyllama-7b.gguf",
}

model_path = MODEL_PATHS[MODEL_CHOICE]
model_url = MODEL_URLS[MODEL_CHOICE]

# -------------------------------
# Helper function to download model
# -------------------------------
def download_model(url: str, dest_path: str, token: str):
    if os.path.exists(dest_path):
        print(f"[INFO] Model already exists: {dest_path}")
        return
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    print(f"[INFO] Downloading model from {url} ...")
    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"[INFO] Download complete: {dest_path}")

# -------------------------------
# Download if missing
# -------------------------------
download_model(model_url, model_path, HF_TOKEN)

# -------------------------------
# Load model
# -------------------------------
print(f"[INFO] Loading model from {model_path} ...")
llm = Llama(model_path=model_path)

# -------------------------------
# Example usage
# -------------------------------
prompt = "Hello Gink, summarize your setup."
response = llm(prompt)
print("[RESPONSE]", response)