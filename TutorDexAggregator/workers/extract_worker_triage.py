from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from logging_setup import log_event
from workers.utils import build_message_link


def _chunk_text(text: str, *, max_len: int) -> List[str]:
    t = str(text or "")
    if not t:
        return [""]
    if max_len <= 0:
        return [t]
    return [t[i : i + max_len] for i in range(0, len(t), max_len)]


def _skipped_messages_chat_id(cfg: Any) -> Optional[str]:
    v = str(getattr(cfg, "skipped_messages_chat_id", "") or "").strip()
    return v or None


def _default_skipped_messages_thread_id(cfg: Any) -> Optional[int]:
    return getattr(cfg, "skipped_messages_thread_id", None)


def _triage_thread_id(cfg: Any, kind: str) -> Optional[int]:
    k = str(kind or "").strip().lower()
    if k in {"extraction_error", "extraction_errors", "extraction"}:
        v = getattr(cfg, "skipped_messages_thread_id_extraction_errors", None)
        return v or _default_skipped_messages_thread_id(cfg)
    if k in {"non_assignment", "non-assignments", "nonassignment"}:
        v = getattr(cfg, "skipped_messages_thread_id_non_assignment", None)
        return v or _default_skipped_messages_thread_id(cfg)
    if k in {"compilation", "compilations"}:
        v = getattr(cfg, "skipped_messages_thread_id_compilations", None)
        return v or _default_skipped_messages_thread_id(cfg)
    return _default_skipped_messages_thread_id(cfg)


def _skipped_messages_bot_token(cfg: Any) -> Optional[str]:
    v = str(getattr(cfg, "group_bot_token", "") or "").strip() or str(getattr(cfg, "dm_bot_token", "") or "").strip()
    return v or None


def _telegram_bot_api_base(cfg: Any) -> Optional[str]:
    return str(getattr(cfg, "bot_api_url", "") or "").strip() or None


def _telegram_send_message(*, cfg: Any, to_chat_id: str, text: str, thread_id: Optional[int] = None) -> Dict[str, Any]:
    token = _skipped_messages_bot_token(cfg)
    base = _telegram_bot_api_base(cfg)
    if not token and not base:
        return {"ok": False, "error": "no_bot_token_or_api_url"}

    url = base
    if not url and token:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
    elif url and not url.endswith("/sendMessage"):
        url = url.rstrip("/") + "/sendMessage"

    try:
        body: Dict[str, Any] = {
            "chat_id": to_chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "disable_notification": True,
        }
        if thread_id is not None:
            body["message_thread_id"] = int(thread_id)
        resp = requests.post(url, json=body, timeout=10)
        return {"ok": resp.status_code < 400, "status_code": resp.status_code, "body": (resp.text or "")[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def try_report_triage_message(
    *,
    cfg: Any,
    logger: logging.Logger,
    kind: str,
    raw: Dict[str, Any],
    channel_link: str,
    summary: str,
    stage: str,
    extracted_codes: Optional[List[str]] = None,
) -> None:
    to_chat_id = _skipped_messages_chat_id(cfg)
    if not to_chat_id:
        return

    thread_id = _triage_thread_id(cfg, kind)
    msg_id = raw.get("message_id")
    link = build_message_link(channel_link, str(msg_id or "")) or ""
    raw_text = str(raw.get("raw_text") or "").strip()

    kind_norm = str(kind or "").strip().lower()
    title = "TutorDex: triage"
    if kind_norm in {"extraction_error", "extraction_errors", "extraction"}:
        title = "TutorDex: extraction error"
    elif kind_norm in {"non_assignment", "non-assignments", "nonassignment"}:
        title = "TutorDex: non-assignment (skipped)"
    elif kind_norm in {"compilation", "compilations"}:
        title = "TutorDex: compilation (skipped)"

    max_msg_len = 3600
    codes_clean: Optional[List[str]] = None
    codes_line = ""
    codes_preview_limit = 40
    if extracted_codes is not None:
        codes_clean = [str(c).strip() for c in (extracted_codes or []) if str(c).strip()]
        if not codes_clean:
            codes_line = "codes=[]\n"
        else:
            preview = codes_clean[:codes_preview_limit]
            rest = len(codes_clean) - len(preview)
            preview_joined = ", ".join(preview)
            codes_line = f"codes=[{preview_joined}{f' (+{rest} more)' if rest > 0 else ''}]\n"

    header = (
        f"{title}\n"
        f"stage={stage}\n"
        f"channel={channel_link}\n"
        + (f"message_id={msg_id}\n" if msg_id is not None else "")
        + (f"link={link}\n" if link else "")
        + (codes_line if codes_line else "")
        + f"summary={str(summary or '')[:800]}\n"
        "\n"
        "raw_text:\n"
    )

    try:
        first_budget = max(200, max_msg_len - len(header))
        raw_chunks = _chunk_text(raw_text, max_len=first_budget)
        first = header + (raw_chunks[0] if raw_chunks else "")
        res0 = _telegram_send_message(cfg=cfg, to_chat_id=to_chat_id, text=first, thread_id=thread_id)
        log_event(
            logger,
            logging.INFO,
            "failed_message_triage_sent",
            ok=bool(res0.get("ok")),
            kind=kind_norm,
            stage=stage,
            channel=channel_link,
            message_id=str(msg_id),
            part=1,
            parts=max(1, len(raw_chunks)),
            thread_id=thread_id,
            res=res0,
        )
    except Exception:
        return

    if codes_clean is not None and len(codes_clean) > codes_preview_limit:
        try:
            codes_full = ", ".join(codes_clean)
            prefix = f"{title}: codes (full)\n"
            budget = max(200, max_msg_len - len(prefix))
            parts = _chunk_text(codes_full, max_len=budget)
            for idx, chunk in enumerate(parts, start=1):
                resi = _telegram_send_message(
                    cfg=cfg,
                    to_chat_id=to_chat_id,
                    text=f"{prefix}(part {idx}/{len(parts)})\n{chunk}",
                    thread_id=thread_id,
                )
                log_event(
                    logger,
                    logging.INFO,
                    "failed_message_triage_sent",
                    ok=bool(resi.get("ok")),
                    kind=kind_norm,
                    stage=stage,
                    channel=channel_link,
                    message_id=str(msg_id),
                    part=f"codes:{idx}",
                    parts=f"codes:{len(parts)}",
                    thread_id=thread_id,
                    res=resi,
                )
        except Exception:
            pass

    if raw_chunks and len(raw_chunks) > 1:
        for idx, chunk in enumerate(raw_chunks[1:], start=2):
            try:
                part_prefix = f"{title}: raw_text (part {idx}/{len(raw_chunks)})\n"
                budget = max(50, max_msg_len - len(part_prefix))
                for sub in _chunk_text(chunk, max_len=budget):
                    resi = _telegram_send_message(cfg=cfg, to_chat_id=to_chat_id, text=part_prefix + sub, thread_id=thread_id)
                    log_event(
                        logger,
                        logging.INFO,
                        "failed_message_triage_sent",
                        ok=bool(resi.get("ok")),
                        kind=kind_norm,
                        stage=stage,
                        channel=channel_link,
                        message_id=str(msg_id),
                        part=idx,
                        parts=len(raw_chunks),
                        thread_id=thread_id,
                        res=resi,
                    )
            except Exception:
                pass

