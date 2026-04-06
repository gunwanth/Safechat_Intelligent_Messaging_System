from flask import Flask, render_template, session, redirect, url_for, request
import os, sys, pickle, warnings
from collections import Counter
import io
import hashlib
import json
import re
from datetime import datetime
from contextlib import redirect_stdout
from flask import jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.exceptions import InconsistentVersionWarning
from sms_generator import SMSGenerator
from email_column_router import EmailColumnRouter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ML_MODEL_DIR = os.path.join(BASE_DIR, "ML_model")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if ML_MODEL_DIR not in sys.path:
    sys.path.insert(0, ML_MODEL_DIR)

try:
    from ML_model.xai_explainer import XAIExplainer
except Exception:
    try:
        from xai_explainer import XAIExplainer  # type: ignore
    except Exception:
        XAIExplainer = None

USERS_FILE = "users.json"
EMAIL_COLUMN_ROUTER = EmailColumnRouter()
_TRANSFORMER_PIPELINES = {}
_SHARED_PHISHING_DETECTOR = None


def safe_load_pickle(path: str):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            with open(path, "rb") as f:
                return pickle.load(f)
    except InconsistentVersionWarning:
        print(f"[WARN] Skipping incompatible sklearn artifact: {path}")
        return None

try:
    from xai_explainer import XAIExplainer
except Exception as e:
    print("[XAI INIT FAILED]", e)
    XAIExplainer = None
    print("XAIExplainer =", XAIExplainer)

try:
    from metadata_trainer import (
        train_and_report_metadata_models as _train_metadata_local,
        predict_meta_ensemble_risk as _predict_meta_risk_local,
        sanitize_text_for_nlu as _sanitize_text_for_nlu_local,
        extract_metadata_features as _extract_metadata_features_local,
    )
except Exception:
    _train_metadata_local = None
    _predict_meta_risk_local = None
    _sanitize_text_for_nlu_local = None
    _extract_metadata_features_local = None

if _train_metadata_local is not None:
    train_and_report_metadata_models = _train_metadata_local
    predict_meta_ensemble_risk = _predict_meta_risk_local
    metadata_sanitize_text = _sanitize_text_for_nlu_local
    metadata_extract_features = _extract_metadata_features_local
else:
    try:
        from ML_model.metadata_trainer import (  # type: ignore
            train_and_report_metadata_models,
            predict_meta_ensemble_risk,
            sanitize_text_for_nlu as metadata_sanitize_text,
            extract_metadata_features as metadata_extract_features,
        )
    except Exception:
        train_and_report_metadata_models = None
        predict_meta_ensemble_risk = None
        metadata_sanitize_text = None
        metadata_extract_features = None

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

def is_valid_password(password: str) -> bool:
    """Password must be at least 8 chars and include at least one uppercase letter."""
    if not password or len(password) < 8:
        return False
    return bool(re.search(r"[A-Z]", password))

def normalize_sms_entry(sms):
    """Ensure all required fields exist for dashboard rendering"""
    return {
        "sender": sms.get("sender", "Unknown"),
        "content": sms.get("content", ""),
        "level": sms.get("level", "Unknown"),
        "ml_prediction": sms.get("ml_prediction", "Pending"),
        "confidence": sms.get("confidence", 0)
    }

def save_spam_email(user_email, email_obj):
    safe_email = user_email.replace("@", "_").replace(".", "_")
    spam_file = f"ML_model/spam_{safe_email}.pkl"

    spam_list = []
    if os.path.exists(spam_file):
        try:
            with open(spam_file, "rb") as f:
                spam_list = pickle.load(f)
        except:
            spam_list = []

    # avoid duplicates
    if not any(e.get("id") == email_obj.get("id") for e in spam_list):
        spam_list.insert(0, email_obj)

    with open(spam_file, "wb") as f:
        pickle.dump(spam_list, f)

def _safe_email(user_email):
    return user_email.replace("@", "_").replace(".", "_")

def _inbox_state_file(user_email):
    safe_email = _safe_email(user_email)
    return f"ML_model/inbox_state_{safe_email}.pkl"

def _emails_file(user_email):
    safe_email = _safe_email(user_email)
    return f"ML_model/emails_{safe_email}.pkl"

def _analytics_state_file(user_email):
    safe_email = _safe_email(user_email)
    return f"ML_model/analytics_state_{safe_email}.pkl"


def _gmail_token_file(user_email):
    token_dir = os.getenv("TOKEN_STORAGE_DIR", ".")
    os.makedirs(token_dir, exist_ok=True)
    return os.path.join(token_dir, f"token_{user_email}.pkl")

def load_inbox_state(user_email):
    state_file = _inbox_state_file(user_email)
    if not os.path.exists(state_file):
        return {"emails": [], "deleted_ids": [], "training": _default_training_state()}

    try:
        with open(state_file, "rb") as f:
            raw_state = pickle.load(f)
    except Exception:
        return {"emails": [], "deleted_ids": [], "training": _default_training_state()}

    if not isinstance(raw_state, dict):
        return {"emails": [], "deleted_ids": [], "training": _default_training_state()}

    emails = raw_state.get("emails", [])
    deleted_ids = raw_state.get("deleted_ids", [])
    if not isinstance(emails, list):
        emails = []
    if not isinstance(deleted_ids, list):
        deleted_ids = []

    return {
        "emails": emails,
        "deleted_ids": deleted_ids,
        "training": _normalize_training_state(raw_state.get("training")),
    }

def save_inbox_state(user_email, state):
    state_file = _inbox_state_file(user_email)
    payload = {
        "emails": state.get("emails", []),
        "deleted_ids": state.get("deleted_ids", []),
        "training": _normalize_training_state(state.get("training")),
    }
    with open(state_file, "wb") as f:
        pickle.dump(payload, f)


def load_analytics_state(user_email):
    state_file = _analytics_state_file(user_email)
    if not os.path.exists(state_file):
        return _default_analytics_state()
    try:
        with open(state_file, "rb") as f:
            raw_state = pickle.load(f)
    except Exception:
        return _default_analytics_state()
    if not isinstance(raw_state, dict):
        return _default_analytics_state()
    return _normalize_analytics_state(raw_state)


def save_analytics_state(user_email, state):
    state_file = _analytics_state_file(user_email)
    with open(state_file, "wb") as f:
        pickle.dump(_normalize_analytics_state(state), f)


def _default_training_state():
    return {
        "trained_signatures": {},
        "pending_ids": [],
        "last_trained_at": None,
        "last_training_count": 0,
    }


def _default_analytics_state():
    return {
        "ml_dashboard": {
            "dataset_signature": None,
            "label_mode": None,
            "entries": {},
            "summary": {},
            "dirty_ids": [],
            "last_built_at": None,
        },
        "data_proof": {
            "dataset_signature": None,
            "label_mode": None,
            "proof": None,
            "last_built_at": None,
        },
    }


def _normalize_training_state(training):
    state = _default_training_state()
    if not isinstance(training, dict):
        return state

    trained_signatures = training.get("trained_signatures", {})
    if isinstance(trained_signatures, dict):
        state["trained_signatures"] = {
            str(k): str(v)
            for k, v in trained_signatures.items()
            if k is not None and v is not None
        }

    pending_ids = training.get("pending_ids", [])
    if isinstance(pending_ids, list):
        deduped = []
        seen = set()
        for item in pending_ids:
            value = str(item)
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        state["pending_ids"] = deduped

    if training.get("last_trained_at"):
        state["last_trained_at"] = str(training.get("last_trained_at"))
    try:
        state["last_training_count"] = int(training.get("last_training_count", 0) or 0)
    except (TypeError, ValueError):
        state["last_training_count"] = 0
    return state


def _normalize_analytics_state(state):
    normalized = _default_analytics_state()
    if not isinstance(state, dict):
        return normalized

    ml_dashboard = state.get("ml_dashboard", {})
    if isinstance(ml_dashboard, dict):
        normalized["ml_dashboard"]["dataset_signature"] = ml_dashboard.get("dataset_signature")
        normalized["ml_dashboard"]["label_mode"] = ml_dashboard.get("label_mode")
        entries = ml_dashboard.get("entries", {})
        if isinstance(entries, dict):
            normalized["ml_dashboard"]["entries"] = {
                str(k): v for k, v in entries.items() if isinstance(v, dict)
            }
        summary = ml_dashboard.get("summary", {})
        if isinstance(summary, dict):
            normalized["ml_dashboard"]["summary"] = summary
        dirty_ids = ml_dashboard.get("dirty_ids", [])
        if isinstance(dirty_ids, list):
            normalized["ml_dashboard"]["dirty_ids"] = [str(v) for v in dirty_ids if v is not None]
        normalized["ml_dashboard"]["last_built_at"] = ml_dashboard.get("last_built_at")

    data_proof = state.get("data_proof", {})
    if isinstance(data_proof, dict):
        normalized["data_proof"]["dataset_signature"] = data_proof.get("dataset_signature")
        normalized["data_proof"]["label_mode"] = data_proof.get("label_mode")
        normalized["data_proof"]["proof"] = data_proof.get("proof")
        normalized["data_proof"]["last_built_at"] = data_proof.get("last_built_at")

    return normalized


def _get_shared_detector():
    global _SHARED_PHISHING_DETECTOR
    if _SHARED_PHISHING_DETECTOR is None:
        _SHARED_PHISHING_DETECTOR = PhishingDetector()
    return _SHARED_PHISHING_DETECTOR


def _email_training_signature(email):
    raw = "||".join(
        [
            str(email.get("id", "")),
            str(email.get("subject", "")),
            str(email.get("sender", "")),
            str(email.get("date", "")),
            str(email.get("content", "")),
            str(email.get("level", "")),
            str(email.get("metadata_level", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _dataset_signature(emails, label_mode="medium_high"):
    parts = [str(label_mode or "medium_high")]
    for email in emails or []:
        if not isinstance(email, dict):
            continue
        signature = email.get("training_signature") or _email_training_signature(email)
        parts.append(f"{email.get('id', '')}:{signature}")
    raw = "||".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _mark_analytics_dirty(user_email, dirty_ids=None):
    state = load_analytics_state(user_email)
    ml_state = state["ml_dashboard"]
    existing = set(str(v) for v in ml_state.get("dirty_ids", []))
    for email_id in dirty_ids or []:
        existing.add(str(email_id))
    ml_state["dirty_ids"] = sorted(existing)
    state["data_proof"]["dataset_signature"] = None
    state["data_proof"]["proof"] = None
    save_analytics_state(user_email, state)


def _metadata_level_from_score(score):
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0.75:
        return "High"
    if value >= 0.45:
        return "Medium"
    return "Low"


def _chunked(items, size):
    chunk = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _normalize_columns(value):
    if not isinstance(value, list):
        return []
    allowed = {"promotions", "social", "purchases"}
    return [item for item in value if item in allowed]


def _analyze_inbox_email(user_email, email, previous=None, enable_meta_learning_inbox=True):
    detector = _get_shared_detector()
    previous = previous if isinstance(previous, dict) else {}

    score = detector.calculate_risk_score(email)
    level = detector.get_risk_level(score)
    threats = detector.detect_threats(email)
    rule_explanations = [
        {"token": threat, "impact": "rule", "direction": "phishing"}
        for threat in threats
    ]

    excluded_columns = _normalize_columns(previous.get("excluded_columns", []))
    secondary_column = classify_secondary_column(email)
    columns = []
    if secondary_column and secondary_column not in excluded_columns:
        columns = [secondary_column]

    message_text = f"{email.get('subject', '')} {email.get('content', '')}"
    nlu_summary = analyze_message_nlu(message_text)
    metadata_score = metadata_first_score(nlu_summary, rule_score=score)

    branch_scores = {}
    meta_learning_score = None
    if enable_meta_learning_inbox and predict_meta_ensemble_risk:
        try:
            branch_scores = predict_meta_ensemble_risk(user_email, message_text) or {}
            if branch_scores:
                meta_learning_score = float(branch_scores.get("ensemble_prob", 0.0))
                metadata_score = round((0.55 * metadata_score) + (0.45 * meta_learning_score), 4)
        except Exception as ml_err:
            print(f"[INBOX META-LEARN WARNING] {ml_err}")

    processed = {
        "id": email.get("id"),
        "subject": email.get("subject", ""),
        "sender": email.get("sender", ""),
        "date": email.get("date", ""),
        "content": email.get("content", ""),
        "snippet": email.get("snippet", ""),
        "level": level,
        "score": score,
        "threats": threats,
        "xai_rules": rule_explanations,
        "xai": rule_explanations,
        "nlu_summary": nlu_summary,
        "metadata_score": metadata_score,
        "metadata_level": _metadata_level_from_score(metadata_score),
        "meta_learning_score": meta_learning_score,
        "meta_baseline_score": branch_scores.get("baseline_prob"),
        "meta_metadata_model_score": branch_scores.get("metadata_prob"),
        "columns": columns,
        "excluded_columns": excluded_columns,
    }
    processed["training_signature"] = _email_training_signature(processed)
    processed["training_state"] = "pending"
    return processed


def _hydrate_stored_email(user_email, email, enable_meta_learning_inbox=True):
    stored = dict(email or {})
    stored["columns"] = _normalize_columns(stored.get("columns", []))
    stored["excluded_columns"] = _normalize_columns(stored.get("excluded_columns", []))

    message_text = f"{stored.get('subject', '')} {stored.get('content', '')}"
    if not stored.get("nlu_summary"):
        stored["nlu_summary"] = analyze_message_nlu(message_text)
    if stored.get("metadata_score") is None:
        stored["metadata_score"] = metadata_first_score(
            stored.get("nlu_summary", {}),
            rule_score=stored.get("score", 0),
        )
    if not stored.get("metadata_level"):
        stored["metadata_level"] = _metadata_level_from_score(stored.get("metadata_score"))

    if enable_meta_learning_inbox and predict_meta_ensemble_risk and stored.get("meta_learning_score") is None:
        try:
            branch = predict_meta_ensemble_risk(user_email, message_text) or {}
            if branch:
                stored["meta_learning_score"] = float(branch.get("ensemble_prob", 0.0))
                stored["meta_baseline_score"] = branch.get("baseline_prob")
                stored["meta_metadata_model_score"] = branch.get("metadata_prob")
        except Exception as ml_err:
            print(f"[INBOX META-LEARN WARNING] {ml_err}")

    if not stored.get("training_signature"):
        stored["training_signature"] = _email_training_signature(stored)
    return stored


def _run_inbox_agentic_loop(gmail, user_email, state, limit=20, chunk_size=5):
    state = {
        "emails": state.get("emails", []),
        "deleted_ids": state.get("deleted_ids", []),
        "training": _normalize_training_state(state.get("training")),
    }
    training_state = state["training"]
    deleted_ids = {str(eid) for eid in state.get("deleted_ids", [])}
    existing_by_id = {}
    for stored in state.get("emails", []):
        if isinstance(stored, dict) and stored.get("id"):
            existing_by_id[str(stored["id"])] = stored

    enable_meta_learning_inbox = _env_bool("ENABLE_META_LEARNING_INBOX", True)
    message_refs = []
    ordered_ids = []
    fetched_by_id = {}
    processed_by_id = {}
    pending_ids = set(training_state.get("pending_ids", []))
    chunk_metrics = {
        "fetched_ref_count": 0,
        "fetched_full_count": 0,
        "reused_count": 0,
        "new_count": 0,
    }

    steps = [
        "scan_message_refs",
        "fetch_new_chunks",
        "hydrate_existing",
        "assemble_results",
    ]

    while steps:
        step = steps.pop(0)

        if step == "scan_message_refs":
            message_refs = gmail.get_recent_message_refs(limit=limit)
            ordered_ids = [
                str(item.get("id"))
                for item in message_refs
                if item.get("id") and str(item.get("id")) not in deleted_ids
            ]
            chunk_metrics["fetched_ref_count"] = len(ordered_ids)
            continue

        if step == "fetch_new_chunks":
            missing_ids = [msg_id for msg_id in ordered_ids if msg_id not in existing_by_id]
            chunk_metrics["new_count"] = len(missing_ids)
            for chunk in _chunked(missing_ids, chunk_size):
                for email in gmail.get_emails_by_ids(chunk):
                    email_id = str(email.get("id", ""))
                    if not email_id:
                        continue
                    fetched_by_id[email_id] = email
            chunk_metrics["fetched_full_count"] = len(fetched_by_id)
            continue

        if step == "hydrate_existing":
            for msg_id in ordered_ids:
                if msg_id in fetched_by_id:
                    processed = _analyze_inbox_email(
                        user_email,
                        fetched_by_id[msg_id],
                        previous=existing_by_id.get(msg_id),
                        enable_meta_learning_inbox=enable_meta_learning_inbox,
                    )
                    processed_by_id[msg_id] = processed
                    pending_ids.add(msg_id)
                    continue

                stored = existing_by_id.get(msg_id)
                if not stored:
                    continue
                hydrated = _hydrate_stored_email(
                    user_email,
                    stored,
                    enable_meta_learning_inbox=enable_meta_learning_inbox,
                )
                processed_by_id[msg_id] = hydrated
                chunk_metrics["reused_count"] += 1
            continue

        if step == "assemble_results":
            ordered_processed = []
            seen_ids = set()
            for msg_id in ordered_ids:
                item = processed_by_id.get(msg_id)
                if not item:
                    continue
                signature = item.get("training_signature") or _email_training_signature(item)
                if training_state["trained_signatures"].get(msg_id) != signature:
                    pending_ids.add(msg_id)
                    item["training_state"] = "pending"
                else:
                    item["training_state"] = "trained"
                ordered_processed.append(item)
                seen_ids.add(msg_id)

            for stored_id, stored in existing_by_id.items():
                if stored_id in seen_ids or stored_id in deleted_ids:
                    continue
                hydrated = _hydrate_stored_email(
                    user_email,
                    stored,
                    enable_meta_learning_inbox=enable_meta_learning_inbox,
                )
                signature = hydrated.get("training_signature") or _email_training_signature(hydrated)
                hydrated["training_state"] = (
                    "trained"
                    if training_state["trained_signatures"].get(stored_id) == signature
                    else "pending"
                )
                if hydrated["training_state"] == "pending":
                    pending_ids.add(stored_id)
                ordered_processed.append(hydrated)

            training_state["pending_ids"] = sorted(pending_ids)
            return ordered_processed, training_state, chunk_metrics

    return [], training_state, chunk_metrics


def _train_pending_inbox_models(user_email, emails, training_state, label_mode):
    training_state = _normalize_training_state(training_state)
    pending_ids = {
        str(email_id)
        for email_id in training_state.get("pending_ids", [])
        if str(email_id)
    }
    if not pending_ids:
        return training_state, False

    if not train_and_report_metadata_models:
        return training_state, False

    relevant_emails = [
        email for email in emails
        if isinstance(email, dict) and str(email.get("id", "")) in pending_ids
    ]
    if not relevant_emails:
        training_state["pending_ids"] = []
        return training_state, False

    try:
        train_and_report_metadata_models(user_email, relevant_emails, label_mode=label_mode)
    except Exception as train_err:
        print(f"[INBOX META TRAIN WARNING] {train_err}")
        return training_state, False

    trained_ids = []
    for email in relevant_emails:
        email_id = str(email.get("id", ""))
        if not email_id:
            continue
        signature = email.get("training_signature") or _email_training_signature(email)
        training_state["trained_signatures"][email_id] = signature
        email["training_state"] = "trained"
        trained_ids.append(email_id)

    training_state["pending_ids"] = sorted(pending_ids - set(trained_ids))
    training_state["last_trained_at"] = datetime.utcnow().isoformat() + "Z"
    training_state["last_training_count"] = len(relevant_emails)
    _mark_analytics_dirty(user_email, trained_ids)
    return training_state, True


def _build_inbox_stats(processed, label_mode):
    phishing_count = 0
    threat_count = 0
    all_labels = []
    for email in processed:
        level = email.get("level")
        if level == "High":
            phishing_count += 1
        if email.get("threats"):
            threat_count += 1
        all_labels.append(derive_label_from_level(level, label_mode=label_mode))

    email_columns = {
        "primary": processed,
        "promotions": [e for e in processed if "promotions" in e.get("columns", [])],
        "social": [e for e in processed if "social" in e.get("columns", [])],
        "purchases": [e for e in processed if "purchases" in e.get("columns", [])],
    }
    stats = {
        "total": len(email_columns["primary"]),
        "phishing": phishing_count,
        "threats": threat_count,
        "threat_percent": round((threat_count / len(email_columns["primary"]) * 100), 2)
        if email_columns["primary"] else 0,
    }
    return email_columns, stats, all_labels


def _metadata_report_file(user_email):
    safe_email = _safe_email(user_email)
    return os.path.join("ML_model", f"metrics_report_{safe_email}.json")


def _load_saved_metadata_report(user_email):
    report_file = _metadata_report_file(user_email)
    if not os.path.exists(report_file):
        return None
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def classify_secondary_column(email):
    try:
        return EMAIL_COLUMN_ROUTER.classify(email)
    except Exception as e:
        print("[COLUMN ROUTER ERROR]", e)
        return None

def prediction_confidence_pct(trainer, pred_val, proba_row):
    """Return confidence % for the predicted class probability."""
    try:
        classes = list(getattr(trainer.model, "classes_", []))
        if classes:
            # 1) Exact class match
            for idx, cls in enumerate(classes):
                if cls == pred_val or str(cls) == str(pred_val):
                    return round(float(proba_row[idx]) * 100, 2)

            # 2) Semantic binary match (e.g. classes are "0"/"1" but pred is int)
            pred_sem = to_binary_semantic(pred_val)
            if pred_sem is not None:
                for idx, cls in enumerate(classes):
                    if to_binary_semantic(cls) == pred_sem:
                        return round(float(proba_row[idx]) * 100, 2)
    except Exception:
        pass
    return round(float(max(proba_row)) * 100, 2)

def to_binary_semantic(v):
    s = str(v).strip().lower()
    if s in {"1", "phishing", "spam", "high", "true"}:
        return 1
    if s in {"0", "safe", "ham", "low", "false"}:
        return 0
    if "phish" in s or "spam" in s:
        return 1
    if "safe" in s:
        return 0
    return None

def to_prediction_label(v):
    b = to_binary_semantic(v)
    if b == 1:
        return "Phishing"
    if b == 0:
        return "Safe"
    return str(v)

def derive_label_from_level(level: str, label_mode: str = "medium_high") -> int:
    lvl = str(level or "").strip().lower()
    mode = str(label_mode or "medium_high").strip().lower()
    if mode == "medium_high":
        return 1 if lvl in {"medium", "high", "phishing"} else 0
    return 1 if lvl in {"high", "phishing"} else 0

def sanitize_text_for_ml(text: str) -> str:
    """
    Normalize noisy email text (HTML, URLs, symbols) to improve vectorizer coverage.
    """
    text = str(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\\S+|www\\.\\S+", " ", text)
    text = re.sub(r"[^A-Za-z0-9\\s]", " ", text)
    text = re.sub(r"\\s+", " ", text).strip().lower()
    return text

def sanitize_text_for_nlu(text: str) -> str:
    """
    NLU-focused normalization that preserves raw URL evidence and URL-derived tokens.
    """
    text = str(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower()

    raw_urls = re.findall(r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", text, flags=re.IGNORECASE)
    url_tokens = []
    for raw_url in raw_urls:
        url = raw_url.strip(".,;:!?)]}\"'")
        if not url:
            continue
        url_tokens.append(url)

        domain_match = re.search(r"(?:https?://)?(?:www\.)?([^/\s:?#]+)", url)
        if domain_match:
            domain = domain_match.group(1)
            if domain:
                url_tokens.append("url_domain_" + re.sub(r"[^a-z0-9]+", "_", domain))

        if re.search(r"\b(?:bit\.ly|tinyurl(?:\.com)?|t\.co|goo\.gl|ow\.ly)\b", url):
            url_tokens.append("url_shortener")

        if re.search(r"(?:\d{1,3}\.){3}\d{1,3}", url):
            url_tokens.append("url_ip_host")

    # Keep URL separator chars for intent patterns like link paths and query markers.
    text = re.sub(r"[^a-z0-9\s:/\.\-_?=&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if url_tokens:
        text = f"{text} {' '.join(url_tokens)}".strip()
    return re.sub(r"\s+", " ", text)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)

def _compute_binary_accuracy(y_true, y_pred) -> float:
    pairs = []
    for t, p in zip(y_true, y_pred):
        tb = to_binary_semantic(t)
        pb = to_binary_semantic(p)
        if tb is None or pb is None:
            continue
        pairs.append((tb, pb))
    if not pairs:
        return None
    correct = sum(1 for t, p in pairs if t == p)
    return round((correct / len(pairs)) * 100, 2)

def _extract_nlu_metadata(raw_text: str, normalized_text: str):
    raw = str(raw_text or "")
    t = str(normalized_text or "")
    urls = re.findall(r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", raw, flags=re.IGNORECASE)

    domains = []
    shorteners = 0
    ip_host = 0
    for raw_url in urls:
        url = raw_url.strip(".,;:!?)]}\"'")
        if not url:
            continue
        d = re.search(r"(?:https?://)?(?:www\.)?([^/\s:?#]+)", url, flags=re.IGNORECASE)
        if d:
            domains.append(d.group(1).lower())
        if re.search(r"\b(?:bit\.ly|tinyurl(?:\.com)?|t\.co|goo\.gl|ow\.ly)\b", url, flags=re.IGNORECASE):
            shorteners += 1
        if re.search(r"(?:\d{1,3}\.){3}\d{1,3}", url):
            ip_host += 1

    tokens = re.findall(r"\b[a-z0-9]+\b", t)
    total_tokens = len(tokens) if tokens else 1
    money_markers = len(re.findall(r"(?:\b(?:usd|inr|rs|dollar|payment|refund|invoice|billing)\b|\$\d+)", t))
    cta_markers = len(re.findall(r"\b(?:click|open|visit|tap|verify|reset|confirm|update|login|claim|pay)\b", t))

    uppercase_chars = sum(1 for c in raw if c.isalpha() and c.isupper())
    alpha_chars = sum(1 for c in raw if c.isalpha())
    digit_chars = sum(1 for c in raw if c.isdigit())
    non_space_chars = sum(1 for c in raw if not c.isspace())

    return {
        "url_count": len(urls),
        "domains": sorted(set(domains))[:8],
        "shortener_count": shorteners,
        "ip_host_count": ip_host,
        "money_markers": money_markers,
        "cta_markers": cta_markers,
        "token_count": total_tokens,
        "uppercase_ratio": round((uppercase_chars / alpha_chars), 4) if alpha_chars else 0.0,
        "digit_ratio": round((digit_chars / non_space_chars), 4) if non_space_chars else 0.0,
        "exclamation_count": raw.count("!"),
    }

def _transformer_nlu_inference(text: str):
    """
    Optional transformer NLU (local/cached models only). Safe fallback when unavailable.
    """
    if not _env_bool("ENABLE_TRANSFORMER_NLU", False):
        return {"enabled": False, "available": False, "reason": "disabled"}

    try:
        import importlib.util
        backend_available = any(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "tensorflow", "flax")
        )
    except Exception:
        backend_available = False

    if not backend_available:
        return {
            "enabled": True,
            "available": False,
            "reason": "No PyTorch/TensorFlow/Flax backend installed",
        }

    model_name = os.getenv("TRANSFORMER_NLU_MODEL", "facebook/bart-large-mnli")
    labels = [
        "credential theft",
        "payment fraud",
        "account takeover",
        "social engineering",
        "benign message",
    ]

    try:
        if "zero_shot" not in _TRANSFORMER_PIPELINES:
            from transformers import pipeline
            _TRANSFORMER_PIPELINES["zero_shot"] = pipeline(
                "zero-shot-classification",
                model=model_name,
                tokenizer=model_name,
                model_kwargs={"local_files_only": True},
            )
        classifier = _TRANSFORMER_PIPELINES["zero_shot"]
        out = classifier(text[:3000], labels, multi_label=True)
        top = []
        for lbl, score in zip(out.get("labels", []), out.get("scores", [])):
            top.append({"label": lbl, "score": round(float(score), 4)})
        top = sorted(top, key=lambda x: x["score"], reverse=True)[:4]
        return {
            "enabled": True,
            "available": True,
            "model": model_name,
            "intents": top,
        }
    except Exception as e:
        return {"enabled": True, "available": False, "reason": str(e)}

def phishing_probability_pct(trainer, proba_row):
    """
    Return phishing probability percentage when class mapping is available.
    Falls back to max probability if mapping is unknown.
    """
    try:
        classes = list(getattr(trainer.model, "classes_", []))
        if classes and len(classes) == len(proba_row):
            for idx, cls in enumerate(classes):
                if to_binary_semantic(cls) == 1:
                    return round(float(proba_row[idx]) * 100, 2)
    except Exception:
        pass
    return round(float(max(proba_row)) * 100, 2)

def analyze_message_nlu(text: str):
    """
    Lightweight NLU-style analysis for major phishing tracking signals.
    This complements keyword scoring with intent/entity pattern co-occurrence.
    """
    raw_text = str(text or "")
    t = sanitize_text_for_nlu(raw_text)
    if not t:
        return {"risk_score": 0.0, "signals": [], "metadata": {}, "transformer": {"enabled": False, "available": False}}

    # Intent/entity pattern groups (major tracking dimensions)
    trackers = [
        {
            "name": "Credential Harvesting Intent",
            "weight": 0.22,
            "patterns": [
                r"\bverify\b.*\b(account|identity|login)\b",
                r"\breset\b.*\b(password|pin)\b",
                r"\bconfirm\b.*\b(?:details|credentials)\b",
                r"\benter\b.*\b(?:otp|pin|password)\b",
            ],
        },
        {
            "name": "Urgency Pressure",
            "weight": 0.16,
            "patterns": [
                r"\b(immediately|urgent|final notice|act now|within \d+ (minutes|hours))\b",
                r"\bexpires?\b.*\b(today|soon|now)\b",
            ],
        },
        {
            "name": "Financial Manipulation",
            "weight": 0.18,
            "patterns": [
                r"\b(payment|invoice|refund|transaction|billing)\b",
                r"(?:rs|inr|usd|\$)\s?\d+",
                r"\b(?:card|bank|upi|wallet)\b.*\b(?:update|verify|failed)\b",
            ],
        },
        {
            "name": "Account Security Narrative",
            "weight": 0.14,
            "patterns": [
                r"\b(account|profile)\b.*\b(suspended|locked|restricted|blocked)\b",
                r"\b(unusual|suspicious)\b.*\b(activity|login)\b",
                r"\bsecurity alert\b",
            ],
        },
        {
            "name": "Reward/Lure Narrative",
            "weight": 0.12,
            "patterns": [
                r"\b(congratulations|winner|won|prize|gift)\b",
                r"\bclaim\b.*\b(?:now|reward|bonus)\b",
            ],
        },
        {
            "name": "Link Action Trigger",
            "weight": 0.18,
            "patterns": [
                r"\b(?:click|open|visit|tap)\b.*\b(?:link|url|here|portal)\b",
                r"https?://",
                r"\b(?:bit\.ly|tinyurl(?:\.com)?|t\.co|goo\.gl|ow\.ly)\b",
            ],
        },
    ]

    signals = []
    cumulative = 0.0
    for tr in trackers:
        hits = 0
        for pat in tr["patterns"]:
            if re.search(pat, t):
                hits += 1
        if hits > 0:
            # Saturating score so many hits in one intent do not dominate.
            strength = min(1.0, 0.45 + 0.25 * hits)
            impact = round(tr["weight"] * strength, 4)
            cumulative += impact
            signals.append({
                "name": tr["name"],
                "hits": hits,
                "impact": impact,
            })

    signals.sort(key=lambda x: x["impact"], reverse=True)
    metadata = _extract_nlu_metadata(raw_text, t)
    transformer = _transformer_nlu_inference(raw_text)
    return {
        "risk_score": round(min(1.0, cumulative), 4),
        "signals": signals[:6],
        "metadata": metadata,
        "transformer": transformer,
    }

def metadata_first_score(nlu_summary: dict, rule_score: float = None) -> float:
    """
    Convert NLU metadata + optional rule score into a metadata-first phishing risk.
    """
    nlu = nlu_summary or {}
    score = float(nlu.get("risk_score", 0.0))
    md = nlu.get("metadata", {}) or {}
    tf = nlu.get("transformer", {}) or {}

    if int(md.get("shortener_count", 0)) > 0:
        score += 0.08
    if int(md.get("ip_host_count", 0)) > 0:
        score += 0.08
    if int(md.get("money_markers", 0)) >= 2:
        score += 0.05
    if int(md.get("cta_markers", 0)) >= 2:
        score += 0.05
    if float(md.get("uppercase_ratio", 0.0)) >= 0.35:
        score += 0.03
    if int(md.get("exclamation_count", 0)) >= 2:
        score += 0.03

    if isinstance(rule_score, (int, float)):
        score += max(0.0, min(0.2, (float(rule_score) / 100.0) * 0.15))

    # If transformer is available, fold in suspicious intent confidence.
    if tf.get("available") and tf.get("intents"):
        suspicious = []
        for intent in tf.get("intents", []):
            lbl = str(intent.get("label", "")).lower()
            val = float(intent.get("score", 0.0))
            if lbl != "benign message":
                suspicious.append(val)
        if suspicious:
            score += 0.15 * max(suspicious)

    return round(min(1.0, max(0.0, score)), 4)

def _safe_pct(part, total):
    if not total:
        return 0.0
    return round((float(part) / float(total)) * 100.0, 2)

def _prediction_to_binary(prediction):
    return 1 if to_binary_semantic(prediction) == 1 else 0

def _confusion_from_binary(y_true, y_pred):
    tp = fp = tn = fn = 0
    for truth, pred in zip(y_true, y_pred):
        truth = int(truth)
        pred = int(pred)
        if truth == 1 and pred == 1:
            tp += 1
        elif truth == 0 and pred == 1:
            fp += 1
        elif truth == 0 and pred == 0:
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

def build_data_proof_context(user_email: str, emails, label_mode: str = "medium_high"):
    labels = [derive_label_from_level(e.get("level"), label_mode=label_mode) for e in emails]
    texts_raw = [f"{e.get('subject', '')} {e.get('content', '')}".strip() for e in emails]
    texts_ml = [sanitize_text_for_ml(t) or t for t in texts_raw]

    trainer = LiveTrainer(user_email)
    with redirect_stdout(io.StringIO()):
        trainer.train_user(texts_ml, labels)
        raw_preds, _raw_probas = trainer.predict_with_proba(texts_ml)
    raw_binary = [_prediction_to_binary(v) for v in raw_preds]
    raw_accuracy = _compute_binary_accuracy(labels, raw_binary)

    metadata_report = _load_saved_metadata_report(user_email)
    should_train_metadata = (
        _env_bool("DATA_PROOF_TRAIN_METADATA_ON_REQUEST", False)
        or metadata_report is None
    )
    if should_train_metadata and train_and_report_metadata_models:
        try:
            with redirect_stdout(io.StringIO()):
                metadata_report = train_and_report_metadata_models(user_email, emails, label_mode=label_mode)
        except Exception as metadata_err:
            print(f"[DATA PROOF] metadata training failed: {metadata_err}")

    metadata_scores = []
    meta_ensemble_scores = []
    baseline_branch_scores = []
    metadata_branch_scores = []
    nlu_scores = []
    metadata_vectors = []

    for email, raw_text in zip(emails, texts_raw):
        nlu_summary = email.get("nlu_summary") or analyze_message_nlu(raw_text)
        nlu_scores.append(round(float(nlu_summary.get("risk_score", 0.0)), 4))

        metadata_score = float(email.get("metadata_score", metadata_first_score(nlu_summary, rule_score=email.get("score", 0))))
        metadata_scores.append(round(metadata_score, 4))

        if metadata_sanitize_text and metadata_extract_features:
            try:
                normalized = metadata_sanitize_text(raw_text)
                metadata_vectors.append(metadata_extract_features(raw_text, normalized))
            except Exception:
                pass

        branch = {}
        if predict_meta_ensemble_risk:
            try:
                branch = predict_meta_ensemble_risk(user_email, raw_text) or {}
            except Exception:
                branch = {}
        baseline_branch_scores.append(float(branch.get("baseline_prob", 0.0)))
        metadata_branch_scores.append(float(branch.get("metadata_prob", 0.0)))
        meta_ensemble_scores.append(float(branch.get("ensemble_prob", metadata_score)))

    metadata_pred_binary = [1 if score >= 0.5 else 0 for score in metadata_scores]
    metadata_accuracy = _compute_binary_accuracy(labels, metadata_pred_binary)
    ensemble_pred_binary = [1 if score >= 0.5 else 0 for score in meta_ensemble_scores]
    ensemble_accuracy = _compute_binary_accuracy(labels, ensemble_pred_binary)
    deltas_metadata = [round(metadata - raw, 4) for raw, metadata in zip(nlu_scores, metadata_scores)]
    deltas_ensemble = [round(ensemble - metadata, 4) for ensemble, metadata in zip(meta_ensemble_scores, metadata_scores)]

    url_count_total = 0
    shortener_total = 0
    ip_host_total = 0
    money_total = 0
    cta_total = 0
    uppercase_total = 0.0
    digit_total = 0.0
    if metadata_vectors:
        for vector in metadata_vectors:
            if len(vector) >= 9:
                url_count_total += vector[0]
                shortener_total += vector[1]
                ip_host_total += vector[2]
                money_total += vector[3]
                cta_total += vector[4]
                uppercase_total += vector[6]
                digit_total += vector[7]

    signal_counts = Counter()
    for email, raw_text in zip(emails, texts_raw):
        nlu_summary = email.get("nlu_summary") or analyze_message_nlu(raw_text)
        for signal in nlu_summary.get("signals", []):
            signal_counts[signal.get("name", "Unknown")] += signal.get("hits", 0)

    changed_to_medium = sum(1 for e in emails if str(e.get("metadata_level", "")).lower() == "medium")
    changed_to_high = sum(1 for e in emails if str(e.get("metadata_level", "")).lower() == "high")
    has_meta_learning = sum(1 for e in emails if e.get("meta_learning_score") is not None)
    xai_direction_counts = Counter()
    xai_token_counts = Counter()
    xai_direction_impact = {"phishing": [], "safe": [], "other": []}

    if XAIExplainer:
        try:
            with redirect_stdout(io.StringIO()):
                xai_explainer = XAIExplainer(user_email)
            for email in emails:
                content = str(email.get("content", ""))
                if not content:
                    continue
                try:
                    with redirect_stdout(io.StringIO()):
                        explanations = xai_explainer.explain_text(content, top_k=6)
                except Exception:
                    explanations = []
                for explanation in explanations:
                    direction = str(explanation.get("direction", "other")).lower()
                    if direction not in {"phishing", "safe"}:
                        direction = "other"
                    token = str(explanation.get("token", "")).strip()
                    impact = float(explanation.get("impact", 0.0))
                    xai_direction_counts[direction] += 1
                    if token:
                        xai_token_counts[token] += 1
                    xai_direction_impact[direction].append(impact)
        except Exception as xai_proof_err:
            print(f"[DATA PROOF] xai aggregation failed: {xai_proof_err}")

    methodology_steps = [
        "Receive raw Gmail email payloads from the inbox route.",
        "Normalize text for raw ML without metadata conversion.",
        "Train the text-only LiveTrainer on current inbox labels.",
        "Extract NLU metadata features including URLs, CTA markers, and financial cues.",
        "Train metadata and meta-learner models on the same live inbox set.",
        "Compare raw, metadata, and ensemble predictions against live labels.",
    ]

    live_accuracy_reasons = [
        "We do not rely on a single live classifier. The project compares raw text ML, metadata scoring, and the stacked meta learner on the same inbox emails.",
        "Incoming emails are labeled consistently using the active live label mode, which avoids training skips from single-class inbox snapshots.",
        "Metadata conversion preserves high-signal live artifacts such as URLs, shorteners, CTA pressure, account language, and financial cues that plain text models often miss.",
        "Meta learning combines the baseline text probability and metadata-model probability, which stabilizes performance on noisy live inbox data.",
        "The proof page recalculates metrics from the current received emails, so the graphs show what happened on the live dataset rather than a static benchmark.",
    ]

    glossary = [
        {"term": "Raw Accuracy", "meaning": "Accuracy from the text-only LiveTrainer without metadata conversion."},
        {"term": "Metadata Accuracy", "meaning": "Accuracy from thresholding the converted metadata scores generated from live emails."},
        {"term": "Meta Learner", "meaning": "A stacked model that learns from baseline and metadata model probabilities together."},
        {"term": "NLU Score", "meaning": "Intent-pattern risk score from message language such as urgency, credential theft, and link triggers."},
        {"term": "Metadata Score", "meaning": "Combined risk score built from NLU signals, URL patterns, CTA markers, and other engineered live features."},
        {"term": "Sparse Weightage", "meaning": "How many learned model weights are active versus zero, plus L1/L2 strength summaries."},
        {"term": "Label Mode", "meaning": "Rule used to convert live inbox levels into phishing labels, such as medium/high or strict high only."},
    ]

    metadata_types = [
        "Structural metadata: URL count, shorteners, IP-host URLs, token volume.",
        "Behavioral metadata: CTA markers such as click, verify, login, reset, claim, and pay.",
        "Financial metadata: invoice, payment, refund, billing, money symbols, and transaction terms.",
        "Security narrative metadata: account lock, unusual activity, identity confirmation, and password reset language.",
        "Stylistic metadata: uppercase ratio, digit ratio, and exclamation intensity.",
        "Semantic metadata: optional transformer intent scores for credential theft, payment fraud, account takeover, and social engineering.",
    ]

    methodology_explanation = [
        "We evaluate the same live inbox emails through multiple representations rather than trusting one model path.",
        "Raw text is normalized for the baseline ML model so we can measure plain-text performance directly.",
        "Metadata conversion preserves signals that raw text models usually underuse in live inbox data, especially links and action pressure.",
        "The metadata model learns from a joint feature space: TF-IDF text plus engineered metadata vectors.",
        "The meta learner then learns how to combine baseline and metadata probabilities into a stronger final decision.",
        "All proof metrics are recalculated from current received emails, so the analytics page remains dynamic as new data arrives.",
    ]

    learning_process = [
        "Label live emails using the configured label mode so the pipeline can train on current inbox state.",
        "Train the text-only LiveTrainer on normalized raw text.",
        "Convert the same live emails into metadata-aware text and engineered feature vectors.",
        "Train the metadata model on the fused sparse+dense feature space.",
        "Train the meta learner stacker on baseline and metadata branch probabilities.",
        "Compare branch outputs, generate proof metrics, and store reports for reproducibility.",
    ]

    patterns_used = [
        "Credential harvesting intent patterns",
        "Urgency and deadline pressure patterns",
        "Financial manipulation and payment patterns",
        "Account security narrative patterns",
        "Reward or lure narrative patterns",
        "Link action trigger patterns",
        "URL shortener and IP-host patterns",
        "Capitalization, digit density, and punctuation pressure patterns",
    ]

    pipeline_steps = [
        "Raw Email -> Rule Score -> NLU Summary",
        "NLU Summary -> Metadata Score -> Metadata Level",
        "Raw Text -> LiveTrainer -> Raw Accuracy",
        "Metadata Features -> Metadata Trainer -> Metadata Accuracy",
        "Baseline + Metadata Probabilities -> Meta Learner -> Ensemble Accuracy",
        "Reports -> JSON/MD artifacts for dynamic proof page",
    ]

    return {
        "sample_count": len(emails),
        "label_mode": label_mode,
        "raw_accuracy": raw_accuracy or 0.0,
        "metadata_accuracy": metadata_accuracy or 0.0,
        "ensemble_accuracy": ensemble_accuracy or 0.0,
        "report_metadata_accuracy": (metadata_report or {}).get("metadata_accuracy"),
        "report_meta_learner_accuracy": (metadata_report or {}).get("meta_learner_accuracy"),
        "weightage": (metadata_report or {}).get("weightage", {}),
        "class_counts": {
            "safe": int(sum(1 for x in labels if x == 0)),
            "phishing": int(sum(1 for x in labels if x == 1)),
        },
        "state_changes": {
            "metadata_medium": changed_to_medium,
            "metadata_high": changed_to_high,
            "meta_learning_applied": has_meta_learning,
        },
        "metadata_summary": {
            "total_urls": int(url_count_total),
            "shorteners": int(shortener_total),
            "ip_hosts": int(ip_host_total),
            "money_markers": int(money_total),
            "cta_markers": int(cta_total),
            "avg_uppercase_ratio": round((uppercase_total / len(metadata_vectors)), 4) if metadata_vectors else 0.0,
            "avg_digit_ratio": round((digit_total / len(metadata_vectors)), 4) if metadata_vectors else 0.0,
        },
        "patterns": [{"name": k, "hits": v} for k, v in signal_counts.most_common(8)],
        "xai_summary": {
            "direction_counts": {
                "phishing": xai_direction_counts.get("phishing", 0),
                "safe": xai_direction_counts.get("safe", 0),
                "other": xai_direction_counts.get("other", 0),
            },
            "avg_impact": {
                "phishing": round(sum(xai_direction_impact["phishing"]) / len(xai_direction_impact["phishing"]), 4) if xai_direction_impact["phishing"] else 0.0,
                "safe": round(sum(xai_direction_impact["safe"]) / len(xai_direction_impact["safe"]), 4) if xai_direction_impact["safe"] else 0.0,
                "other": round(sum(xai_direction_impact["other"]) / len(xai_direction_impact["other"]), 4) if xai_direction_impact["other"] else 0.0,
            },
            "top_tokens": [{"name": k, "hits": v} for k, v in xai_token_counts.most_common(8)],
        },
        "scores": {
            "raw": raw_binary,
            "raw_probability": [round(float(x), 4) for x in raw_binary],
            "metadata": metadata_scores,
            "ensemble": meta_ensemble_scores,
            "baseline_branch": baseline_branch_scores,
            "metadata_branch": metadata_branch_scores,
            "nlu": nlu_scores,
            "labels": labels,
            "delta_metadata": deltas_metadata,
            "delta_ensemble": deltas_ensemble,
        },
        "confusion": {
            "raw": _confusion_from_binary(labels, raw_binary),
            "metadata": _confusion_from_binary(labels, metadata_pred_binary),
            "ensemble": _confusion_from_binary(labels, ensemble_pred_binary),
        },
        "email_transitions": [
            {
                "index": index + 1,
                "subject": (email.get("subject") or "No Subject")[:90],
                "label": labels[index],
                "nlu_score": nlu_scores[index],
                "metadata_score": metadata_scores[index],
                "ensemble_score": round(meta_ensemble_scores[index], 4),
                "delta_metadata": deltas_metadata[index],
                "delta_ensemble": deltas_ensemble[index],
            }
            for index, email in enumerate(emails)
        ],
        "methodology_steps": methodology_steps,
        "live_accuracy_reasons": live_accuracy_reasons,
        "glossary": glossary,
        "metadata_types": metadata_types,
        "methodology_explanation": methodology_explanation,
        "learning_process": learning_process,
        "patterns_used": patterns_used,
        "pipeline_steps": pipeline_steps,
    }


def get_cached_data_proof_context(user_email: str, emails, label_mode: str = "medium_high"):
    analytics_state = load_analytics_state(user_email)
    proof_state = analytics_state["data_proof"]
    dataset_signature = _dataset_signature(emails, label_mode=label_mode)

    if (
        proof_state.get("dataset_signature") == dataset_signature
        and proof_state.get("label_mode") == label_mode
        and proof_state.get("proof")
    ):
        return proof_state.get("proof")

    proof = build_data_proof_context(user_email, emails, label_mode=label_mode)
    proof_state["dataset_signature"] = dataset_signature
    proof_state["label_mode"] = label_mode
    proof_state["proof"] = proof
    proof_state["last_built_at"] = datetime.utcnow().isoformat() + "Z"
    save_analytics_state(user_email, analytics_state)
    return proof


def get_cached_ml_dashboard_context(user_email: str, emails, label_mode: str = "medium_high"):
    analytics_state = load_analytics_state(user_email)
    ml_state = analytics_state["ml_dashboard"]
    dataset_signature = _dataset_signature(emails, label_mode=label_mode)
    dirty_ids = set(str(v) for v in ml_state.get("dirty_ids", []))

    if (
        ml_state.get("dataset_signature") == dataset_signature
        and ml_state.get("label_mode") == label_mode
        and ml_state.get("summary")
        and not dirty_ids
    ):
        cached = dict(ml_state["summary"])
        cached["class_counts"] = Counter(cached.get("class_counts", {}))
        return cached

    labels = [derive_label_from_level(e.get("level"), label_mode=label_mode) for e in emails]
    texts = [
        sanitize_text_for_ml(f"{e.get('subject', '')} {e.get('content', '')}") or
        f"{e.get('subject', '')} {e.get('content', '')}"
        for e in emails
    ]

    trainer = LiveTrainer(user_email)
    trainer.train_user(texts, labels)

    enable_metadata_first = _env_bool("ENABLE_METADATA_FIRST_SCORING", True)
    metadata_force_threshold = _env_float("METADATA_FORCE_PHISH_THRESHOLD", 0.90)
    metadata_force_max_conf = _env_float("METADATA_FORCE_PHISH_MAX_CONF", 80.0)
    enable_fused_risk = _env_bool("ENABLE_FUSED_RISK", False)
    alpha = max(0.0, _env_float("FUSED_RISK_ALPHA", 0.7))
    beta = max(0.0, _env_float("FUSED_RISK_BETA", 0.3))
    if alpha + beta == 0:
        alpha, beta = 0.7, 0.3
    weight_sum = alpha + beta
    alpha = alpha / weight_sum
    beta = beta / weight_sum

    metadata_report = _load_saved_metadata_report(user_email)
    should_train_metadata = (
        _env_bool("ML_DASHBOARD_TRAIN_METADATA_ON_REQUEST", False)
        or metadata_report is None
    )
    if should_train_metadata and _env_bool("AUTO_TRAIN_METADATA_ARTIFACTS", True) and train_and_report_metadata_models:
        try:
            metadata_report = train_and_report_metadata_models(
                user_email,
                emails,
                label_mode=label_mode,
            )
        except Exception as mt_err:
            print(f"[METADATA TRAIN WARNING] {mt_err}")

    preds, probas = trainer.predict_with_proba(texts)
    baseline_preds = None
    baseline_accuracy = None
    model_accuracy = None
    enhanced_accuracy = None

    base_model_file = "ML_model/base_model.pkl"
    base_vectorizer_file = "ML_model/base_vectorizer.pkl"
    if os.path.exists(base_model_file) and os.path.exists(base_vectorizer_file):
        try:
            base_model = safe_load_pickle(base_model_file)
            base_vectorizer = safe_load_pickle(base_vectorizer_file)
            if base_model is not None and base_vectorizer is not None:
                base_X = base_vectorizer.transform(texts)
                baseline_preds = base_model.predict(base_X)
        except Exception as base_eval_err:
            print(f"[BASELINE EVAL WARNING] {base_eval_err}")

    explanations = []
    for text in texts:
        try:
            expl = trainer.explain_text(text)
        except Exception:
            expl = []
        explanations.append(expl)

    xai_explanations = {}
    xai_available = False
    try:
        xai_explainer = XAIExplainer(user_email)
        xai_available = True
    except Exception as xai_err:
        print(f"[XAI WARNING] XAI Explainer initialization failed: {xai_err}")

    if xai_available:
        for i, email in enumerate(emails):
            content = email.get("content", "")
            try:
                xai_expl = xai_explainer.explain_text(content, top_k=8)
                label_now = to_prediction_label(preds[i])
                target_direction = "phishing" if label_now == "Phishing" else "safe"
                filtered = [e for e in xai_expl if e.get("direction") == target_direction]
                xai_explanations[i] = filtered if filtered else xai_expl
            except Exception:
                xai_explanations[i] = []

    results = []
    enhanced_preds = []
    for i, email in enumerate(emails):
        pred_val = preds[i]
        confidence = prediction_confidence_pct(trainer, preds[i], probas[i])
        phishing_conf_pct = phishing_probability_pct(trainer, probas[i])
        ml_risk = round(min(1.0, max(0.0, phishing_conf_pct / 100.0)), 4)

        pred_label = to_prediction_label(pred_val)
        nlu_summary = email.get("nlu_summary") or analyze_message_nlu(
            f"{email.get('subject', '')} {email.get('content', '')}"
        )
        nlu_risk = round(float(nlu_summary.get("risk_score", 0.0)), 4)
        metadata_pre_score = float(
            email.get("metadata_score", metadata_first_score(nlu_summary, rule_score=email.get("score", 0)))
        )
        if enable_metadata_first:
            nlu_risk = max(nlu_risk, metadata_pre_score)
            if (
                pred_label == "Safe"
                and metadata_pre_score >= metadata_force_threshold
                and float(confidence) <= metadata_force_max_conf
            ):
                pred_label = "Phishing"
        fused_risk = None
        if enable_fused_risk:
            fused_risk = round(min(1.0, max(0.0, (alpha * ml_risk) + (beta * nlu_risk))), 4)
            enhanced_preds.append(1 if fused_risk >= 0.5 else 0)

        results.append({
            "subject": email.get("subject", "No Subject"),
            "content": email.get("content", "No Content"),
            "prediction": pred_label,
            "confidence": confidence,
            "ml_risk": ml_risk,
            "explanations": explanations[i],
            "xai_explanations": xai_explanations.get(i, []),
            "nlu_summary": nlu_summary,
            "nlu_risk": nlu_risk,
            "metadata_pre_score": metadata_pre_score,
            "fused_risk": fused_risk,
        })

    model_accuracy = _compute_binary_accuracy(labels, preds)
    if baseline_preds is not None:
        baseline_accuracy = _compute_binary_accuracy(labels, baseline_preds)
    if enable_fused_risk and enhanced_preds:
        enhanced_accuracy = _compute_binary_accuracy(labels, enhanced_preds)

    class_counts = Counter([r["prediction"] for r in results])
    total = sum(class_counts.values())
    if set(class_counts.keys()) <= {"Safe", "Phishing"}:
        class_percentages = {
            "Safe": round((class_counts.get("Safe", 0) / total) * 100, 2) if total else 0,
            "Phishing": round((class_counts.get("Phishing", 0) / total) * 100, 2) if total else 0,
        }
        is_binary = True
    else:
        class_percentages = {
            cls: round((cnt / total) * 100, 2) for cls, cnt in class_counts.items()
        }
        is_binary = False

    warning_msg = None
    if len(set(labels)) < 2:
        warning_msg = "âš  Fine-tuning skipped (only one class in your emails). Using base model."

    context = {
        "results": results,
        "class_counts": class_counts,
        "class_percentages": class_percentages,
        "total": total,
        "is_binary": is_binary,
        "warning_msg": warning_msg,
        "xai_available": xai_available,
        "model_accuracy": model_accuracy,
        "baseline_accuracy": baseline_accuracy,
        "enhanced_accuracy": enhanced_accuracy,
        "fused_risk_enabled": enable_fused_risk,
        "metadata_first_enabled": enable_metadata_first,
        "metadata_report": metadata_report,
    }

    ml_state["dataset_signature"] = dataset_signature
    ml_state["label_mode"] = label_mode
    ml_state["summary"] = {
        **context,
        "class_counts": dict(class_counts),
    }
    ml_state["dirty_ids"] = []
    ml_state["last_built_at"] = datetime.utcnow().isoformat() + "Z"
    save_analytics_state(user_email, analytics_state)
    return context

# ✅ Allow ML_model imports
sys.path.append("ML_model")

from gmail_client import GmailClient
from phishing_detector import PhishingDetector
try:
    from live_trainer import LiveTrainer
    trainer_available = True
except Exception as e:
    trainer_available = False
    trainer_error = str(e)

app = Flask(__name__)
app.secret_key = "c61da3f20d9b2bde86db02cc0426fd5e9cd4efe58185a7010b9ddb38a527be46"  # ⚠️ Replace with secure secret key
# ---------------- BLUEPRINTS ----------------
try:
    from smsmlmodel import sms_ml_bp
    app.register_blueprint(sms_ml_bp)
except Exception as _bp_err:
    print(f"[WARN] SMS ML blueprint not registered: {_bp_err}")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template("login.html", error="❌ Please provide both email and password.")

        # Load users
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r") as f:
                    users = json.load(f)
            except json.JSONDecodeError:
                users = {}
        else:
            users = {}

        # Validate credentials
        if email in users and check_password_hash(users[email], password):
            session["user_email"] = email

            gmail = GmailClient(email)
            try:
                authenticated = gmail.authenticate()
            except Exception:
                authenticated = False

            if authenticated:
                return redirect(url_for("inbox"))

            if gmail.pending_auth_url and gmail.pending_auth_state:
                session["gmail_oauth_user_email"] = email
                session["gmail_oauth_state"] = gmail.pending_auth_state
                return redirect(gmail.pending_auth_url)

            return render_template("error.html", msg="Authentication failed.")
        else:
            return render_template("login.html", error="❌ Invalid email or password.")

    return render_template("login.html")

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not new_password or not confirm_password:
            return render_template(
                "forgot_password.html",
                error="Please provide email, new password, and confirm password."
            )

        if new_password != confirm_password:
            return render_template("forgot_password.html", error="Passwords do not match.")

        if not is_valid_password(new_password):
            return render_template(
                "forgot_password.html",
                error="Password must be at least 8 characters and include at least one uppercase letter."
            )

        users = load_users()
        if email not in users:
            return render_template("forgot_password.html", error="User not found.")

        users[email] = generate_password_hash(new_password)
        save_users(users)

        # Remove old auth token so user can re-authenticate with updated credentials.
        token_file = _gmail_token_file(email)
        if os.path.exists(token_file):
            os.remove(token_file)

        # If currently logged in as same user, clear session.
        if session.get("user_email") == email:
            session.clear()

        return render_template(
            "forgot_password.html",
            success="Password reset successful. Please login with your new password."
        )

    return render_template("forgot_password.html")

#---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")

        if not email or not password:
            return render_template("signup.html", error="❌ Please provide both email and password.")

        # Ensure users.json exists and load safely
        users = {}
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r") as f:
                    content = f.read().strip()
                    if content:  # file not empty
                        users = json.loads(content)
            except json.JSONDecodeError:
                users = {}

        # 🔹 Debug print (check what's inside users.json)
        print("[DEBUG] Current users:", users)

        # Check if user exists
        if email in users:
            return render_template("signup.html", error="⚠️ User already exists. Please login.")

        # Add new user
        users[email] = generate_password_hash(password)

        # Save back to users.json
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=4)

        print(f"[✔] User {email} saved to {USERS_FILE}")

        return redirect(url_for("login"))

    return render_template("signup.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    user_email = session.get("user_email")
    token_dir = os.getenv("TOKEN_STORAGE_DIR", ".")
    token_cleanup_files = []
    try:
        token_cleanup_files = [
            os.path.join(token_dir, name)
            for name in os.listdir(token_dir)
            if name.startswith("token_") and name.endswith(".pkl")
        ]
    except Exception:
        token_cleanup_files = []

    if user_email:
        # Remove user tokens and model files
        safe_email = user_email.replace("@", "_").replace(".", "_")
        cleanup_files = [
            *token_cleanup_files,
            f"ML_model/model_{safe_email}.pkl",
            f"ML_model/vectorizer_{safe_email}.pkl",
            f"ML_model/emails_{safe_email}.pkl"
        ]
        for path in cleanup_files:
            if os.path.exists(path):
                os.remove(path)
    else:
        for path in token_cleanup_files:
            if os.path.exists(path):
                os.remove(path)

    session.clear()
    return redirect(url_for("login"))

# ---------------- HOME ----------------
@app.route("/")
def home():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("inbox"))

# ---------------- EXPLANATION ----------------

@app.route("/explain/<email_id>")
def explain_email(email_id):
    user_email = session.get("user_email")
    if not user_email:
        return jsonify({"error": "Not logged in"}), 401

    safe_email = user_email.replace("@", "_").replace(".", "_")
    email_file = f"ML_model/emails_{safe_email}.pkl"

    if not os.path.exists(email_file):
        return jsonify({"error": "No emails found"})

    with open(email_file, "rb") as f:
        emails = pickle.load(f)

    email = next((e for e in emails if e["id"] == email_id), None)
    if not email:
        return jsonify({"error": "Email not found"})

    explanation = []

    # 1️⃣ Rule-based explanations
    RULE_CONFIDENCE = {
    "otp": 85,
    "verify": 80,
    "urgent": 75,
    "account": 70,
    "password": 90,
    "login": 85,
    "bank": 90,
    "click": 80,
    "link": 75,
    "payment": 85,
    "suspend": 88,
    }

    for t in email.get("threats", []):
        score = RULE_CONFIDENCE.get(t.lower(), 65)

        explanation.append({
            "token": t,
            "impact": score,
            "direction": "phishing"
        })


    # 2️⃣ SHAP explanation
    try:
        xai = XAIExplainer(user_email)
        shap_items = xai.explain_text(email["content"])
        explanation.extend(shap_items)
    except Exception as e:
        print("[XAI ERROR]", e)

    return jsonify({
        "explanation": explanation
    })


# ---------------- INBOX ----------------
@app.route("/inbox")
def inbox():
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    gmail = GmailClient(user_email)

    try:
        authenticated = gmail.authenticate()
    except Exception:
        authenticated = False

    if not authenticated:
        if gmail.pending_auth_url and gmail.pending_auth_state:
            session["gmail_oauth_user_email"] = user_email
            session["gmail_oauth_state"] = gmail.pending_auth_state
            return redirect(gmail.pending_auth_url)
        return render_template("error.html", msg="Authentication failed.")

    state = load_inbox_state(user_email)
    metadata_label_mode = os.getenv("METADATA_LABEL_MODE", "medium_high")
    processed, training_state, agent_metrics = _run_inbox_agentic_loop(
        gmail,
        user_email,
        state,
        limit=20,
        chunk_size=5,
    )

    trained_now = False
    if _env_bool("AUTO_TRAIN_METADATA_ARTIFACTS", True):
        training_state, trained_now = _train_pending_inbox_models(
            user_email,
            processed,
            training_state,
            metadata_label_mode,
        )
    else:
        _mark_analytics_dirty(user_email, training_state.get("pending_ids", []))

    print(
        "[INBOX AGENT] refs=%s fetched_new=%s reused=%s pending=%s trained_now=%s"
        % (
            agent_metrics.get("fetched_ref_count", 0),
            agent_metrics.get("fetched_full_count", 0),
            agent_metrics.get("reused_count", 0),
            len(training_state.get("pending_ids", [])),
            trained_now,
        )
    )

    state["emails"] = processed
    state["training"] = training_state
    try:
        save_inbox_state(user_email, state)
    except Exception as e:
        print("[INBOX STATE SAVE ERROR]", e)

    email_file = _emails_file(user_email)
    try:
        with open(email_file, "wb") as f:
            pickle.dump(processed, f)
    except Exception as e:
        print("[SAVE ERROR]", e)

    email_columns, stats, _all_labels = _build_inbox_stats(processed, metadata_label_mode)

    session.pop("last_emails", None)
    session.pop("last_labels", None)

    return render_template("inbox.html", emails=processed, email_columns=email_columns, stats=stats)


@app.route("/gmail_oauth_callback")
def gmail_oauth_callback():
    user_email = session.get("gmail_oauth_user_email") or session.get("user_email")
    expected_state = session.get("gmail_oauth_state")
    callback_state = request.args.get("state")

    if not user_email or not expected_state or not callback_state:
        return render_template("error.html", msg="Missing Gmail OAuth session state.")

    if callback_state != expected_state:
        return render_template("error.html", msg="Invalid Gmail OAuth state.")

    gmail = GmailClient(user_email)
    try:
        gmail.complete_auth(expected_state, request.url)
    except Exception as e:
        return render_template("error.html", msg=f"Gmail OAuth callback failed: {e}")

    session["user_email"] = user_email
    session.pop("gmail_oauth_user_email", None)
    session.pop("gmail_oauth_state", None)
    return redirect(url_for("inbox"))

# ---------------- ML DASHBOARD ----------------
@app.route("/ml_dashboard")
def ml_dashboard():
    if not trainer_available:
        return render_template("error.html", msg=f"ML Trainer not available: {trainer_error}")

    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")
    email_file = f"ML_model/emails_{safe_email}.pkl"
    metadata_label_mode = os.getenv("METADATA_LABEL_MODE", "medium_high")

    emails = []
    if os.path.exists(email_file):
        try:
            with open(email_file, "rb") as f:
                emails = pickle.load(f)
        except Exception as e:
            return render_template("error.html", msg=f"Failed to load emails from PKL: {e}")

    if not emails:
        return render_template("error.html", msg="No emails found for ML training.")

    try:
        context = get_cached_ml_dashboard_context(user_email, emails, label_mode=metadata_label_mode)
        return render_template("ml_dashboard.html", **context)
    except Exception as e:
        return render_template("error.html", msg=f"ML Prediction failed: {e}")

@app.route("/data_proof")
def data_proof():
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")
    email_file = f"ML_model/emails_{safe_email}.pkl"
    metadata_label_mode = os.getenv("METADATA_LABEL_MODE", "medium_high")

    emails = []
    if os.path.exists(email_file):
        try:
            with open(email_file, "rb") as f:
                emails = pickle.load(f)
        except Exception as e:
            return render_template("error.html", msg=f"Failed to load emails for data proof: {e}")

    if not emails:
        return render_template("error.html", msg="No emails available for dynamic proof analytics.")

    try:
        proof = get_cached_data_proof_context(user_email, emails, label_mode=metadata_label_mode)
        return render_template(
            "data_proof.html",
            proof=proof,
            emails=emails,
            total=len(emails),
        )
    except Exception as e:
        return render_template("error.html", msg=f"Failed to generate proof analytics: {e}")

@app.route("/data_proof_explained")
def data_proof_explained():
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")
    email_file = f"ML_model/emails_{safe_email}.pkl"
    metadata_label_mode = os.getenv("METADATA_LABEL_MODE", "medium_high")

    emails = []
    if os.path.exists(email_file):
        try:
            with open(email_file, "rb") as f:
                emails = pickle.load(f)
        except Exception as e:
            return render_template("error.html", msg=f"Failed to load emails for explanation page: {e}")

    if not emails:
        return render_template("error.html", msg="No emails available for detailed explanation.")

    try:
        proof = get_cached_data_proof_context(user_email, emails, label_mode=metadata_label_mode)
        explanation_cards = [
            {
                "title": "What This Project Does",
                "points": [
                    "This system checks real incoming emails and decides whether they look safe or risky.",
                    "It does not depend on one method only. It combines rule checks, machine learning, metadata analysis, and explainable reasoning.",
                    "The project also shows why a message was considered risky, not only the final label.",
                ],
            },
            {
                "title": "How The Comparison Works",
                "points": [
                    "The same live email set is tested in more than one way.",
                    "First, the raw text is used by the text-only model.",
                    "Then the same emails are converted into metadata-aware form, where links, action words, money cues, and message style are measured.",
                    "Finally, a combined learner uses both branches together to make a stronger decision.",
                ],
            },
            {
                "title": "What Changed After Metadata Conversion",
                "points": [
                    f"Live emails contained {proof['metadata_summary']['total_urls']} URL signals and {proof['metadata_summary']['shorteners']} shortener signals in the current dataset.",
                    f"The project detected {proof['metadata_summary']['money_markers']} financial markers and {proof['metadata_summary']['cta_markers']} call-to-action markers.",
                    f"Metadata conversion moved {proof['state_changes']['metadata_medium']} emails into medium-risk state and {proof['state_changes']['metadata_high']} into high-risk state.",
                ],
            },
            {
                "title": "Why Accuracy Improves",
                "points": [
                    f"Raw text accuracy on the current live set is {proof['raw_accuracy']} percent.",
                    f"Metadata-aware accuracy on the same live set is {proof['metadata_accuracy']} percent.",
                    f"The stacked combined learner reaches {proof['ensemble_accuracy']} percent on the same data.",
                    "This happens because metadata captures behavior and structure that plain text alone can miss.",
                ],
            },
            {
                "title": "How The Project Learns",
                "points": proof["learning_process"],
            },
            {
                "title": "Patterns And Events Tracked",
                "points": proof["patterns_used"],
            },
            {
                "title": "Explainable Analysis In Simple Words",
                "points": [
                    "The explainable layer highlights words or patterns that pushed the decision toward risk or safety.",
                    "The graph on the proof page summarizes how many explainable states leaned toward phishing and how strong those impacts were.",
                    "This helps the user understand what the system noticed in live emails.",
                ],
            },
            {
                "title": "Architecture In Easy Words",
                "points": [
                    "Email enters through Gmail integration.",
                    "Rule logic and pattern analysis score it immediately.",
                    "The email is stored, routed into inbox columns, and passed to learning models.",
                    "Raw learning, metadata learning, and the stacked learner are compared together.",
                    "The dashboards then show the result, explanation, and proof charts.",
                ],
            },
        ]

        return render_template(
            "data_proof_explained.html",
            proof=proof,
            explanation_cards=explanation_cards,
        )
    except Exception as e:
        return render_template("error.html", msg=f"Failed to build detailed explanation page: {e}")
    
# ---------------- SMS RECIEVER ----------------
@app.route("/sms_dashboard")
def sms_dashboard():
    """Display generated SMS with ML predictions and XAI explanations"""
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))
    
    sms_file = "ML_model/sms_incoming.pkl"
    sms_data = []

    if os.path.exists(sms_file):
        try:
            with open(sms_file, "rb") as f:
                raw_sms = pickle.load(f)

            # Process each SMS with ML prediction and XAI only when fields are missing.
            trainer = None
            xai_explainer = None
            try:
                trainer = LiveTrainer(user_email)
                xai_available = _env_bool("SMS_XAI_ON_READ", False)
                if xai_available:
                    xai_explainer = XAIExplainer(user_email)
            except Exception as e:
                print(f"[XAI] Failed to init: {e}")
                xai_available = False

            for i, sms in enumerate(raw_sms):
                # Normalize basic fields
                sms_normalized = {
                    "sender": sms.get("sender", "Unknown"),
                    "content": sms.get("content", ""),
                    "timestamp": sms.get("timestamp", ""),
                    "ml_prediction": sms.get("ml_prediction", "Pending"),
                    "confidence": sms.get("confidence", 0),
                    "xai_explanations": sms.get("xai_explanations", []),
                }

                if "ml_prediction" in sms and "confidence" in sms:
                    sms_data.append(sms_normalized)
                    continue

                try:
                    text = sms.get("content", "")
                    preds, probas = trainer.predict_with_proba([text])
                    
                    pred_label = "Spam" if preds[0] == 1 else "Safe"
                    confidence = prediction_confidence_pct(trainer, preds[0], probas[0])
                    
                    sms_normalized["ml_prediction"] = pred_label
                    sms_normalized["confidence"] = confidence
                    
                    # Get XAI explanations for spam SMS
                    xai_expl = []
                    if xai_available and pred_label == "Spam":
                        try:
                            xai_expl = xai_explainer.explain_text(text, top_k=5)
                            print(f"[SMS] SMS {i}: Got {len(xai_expl)} XAI explanations")
                        except Exception as xai_err:
                            print(f"[SMS] SMS {i}: XAI error - {xai_err}")
                    
                    sms_normalized["xai_explanations"] = xai_expl
                    sms["ml_prediction"] = sms_normalized["ml_prediction"]
                    sms["confidence"] = sms_normalized["confidence"]
                    sms["xai_explanations"] = sms_normalized["xai_explanations"]
                    
                except Exception as e:
                    print(f"[SMS] Prediction error for SMS {i}: {e}")
                    sms_normalized["ml_prediction"] = "Pending"
                    sms_normalized["confidence"] = 0
                    sms_normalized["xai_explanations"] = []
                
                sms_data.append(sms_normalized)

            with open(sms_file, "wb") as f:
                pickle.dump(raw_sms, f)

        except Exception as e:
            print(f"[SMS] Failed to load SMS data: {e}")
            sms_data = []

    print(f"[SMS] Loaded {len(sms_data)} SMS messages with predictions")

    return render_template(
        "sms_dashboard.html",
        sms_messages=sms_data,
        total_sms=len(sms_data),
        spam_count=sum(1 for s in sms_data if s.get("ml_prediction") == "Spam"),
        safe_count=sum(1 for s in sms_data if s.get("ml_prediction") == "Safe")
    )


@app.route("/api/generate_sms", methods=["POST"])
def api_generate_sms():
    """API endpoint to generate new SMS messages and classify them with ML."""
    user_email = session.get("user_email")
    if not user_email:
        return jsonify({"error": "Not logged in"}), 401

    try:
        data = request.get_json() or {}
        count = int(data.get("count", 10))

        print(f"\n[SMS GEN] Generating {count} SMS messages...")

        generator = SMSGenerator()
        new_sms = generator.generate_sms(count)
        print(f"[SMS GEN] Generated {len(new_sms)} SMS")

        trainer = None
        xai_explainer = None
        try:
            trainer = LiveTrainer(user_email)

            # Warm-start user model with generated labels when available.
            bootstrap_texts = [s.get("content", "") for s in new_sms if s.get("content")]
            bootstrap_labels = [1 if s.get("label") == "High" else 0 for s in new_sms if s.get("content")]
            if bootstrap_texts and len(set(bootstrap_labels)) >= 2:
                try:
                    trainer.train_user(bootstrap_texts, bootstrap_labels)
                except Exception as train_err:
                    print(f"[SMS GEN] Training warm-start skipped: {train_err}")

            xai_explainer = XAIExplainer(user_email)
        except Exception as e:
            print(f"[SMS GEN] ML initialization failed: {e}")
            return jsonify({"error": "SMS generated but ML model is unavailable. Train/load model first."}), 500

        result_sms = []
        for i, sms in enumerate(new_sms):
            sms_result = sms.copy()
            try:
                text = sms.get("content", "")
                preds, probas = trainer.predict_with_proba([text])

                sms_result["ml_prediction"] = "Spam" if preds[0] == 1 else "Safe"
                sms_result["confidence"] = prediction_confidence_pct(trainer, preds[0], probas[0])

                if xai_explainer:
                    try:
                        xai_expl = xai_explainer.explain_text(text, top_k=8)
                        if sms_result["ml_prediction"] == "Spam":
                            sms_result["xai_explanations"] = [e for e in xai_expl if e.get("direction") == "phishing"]
                        else:
                            sms_result["xai_explanations"] = [e for e in xai_expl if e.get("direction") == "safe"]
                    except Exception as xai_err:
                        print(f"[SMS GEN XAI] failed for sms {i}: {xai_err}")
                        sms_result["xai_explanations"] = []
                else:
                    sms_result["xai_explanations"] = []

            except Exception as e:
                print(f"[SMS GEN] Error predicting SMS {i}: {e}")
                sms_result["ml_prediction"] = "Pending"
                sms_result["confidence"] = 0
                sms_result["xai_explanations"] = []

            result_sms.append(sms_result)

        sms_file = "ML_model/sms_incoming.pkl"
        with open(sms_file, "wb") as f:
            pickle.dump(result_sms, f)

        print(f"[SMS GEN] Added predictions and saved to {sms_file}")

        return jsonify({
            "success": True,
            "message": f"Generated {count} new SMS",
            "sms_count": len(result_sms),
            "spam_count": sum(1 for s in result_sms if s.get("ml_prediction") == "Spam")
        })

    except Exception as e:
        print(f"[SMS GEN] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ---------------- RECEIVE SMS API ----------------
@app.route("/receive_sms", methods=["POST", "GET"])
def receive_sms():
    if request.method == "GET":
        # 👀 If accessed from browser manually, just redirect to dashboard
        return redirect(url_for("sms_dashboard"))

    data = request.get_json()
    if not data or "content" not in data or "sender" not in data:
        return jsonify({"error": "❌ Invalid SMS data"}), 400

    # Default rule-based "level"
    sms_entry = {
        "sender": data["sender"],
        "content": data["content"],
        "level": "High" if "bank" in data["content"].lower() or "otp" in data["content"].lower() else "Safe"
    }

    sms_file = "ML_model/sms_incoming.pkl"
    sms_data = []
    if os.path.exists(sms_file):
        try:
            with open(sms_file, "rb") as f:
                sms_data = pickle.load(f)
        except:
            sms_data = []

    # ✅ Pass new SMS to ML model
    try:
        user_email = session.get("user_email", "default_user")
        trainer = LiveTrainer(user_email)

        text = sms_entry["content"]

        preds, probas = trainer.predict_with_proba([text])
        pred_val = preds[0]
        confidence = prediction_confidence_pct(trainer, preds[0], probas[0])

        if pred_val == 1:
            label = "Spam"
        elif pred_val == 0:
            label = "Safe"
        else:
            label = str(pred_val)

        # Generate XAI explanations (SHAP) and attach filtered tokens
        try:
            xai_explainer = XAIExplainer(user_email)
            xai_explanations = xai_explainer.explain_text(text, top_k=8)
            if label == "Spam":
                xai_explanations = [e for e in xai_explanations if e.get("direction") == "phishing"]
            else:
                xai_explanations = [e for e in xai_explanations if e.get("direction") == "safe"]
        except Exception as e:
            print(f"[XAI SMS] Explanation failed: {e}")
            xai_explanations = []

        sms_entry["xai_explanations"] = xai_explanations
        sms_entry["ml_prediction"] = label
        sms_entry["confidence"] = confidence

    except Exception as e:
        sms_entry["ml_prediction"] = "⚠️ ML Error"
        sms_entry["confidence"] = 0
        print("[ML ERROR]", e)


    # Save latest SMS (prepend)
    sms_data.insert(0, sms_entry)

    with open(sms_file, "wb") as f:
        pickle.dump(sms_data, f)

    # 📌 If it’s the SMS forwarder calling, return JSON
    if request.is_json:
        return jsonify({"message": "📩 SMS received, saved & classified", "sms": sms_entry}), 200
    else:
        # 📌 If accessed from browser, show the dashboard
        
        return redirect(url_for("sms_dashboard"))


# ---------------- SMS DATA API (JSON) ----------------
@app.route("/sms_data", methods=["GET"])
def sms_data():
    sms_file = "ML_model/sms_incoming.pkl"
    sms_list = []

    if os.path.exists(sms_file):
        try:
            with open(sms_file, "rb") as f:
                sms_list = pickle.load(f) or []
        except Exception:
            sms_list = []

    # Ensure ML fields present; compute when missing
    if trainer_available and sms_list:
        user_email = session.get("user_email", "default_user")
        trainer = LiveTrainer(user_email)

        for sms in sms_list:
            if not isinstance(sms, dict):
                continue
            content = sms.get("content", "")
            if not content:
                sms.setdefault("ml_prediction", "N/A")
                sms.setdefault("confidence", 0)
                sms.setdefault("xai_explanations", [])
                continue

            if "ml_prediction" in sms and "confidence" in sms:
                sms.setdefault("xai_explanations", [])
                continue

            try:
                preds, probas = trainer.predict_with_proba([content])
                pred_val = preds[0]
                confidence = prediction_confidence_pct(trainer, preds[0], probas[0])
                if pred_val == 1:
                    pred_label = "Spam"
                elif pred_val == 0:
                    pred_label = "Safe"
                else:
                    pred_label = str(pred_val)
                sms["ml_prediction"] = pred_label
                sms["confidence"] = confidence

                if _env_bool("SMS_XAI_ON_READ", False):
                    try:
                        xai_explainer = XAIExplainer(user_email)
                        xai_expl = xai_explainer.explain_text(content, top_k=8)
                        if pred_label == "Spam":
                            sms["xai_explanations"] = [e for e in xai_expl if e.get("direction") == "phishing"]
                        else:
                            sms["xai_explanations"] = [e for e in xai_expl if e.get("direction") == "safe"]
                    except Exception as e:
                        print(f"[SMS DATA XAI] {e}")
                        sms["xai_explanations"] = []
                else:
                    sms.setdefault("xai_explanations", [])
            except Exception:
                sms["ml_prediction"] = "⚠️ ML Error"
                sms["confidence"] = 0
                sms["xai_explanations"] = []
        try:
            with open(sms_file, "wb") as f:
                pickle.dump(sms_list, f)
        except Exception:
            pass
    return jsonify(sms_list)

@app.route("/delete_email/<email_id>/<column>", methods=["POST"])
def delete_email(email_id, column):
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    valid_columns = {"primary", "promotions", "social", "purchases"}
    column = (column or "").lower()
    if column not in valid_columns:
        return redirect(url_for("inbox"))

    state = load_inbox_state(user_email)
    emails = state.get("emails", [])
    deleted_ids = {str(eid) for eid in state.get("deleted_ids", [])}
    email_id = str(email_id)

    for idx, email in enumerate(emails):
        if str(email.get("id")) != email_id:
            continue

        if column == "primary":
            emails.pop(idx)
            deleted_ids.add(email_id)
        else:
            current_columns = email.get("columns", [])
            if not isinstance(current_columns, list):
                current_columns = []
            email["columns"] = [c for c in current_columns if c != column]

            excluded = email.get("excluded_columns", [])
            if not isinstance(excluded, list):
                excluded = []
            if column not in excluded:
                excluded.append(column)
            email["excluded_columns"] = excluded
        break

    state["emails"] = emails
    state["deleted_ids"] = list(deleted_ids)

    try:
        save_inbox_state(user_email, state)
    except Exception as e:
        print("[DELETE EMAIL] Failed to save inbox state:", e)

    try:
        with open(_emails_file(user_email), "wb") as f:
            pickle.dump(emails, f)
    except Exception as e:
        print("[DELETE EMAIL] Failed to save emails file:", e)

    return redirect(url_for("inbox"))

@app.route("/mark_spam/<email_id>", methods=["POST"])
def mark_spam(email_id):
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")

    emails_file = f"ML_model/emails_{safe_email}.pkl"
    spam_file = f"ML_model/spam_{safe_email}.pkl"

    if not os.path.exists(emails_file):
        return redirect(url_for("inbox"))

    # Load inbox emails
    try:
        with open(emails_file, "rb") as f:
            emails = pickle.load(f)
    except Exception:
        return redirect(url_for("inbox"))

    # Find selected email
    spam_email = None
    remaining = []

    for e in emails:
        if str(e.get("id")) == str(email_id):
            e["marked_as_spam"] = True
            spam_email = e
        else:
            remaining.append(e)

    if not spam_email:
        return redirect(url_for("inbox"))

    # Save updated inbox (optional)
    with open(emails_file, "wb") as f:
        pickle.dump(remaining, f)

    # Keep inbox state in sync so moved spam does not reappear in inbox columns
    try:
        state = load_inbox_state(user_email)
        state_emails = state.get("emails", [])
        state["emails"] = [e for e in state_emails if str(e.get("id")) != str(email_id)]
        save_inbox_state(user_email, state)
    except Exception as e:
        print("[MARK SPAM] Failed to sync inbox state:", e)

    # Load existing spam list
    spam_list = []
    if os.path.exists(spam_file):
        try:
            with open(spam_file, "rb") as f:
                spam_list = pickle.load(f)
        except:
            spam_list = []

    # Insert newest spam on top
    spam_list.insert(0, spam_email)

    with open(spam_file, "wb") as f:
        pickle.dump(spam_list, f)

    return redirect(url_for("spam_dashboard"))

# ============ XAI EXPLANATION API ============
@app.route("/api/explain_prediction", methods=["POST"])
def api_explain_prediction():
    """
    REST API endpoint for XAI explanations.
    Returns SHAP-based word explanations for phishing detection.
    Does NOT interfere with existing routes.
    """
    user_email = session.get("user_email")
    if not user_email:
        return jsonify({"error": "Not logged in"}), 401

    try:
        data = request.get_json()
        email_content = data.get("content", "")
        
        if not email_content:
            return jsonify({"error": "No email content provided"}), 400

        # Initialize XAI explainer
        explainer = XAIExplainer(user_email)
        
        # Get explanations
        explanations = explainer.explain_text(email_content, top_k=8)
        
        return jsonify({
            "success": True,
            "explanations": explanations
        })
    
    except FileNotFoundError:
        return jsonify({"error": "User model not found. Train model first."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ XAI EXPLANATION API ============

# ---------------- SPAM DASHBOARD ----------------
@app.route("/spam_dashboard")
def spam_dashboard():
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")
    spam_file = f"ML_model/spam_{safe_email}.pkl"

    spam_messages = []

    if os.path.exists(spam_file):
        try:
            with open(spam_file, "rb") as f:
                spam_messages = pickle.load(f)
        except:
            spam_messages = []

    return render_template("spam_dashboard.html", spam_messages=spam_messages)


@app.route("/unmark_spam/<email_id>", methods=["POST"])
def unmark_spam(email_id):
    user_email = session.get("user_email")
    if not user_email:
        return redirect(url_for("login"))

    safe_email = user_email.replace("@", "_").replace(".", "_")
    spam_file = f"ML_model/spam_{safe_email}.pkl"
    emails_file = f"ML_model/emails_{safe_email}.pkl"

    # Load spam list
    spam_list = []
    if os.path.exists(spam_file):
        try:
            with open(spam_file, "rb") as f:
                spam_list = pickle.load(f)
        except Exception:
            spam_list = []

    # Find and remove the email from spam
    removed = None
    for i, e in enumerate(spam_list):
        if str(e.get("id")) == str(email_id):
            removed = spam_list.pop(i)
            break

    # Save updated spam list
    try:
        with open(spam_file, "wb") as f:
            pickle.dump(spam_list, f)
    except Exception as e:
        print("[UNMARK SPAM] Failed to update spam file:", e)

    # If removed, add back to inbox storage (emails file)
    if removed:
        inbox_list = []
        if os.path.exists(emails_file):
            try:
                with open(emails_file, "rb") as f:
                    inbox_list = pickle.load(f)
            except Exception:
                inbox_list = []

        # avoid duplicate ids
        if not any(str(x.get("id")) == str(removed.get("id")) for x in inbox_list):
            inbox_list.insert(0, removed)

        try:
            with open(emails_file, "wb") as f:
                pickle.dump(inbox_list, f)
        except Exception as e:
            print("[UNMARK SPAM] Failed to update emails file:", e)

    return redirect(url_for("spam_dashboard"))

if __name__ == "__main__":
    # 💡 On Windows, watchdog can trigger infinite reloads due to system file access.
    # We disable the reloader but keep debug=True for error pages and interactive debugger.
    debug_enabled = str(os.getenv("APP_DEBUG", "false")).strip().lower() in {"1", "true", "yes", "on"}
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host=host, port=port, debug=debug_enabled, use_reloader=False)







