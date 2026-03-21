import re
import nltk
import numpy as np
import os
import shutil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from url_analyzer import URLAnalyzer
from zipfile import BadZipFile


def _reset_nltk_resource(relative_path: str):
    for base in nltk.data.path:
        target = os.path.join(base, relative_path)
        zip_target = f"{target}.zip"
        try:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                os.remove(target)
        except OSError:
            pass
        try:
            if os.path.exists(zip_target):
                os.remove(zip_target)
        except OSError:
            pass


def _ensure_nltk_resource(resource_name: str, download_name: str):
    try:
        nltk.data.find(resource_name)
        return
    except (LookupError, BadZipFile, OSError):
        _reset_nltk_resource(resource_name)
        nltk.download(download_name, quiet=True)
        nltk.data.find(resource_name)


_ensure_nltk_resource('tokenizers/punkt', 'punkt')
_ensure_nltk_resource('corpora/stopwords', 'stopwords')


class PhishingDetector:
    def __init__(self):
        self.model = None
        self.vectorizer = None
        self.is_trained = False

        self.suspicious_keywords = [
            'urgent', 'immediate', 'verify', 'suspend', 'click here', 'act now',
            'limited time', 'congratulations', 'winner', 'prize', 'claim',
            'suspicious activity', 'security alert', 'confirm identity',
            'update payment', 'account locked', 'unusual activity',
            'verify account', 'suspended', 'expired', 'final notice',
            'legal action', 'debt collection', 'irs', 'refund'
        ]

        self.suspicious_domains = [
            'suspicious-bank.com', 'fake-lottery.net', 'paypal-verify.net',
            'debt-collection.biz', 'amazon-security.org', 'microsoft-support.net',
            'apple-id-verify.com', 'google-security.org', 'facebook-security.net'
        ]

        self.legitimate_domains = [
            'gmail.com', 'amazon.com', 'paypal.com', 'microsoft.com',
            'apple.com', 'google.com', 'facebook.com', 'linkedin.com',
            'twitter.com', 'instagram.com', 'youtube.com'
        ]
        self.url_analyzer = URLAnalyzer()

        self.initialize_model()

    def initialize_model(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self._train_with_sample_data()

    def _train_with_sample_data(self):
        phishing_samples = [
            "URGENT: Your account will be suspended. Click here to verify immediately.",
            "Congratulations! You've won $1,000,000. Click to claim your prize now!",
            "Security alert: Unusual activity detected. Verify your identity now.",
            "FINAL NOTICE: Pay immediately or face legal action and credit damage.",
            "Your PayPal account has been limited. Click here to restore access.",
            "IRS REFUND: You are eligible for a $2,500 tax refund. Claim now!",
            "WINNER SELECTED: You have won a gift card. Provide details to claim.",
            "Account suspended due to suspicious activity. Verify to restore.",
        ]

        legitimate_samples = [
            "Thank you for your recent purchase. Your order has been confirmed.",
            "Your weekly newsletter with the latest industry updates and news.",
            "Meeting reminder: Team standup tomorrow at 10 AM in conference room.",
            "Your subscription has been renewed successfully. Thank you.",
            "Project update: Here are the deliverables completed this week.",
            "Invoice for your recent order. Payment due within 30 days.",
            "Welcome to our service! Here's how to get started with your account.",
            "Your package has been shipped and is on its way to your address.",
        ]

        texts = phishing_samples + legitimate_samples
        labels = [1] * len(phishing_samples) + [0] * len(legitimate_samples)

        X_train = self.vectorizer.fit_transform(texts)
        self.model.fit(X_train, labels)
        self.is_trained = True

    def extract_features(self, email_data):
        features = {}

        subject = email_data.get('subject', '').lower()
        content = email_data.get('content', '').lower()
        sender = email_data.get('sender', '').lower()
        combined = f"{subject} {content}"

        features['suspicious_keyword_count'] = sum(1 for kw in self.suspicious_keywords if kw in combined)
        features['urgency_words'] = sum(1 for word in ['urgent', 'immediate', 'now', 'asap'] if word in combined)
        features['money_mentions'] = len(re.findall(r'\$[\d,]+', combined))
        features['suspicious_domain'] = any(domain in sender for domain in self.suspicious_domains)
        features['legitimate_domain'] = any(domain in sender for domain in self.legitimate_domains)
        features['excessive_caps'] = len(re.findall(r'[A-Z]{3,}', subject + content))
        features['exclamation_marks'] = combined.count('!')
        features['question_marks'] = combined.count('?')

        urls = re.findall(r'http[s]?://\S+', content)
        features['url_count'] = len(urls)
        features['suspicious_urls'] = [url for url in urls if any(domain in url for domain in self.suspicious_domains)]

        # Robust URL analysis (domain/IP/shortener/path/TLD heuristics)
        url_summary = self.url_analyzer.analyze_email_urls(content)
        features['url_overall_risk'] = float(url_summary.get('overall_risk', 0.0))
        features['suspicious_url_count'] = len(url_summary.get('suspicious_urls', []))
        features['url_indicators'] = []
        for item in url_summary.get('suspicious_urls', []):
            for indicator in item.get('indicators', []):
                if indicator not in features['url_indicators']:
                    features['url_indicators'].append(indicator)

        return features

    def calculate_risk_score(self, email_data):
        if not self.is_trained:
            return 0.5

        try:
            text = f"{email_data.get('subject', '')} {email_data.get('content', '')}"
            X = self.vectorizer.transform([text])
            ml_score = self.model.predict_proba(X)[0][1]

            features = self.extract_features(email_data)
            manual_score = 0.0

            if features['suspicious_keyword_count'] > 0:
                manual_score += min(0.3, features['suspicious_keyword_count'] * 0.1)
            if features['urgency_words'] > 0:
                manual_score += min(0.2, features['urgency_words'] * 0.1)
            if features['money_mentions'] > 0:
                manual_score += min(0.2, features['money_mentions'] * 0.1)
            if features['suspicious_domain']:
                manual_score += 0.4
            elif features['legitimate_domain']:
                manual_score -= 0.2
            if features['excessive_caps'] > 2:
                manual_score += 0.1
            if features['exclamation_marks'] > 2:
                manual_score += 0.1
            if features['url_count'] > 3:
                manual_score += 0.1
            if features['suspicious_urls']:
                manual_score += 0.3
            if features['suspicious_url_count'] > 0:
                manual_score += min(0.35, features['suspicious_url_count'] * 0.12)
            manual_score += min(0.25, features['url_overall_risk'] * 0.25)

            return round(min(1.0, max(0.0, ml_score * 0.7 + manual_score * 0.3)), 2)

        except Exception:
            features = self.extract_features(email_data)
            return min(1.0, sum([
                features['suspicious_keyword_count'] * 0.1,
                features['urgency_words'] * 0.1,
                features['money_mentions'] * 0.1,
                0.4 if features['suspicious_domain'] else 0,
                0.1 if features['excessive_caps'] > 2 else 0,
                0.1 if features['exclamation_marks'] > 2 else 0,
                0.3 if features['suspicious_urls'] else 0,
                min(0.35, features.get('suspicious_url_count', 0) * 0.12),
                min(0.25, features.get('url_overall_risk', 0.0) * 0.25),
            ]))

    def detect_threats(self, email_data):
        threats = []
        text = f"{email_data.get('subject', '').lower()} {email_data.get('content', '').lower()}"
        sender = email_data.get('sender', '').lower()

        if any(k in text for k in ['urgent', 'immediate', 'act now']):
            threats.append("Urgency tactics")
        if any(k in text for k in ['verify', 'confirm', 'update']):
            threats.append("Info verification requested")
        if any(k in text for k in ['suspended', 'locked']):
            threats.append("Fear tactics")
        if any(k in text for k in ['winner', 'congratulations', 'selected']):
            threats.append("Fake prize scam")
        if re.search(r'\$[\d,]+', text):
            threats.append("Money lure")

        if any(domain in sender for domain in self.suspicious_domains):
            threats.append("Suspicious sender domain")

        urls = re.findall(r'http[s]?://\S+', text)
        if any(domain in url for domain in self.suspicious_domains for url in urls):
            threats.append("Malicious links")

        # Add robust URL indicators from analyzer
        url_summary = self.url_analyzer.analyze_email_urls(email_data.get('content', ''))
        if url_summary.get('suspicious_urls'):
            threats.append("Suspicious URL structure")
            for u in url_summary.get('suspicious_urls', []):
                for ind in u.get('indicators', [])[:2]:
                    msg = f"URL risk: {ind}"
                    if msg not in threats:
                        threats.append(msg)

        if len(re.findall(r'[A-Z]{3,}', text)) > 2:
            threats.append("Excessive CAPS")

        if text.count('!') > 3:
            threats.append("Too many exclamations")

        return threats

    def get_risk_level(self, score):
        if score >= 0.7:
            return "High"
        elif score >= 0.4:
            return "Medium"
        else:
            return "Low"
        
print(">>> phishing_detector.py loaded")
print(">>> Available names:", dir())
