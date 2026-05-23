"""AI service: provider rotation, random API key selection, streaming.

429 retry strategy:
  - Read Retry-After header (seconds or HTTP-date) and respect it.
  - Otherwise apply exponential backoff: 5s, 15s, 30s, 60s.
  - Try a *different* random key on each retry (per-key quotas).
  - Cap total retries at MAX_RETRIES.

Streaming:
  - on_token(text) is called for each token as it arrives — the caller
    can yield directly to the SSE response without buffering.
"""
import json
import random
import time
from datetime import datetime
import requests
from .db import db
from .models import ApiService, ApiKey, ApiKeyFolder, AiModel


MAX_RETRIES = 6
BACKOFF_SCHEDULE = [5, 15, 30, 60, 90, 120]   # seconds, by attempt index
REQUEST_TIMEOUT = 300                          # generous read timeout for slow models


def _parse_retry_after(value: str) -> float:
    """Parse Retry-After header. Returns seconds (float)."""
    if not value:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(value)
            return max(0.0, (d - datetime.utcnow()).total_seconds())
        except Exception:
            return 0.0


def pick_random_key(folder_id, exclude_ids=()):
    """Pick a random enabled key from a folder, optionally excluding ids."""
    q = ApiKey.query.filter_by(folder_id=folder_id, enabled=True)
    if exclude_ids:
        q = q.filter(~ApiKey.id.in_(list(exclude_ids)))
    keys = q.all()
    if not keys:
        return None
    return random.choice(keys)


def call_chat_stream(model: AiModel, messages, on_token,
                     on_status=None, max_retries=MAX_RETRIES):
    """Stream chat completion. Returns dict {ok, error, full_text}.

    Args:
      model: AiModel
      messages: OpenAI-style messages list
      on_token(text): called for each token (live streaming)
      on_status(text): optional, called with human-readable status updates
                       (e.g. "Rate limit, waiting 15s...") so UI can show them
    """
    full_text = ""
    last_error = None
    used_key_ids = set()       # avoid re-trying the same dead key on a 429 if alternatives exist

    def status(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    folder_keys_count = ApiKey.query.filter_by(
        folder_id=model.folder_id, enabled=True
    ).count()
    if folder_keys_count == 0:
        return {"ok": False, "error": "API kalit topilmadi.", "full_text": full_text}

    for attempt in range(max_retries):
        # Pick a different key when possible
        key = pick_random_key(model.folder_id, exclude_ids=used_key_ids)
        if not key:
            # All keys tried — reset and reuse, but still respect backoff
            used_key_ids.clear()
            key = pick_random_key(model.folder_id)
            if not key:
                break
        used_key_ids.add(key.id)

        try:
            service = model.service
            url = service.base_url.rstrip("/") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {key.secret}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            if service.request_format == "openrouter":
                headers["HTTP-Referer"] = "https://aurexai.uz"
                headers["X-Title"] = "AurexAi"

            payload = {
                "model": model.model_id,
                "messages": messages,
                "stream": True,
            }
            r = requests.post(
                url, headers=headers, json=payload,
                stream=True, timeout=(15, REQUEST_TIMEOUT),
            )

            # 429 → respect Retry-After, then continue loop with a fresh key
            if r.status_code == 429:
                retry_after = _parse_retry_after(r.headers.get("Retry-After", ""))
                if retry_after <= 0:
                    retry_after = BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]
                last_error = f"429 Rate limit. {retry_after:.0f}s kutilmoqda..."
                key.failures = (key.failures or 0) + 1
                db.session.commit()
                status(last_error)
                # cap actual sleep so user isn't blocked forever
                time.sleep(min(retry_after, 90))
                r.close()
                continue

            # 5xx → short backoff
            if 500 <= r.status_code < 600:
                wait = min(BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)], 30)
                last_error = f"{r.status_code}: server xatosi, {wait}s kutilmoqda..."
                key.failures = (key.failures or 0) + 1
                db.session.commit()
                status(last_error)
                time.sleep(wait)
                r.close()
                continue

            # Other 4xx → don't retry (auth/model error etc.)
            if r.status_code >= 400:
                last_error = f"{r.status_code}: {r.text[:300]}"
                key.failures = (key.failures or 0) + 1
                db.session.commit()
                r.close()
                # If only one key, give up; otherwise try another
                if folder_keys_count > 1 and attempt < max_retries - 1:
                    continue
                return {"ok": False, "error": last_error, "full_text": full_text}

            # Success — stream tokens through
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
                # OpenRouter sometimes returns mid-stream errors
                if isinstance(chunk, dict) and chunk.get("error"):
                    err = chunk["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    code = err.get("code", "") if isinstance(err, dict) else ""
                    last_error = f"{code or 'stream'}: {msg}"
                    if code == 429 or "rate" in msg.lower():
                        wait = BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]
                        status(f"429 oqimda — {wait}s kutilmoqda...")
                        time.sleep(wait)
                        break  # break inner loop, retry outer
                    return {"ok": False, "error": last_error, "full_text": full_text}
                delta = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content")
                )
                if delta:
                    full_text += delta
                    on_token(delta)

            if full_text:
                return {"ok": True, "full_text": full_text}
            # Empty response — retry
            last_error = "Bo'sh javob qaytdi, qayta urinilmoqda..."
            status(last_error)
            continue

        except requests.exceptions.Timeout:
            last_error = "Vaqt tugadi (timeout). Qayta urinilmoqda..."
            status(last_error)
            try:
                key.failures = (key.failures or 0) + 1
                db.session.commit()
            except Exception:
                db.session.rollback()
            time.sleep(min(BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)], 30))
            continue
        except Exception as e:
            last_error = f"Ulanish xatosi: {e}"
            try:
                key.failures = (key.failures or 0) + 1
                db.session.commit()
            except Exception:
                db.session.rollback()
            status(last_error)
            time.sleep(min(BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)], 15))
            continue

    return {
        "ok": False,
        "error": last_error or "AI ulanishi muvaffaqiyatsiz (limit oshib ketdi).",
        "full_text": full_text,
    }


OPENROUTER_NAME = "OpenRouter"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_FOLDER = "default"


def get_default_service() -> ApiService:
    """Return (and create if missing) the OpenRouter service."""
    svc = ApiService.query.filter_by(name=OPENROUTER_NAME).first()
    if not svc:
        svc = ApiService(
            name=OPENROUTER_NAME,
            base_url=OPENROUTER_BASE,
            request_format="openrouter",
            enabled=True,
        )
        db.session.add(svc)
        db.session.commit()
    return svc


def get_default_folder() -> ApiKeyFolder:
    """Return (and create if missing) the default OpenRouter key folder."""
    svc = get_default_service()
    f = ApiKeyFolder.query.filter_by(service_id=svc.id, name=OPENROUTER_FOLDER).first()
    if not f:
        f = ApiKeyFolder(service_id=svc.id, name=OPENROUTER_FOLDER)
        db.session.add(f)
        db.session.commit()
    return f


def seed_default_provider(default_openrouter_key: str = ""):
    """Idempotent: always ensures OpenRouter + default folder exist.

    Adds a few starter models *only* on first install (when there are 0 models).
    """
    folder = get_default_folder()
    svc = folder.service

    if default_openrouter_key:
        exists = ApiKey.query.filter_by(folder_id=folder.id, secret=default_openrouter_key).first()
        if not exists:
            db.session.add(ApiKey(folder_id=folder.id, label="bootstrap", secret=default_openrouter_key))
            db.session.commit()

    if AiModel.query.count() == 0:
        starters = [
            ("Aurex Lite", "deepseek/deepseek-v4-flash:free", "ODDIY", False),
            ("Aurex Pro",  "anthropic/claude-3.5-sonnet",     "PRO",   False),
            ("Aurex Plus", "openai/gpt-4o",                   "PLUS",  False),
            ("Aurex Codex","anthropic/claude-3.5-sonnet",     "PLUS",  True),
        ]
        for name, mid, plan, codex in starters:
            db.session.add(AiModel(
                display_name=name, model_id=mid,
                service_id=svc.id, folder_id=folder.id,
                min_plan=plan, is_codex=codex,
            ))
        db.session.commit()
