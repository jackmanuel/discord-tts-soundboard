import requests

from . import settings


class LLMConfigurationError(Exception):
    pass


def _post_chat_completion(url, headers, model, messages, extra_payload=None):
    payload = {
        "model": model,
        "messages": messages,
    }
    if extra_payload:
        payload.update(extra_payload)

    response = requests.post(
        url=url,
        headers=headers,
        json=payload,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _get_provider_config():
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY or not settings.OPENROUTER_MODEL:
            raise LLMConfigurationError("OPENROUTER_API_KEY and OPENROUTER_MODEL are required for OpenRouter.")

        return {
            "provider": provider,
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
            "model": settings.OPENROUTER_MODEL,
            "api_key_configured": True,
        }

    if provider == "local":
        if not settings.LOCAL_LLM_URL or not settings.LOCAL_LLM_MODEL:
            raise LLMConfigurationError("LOCAL_LLM_URL and LOCAL_LLM_MODEL are required for local inference.")

        headers = {}
        if settings.LOCAL_LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LOCAL_LLM_API_KEY}"

        return {
            "provider": provider,
            "url": settings.LOCAL_LLM_URL,
            "headers": headers,
            "model": settings.LOCAL_LLM_MODEL,
            "api_key_configured": bool(settings.LOCAL_LLM_API_KEY),
        }

    raise LLMConfigurationError("LLM_PROVIDER must be either 'openrouter' or 'local'.")


def ask_llm(messages):
    config = _get_provider_config()
    return _post_chat_completion(
        url=config["url"],
        headers=config["headers"],
        model=config["model"],
        messages=messages,
    )


def describe_llm_config():
    config = _get_provider_config()
    return {
        "provider": config["provider"],
        "url": config["url"],
        "model": config["model"],
        "api_key_configured": config["api_key_configured"],
        "timeout_seconds": settings.LLM_TIMEOUT_SECONDS,
    }


def check_llm_status():
    config = _get_provider_config()
    _post_chat_completion(
        url=config["url"],
        headers=config["headers"],
        model=config["model"],
        messages=[
            {"role": "system", "content": "Reply with OK."},
            {"role": "user", "content": "Status check"},
        ],
        extra_payload={"max_tokens": 5},
    )
    return describe_llm_config()
