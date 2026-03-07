import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"

if USE_OPENAI:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
else:
    client = OpenAI(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",
    )
    MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def chat(messages: list[dict], **kwargs) -> str:
    """Single call interface — returns assistant content string."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content
