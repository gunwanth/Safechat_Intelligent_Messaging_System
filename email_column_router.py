import re
from urllib.parse import urlparse


class EmailColumnRouter:
    """
    Route incoming emails to inbox columns.
    Returns one of: "promotions", "social", "purchases", or None.
    """

    VALID_COLUMNS = {"promotions", "social", "purchases"}

    def __init__(self):
        self.keyword_weights = {
            "promotions": {
                "sale": 3,
                "discount": 3,
                "coupon": 3,
                "offer": 2,
                "deal": 2,
                "promo": 2,
                "promotion": 2,
                "limited time": 3,
                "shop now": 3,
                "buy now": 2,
                "free shipping": 3,
                "clearance": 3,
                "exclusive": 2,
                "black friday": 4,
                "cyber monday": 4,
            },
            "social": {
                "friend request": 4,
                "liked your": 3,
                "commented": 3,
                "mention": 3,
                "tagged": 3,
                "follow": 2,
                "follower": 2,
                "community": 2,
                "group": 2,
                "message request": 3,
                "new connection": 4,
                "invited you": 3,
                "notification": 1,
            },
            "purchases": {
                "order": 3,
                "invoice": 4,
                "receipt": 4,
                "shipment": 4,
                "delivered": 3,
                "tracking": 4,
                "refund": 3,
                "payment": 3,
                "billing": 3,
                "subscription": 2,
                "renewal": 2,
                "transaction": 4,
                "amount paid": 4,
                "tax invoice": 4,
            },
        }

        self.domain_hints = {
            "social": {
                "facebook.com",
                "instagram.com",
                "linkedin.com",
                "twitter.com",
                "x.com",
                "discord.com",
                "reddit.com",
                "snapchat.com",
                "tiktok.com",
                "pinterest.com",
            },
            "purchases": {
                "amazon.com",
                "walmart.com",
                "ebay.com",
                "paypal.com",
                "stripe.com",
                "shopify.com",
                "fedex.com",
                "ups.com",
                "usps.com",
                "dhl.com",
            },
            "promotions": {
                "mailchi.mp",
                "sendgrid.net",
                "constantcontact.com",
                "klaviyo.com",
            },
        }

        self.label_map = {
            "CATEGORY_PROMOTIONS": "promotions",
            "CATEGORY_SOCIAL": "social",
            "CATEGORY_PURCHASES": "purchases",
        }

        self.min_score = 3

    def classify(self, email):
        labels = set(email.get("labels", []))
        for label, column in self.label_map.items():
            if label in labels:
                return column

        text = self._normalized_text(email)
        sender_domain = self._extract_sender_domain(email.get("sender", ""))

        scores = {
            "promotions": 0,
            "social": 0,
            "purchases": 0,
        }

        if sender_domain:
            for column, domains in self.domain_hints.items():
                if any(sender_domain.endswith(d) for d in domains):
                    scores[column] += 3

        for column, keywords in self.keyword_weights.items():
            for phrase, weight in keywords.items():
                if phrase in text:
                    scores[column] += weight

        # Lightweight intent features from links and receipts-like patterns.
        links = self._extract_urls(text)
        if links:
            for column, domains in self.domain_hints.items():
                if any(any(link_domain.endswith(d) for d in domains) for link_domain in links):
                    scores[column] += 2

        if re.search(r"\b(order|invoice|receipt)\s*#?\s*[a-z0-9-]{4,}\b", text):
            scores["purchases"] += 3

        if "unsubscribe" in text:
            scores["promotions"] += 2

        top_column = max(scores, key=scores.get)
        top_score = scores[top_column]
        if top_score < self.min_score:
            return None

        # Avoid weak ties.
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1 and (sorted_scores[0] - sorted_scores[1]) <= 1:
            return None

        return top_column if top_column in self.VALID_COLUMNS else None

    def _normalized_text(self, email):
        subject = (email.get("subject") or "").lower()
        sender = (email.get("sender") or "").lower()
        content = (email.get("content") or "").lower()
        snippet = (email.get("snippet") or "").lower()
        return f"{subject} {sender} {content} {snippet}"

    def _extract_sender_domain(self, sender):
        # Handles "Name <user@domain.com>" and plain addresses.
        sender = sender.strip().lower()
        match = re.search(r"<([^>]+)>", sender)
        address = match.group(1) if match else sender
        if "@" not in address:
            return ""
        return address.split("@", 1)[1].strip()

    def _extract_urls(self, text):
        matches = re.findall(r"https?://[^\s)>\"]+", text)
        domains = []
        for url in matches:
            try:
                domain = urlparse(url).netloc.lower()
            except Exception:
                domain = ""
            if domain:
                domains.append(domain)
        return domains
