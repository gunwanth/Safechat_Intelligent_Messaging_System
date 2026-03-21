"""
SMS Generator - Creates varied phishing and legitimate SMS messages.
"""
import random
import string
from datetime import datetime, timedelta


class SMSGenerator:
    """Generate realistic, non-repetitive SMS messages for testing."""

    def __init__(self):
        self.phishing_brands = [
            "BankSecure", "PayGate", "CardShield", "GovTax", "ParcelTrack",
            "Apple ID", "Netflix", "PayPal", "Amazon", "WhatsApp Security"
        ]
        self.legit_brands = [
            "Uber", "Swiggy", "Zomato", "Amazon", "BlueDart",
            "Airtel", "HDFC", "ICICI", "Apollo", "IRCTC"
        ]

        self.phishing_actions = [
            "verify your account", "confirm your card", "reset your password",
            "unlock access", "update KYC", "confirm payment details"
        ]
        self.legit_actions = [
            "has been delivered", "is confirmed", "is scheduled",
            "has been credited", "is ready for pickup", "will arrive shortly"
        ]

        self.phishing_domains = [
            "secure-checks.com", "verify-access.net", "account-alerts.org",
            "support-now.app", "billing-fast.site"
        ]
        self.legit_domains = [
            "amazon.in", "irctc.co.in", "bluedart.com", "airtel.in", "swiggy.com"
        ]

        self.otp_words = ["OTP", "PIN", "code", "verification code"]
        self.warning_words = ["urgent", "immediate", "suspended", "blocked", "failed"]
        self.currency_words = ["Rs", "INR", "$"]

    def generate_sms(self, count=10):
        """Generate a mixed batch with strong variation and low repetition."""
        sms_list = []
        used_contents = set()
        target_phishing = count // 2
        target_safe = count - target_phishing

        for _ in range(target_phishing):
            sms_list.append(self._generate_unique("High", used_contents))
        for _ in range(target_safe):
            sms_list.append(self._generate_unique("Safe", used_contents))

        random.shuffle(sms_list)
        return sms_list

    def _generate_unique(self, label, used_contents):
        """Retry until a unique content is produced (best effort)."""
        attempts = 0
        while attempts < 25:
            sms = self._build_message(label)
            if sms["content"] not in used_contents:
                used_contents.add(sms["content"])
                return sms
            attempts += 1

        # Fallback with forced random suffix to avoid exact duplicates.
        sms = self._build_message(label)
        sms["content"] += f" Ref:{self._rand_alnum(5)}"
        used_contents.add(sms["content"])
        return sms

    def _build_message(self, label):
        if label == "High":
            brand = random.choice(self.phishing_brands)
            action = random.choice(self.phishing_actions)
            warning = random.choice(self.warning_words)
            amount = self._money()
            link = f"http://{random.choice(self.phishing_domains)}/{self._rand_path()}"
            otp = self._otp()

            patterns = [
                f"{brand}: {warning.title()} alert. {action} now: {link}",
                f"{brand} notice: Transaction {amount} flagged. {action}: {link}",
                f"{brand}: Your account is {warning}. Use {otp} at {link}",
                f"{brand}: Device login blocked. {action} within 10 min: {link}",
                f"{brand}: Subscription payment failed ({amount}). {action}: {link}",
            ]
            content = random.choice(patterns)
            sender = self._generate_sender("phishing")
        else:
            brand = random.choice(self.legit_brands)
            action = random.choice(self.legit_actions)
            amount = self._money()
            order_id = self._order_id()
            link = f"https://{random.choice(self.legit_domains)}/{self._rand_path()}"
            eta = random.choice(["30 mins", "2 hours", "tomorrow", "today 7 PM"])

            patterns = [
                f"{brand}: Order {order_id} {action}. Track: {link}",
                f"{brand}: Payment of {amount} successful. Ref {self._rand_alnum(8)}.",
                f"{brand}: Your booking {order_id} is confirmed for {eta}.",
                f"{brand}: Delivery {order_id} {action}. ETA {eta}.",
                f"{brand}: Reminder - appointment {order_id} scheduled at {eta}.",
            ]
            content = random.choice(patterns)
            sender = self._generate_sender("legitimate")

        return {
            "content": content,
            "sender": sender,
            "timestamp": self._generate_timestamp(),
            "label": label
        }

    def _money(self):
        currency = random.choice(self.currency_words)
        value = random.randint(199, 99999)
        return f"{currency} {value:,}"

    def _otp(self):
        token = random.choice(self.otp_words)
        code = random.randint(100000, 999999)
        return f"{token} {code}"

    def _order_id(self):
        return f"#{self._rand_alnum(3)}{random.randint(1000, 9999)}"

    def _rand_path(self):
        words = ["verify", "secure", "billing", "confirm", "track", "update", "access"]
        return f"{random.choice(words)}/{self._rand_alnum(6)}"

    def _rand_alnum(self, n):
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choice(chars) for _ in range(n))

    def _generate_sender(self, sms_type):
        if sms_type == "phishing":
            # Randomized mobile-like number for suspicious senders.
            first = str(random.choice([6, 7, 8, 9]))
            rest = "".join(str(random.randint(0, 9)) for _ in range(9))
            return f"+91{first}{rest}"

        service_senders = [
            "UBER", "AMAZON", "BLUEDART", "AIRTEL", "HDFCBK",
            "ICICIB", "SWIGGY", "ZOMATO", "APOLLO", "IRCTC"
        ]
        return random.choice(service_senders)

    def _generate_timestamp(self):
        now = datetime.now()
        days_ago = random.randint(0, 7)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        timestamp = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    generator = SMSGenerator()
    sms_list = generator.generate_sms(12)
    for i, sms in enumerate(sms_list, 1):
        print(f"{i}. [{sms['label']}] {sms['sender']}: {sms['content']}")
