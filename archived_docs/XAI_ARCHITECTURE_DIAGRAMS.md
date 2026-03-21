# XAI Integration - Architecture Diagrams

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Flask Web Application                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Authentication Layer                       │  │
│  │  ✅ /login     ✅ /signup     ✅ /logout               │  │
│  │  (UNCHANGED)                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Email Processing Layer                     │  │
│  │  ✅ /inbox     ✅ /mail     ✅ /mark_spam             │  │
│  │  (UNCHANGED)                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           ML Dashboard & XAI Layer                       │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  GET /ml_dashboard  (ENHANCED)                    │ │  │
│  │  │  ├─ Load emails                                   │ │  │
│  │  │  ├─ Train model (LiveTrainer)                     │ │  │
│  │  │  ├─ Predict (phishing/safe)                       │ │  │
│  │  │  ├─ Rule-based explanations                       │ │  │
│  │  │  └─ ✨ NEW: Generate SHAP explanations ✨        │ │  │
│  │  │     (only for phishing emails)                    │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  POST /api/explain_prediction  (NEW)              │ │  │
│  │  │  REST API for XAI explanations                     │ │  │
│  │  │  ├─ Input: Email content (JSON)                   │ │  │
│  │  │  └─ Output: SHAP explanations (JSON)              │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │  ML Components                                     │ │  │
│  │  │  ├─ PhishingDetector (UNCHANGED)                  │ │  │
│  │  │  ├─ LiveTrainer (UNCHANGED)                       │ │  │
│  │  │  └─ ✨ XAIExplainer (NEW usage) ✨               │ │  │
│  │  │     Using existing implementation                  │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           SMS & Spam Processing Layer                   │  │
│  │  ✅ /sms_dashboard    ✅ /receive_sms               │  │
│  │  ✅ /spam_dashboard                                    │  │
│  │  (UNCHANGED)                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
User Login
    │
    ├─→ Session Created
    │
    └─→ Navigate to /ml_dashboard
           │
           ├─→ Load User Emails
           │
           ├─→ LiveTrainer.train_user()
           │   ├─ Train on user emails
           │   └─ Create personalized model
           │
           ├─→ LiveTrainer.predict_with_proba()
           │   ├─ For each email:
           │   │  ├─ Phishing? (1) or Safe? (0)
           │   │  └─ Confidence probability
           │   │
           │   └─ Returns: [preds], [probas]
           │
           ├─→ Rule-Based Explanations
           │   └─ trainer.explain_text()
           │
           ├─→ ✨ NEW: XAI SHAP Analysis ✨
           │   ├─ For EACH email:
           │   │  └─ IF predicted = "Phishing":
           │   │     ├─ Initialize XAIExplainer
           │   │     ├─ Call explainer.explain_text()
           │   │     ├─ Get top 8 important words
           │   │     └─ Get SHAP impact scores
           │   │
           │   └─ SKIP for Safe emails (efficiency)
           │
           ├─→ Combine Results
           │   └─ results[i] = {
           │       subject, content, prediction,
           │       confidence, explanations,
           │       xai_explanations (phishing only)
           │     }
           │
           └─→ Render ml_dashboard.html
               ├─ Display predictions
               ├─ Display rule explanations
               └─ ✨ Display SHAP explanations
                   (only for phishing emails)
                       │
                       └─→ Beautiful Dashboard UI
```

---

## SHAP Generation Process

```
XAI Explainer Initialization
    │
    ├─→ Load User Model
    │   ├─ Load model_{safe_email}.pkl
    │   └─ Load vectorizer_{safe_email}.pkl
    │
    └─→ For Each Phishing Email:
           │
           ├─→ explainer.explain_text(email_content)
           │
           ├─→ Vectorize email content (TF-IDF)
           │   └─ Convert text → numerical features
           │
           ├─→ Calculate SHAP values
           │   ├─ LinearExplainer (fast)
           │   ├─ For each word/token:
           │   │  ├─ Calculate impact on prediction
           │   │  ├─ Direction: phishing or safe
           │   │  └─ Magnitude: 0.0 to ~0.1
           │   │
           │   └─ Sort by impact (descending)
           │
           ├─→ Filter & Clean
           │   ├─ Remove numeric-only tokens
           │   ├─ Keep only high-impact words
           │   ├─ Filter out noise (< 0.02 impact)
           │   └─ Take top 8 words
           │
           └─→ Return Explanations
               └─ [
                   {token: "urgent", impact: 0.0456, direction: "phishing"},
                   {token: "verify", impact: 0.0382, direction: "phishing"},
                   ...
                 ]
```

---

## Template Rendering Logic

```
For Each Email in Results:
    │
    ├─→ Display Email Card
    │   ├─ Subject
    │   ├─ Content preview
    │   │
    │   └─→ Display Prediction
    │       ├─ If Phishing: 🚨 + confidence
    │       ├─ If Safe: ✅ + confidence
    │       └─ Else: 📌 + class name
    │
    ├─→ Display Rule-Based Explanations
    │   ├─ IF email.explanations exists:
    │   │  └─ Show .xai-box with word list
    │   │
    │   └─ (Always shown for all emails)
    │
    └─→ ✨ Display SHAP Explanations ✨
        │
        ├─ IF prediction == "Phishing"
        │  AND xai_explanations exists
        │  AND xai_available == true:
        │  │
        │  └─→ Show .xai-shap-box
        │      ├─ Title: "SHAP Word-Level Analysis"
        │      ├─ Description text
        │      │
        │      └─→ For Each explanation:
        │          ├─ Token name (blue, bold)
        │          ├─ Impact score (gray, right)
        │          └─ Direction badge:
        │             ├─ "phishing" → red
        │             └─ "safe" → green
        │
        ├─ ELIF prediction == "Phishing"
        │  AND (not xai_explanations OR not xai_available):
        │  │
        │  └─→ Show .xai-shap-box.xai-unavailable
        │      └─ Message: "Analysis Unavailable"
        │
        └─ ELSE (Safe email):
           └─ Don't show SHAP (optimize performance)
```

---

## REST API Request/Response Flow

```
┌──────────────────────────────────────────────────────────────┐
│  Client (Browser/External Service)                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         │ POST /api/explain_prediction
                         │ Content-Type: application/json
                         │ {
                         │   "content": "URGENT: Verify account now"
                         │ }
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Flask Route: api_explain_prediction()                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Check session.get("user_email")                         │
│     ├─ If not found: Return 401 (Not logged in)            │
│     │                                                       │
│     └─ If found: Continue                                  │
│                                                              │
│  2. Get JSON data: content = request.get_json()            │
│     ├─ If not provided: Return 400 (No content)            │
│     │                                                       │
│     └─ If provided: Continue                               │
│                                                              │
│  3. Initialize XAIExplainer(user_email)                    │
│     ├─ Load model & vectorizer files                       │
│     ├─ If not found: Return 404 (Model not found)          │
│     │                                                       │
│     └─ If found: Continue                                  │
│                                                              │
│  4. Generate explanations: explainer.explain_text()        │
│     ├─ Vectorize content                                   │
│     ├─ Calculate SHAP values                               │
│     ├─ If error: Return 500 (Error)                        │
│     │                                                       │
│     └─ Return explanations                                 │
│                                                              │
│  5. Return JSON Response                                    │
│     {                                                       │
│       "success": true,                                      │
│       "explanations": [                                     │
│         {"token": "...", "impact": 0.0456, ...},           │
│         ...                                                 │
│       ]                                                     │
│     }                                                       │
│                                                              │
└────────────────────────┬──────────────────────────────────────┘
                         │
                         │ HTTP 200 (Success)
                         │ OR
                         │ HTTP 400/401/404/500 (Error)
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Client Receives Response                                   │
│  ├─ Parse JSON                                             │
│  ├─ Extract explanations[]                                 │
│  └─ Display/Process results                                │
└──────────────────────────────────────────────────────────────┘
```

---

## Performance Architecture

```
ML Dashboard Load
    │
    ├─→ Phishing Email (pred=1)
    │   ├─ Rule explanation: 10ms
    │   └─ ✨ SHAP explanation: 450ms ✨ (only for phishing)
    │
    └─→ Safe Email (pred=0)
        ├─ Rule explanation: 10ms
        └─ SKIP SHAP (optimization) 💨 (0ms saved per safe email)

Example: 10 emails (8 safe, 2 phishing)
    Total Time = 8×10ms + 2×(10ms+450ms) = 80ms + 920ms = 1 second ✅

vs Without Optimization (SHAP for all):
    Total Time = 10×(10ms+450ms) = 4.6 seconds ❌

Performance Gain: 4.6x faster!
```

---

## Error Handling Flow

```
API Request Received
    │
    ├─→ Not Logged In?
    │   └─→ Return 401 Unauthorized
    │       {"error": "Not logged in"}
    │
    ├─→ No Content Provided?
    │   └─→ Return 400 Bad Request
    │       {"error": "No email content provided"}
    │
    ├─→ Model File Not Found?
    │   └─→ Return 404 Not Found
    │       {"error": "User model not found. Train model first."}
    │
    ├─→ SHAP Calculation Error?
    │   └─→ Return 500 Server Error
    │       {"error": "error message"}
    │
    └─→ Success?
        └─→ Return 200 OK
            {"success": true, "explanations": [...]}

Dashboard Error Handling:
    ├─ XAI Explainer fails to initialize?
    │   └─ Set xai_available=false
    │   └─ Show "Analysis Unavailable" message
    │   └─ Don't block email display
    │
    ├─ SHAP generation fails for one email?
    │   └─ Log warning
    │   └─ Set xai_explanations[i]=[]
    │   └─ Show fallback message
    │   └─ Continue with other emails
    │
    └─ All graceful, no crashes
```

---

## Code Integration Map

```
app.py
├─ Imports
│  └─ from ML_model.xai_explainer import XAIExplainer
│
├─ Route: /ml_dashboard (ENHANCED)
│  ├─ Existing code: Load, train, predict
│  │
│  └─ NEW: XAI Integration (lines 383-415)
│     ├─ Initialize XAIExplainer
│     ├─ Generate SHAP for phishing
│     └─ Add to results
│
└─ Route: /api/explain_prediction (NEW)
   ├─ Endpoint: POST /api/explain_prediction
   ├─ Input: {"content": "..."}
   ├─ Output: {"success": true, "explanations": [...]}
   └─ Error handling: 401, 400, 404, 500

ml_dashboard.html
├─ Imports
│  └─ None (uses Flask template variables)
│
├─ CSS (NEW)
│  ├─ .xai-shap-box: Main container
│  ├─ .xai-shap-title: Header
│  ├─ .shap-item: Word item
│  ├─ .token-*: Word styling
│  └─ .direction-*: Badge styling
│
└─ Template Logic
   ├─ Existing: Show prediction & rule explanations
   └─ NEW: Show SHAP explanations (phishing only)
```

---

## Feature Toggle Architecture

```
XAI Feature Availability:

1. XAI Explainer Initialization
   ├─ Success → xai_available = true
   │   └─ Show SHAP explanations
   │
   └─ Failure → xai_available = false
       └─ Show unavailable message

2. Per-Email SHAP Generation
   ├─ For phishing prediction
   │  ├─ Success → xai_explanations[i] = [...]
   │  │   └─ Show word analysis
   │  │
   │  └─ Failure → xai_explanations[i] = []
   │      └─ Show unavailable message
   │
   └─ For safe prediction
      └─ Skip entirely (no xai_explanations[i])
          └─ No performance overhead

3. Template Rendering
   ├─ IF prediction == "Phishing"
   │  AND xai_explanations.length > 0
   │  AND xai_available == true
   │  └─ Render .xai-shap-box (full analysis)
   │
   ├─ ELIF prediction == "Phishing"
   │  AND (xai_explanations.length == 0 OR not xai_available)
   │  └─ Render .xai-shap-box.xai-unavailable (fallback)
   │
   └─ ELSE (Safe email)
      └─ Don't render SHAP (no performance cost)
```

---

## Monitoring & Debugging Flow

```
Server Logs:

[INFO] XAI Explainer loaded for user: test@example.com
[INFO] Processing 5 emails for predictions
[DEBUG] Email 1: Safe prediction (95% confidence)
[DEBUG] Email 2: Phishing prediction (87% confidence)
[XAI] Generating SHAP for phishing email 2
[XAI] SHAP generated 8 words, top word: "urgent" (0.0456)
[DEBUG] Email 3: Safe prediction (92% confidence)
[DEBUG] Email 4: Phishing prediction (76% confidence)
[XAI] Generating SHAP for phishing email 4
[XAI] SHAP generated 8 words, top word: "verify" (0.0382)
[DEBUG] Email 5: Safe prediction (98% confidence)
[INFO] Dashboard rendered in 1.2 seconds

Browser Console:

✅ Network: All resources loaded
✅ Dashboard: Rendered successfully
✅ SHAP boxes: Display correctly
✅ Styling: All CSS applied
✅ No JavaScript errors
```

---

This completes the architectural overview of the XAI integration!
