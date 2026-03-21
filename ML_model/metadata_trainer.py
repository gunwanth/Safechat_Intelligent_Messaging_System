import os
import re
import json
import pickle
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.model_selection import StratifiedKFold
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


_META_ARTIFACT_CACHE: Dict[str, Dict[str, Any]] = {}


def _safe_email(user_email: str) -> str:
    return user_email.replace("@", "_").replace(".", "_")


def _artifact_paths(safe_email: str) -> Dict[str, str]:
    return {
        "base_model": os.path.join("ML_model", f"baseline_model_{safe_email}.pkl"),
        "base_vec": os.path.join("ML_model", f"baseline_vectorizer_{safe_email}.pkl"),
        "meta_model": os.path.join("ML_model", f"metadata_model_{safe_email}.pkl"),
        "meta_vec": os.path.join("ML_model", f"metadata_vectorizer_{safe_email}.pkl"),
        "meta_scaler": os.path.join("ML_model", f"metadata_scaler_{safe_email}.pkl"),
        "meta_cfg": os.path.join("ML_model", f"metadata_feature_config_{safe_email}.json"),
        "stacker": os.path.join("ML_model", f"meta_learner_model_{safe_email}.pkl"),
    }


def _invalidate_artifact_cache(user_email: str) -> None:
    _META_ARTIFACT_CACHE.pop(_safe_email(user_email), None)


def _load_artifacts_for_prediction(user_email: str) -> Optional[Dict[str, Any]]:
    safe_email = _safe_email(user_email)
    paths = _artifact_paths(safe_email)
    required = [
        paths["base_model"],
        paths["base_vec"],
        paths["meta_model"],
        paths["meta_vec"],
        paths["meta_scaler"],
        paths["meta_cfg"],
    ]
    if not all(os.path.exists(path) for path in required):
        return None

    mtimes = {name: os.path.getmtime(path) for name, path in paths.items() if os.path.exists(path)}
    cached = _META_ARTIFACT_CACHE.get(safe_email)
    if cached and cached.get("mtimes") == mtimes:
        return cached["artifacts"]

    with open(paths["base_model"], "rb") as f:
        base_model = pickle.load(f)
    with open(paths["base_vec"], "rb") as f:
        base_vec = pickle.load(f)
    with open(paths["meta_model"], "rb") as f:
        metadata_model = pickle.load(f)
    with open(paths["meta_vec"], "rb") as f:
        metadata_vec = pickle.load(f)
    with open(paths["meta_scaler"], "rb") as f:
        metadata_scaler = pickle.load(f)
    with open(paths["meta_cfg"], "r", encoding="utf-8") as f:
        meta_cfg = json.load(f)

    stacker = None
    if os.path.exists(paths["stacker"]):
        with open(paths["stacker"], "rb") as f:
            stacker = pickle.load(f)

    artifacts = {
        "base_model": base_model,
        "base_vec": base_vec,
        "metadata_model": metadata_model,
        "metadata_vec": metadata_vec,
        "metadata_scaler": metadata_scaler,
        "meta_cfg": meta_cfg,
        "stacker": stacker,
    }
    _META_ARTIFACT_CACHE[safe_email] = {
        "mtimes": mtimes,
        "artifacts": artifacts,
    }
    return artifacts

def derive_label_from_level(level: str, label_mode: str = "medium_high") -> int:
    lvl = str(level or "").strip().lower()
    mode = str(label_mode or "medium_high").strip().lower()
    if mode == "medium_high":
        return 1 if lvl in {"medium", "high", "phishing"} else 0
    return 1 if lvl in {"high", "phishing"} else 0


def sanitize_text_for_nlu(text: str) -> str:
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

    text = re.sub(r"[^a-z0-9\s:/\.\-_?=&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if url_tokens:
        text = f"{text} {' '.join(url_tokens)}".strip()
    return re.sub(r"\s+", " ", text)


def extract_metadata_features(raw_text: str, normalized_text: str) -> List[float]:
    raw = str(raw_text or "")
    t = str(normalized_text or "")
    urls = re.findall(r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", raw, flags=re.IGNORECASE)

    shorteners = 0
    ip_host = 0
    for raw_url in urls:
        url = raw_url.strip(".,;:!?)]}\"'")
        if not url:
            continue
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

    return [
        float(len(urls)),
        float(shorteners),
        float(ip_host),
        float(money_markers),
        float(cta_markers),
        float(total_tokens),
        float(uppercase_chars / alpha_chars) if alpha_chars else 0.0,
        float(digit_chars / non_space_chars) if non_space_chars else 0.0,
        float(raw.count("!")),
    ]


def _transformer_intent_scores(texts: List[str]) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Returns (n_samples, 4) intent scores if transformers and local model are available.
    """
    labels = [
        "credential theft",
        "payment fraud",
        "account takeover",
        "social engineering",
    ]
    try:
        import importlib.util
        backend_available = any(
            importlib.util.find_spec(name) is not None
            for name in ("torch", "tensorflow", "flax")
        )
    except Exception:
        backend_available = False

    if not backend_available:
        return np.zeros((len(texts), 0), dtype=float), {
            "available": False,
            "labels": labels,
            "model": None,
            "reason": "No PyTorch/TensorFlow/Flax backend installed",
        }

    try:
        from transformers import pipeline
        model_name = os.getenv("TRANSFORMER_NLU_MODEL", "facebook/bart-large-mnli")
        classifier = pipeline(
            "zero-shot-classification",
            model=model_name,
            tokenizer=model_name,
            model_kwargs={"local_files_only": True},
        )
        rows = []
        for txt in texts:
            out = classifier(str(txt or "")[:3000], labels, multi_label=True)
            score_map = {k: 0.0 for k in labels}
            for lbl, score in zip(out.get("labels", []), out.get("scores", [])):
                if lbl in score_map:
                    score_map[lbl] = float(score)
            rows.append([score_map[l] for l in labels])
        return np.array(rows, dtype=float), {
            "available": True,
            "labels": labels,
            "model": model_name,
            "reason": None,
        }
    except Exception as e:
        return np.zeros((len(texts), 0), dtype=float), {
            "available": False,
            "labels": labels,
            "model": None,
            "reason": str(e),
        }


def _compute_cv_accuracy_for_metadata_matrix(X, y, n_splits: int = 5) -> Tuple[float, float]:
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = []
    for tr, te in cv.split(X, y):
        clf = LogisticRegression(max_iter=4000, class_weight="balanced", random_state=42)
        clf.fit(X[tr], y[tr])
        pred = clf.predict(X[te])
        scores.append((pred == y[te]).mean())
    return round(float(np.mean(scores)) * 100.0, 2), round(float(np.std(scores)) * 100.0, 2)

def _phishing_probability(model, X) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        if proba.ndim == 2 and proba.shape[1] >= 2:
            # class index for phishing (1) if available
            classes = list(getattr(model, "classes_", []))
            if classes:
                for idx, c in enumerate(classes):
                    if str(c) == "1":
                        return proba[:, idx]
            return proba[:, -1]
    pred = model.predict(X)
    return np.array([1.0 if str(p) == "1" else 0.0 for p in pred], dtype=float)

def _linear_weightage(model) -> Dict[str, Any]:
    coef = getattr(model, "coef_", None)
    if coef is None:
        return {
            "supported": False,
            "non_zero": None,
            "total": None,
            "non_zero_pct": None,
            "sparsity_pct": None,
            "l1_norm": None,
            "l2_norm": None,
        }
    arr = np.asarray(coef, dtype=float)
    total = int(arr.size) if arr.size else 0
    non_zero = int(np.count_nonzero(np.abs(arr) > 1e-12)) if total else 0
    non_zero_pct = round((non_zero / total) * 100.0, 2) if total else 0.0
    sparsity_pct = round(100.0 - non_zero_pct, 2)
    return {
        "supported": True,
        "non_zero": non_zero,
        "total": total,
        "non_zero_pct": non_zero_pct,
        "sparsity_pct": sparsity_pct,
        "l1_norm": round(float(np.abs(arr).sum()), 4),
        "l2_norm": round(float(np.sqrt((arr ** 2).sum())), 4),
    }


def train_and_report_metadata_models(
    user_email: str,
    emails: List[Dict[str, Any]],
    label_mode: str = "medium_high",
) -> Dict[str, Any]:
    safe_email = _safe_email(user_email)
    artifacts_dir = "ML_model"

    texts_raw = []
    labels = []
    for e in emails:
        lvl = str(e.get("level", "")).lower()
        lbl = derive_label_from_level(lvl, label_mode=label_mode)
        txt = f"{e.get('subject', '')} {e.get('content', '')}".strip()
        texts_raw.append(txt)
        labels.append(lbl)

    labels = np.array(labels, dtype=int)
    result = {
        "user_email": user_email,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "label_mode": label_mode,
        "samples": int(len(labels)),
        "class_counts": {
            "safe": int((labels == 0).sum()),
            "phishing": int((labels == 1).sum()),
        },
        "baseline_accuracy": None,
        "baseline_std": None,
        "metadata_accuracy": None,
        "metadata_std": None,
        "meta_learner_accuracy": None,
        "delta_points": None,
        "weightage": {
            "baseline": {},
            "metadata": {},
        },
        "transformer": {"available": False, "reason": None, "model": None, "labels": []},
        "status": "ok",
        "note": None,
    }

    if len(labels) < 6 or len(set(labels.tolist())) < 2:
        result["status"] = "skipped"
        result["note"] = "Insufficient samples or single class; skipped training."
        _write_reports(safe_email, result)
        return result

    min_class = int(min((labels == 0).sum(), (labels == 1).sum()))
    n_splits = 5 if min_class >= 5 else (3 if min_class >= 3 else 2)

    # Baseline text model (TF-IDF + Logistic Regression)
    base_vectorizer = TfidfVectorizer(stop_words="english", max_features=10000, ngram_range=(1, 2))
    text_inputs = [str(t or "").lower() for t in texts_raw]
    X_base = base_vectorizer.fit_transform(text_inputs)

    base_mean, base_std = _compute_cv_accuracy_for_metadata_matrix(X_base, labels, n_splits=n_splits)
    baseline_model = LogisticRegression(max_iter=4000, class_weight="balanced", random_state=42)
    baseline_model.fit(X_base, labels)

    with open(os.path.join(artifacts_dir, f"baseline_model_{safe_email}.pkl"), "wb") as f:
        pickle.dump(baseline_model, f)
    with open(os.path.join(artifacts_dir, f"baseline_vectorizer_{safe_email}.pkl"), "wb") as f:
        pickle.dump(base_vectorizer, f)

    # Metadata-augmented model
    nlu_texts = [sanitize_text_for_nlu(t) for t in texts_raw]
    metadata_rows = np.array([extract_metadata_features(r, n) for r, n in zip(texts_raw, nlu_texts)], dtype=float)
    tfidf_meta = TfidfVectorizer(stop_words="english", max_features=12000, ngram_range=(1, 2))
    X_meta_text = tfidf_meta.fit_transform(nlu_texts)

    transformer_scores, transformer_info = _transformer_intent_scores(texts_raw)
    if transformer_scores.shape[1] > 0:
        metadata_rows = np.hstack([metadata_rows, transformer_scores])

    scaler = StandardScaler()
    X_meta_dense = scaler.fit_transform(metadata_rows)
    X_meta_num = csr_matrix(X_meta_dense)
    X_full = hstack([X_meta_text, X_meta_num], format="csr")

    meta_mean, meta_std = _compute_cv_accuracy_for_metadata_matrix(X_full, labels, n_splits=n_splits)
    metadata_model = LogisticRegression(max_iter=4000, class_weight="balanced", random_state=42)
    metadata_model.fit(X_full, labels)

    # Meta-learning stacker over baseline + metadata probabilities
    base_prob = _phishing_probability(baseline_model, X_base).reshape(-1, 1)
    meta_prob = _phishing_probability(metadata_model, X_full).reshape(-1, 1)
    stack_X = np.hstack([base_prob, meta_prob])
    meta_learner = LogisticRegression(max_iter=4000, class_weight="balanced", random_state=42)
    meta_learner.fit(stack_X, labels)
    meta_pred = meta_learner.predict(stack_X)
    meta_learner_accuracy = round(float((meta_pred == labels).mean()) * 100.0, 2)

    with open(os.path.join(artifacts_dir, f"metadata_model_{safe_email}.pkl"), "wb") as f:
        pickle.dump(metadata_model, f)
    with open(os.path.join(artifacts_dir, f"metadata_vectorizer_{safe_email}.pkl"), "wb") as f:
        pickle.dump(tfidf_meta, f)
    with open(os.path.join(artifacts_dir, f"metadata_scaler_{safe_email}.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    with open(os.path.join(artifacts_dir, f"meta_learner_model_{safe_email}.pkl"), "wb") as f:
        pickle.dump(meta_learner, f)
    with open(os.path.join(artifacts_dir, f"metadata_feature_config_{safe_email}.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "base_feature_count": 9,
                "transformer_enabled": bool(transformer_info.get("available")),
                "transformer_labels": transformer_info.get("labels", []),
            },
            f,
            indent=2,
        )

    result["baseline_accuracy"] = base_mean
    result["baseline_std"] = base_std
    result["metadata_accuracy"] = meta_mean
    result["metadata_std"] = meta_std
    result["meta_learner_accuracy"] = meta_learner_accuracy
    result["delta_points"] = round(meta_mean - base_mean, 2)
    result["weightage"]["baseline"] = _linear_weightage(baseline_model)
    result["weightage"]["metadata"] = _linear_weightage(metadata_model)
    result["transformer"] = transformer_info

    _write_reports(safe_email, result)
    _invalidate_artifact_cache(user_email)
    return result


def _write_reports(safe_email: str, result: Dict[str, Any]) -> None:
    json_path = os.path.join("ML_model", f"metrics_report_{safe_email}.json")
    md_path = os.path.join("ML_model", f"metrics_report_{safe_email}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    lines = [
        "# Metadata Training Report",
        "",
        f"- Generated At: `{result.get('generated_at')}`",
        f"- Label Mode: `{result.get('label_mode')}`",
        f"- Samples: `{result.get('samples')}`",
        f"- Class Counts: `{result.get('class_counts')}`",
        f"- Status: `{result.get('status')}`",
        "",
    ]

    if result.get("status") == "ok":
        lines.extend(
            [
                "## Accuracy",
                "",
                f"- Baseline Accuracy: `{result.get('baseline_accuracy')}%` (std `{result.get('baseline_std')}`)",
                f"- Metadata Accuracy: `{result.get('metadata_accuracy')}%` (std `{result.get('metadata_std')}`)",
                f"- Meta-Learner Accuracy: `{result.get('meta_learner_accuracy')}%`",
                f"- Delta Points: `{result.get('delta_points')}`",
                "",
                "## Sparse Weightage",
                "",
                f"- Baseline Weightage: `{result.get('weightage', {}).get('baseline')}`",
                f"- Metadata Weightage: `{result.get('weightage', {}).get('metadata')}`",
                "",
                "## Transformer NLU",
                "",
                f"- Available: `{result.get('transformer', {}).get('available')}`",
                f"- Model: `{result.get('transformer', {}).get('model')}`",
                f"- Labels: `{result.get('transformer', {}).get('labels')}`",
            ]
        )
    else:
        lines.extend(
            [
                "## Note",
                "",
                f"- `{result.get('note')}`",
            ]
        )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def predict_meta_ensemble_risk(user_email: str, raw_text: str) -> Optional[Dict[str, float]]:
    """
    Infer phishing risk from persisted baseline + metadata + meta-learner artifacts.
    Returns None if required artifacts are missing.
    """
    artifacts = _load_artifacts_for_prediction(user_email)
    if artifacts is None:
        return None

    text = str(raw_text or "")
    text_base = text.lower()
    text_nlu = sanitize_text_for_nlu(text)

    X_base = artifacts["base_vec"].transform([text_base])
    base_prob = float(_phishing_probability(artifacts["base_model"], X_base)[0])

    meta_num = np.array([extract_metadata_features(text, text_nlu)], dtype=float)
    tf_labels = artifacts["meta_cfg"].get("transformer_labels", []) or []
    if artifacts["meta_cfg"].get("transformer_enabled") and tf_labels:
        tf_scores, _tf_info = _transformer_intent_scores([text])
        if tf_scores.shape[1] == len(tf_labels):
            meta_num = np.hstack([meta_num, tf_scores])
        else:
            meta_num = np.hstack([meta_num, np.zeros((1, len(tf_labels)), dtype=float)])

    X_meta_txt = artifacts["metadata_vec"].transform([text_nlu])
    X_meta_num = csr_matrix(artifacts["metadata_scaler"].transform(meta_num))
    X_full = hstack([X_meta_txt, X_meta_num], format="csr")
    metadata_prob = float(_phishing_probability(artifacts["metadata_model"], X_full)[0])

    ensemble_prob = (base_prob + metadata_prob) / 2.0
    if artifacts.get("stacker") is not None:
        ensemble_prob = float(
            _phishing_probability(
                artifacts["stacker"],
                np.array([[base_prob, metadata_prob]], dtype=float),
            )[0]
        )

    return {
        "baseline_prob": round(base_prob, 4),
        "metadata_prob": round(metadata_prob, 4),
        "ensemble_prob": round(ensemble_prob, 4),
    }
