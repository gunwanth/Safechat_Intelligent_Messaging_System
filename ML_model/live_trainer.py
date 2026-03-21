# ML_model/live_trainer.py
import os
import pickle
import warnings
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import InconsistentVersionWarning


class LiveTrainer:
    """
    - Loads/creates a base model (optionally from Kaggle dataset).
    - Fine-tunes a user-specific model on the user's emails.
    - Supports prediction with probabilities for per-email confidence %.
    """

    def __init__(self, user_email: str, dataset_path: str = "ML_model/kaggle_dataset.csv"):
        safe_email = user_email.replace("@", "_").replace(".", "_")

        # User-specific artifacts
        self.model_file = f"ML_model/model_{safe_email}.pkl"
        self.vectorizer_file = f"ML_model/vectorizer_{safe_email}.pkl"
        self.email_file = f"ML_model/emails_{safe_email}.pkl"

        # Base artifacts
        self.base_model_file = "ML_model/base_model.pkl"
        self.base_vectorizer_file = "ML_model/base_vectorizer.pkl"

        self.vectorizer: Optional[TfidfVectorizer] = None
        self.model: Optional[LogisticRegression] = None

        # Try to load user model → else base → else train base if dataset exists
        if not self._load_user_model():
            if not self._load_base_model():
                # If a dataset is present, try to create a base model silently
                if os.path.exists(dataset_path):
                    try:
                        self.train_base_model(dataset_path=dataset_path, force_retrain=True)
                    except Exception as e:
                        print(f"[WARN] Could not auto-train base model: {e}")
                # Try loading base again (maybe it was just created)
                self._load_base_model()

    # ---------- Public API ----------

    def train_base_model(self, dataset_path: str = "ML_model/kaggle_dataset.csv", force_retrain: bool = False) -> None:
        """
        One-time training of a base model from a dataset.
        The dataset can have various column names; we'll try to detect them.
        """
        if (
            not force_retrain
            and os.path.exists(self.base_model_file)
            and os.path.exists(self.base_vectorizer_file)
            and self._base_artifacts_loadable()
        ):
            print("[OK] Base model already exists. Skipping training.")
            return

        if not os.path.exists(dataset_path):
            raise FileNotFoundError(f"[ERROR] Dataset not found at {dataset_path}")

        df = pd.read_csv(dataset_path)

        # --- Detect label column ---
        label_col = self._detect_label_column(df)
        if label_col is None:
            raise Exception("[ERROR] Could not detect label column in dataset")

        # --- Detect / build text column ---
        text_col = self._detect_text_column(df, exclude={label_col})
        if text_col is None:
            # build text by concatenating all non-label columns
            text_series = self._concatenate_text_columns(df.drop(columns=[label_col]))
        else:
            text_series = df[text_col].astype(str).fillna("")

        y = df[label_col].astype(str).fillna("unknown")

        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=10000, ngram_range=(1, 2))
        X_vec = self.vectorizer.fit_transform(text_series)

        self.model = LogisticRegression(max_iter=4000)
        self.model.fit(X_vec, y)

        with open(self.base_model_file, "wb") as f:
            pickle.dump(self.model, f)
        with open(self.base_vectorizer_file, "wb") as f:
            pickle.dump(self.vectorizer, f)

        print("[OK] Base model trained and saved.")

    def _base_artifacts_loadable(self) -> bool:
        model = None
        vectorizer = None
        if os.path.exists(self.base_model_file):
            model = self._safe_load_pickle(self.base_model_file)
        if os.path.exists(self.base_vectorizer_file):
            vectorizer = self._safe_load_pickle(self.base_vectorizer_file)
        return model is not None and vectorizer is not None

    def train_user(self, emails: List[str], labels: List) -> None:
        """
        Fine-tune (re-fit) a user-specific model.
        If user data has only one class, skip re-fit and keep base model.
        
        IMPORTANT: Always saves user artifacts for XAI compatibility.
        """
        if self.vectorizer is None or self.model is None:
            # try to load user or base model
            if not self._load_user_model() and not self._load_base_model():
                raise Exception("[ERROR] No trained model found. Train a base model first.")

        if len(set(labels)) < 2:
            print("[WARN] Only one class in user emails; skipping fine-tune. Using base model.")
            print("[TIP] Add more diverse emails (both phishing & safe) for better XAI explanations.")
            # Write out the base artifacts as user artifacts so XAI can find them
            self._persist_user_artifacts()
            print(f"[OK] User model artifacts saved for XAI: {self.model_file}")
            return

        # Multi-class: Train user-specific model
        print(f"[TRAIN] Training user model with {len(emails)} emails and {len(set(labels))} classes...")
        X_user = self.vectorizer.transform(emails)
        
        # Refit classifier on user data
        user_model = LogisticRegression(max_iter=4000)
        user_model.fit(X_user, labels)
        self.model = user_model

        # Ensure user artifacts are saved for XAI compatibility
        self._persist_user_artifacts()
        print(f"[OK] User model trained and saved: {self.model_file}")
        print(f"[OK] User vectorizer saved: {self.vectorizer_file}")
        print("[OK] XAI explanations now available for your emails!")
        

    def predict(self, emails: List[str]) -> np.ndarray:
        """
        Predict class labels for emails.
        """
        if self.model is None or self.vectorizer is None:
            if not self._load_user_model() and not self._load_base_model():
                raise Exception("[ERROR] No trained model available for prediction.")
        X = self.vectorizer.transform(emails)
        return self.model.predict(X)

    def predict_with_proba(self, emails: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict class labels and probabilities.
        Returns (preds, probas) where probas is shape (n_samples, n_classes).
        """
        if self.model is None or self.vectorizer is None:
            if not self._load_user_model() and not self._load_base_model():
                raise Exception("[ERROR] No trained model available for prediction.")

        X = self.vectorizer.transform(emails)
        preds = self.model.predict(X)

        if hasattr(self.model, "predict_proba"):
            probas = self.model.predict_proba(X)
        elif hasattr(self.model, "decision_function"):
            scores = self.model.decision_function(X)
            # Binary: scores shape (n_samples,)
            if scores.ndim == 1:
                p1 = 1.0 / (1.0 + np.exp(-scores))
                probas = np.vstack([1 - p1, p1]).T
            else:
                # Multiclass: softmax
                e = np.exp(scores - scores.max(axis=1, keepdims=True))
                probas = e / e.sum(axis=1, keepdims=True)
        else:
            # Fallback: one-hot on predicted class
            classes = getattr(self.model, "classes_", np.unique(preds))
            idx = {c: i for i, c in enumerate(classes)}
            probas = np.zeros((len(preds), len(classes)), dtype=float)
            for i, y in enumerate(preds):
                proba_row = np.zeros(len(classes))
                proba_row[idx[y]] = 1.0
                probas[i] = proba_row

        return preds, probas

    # ---------- Internal helpers ----------

    @staticmethod
    def _safe_load_pickle(path: str):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", InconsistentVersionWarning)
                with open(path, "rb") as f:
                    return pickle.load(f)
        except InconsistentVersionWarning:
            print(f"[WARN] Skipping incompatible sklearn artifact: {path}")
            return None

    def _persist_user_artifacts(self) -> None:
        """Save current model/vectorizer as the user's artifacts."""
        if self.model is not None:
            with open(self.model_file, "wb") as f:
                pickle.dump(self.model, f)
        if self.vectorizer is not None:
            with open(self.vectorizer_file, "wb") as f:
                pickle.dump(self.vectorizer, f)

    def _load_user_model(self) -> bool:
        if os.path.exists(self.model_file) and os.path.exists(self.vectorizer_file):
            model = self._safe_load_pickle(self.model_file)
            vectorizer = self._safe_load_pickle(self.vectorizer_file)
            if model is not None and vectorizer is not None:
                self.model = model
                self.vectorizer = vectorizer
                return True
        return False

    def _load_base_model(self) -> bool:
        if os.path.exists(self.base_model_file) and os.path.exists(self.base_vectorizer_file):
            model = self._safe_load_pickle(self.base_model_file)
            vectorizer = self._safe_load_pickle(self.base_vectorizer_file)
            if model is not None and vectorizer is not None:
                self.model = model
                self.vectorizer = vectorizer
                return True
        return False

    # --- Dataset column detection utilities ---

    @staticmethod
    def _detect_label_column(df: pd.DataFrame) -> Optional[str]:
        """
        Try to find a label/target column.
        """
        candidates = [
            "label", "labels", "class", "category", "target", "type", "tag",
            "intent", "is_phishing", "spam", "phishing"
        ]
        lower_cols = {c.lower(): c for c in df.columns}

        for key in candidates:
            if key in lower_cols:
                return lower_cols[key]

        # Heuristic: a column with few unique values (2..10) and not too text-like
        for col in df.columns:
            nunique = df[col].nunique(dropna=True)
            if 2 <= nunique <= 10:
                # avoid obvious ids / long free text
                if df[col].dtype != object or df[col].astype(str).str.len().median() < 30:
                    return col
        return None

    @staticmethod
    def _detect_text_column(df: pd.DataFrame, exclude: set) -> Optional[str]:
        """
        Try to find the most likely single text column.
        """
        text_like = [
            "text", "message", "content", "body", "subject", "email", "msg",
            "description", "sentence"
        ]
        lower_cols = {c.lower(): c for c in df.columns if c not in exclude}
        for key in text_like:
            if key in lower_cols:
                return lower_cols[key]
        # heuristic: pick the object column with the longest avg length
        best_col, best_len = None, -1
        for col in df.columns:
            if col in exclude:
                continue
            if df[col].dtype == object:
                avg_len = df[col].astype(str).str.len().mean()
                if avg_len > best_len:
                    best_col, best_len = col, avg_len
        return best_col

    @staticmethod
    def _concatenate_text_columns(df: pd.DataFrame) -> pd.Series:
        """
        Concatenate multiple non-label columns into a single text blob.
        """
        cols = [c for c in df.columns if df[c].dtype == object]
        if not cols:
            # if nothing object-like, just stringify everything
            cols = df.columns.tolist()
        text = df[cols].astype(str).fillna("").agg(" ".join, axis=1)
        return text
