import shap
import numpy as np
import pickle
import os
import re
import warnings
from typing import Optional
from url_analyzer import URLAnalyzer
from sklearn.exceptions import InconsistentVersionWarning


class XAIExplainer:
    """
    SHAP-based explanation engine for TF-IDF + LogisticRegression
    Uses actual training data for better SHAP background explanations.
    
    AUTO-TRAINS user model with saved emails if not yet trained.
    Falls back to base model if user model not available.
    """

    def __init__(self, user_email: str, use_training_data: bool = True):
        safe_email = user_email.replace("@", "_").replace(".", "_")

        self.model_path = f"ML_model/model_{safe_email}.pkl"
        self.vectorizer_path = f"ML_model/vectorizer_{safe_email}.pkl"
        self.emails_path = f"ML_model/emails_{safe_email}.pkl"
        
        # Fallback paths for base model
        self.base_model_path = "ML_model/base_model.pkl"
        self.base_vectorizer_path = "ML_model/base_vectorizer.pkl"

        self.model = None
        self.vectorizer = None
        self.using_base_model = False
        self.training_data = None
        self.url_analyzer = URLAnalyzer()

        def safe_load(path):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", InconsistentVersionWarning)
                    with open(path, "rb") as f:
                        return pickle.load(f)
            except InconsistentVersionWarning:
                print(f"[XAI] Skipping incompatible sklearn artifact: {path}")
                return None

        # Try to load user model first
        if os.path.exists(self.model_path) and os.path.exists(self.vectorizer_path):
            try:
                self.model = safe_load(self.model_path)
                self.vectorizer = safe_load(self.vectorizer_path)
                if self.model is not None and self.vectorizer is not None:
                    print(f"[XAI] Using user-trained model for {user_email}")
            except Exception as e:
                print(f"⚠️  Failed to load user model: {e}. Trying base model...")
                self.model = None
                self.vectorizer = None
        
        # If user model not available, try to auto-train with saved emails
        if self.model is None or self.vectorizer is None:
            if os.path.exists(self.emails_path):
                try:
                    print(f"🔄 Auto-training user model with saved emails...")
                    self._auto_train_with_emails(user_email)
                    print(f"✅ XAI using newly trained model for {user_email}")
                except Exception as e:
                    print(f"⚠️  Auto-training failed: {e}. Using base model...")
                    self.model = None
                    self.vectorizer = None
        
        # Fallback to base model if user model still not available
        if self.model is None or self.vectorizer is None:
            if os.path.exists(self.base_model_path) and os.path.exists(self.base_vectorizer_path):
                try:
                    self.model = safe_load(self.base_model_path)
                    self.vectorizer = safe_load(self.base_vectorizer_path)
                    if self.model is not None and self.vectorizer is not None:
                        self.using_base_model = True
                        print("[XAI] Using base model")
                    else:
                        self._create_fallback_model()
                except Exception as e:
                    print(f"⚠️  Failed to load base model: {e}")
                    # Create a minimal fallback vectorizer if base fails
                    self._create_fallback_model()
            else:
                print(f"⚠️  Base model not found, creating fallback...")
                self._create_fallback_model()


        # Load training data for better SHAP background
        background_data = self._get_background_data(use_training_data)
        
        # SHAP explainer for linear models with actual background data
        self.explainer = shap.LinearExplainer(
            self.model,
            background_data,
            feature_perturbation="interventional"
        )

    def _create_fallback_model(self):
        """
        Create a fallback model when base model is unavailable.
        Uses common phishing/spam vocabulary.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        
        print("[FALLBACK] Creating fallback model with common email vocabulary...")
        
        # Common phishing and spam emails for training
        fallback_texts = [
            # Phishing emails
            "click here verify account urgent",
            "confirm your identity immediately payment",
            "unusual activity detected please verify",
            "suspend account activate now quickly",
            "urgent action required click link",
            "update your security information now",
            "verify your password reset",
            "congratulations won prize claim",
            # Legitimate emails
            "thank you order shipped tracking",
            "welcome to our service start using",
            "meeting scheduled tomorrow at",
            "team update project progress report",
            "your subscription confirmed details",
            "invoice receipt attached download",
            "password reset request successful",
            "confirm email address verification"
        ]
        
        labels = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]  # 1=phishing, 0=safe
        
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
            min_df=1
        )
        X = self.vectorizer.fit_transform(fallback_texts)
        
        self.model = LogisticRegression(max_iter=1000, random_state=42)
        self.model.fit(X, labels)
        self.using_base_model = True
        
        print("[FALLBACK] ✅ Fallback model created with common email vocabulary")

    def _auto_train_with_emails(self, user_email: str):
        """
        Automatically train user model with saved emails.
        Loads emails from pkl, extracts labels from level, and trains.
        """
        safe_email = user_email.replace("@", "_").replace(".", "_")
        
        # Load emails from pkl
        print(f"[AUTO-TRAIN] Loading emails from: {self.emails_path}")
        with open(self.emails_path, "rb") as f:
            emails_list = pickle.load(f)
        
        print(f"[AUTO-TRAIN] Loaded {len(emails_list)} emails from pkl")
        
        if not emails_list:
            raise Exception("No emails found in saved data")
        
        # Extract content and labels
        contents = []
        labels = []
        
        for email in emails_list:
            if isinstance(email, dict):
                content = email.get("content", "")
                level = email.get("level", "Unknown")
                
                if content and len(content.strip()) > 0:
                    contents.append(content)
                    # Label: 1 for phishing (High), 0 for safe
                    labels.append(1 if level == "High" else 0)
        
        if len(contents) < 2:
            raise Exception("Not enough emails to train (need at least 2)")
        
        # Check if we have multiple classes
        unique_labels = set(labels)
        if len(unique_labels) < 2:
            print(f"⚠️  Only one class in {len(contents)} emails. Loading base model instead.")
            # Load base model
            if os.path.exists(self.base_model_path) and os.path.exists(self.base_vectorizer_path):
                self.model = safe_load(self.base_model_path)
                self.vectorizer = safe_load(self.base_vectorizer_path)
                if self.model is not None and self.vectorizer is not None:
                    self.using_base_model = True
                else:
                    raise Exception("Cannot load compatible base model")
            else:
                raise Exception("Cannot train or load base model")
            return
        
        # Train TF-IDF vectorizer on user emails
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        
        print(f"📊 Training on {len(contents)} emails with classes {unique_labels}")
        
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=10000, ngram_range=(1, 2))
        X = self.vectorizer.fit_transform(contents)
        
        # Train classifier on user emails
        self.model = LogisticRegression(max_iter=4000, random_state=42)
        self.model.fit(X, labels)
        
        # Save trained model and vectorizer
        with open(self.model_path, "wb") as f:
            pickle.dump(self.model, f)
        with open(self.vectorizer_path, "wb") as f:
            pickle.dump(self.vectorizer, f)
        
        print(f"💾 Saved user model to {self.model_path}")
        print(f"💾 Saved vectorizer to {self.vectorizer_path}")

    def _get_background_data(self, use_training_data: bool = True):
        """
        Get background data for SHAP explainer.
        Uses actual training emails if available for better explanations.
        Falls back to dummy data if not available.
        """
        # Try to load actual training emails
        if use_training_data and os.path.exists(self.emails_path):
            try:
                with open(self.emails_path, "rb") as f:
                    emails = pickle.load(f)
                if emails and len(emails) > 0:
                    # Extract content from emails
                    contents = []
                    for email in emails[:100]:  # Use up to 100 emails as background
                        if isinstance(email, dict) and "content" in email:
                            content = email.get("content", "")
                            if content and len(content) > 10:  # Only valid content
                                contents.append(content)
                    
                    if contents and len(contents) > 0:
                        # Vectorize the actual emails
                        background = self.vectorizer.transform(contents)
                        print(f"✅ SHAP using {len(contents)} real emails as background")
                        return background
            except Exception as e:
                print(f"⚠️  Could not load training data: {e}. Using default background.")
        
        # Fallback: Use diverse dummy samples
        dummy_samples = [
            "click here urgent verify account",
            "confirm your identity now payment",
            "congratulations winner claim prize",
            "suspicious activity alert security",
            "thank you order confirmation shipped",
            "meeting reminder team update",
            "welcome new user registration",
            "password reset request notification"
        ]
        background = self.vectorizer.transform(dummy_samples)
        print(f"✅ SHAP using default background samples")
        return background

    def explain_text(self, text: str, top_k: int = 8):
        """
        Generate human-readable SHAP explanations.
        Returns real words instead of numeric indices.
        Handles edge cases gracefully with intelligent fallbacks.
        """
        from collections import Counter

        print(f"\n[EXPLAIN] Processing email (length: {len(text) if text else 0} chars)")

        try:
            if not text or len(text.strip()) < 5:
                print(f"[EXPLAIN] Text too short, using fallback")
                fallback = self._fallback_word_explanation(text, top_k)
                return self._merge_explanations(self._url_feature_explanations(text), fallback, top_k)

            text_clean = text.strip()
            url_feature_explanations = self._url_feature_explanations(text_clean)

            try:
                print(f"[EXPLAIN] Attempting SHAP transformation...")
                model_text = self._normalize_for_model(text_clean)
                X = self.vectorizer.transform([model_text])
                print(f"[EXPLAIN] Vectorized: {X.nnz} non-zero elements")

                if X.nnz == 0:
                    print(f"[EXPLAIN] No vocabulary matches, using fallback")
                    fallback = self._fallback_word_explanation(text_clean, top_k)
                    return self._merge_explanations(url_feature_explanations, fallback, top_k)

                print(f"[EXPLAIN] Computing SHAP values...")
                shap_values = self.explainer(X)
                feature_names = self.vectorizer.get_feature_names_out()
                shap_vals = shap_values.values[0]

                present_indices = X.nonzero()[1]
                explanations = []

                print(f"[EXPLAIN] Processing {len(present_indices)} tokens from SHAP")

                for idx in present_indices:
                    weight = float(shap_vals[idx])
                    token = feature_names[idx]

                    if abs(weight) < 0.001:
                        continue
                    if token.isdigit():
                        continue
                    if token in ['the', 'a', 'an', 'and', 'or', 'is', 'are']:
                        continue

                    explanations.append({
                        "token": token,
                        "impact": round(abs(weight), 4),
                        "direction": "phishing" if weight > 0 else "safe"
                    })

                explanations.sort(key=lambda x: x["impact"], reverse=True)

                if explanations:
                    merged = self._merge_explanations(url_feature_explanations, explanations, top_k)
                    print(f"[EXPLAIN] SHAP: Found {len(merged)} explanations")
                    return merged[:top_k]

                print(f"[EXPLAIN] SHAP found no meaningful explanations, using fallback")
                fallback = self._fallback_word_explanation(text_clean, top_k)
                return self._merge_explanations(url_feature_explanations, fallback, top_k)

            except Exception as shap_err:
                print(f"[EXPLAIN] SHAP failed: {shap_err}, using fallback")
                fallback = self._fallback_word_explanation(text_clean, top_k)
                return self._merge_explanations(url_feature_explanations, fallback, top_k)

        except Exception as e:
            print(f"[EXPLAIN] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            try:
                fallback = self._fallback_word_explanation(text, top_k)
                return self._merge_explanations(self._url_feature_explanations(text), fallback, top_k)
            except Exception:
                return []

    def _normalize_for_model(self, text: str) -> str:
        """Normalize noisy content to increase TF-IDF coverage for SHAP."""
        text = re.sub(r"<[^>]+>", " ", str(text or ""))
        text = re.sub(r"https?://\\S+|www\\.\\S+", " ", text)
        text = re.sub(r"[^A-Za-z0-9\\s]", " ", text)
        return re.sub(r"\\s+", " ", text).strip().lower()

    def _url_feature_explanations(self, text: str):
        """Generate explanation tokens from robust URL analysis."""
        try:
            summary = self.url_analyzer.analyze_email_urls(text or "")
        except Exception:
            return []

        if not summary.get("suspicious_urls"):
            return []

        out = []
        for item in summary.get("suspicious_urls", []):
            risk = float(item.get("risk_score", 0.0))
            for ind in item.get("indicators", []):
                token = f"url:{str(ind).lower()}"
                out.append({
                    "token": token[:80],
                    "impact": round(max(0.05, min(0.9, risk)), 4),
                    "direction": "phishing"
                })
        return out

    def _merge_explanations(self, primary, secondary, top_k):
        """Merge explanation lists, dedupe by token, keep strongest impact."""
        merged = {}
        for item in (primary or []) + (secondary or []):
            token = str(item.get("token", "")).strip()
            if not token:
                continue
            impact = float(item.get("impact", 0.0) or 0.0)
            direction = item.get("direction", "phishing")
            prev = merged.get(token)
            if prev is None or impact > prev["impact"]:
                merged[token] = {"token": token, "impact": impact, "direction": direction}

        ranked = sorted(merged.values(), key=lambda x: x["impact"], reverse=True)
        return ranked[:top_k]
    def _fallback_word_explanation(self, text: str, top_k: int = 8):
        """
        Fallback explanation using word frequency and phishing indicators.
        Always returns something if text exists.
        """
        import re
        from collections import Counter
        
        print(f"[FALLBACK] Analyzing with word-frequency method...")
        
        if not text or len(text.strip()) < 3:
            print(f"[FALLBACK] Text too short")
            return []
        
        try:
            # Extract ALL words (including single/double letters)
            words = re.findall(r'\b[a-z]+\b', text.lower())
            print(f"[FALLBACK] Found {len(words)} total words")
            
            if not words:
                print(f"[FALLBACK] No words found in text")
                return []
            
            # Common phishing indicators (comprehensive list)
            phishing_words = {
                'verify', 'confirm', 'urgent', 'click', 'account', 'password',
                'security', 'update', 'activate', 'payment', 'immediate', 'action',
                'suspended', 'unusual', 'suspicious', 'confirm', 'identity',
                'freeze', 'limit', 'problem', 'issue', 'claim', 'winner', 'prize',
                'congratulations', 'reset', 'login', 'authorize', 'validate',
                'alert', 'fraud', 'compromise', 'breach', 'unusual', 'activity',
                'approval', 'pending', 'expire', 'expired', 'expiring', 'confirm',
                'unblock', 'unlock', 'restricted', 'required', 'immediately',
            }
            
            # Count word frequencies
            word_counts = Counter(words)
            total_words = sum(word_counts.values())
            
            explanations = []
            seen_words = set()
            
            # Process words by frequency
            for word, count in word_counts.most_common(top_k * 2):
                if word in seen_words or len(word) < 3:
                    continue
                
                seen_words.add(word)
                
                # Calculate frequency-based impact
                frequency = count / total_words
                
                # Determine direction
                direction = "phishing" if word in phishing_words else "safe"
                
                explanations.append({
                    "token": word,
                    "impact": round(frequency, 4),
                    "direction": direction
                })
            
            print(f"[FALLBACK] ✅ Generated {len(explanations)} fallback explanations")
            return explanations[:top_k]
            
        except Exception as e:
            print(f"[FALLBACK] Error: {e}")
            return []
    

