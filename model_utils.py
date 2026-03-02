import os
import requests

def download_model(url: str, dest_path: str):
    """
    Download a model from a URL if it doesn't exist.
    """
    if os.path.exists(dest_path):
        print(f"Model already exists at {dest_path}")
        return

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    print(f"Downloading model from {url} ...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Downloaded model to {dest_path}")
