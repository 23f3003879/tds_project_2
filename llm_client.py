import os
import json

# Load provider setting from environment: "gemini" or "openai"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

# ---------------------------
# Gemini (Google) mode - using NEW google-genai SDK
# ---------------------------
if LLM_PROVIDER == "gemini":
    from google import genai

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("Missing GEMINI_API_KEY in environment variables")

    # Create a reusable client instance
    client = genai.Client(api_key=GEMINI_API_KEY)
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def call_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call Gemini model using the latest google-genai SDK"""
        chosen = model or DEFAULT_MODEL
        # The new SDK allows passing a simple string to contents
        prompt = f"{system_prompt}\n\n{user_prompt}"
        resp = client.models.generate_content(
            model=chosen,
            contents=prompt
        )
        return resp.text

# ---------------------------
# OpenAI mode
# ---------------------------
elif LLM_PROVIDER == "openai":
    import openai

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY in environment variables")

    openai.api_key = OPENAI_API_KEY
    if os.getenv("OPENAI_API_BASE"):
        if hasattr(openai, "base_url"):
            openai.base_url = os.getenv("OPENAI_API_BASE")
        else:
            openai.api_base = os.getenv("OPENAI_API_BASE")

    DEFAULT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    def call_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        chosen = model or DEFAULT_MODEL
        resp = openai.ChatCompletion.create(
            model=chosen,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0
        )
        return resp.choices[0].message["content"]

# ---------------------------
# Invalid provider
# ---------------------------
else:
    raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")
