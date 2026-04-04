# 🛡️ SafeChat: Intelligent Secure Messaging System

An AI-powered secure messaging and communication platform designed to detect phishing, analyze URLs, automate message handling, and intelligently route communications using NLP and machine learning.

---

## 📌 Overview

SafeChat is an end-to-end intelligent communication system that enhances security and automation in messaging platforms. It integrates phishing detection, URL analysis, SMS/email processing, and smart routing to prevent malicious communication and improve efficiency.

---

## 🚀 Key Features

### 🔐 Security & Threat Detection
- 🛑 **Phishing Detection System**
  - Detects malicious emails/messages using ML models
- 🔗 **URL Analyzer**
  - Identifies suspicious or unsafe links
- 📊 **Risk Classification**
  - Categorizes messages into safe, spam, phishing, etc.

---

### 📩 Messaging & Automation
- ✉️ **Email Processing Engine**
  - Parses incoming emails and extracts structured data
- 📱 **SMS Generator**
  - Generates automated SMS responses
- 🔔 **Notifier System**
  - Sends alerts/notifications based on message classification

---

### 🤖 AI & Machine Learning
- 🧠 NLP-based message understanding
- 📊 Classification models (`smsmlmodel.py`)
- 📁 Model versioning using Git LFS
- ⚡ Intelligent decision-making pipeline

---

### 🔀 Smart Routing
- 📌 Routes messages based on:
  - Content
  - Priority
  - Category
- 📂 Custom routing logic (`email_column_router.py`)

---

### 🌐 Web Interface
- HTML templates for UI rendering
- Static assets (CSS, JS)
- Interactive frontend

---

### 🐳 Deployment & DevOps
- Dockerized application
- Docker Compose support
- Gunicorn configuration for production

---

## 🏗️ Project Structure
'''
Safechat_Intelligent_Messaging_System/
│
├── ML_model/ # Machine learning models
├── archived_docs/ # Old project documentation
├── static/ # CSS, JS, assets
├── templates/ # HTML templates
│
├── app.py # Main application
├── auth.py # Authentication system
├── notifier.py # Notification service
│
├── email_processor.py # Email parsing logic
├── email_column_router.py # Routing system
├── gmail_client.py # Gmail API integration
│
├── phishing_detector.py # Phishing detection model
├── url_analyzer.py # URL safety analysis
├── sms_generator.py # SMS automation
├── smsmlmodel.py # ML model for SMS classification
│
├── test.py # Testing scripts
│
├── config.toml # Configuration file
├── requirements.txt # Dependencies
├── gunicorn.conf.py # Gunicorn config
├── Dockerfile # Docker setup
├── docker-compose.yml # Multi-container deployment
│
├── PROJECT_ARCHITECTURE_ALIGNED.md
├── PROJECT_FLOWCHART.md
├── METHODOLOGY_NLU_METADATA_DETAILS.md
└── CHANGELOG_PROJECT_UPDATES.md
---

## ⚙️ Tech Stack

| Category        | Technology Used |
|----------------|----------------|
| Backend        | Python (Flask/FastAPI) |
| Frontend       | HTML, CSS, JavaScript |
| ML/NLP         | Scikit-learn, NLP techniques |
| Email API      | Gmail API |
| Deployment     | Docker, Docker Compose, Gunicorn |
| Versioning     | Git + Git LFS |
'''
---

## 🧠 System Workflow

1. 📥 User receives/sends message/email  
2. 🔍 Content is analyzed (NLP + ML models)  
3. 🛑 Phishing detection & URL analysis performed  
4. 📊 Message is classified (safe/spam/phishing)  
5. 🔀 Routing logic determines next action  
6. 🔔 Notifications/SMS triggered if needed  

---

## 🚀 Getting Started

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/Safechat_Intelligent_Messaging_System.git
cd Safechat_Intelligent_Messaging_System
