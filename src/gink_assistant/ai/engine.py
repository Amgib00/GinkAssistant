import os
import platform
from llama_cpp import Llama


class GinkAI:
    def __init__(self, model_path):
        self.os_type = platform.system()
        self.model_path = model_path

        # Adjusting resource usage based on platform
        self.n_threads = 4 if self.os_type == "Darwin" else 2
        self.n_gpu_layers = 1 if self.os_type == "Darwin" else 0  # Metal support for Mac

        self.llm = Llama(
            model_path=self.model_path,
            n_threads=self.n_threads,
            n_gpu_layers=self.n_gpu_layers
        )

    def generate(self, prompt):
        output = self.llm(
            f"Q: {prompt} A: ",
            max_tokens=128,
            stop=["Q:", "\n"],
            echo=False
        )
        return output["choices"][0]["text"]