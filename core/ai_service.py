"""AI service: provider rotation, random API key selection, streaming."""
import json
import random
import time
from datetime import datetime
import requests
from .db import db
from .models import ApiService, ApiKey, ApiKeyFolder, AiModel


def pick_random_key(folder_id):
    """Pick a random enabled key from a folder."""
    keys = ApiKey.query.filter_by(folder_id=folder_id, enabled=True).all()
    if not keys:
        return None
    return random.choice(keys)


def call_chat_stream(model: AiModel, messages, on_token, max_retries=3):
    """Stream chat completion. Calls on_token(text) for each token.

    Tries multiple keys / re-attempts on failure (up to max_retries).
    Returns dict: {ok, error, full_text}.
    """
    full_text = ""
    last_error = None
    tried = set()

    for attempt in range(max_retries):
        key = pick_random_key(model.folder_id)
        if not key:
            return {"ok": False, "error": "API kalit topilmadi.", "full_text": full_text}
        if key.id in tried and len(tried) >= ApiKey.query.filter_by(folder_id=model.folder_id, enabled=True).count():
            break
        tried.add(key.id)

        try:
            service = model.service
            url = service.base_url.rstrip("/") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {key.secret}",
                "Content-Type": "application/json",
            }
            if service.request_format == "openrouter":
                headers["HTTP-Referer"] = "https://aurexai.uz"
                headers["X-Title"] = "AurexAi"

            payload = {
                "model": model.model_id,
                "messages": messages,
                "stream": True,
            }
            with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as r:
                if r.status_code >= 400:
                    last_error = f"{r.status_code}: {r.text[:200]}"
                    key.failures = (key.failures or 0) + 1
                    db.session.commit()
                    continue

                key.last_used_at = datetime.utcnow()
                key.failures = 0
                db.session.commit()

                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        full_text += delta
                        on_token(delta)

                return {"ok": True, "full_text": full_text}
        except Exception as e:
            last_error = str(e)
            try:
                key.failures = (key.failures or 0) + 1
                db.session.commit()
            except Exception:
                db.session.rollback()
            continue

    return {"ok": False, "error": last_error or "AI ulanishi muvaffaqiyatsiz.", "full_text": full_text}


def seed_default_provider(default_openrouter_key: str = ""):
    """Seed an OpenRouter service if none exists."""
    if ApiService.query.first():
        return
    svc = ApiService(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        request_format="openrouter",
        enabled=True,
    )
    db.session.add(svc)
    db.session.flush()
    folder = ApiKeyFolder(service_id=svc.id, name="default")
    db.session.add(folder)
    db.session.flush()
    if default_openrouter_key:
        db.session.add(ApiKey(folder_id=folder.id, label="bootstrap", secret=default_openrouter_key))
    # Default models
    db.session.add(AiModel(
        display_name="Aurex Lite",
        model_id="meta-llama/llama-3.1-8b-instruct:free",
        service_id=svc.id, folder_id=folder.id, min_plan="ODDIY",
    ))
    db.session.add(AiModel(
        display_name="Aurex Pro",
        model_id="anthropic/claude-3.5-sonnet",
        service_id=svc.id, folder_id=folder.id, min_plan="PRO",
    ))
    db.session.add(AiModel(
        display_name="Aurex Plus",
        model_id="openai/gpt-4o",
        service_id=svc.id, folder_id=folder.id, min_plan="PLUS",
    ))
    db.session.add(AiModel(
        display_name="Aurex Codex",
        model_id="anthropic/claude-3.5-sonnet",
        service_id=svc.id, folder_id=folder.id, min_plan="PLUS",
        is_codex=True,
    ))
    db.session.commit()
