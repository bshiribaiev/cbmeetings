import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)

available_models = genai.list_models()
for model_info in available_models:
    print(f"Model name: {model_info.name}")
    print(f"Supported generation methods: {model_info.supported_generation_methods}")
    print("-" * 50)