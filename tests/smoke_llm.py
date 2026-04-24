"""Smoke test: LLM API connectivity."""
import os
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
    timeout=30,
)

resp = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": 'Reply with exactly: {"status":"ok"}'}],
    temperature=0.0,
    max_tokens=20,
)
print("LLM Response:", resp.choices[0].message.content)
print("Model:", resp.model)
print("Usage:", resp.usage)
print("STATUS: PASS")
