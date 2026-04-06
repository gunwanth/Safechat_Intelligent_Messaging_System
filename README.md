

<h1 align="center">💬 SafeChat — Intelligent Secure Messaging System</h1>

<p align="center">
AI-powered messaging system for detecting <b>phishing attacks</b>, analyzing <b>URLs</b>, and automating <b>secure communication workflows</b>.
<br>
Built using <b>Python</b> + <b>Machine Learning</b> + <b>Docker</b>.
</p>

---


<p align="center">
  <img src="https://img.shields.io/badge/Python-3.x-blue" />
  <img src="https://img.shields.io/badge/ML-NLP-green" />
  <img src="https://img.shields.io/badge/Security-PhishingDetection-red" />
  <img src="https://img.shields.io/badge/Deployment-Docker-blueviolet" />
  <img src="https://img.shields.io/badge/Status-Active-success" />
</p>
---

## 📌 Overview

SafeChat is an AI-powered secure communication system designed to:

- Detect phishing messages  
- Analyze suspicious URLs  
- Classify messages (safe/spam/phishing)  
- Automate responses and notifications  
- Route messages intelligently  

This system improves security, automation, and efficiency in communication workflows.

---

## 🧱 Project Features

### 🔐 1. Phishing Detection System
- Detects malicious emails/messages using ML  
- Identifies scams and threats  

### 🔗 2. URL Analysis Engine
- Checks if links are safe or suspicious  
- Prevents malicious redirection  

### 🤖 3. Machine Learning Classification
- Classifies messages into:
  - SAFE  
  - SPAM  
  - PHISHING  

### 🔀 4. Intelligent Routing
- Routes messages based on:
  - Content  
  - Priority  
  - Category  

### 📩 5. Messaging Automation
- Email parsing system  
- SMS generation  
- Notification triggers  

### 🌐 6. Web Application
- Frontend using HTML templates  
- Backend using Python  

### 🐳 7. Deployment Ready
- Docker support  
- Gunicorn configuration  

---

## 📂 Directory Structure

```bash
Safechat_Intelligent_Messaging_System/
│
├── ML_model/                      # Machine learning models
├── archived_docs/                 # Old documentation
├── static/                        # CSS, JS, assets
├── templates/                     # HTML templates
│
├── app.py                         # Main application
├── auth.py                        # Authentication system
├── notifier.py                    # Notification service
│
├── email_processor.py             # Email parsing logic
├── email_column_router.py         # Routing system
├── gmail_client.py                # Gmail API integration
│
├── phishing_detector.py           # Phishing detection model
├── url_analyzer.py                # URL safety analysis
├── sms_generator.py               # SMS automation
├── smsmlmodel.py                  # ML model for SMS classification
│
├── test.py                        # Testing scripts
│
├── config.toml                    # Configuration file
├── requirements.txt               # Dependencies
├── gunicorn.conf.py               # Gunicorn config
├── Dockerfile                     # Docker setup
├── docker-compose.yml             # Multi-container deployment
│
├── PROJECT_ARCHITECTURE_ALIGNED.md
├── PROJECT_FLOWCHART.md
├── METHODOLOGY_NLU_METADATA_DETAILS.md
└── CHANGELOG_PROJECT_UPDATES.md

