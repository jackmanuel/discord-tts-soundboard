import requests

from . import settings


class LLMConfigurationError(Exception):
    pass


def _post_chat_completion(url, headers, model, messages):
    response = requests.post(
        url=url,
        headers=headers,
        json={
            "model": model,
            "messages": messages,
        },
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def ask_llm(messages):
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY or not settings.OPENROUTER_MODEL:
            raise LLMConfigurationError("OPENROUTER_API_KEY and OPENROUTER_MODEL are required for OpenRouter.")

        return _post_chat_completion(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
            model=settings.OPENROUTER_MODEL,
            messages=messages,
        )

    if provider == "local":
        if not settings.LOCAL_LLM_URL or not settings.LOCAL_LLM_MODEL:
            raise LLMConfigurationError("LOCAL_LLM_URL and LOCAL_LLM_MODEL are required for local inference.")

        headers = {}
        if settings.LOCAL_LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LOCAL_LLM_API_KEY}"

        return _post_chat_completion(
            url=settings.LOCAL_LLM_URL,
            headers=headers,
            model=settings.LOCAL_LLM_MODEL,
            messages=messages,
        )

    raise LLMConfigurationError("LLM_PROVIDER must be either 'openrouter' or 'local'.")
