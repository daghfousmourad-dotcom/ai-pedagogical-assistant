import os
import time
import base64
from openai import OpenAI

class ImageTester:
    def __init__(self, key=None):
        self.openai_key = key or os.getenv("OPENAI_API_KEY")
        self.openai = OpenAI(api_key=self.openai_key)

    def analyze_image(self, image_path, prompt, temperature=0.7, max_tokens=300):
        """Version isolée acceptant des hyperparamètres."""
        print(f"   [MLOPS DEBUG IMAGE] Params: Temp={temperature}, MaxTokens={max_tokens}")
        
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        response = self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        },
                    ],
                }
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
