# 📱 SMS Self-Generator with XAI Integration

## Overview
The SMS dashboard has been transformed into a **self-generating SMS detector** that:
1. ✅ **Generates realistic SMS messages** (phishing & legitimate) on demand
2. ✅ **Predicts phishing status** using ML model with confidence scores
3. ✅ **Explains predictions** with XAI (SHAP + fallback word-frequency analysis)
4. ✅ **Displays statistics** (total SMS, spam count, safe count)
5. ✅ **Clears old SMS** when generating new ones (replaces all)

---

## Architecture

### Components

#### 1. **SMS Generator** (`sms_generator.py`)
Creates realistic SMS messages with proper formatting.

**Templates:**
- **15 Phishing SMS:** Account verification, payment confirmation, package delivery, bank alerts, etc.
- **15 Legitimate SMS:** Order confirmations, appointments, flights, deliveries, etc.

**Features:**
- Random mix of phishing and legitimate messages
- Realistic sender IDs (phone numbers for phishing, service names for legitimate)
- Timestamps from last 7 days
- Proper SMS formatting

**Usage:**
```python
from sms_generator import SMSGenerator

gen = SMSGenerator()
sms_list = gen.generate_sms(count=15)  # Returns list of SMS dicts
# Each SMS has: content, sender, timestamp, label
```

#### 2. **Flask Routes** (`app.py`)

**Route: `/sms_dashboard`**
- Displays all generated SMS with ML predictions
- Shows XAI explanations for spam SMS
- Displays statistics (total, spam, safe counts)
- Loads from `ML_model/sms_incoming.pkl`

**Endpoint: `/api/generate_sms` (POST)**
- Accepts `count` parameter (default 10)
- Generates new SMS using SMSGenerator
- **Overwrites existing SMS** in pkl file
- Predicts each SMS with ML model
- Adds XAI explanations for spam SMS
- Returns JSON with statistics

**Workflow:**
```
User clicks "Generate New SMS" button
    ↓
POST /api/generate_sms with count=15
    ↓
SMSGenerator creates 15 random SMS
    ↓
Save to ML_model/sms_incoming.pkl (overwrites)
    ↓
Predict each SMS (Spam/Safe with confidence)
    ↓
Generate XAI explanations for spam
    ↓
Return JSON stats
    ↓
JavaScript reloads page to show new SMS
```

#### 3. **ML Pipeline**

**Prediction:**
- Uses `LiveTrainer` with user-specific or base model
- Returns prediction (0=Safe, 1=Spam) + probability
- Confidence = max(probability) * 100

**XAI Explanation (3-Tier System):**
1. **Tier 1 - SHAP:** If vocabulary matches (X.nnz > 0)
   - Returns SHAP values for important words
   - Shows impact scores and direction

2. **Tier 2 - Fallback:** If no vocabulary matches
   - Word-frequency analysis
   - Detects ~30 phishing keywords
   - Returns words with calculated impact scores

3. **Tier 3 - Empty:** Graceful return if analysis fails

**Phishing Keywords Detected:**
verify, confirm, urgent, click, account, password, security, update, activate, payment, immediate, action, suspended, unusual, suspicious, freeze, limit, problem, issue, claim, winner, prize, congratulations, reset, login, authorize, validate, alert, fraud, compromise, breach, approval, pending, expire, unblock, unlock, restricted, required

---

## Frontend (`templates/sms_dashboard.html`)

### Features

**Header Section:**
- Title: "📊 Generated SMS Analysis"
- Statistics display (Total, Spam, Safe)
- "🔄 Generate New SMS" button

**SMS Display:**
- **Sender & Timestamp:** Displayed at top of each SMS card
- **Prediction Badge:** Shows "🚨 SPAM" or "✅ SAFE" with confidence %
- **Content:** SMS text in italicized box
- **XAI Section:** For spam SMS, shows:
  - List of detected words
  - Impact scores (importance)
  - Direction (PHISHING or SAFE)

**Design:**
- Color-coded cards (red for spam, green for safe)
- Responsive layout
- Hover effects for better UX
- Statistics update automatically

### JavaScript Functions

**`generateNewSMS()`**
```javascript
async function generateNewSMS() {
    // POST to /api/generate_sms with count=15
    // Shows loading state
    // Reloads page on success
}
```

**Auto-reload on Generate:**
After generation completes, page reloads to show new SMS with predictions and explanations.

---

## Data Flow

### Generation Request
```
User → Browser → JavaScript → fetch(/api/generate_sms)
                     ↓
         Flask App → SMSGenerator.generate_sms(15)
                     ↓
         Save to sms_incoming.pkl
         Predict each SMS
         Generate XAI explanations
                     ↓
         Return JSON → Browser reloads page
```

### Display
```
User loads /sms_dashboard
         ↓
Flask reads sms_incoming.pkl
         ↓
For each SMS:
  - Normalize fields
  - Predict (Spam/Safe + confidence)
  - If Spam: Get XAI explanations
         ↓
Pass to template with statistics
         ↓
HTML renders SMS cards with predictions and XAI
```

---

## File Structure

```
phishing_project_full/
├── app.py                          # Flask app with routes
├── sms_generator.py                # SMS generation logic
├── ML_model/
│   ├── xai_explainer.py           # XAI with 3-tier system
│   ├── live_trainer.py            # ML prediction
│   └── sms_incoming.pkl           # Generated SMS storage
└── templates/
    └── sms_dashboard.html         # Enhanced dashboard
```

---

## Usage Guide

### 1. **Access SMS Dashboard**
Navigate to `/sms_dashboard` in the web app

### 2. **Generate New SMS**
Click "🔄 Generate New SMS" button
- Generates 15 random SMS (mix of phishing & legitimate)
- Predicts each one
- Adds XAI explanations
- Page reloads to show results

### 3. **View Predictions**
Each SMS card shows:
- **Sender:** Who sent the SMS
- **Timestamp:** When it was sent
- **Prediction:** "🚨 SPAM" or "✅ SAFE"
- **Confidence:** How sure the model is (0-100%)

### 4. **Understand XAI**
For spam SMS, scroll down to see:
- **Detected Keywords:** Words that indicate phishing
- **Impact Scores:** How much each word contributes (0.0-1.0)
- **Direction:** Whether it points to PHISHING or SAFE

### 5. **Generate More SMS**
Click "Generate New SMS" again
- **Overwrites** previous SMS
- Generates fresh set
- Clears dashboard
- Shows new predictions

---

## Configuration

### SMS Count
Default: 15 SMS per generation
To change, modify in `templates/sms_dashboard.html`:
```javascript
// Line: generateNewSMS() call
body: JSON.stringify({count: 15})  // Change 15 to desired number
```

### XAI Top-K
Default: Show top 5 explanations per SMS
To change, modify in `app.py`:
```python
xai_expl = xai_explainer.explain_text(text, top_k=5)  # Change 5
```

### Phishing Keywords
Modify in `ML_model/xai_explainer.py`:
```python
self.phishing_keywords = {
    "verify", "confirm", "urgent", ...  # Add/remove keywords
}
```

---

## Error Handling

### Graceful Degradation
- **No Model:** Falls back to rule-based analysis
- **No Vocabulary Matches:** Uses word-frequency fallback
- **XAI Unavailable:** Skips explanations, still shows predictions
- **Generation Error:** Shows error message, doesn't crash

### Logging
All operations logged with [SMS] tags:
```
[SMS] Loaded 15 SMS messages with predictions
[SMS GEN] Generating 15 SMS messages...
[SMS] SMS 0: Got 5 XAI explanations
```

---

## Testing

### Test SMS Generation
```bash
cd f:\phishing_project_full
python -c "from sms_generator import SMSGenerator; \
           gen = SMSGenerator(); \
           sms = gen.generate_sms(3); \
           print(sms)"
```

### Test XAI
```bash
python -c "from ML_model.xai_explainer import XAIExplainer; \
           xai = XAIExplainer('test@example.com'); \
           exp = xai.explain_text('Click here to verify'); \
           print(exp)"
```

### Test Full Flow
1. Open browser → `/sms_dashboard`
2. Click "Generate New SMS"
3. Wait for page reload
4. Verify SMS displayed with predictions
5. Check XAI explanations for spam SMS

---

## Success Indicators

✅ **SMS Generation Works**
- 15 random SMS created
- Mix of phishing and legitimate
- Realistic senders and timestamps

✅ **Predictions Accurate**
- Phishing SMS marked as Spam
- Legitimate SMS marked as Safe
- Confidence scores 0-100%

✅ **XAI Explanations Clear**
- Phishing keywords detected
- Impact scores calculated
- Direction (PHISHING/SAFE) shown

✅ **Dashboard Updates**
- Statistics show correct counts
- Old SMS cleared on new generation
- No crashes or errors

---

## Future Enhancements

1. **Batch Operations:** Generate different counts per request
2. **SMS Filtering:** Filter by spam/safe in dashboard
3. **Explanation Export:** Export XAI results to CSV
4. **Pattern Analysis:** Show common phishing patterns
5. **Performance Tuning:** Cache frequently analyzed SMS
6. **Multi-user Support:** Separate SMS per user

---

## Support

For issues or questions:
1. Check the [SMS] logging output
2. Verify `sms_incoming.pkl` exists
3. Ensure XAIExplainer initializes correctly
4. Check Flask app startup for errors

---

**Last Updated:** January 29, 2026
**Status:** ✅ Production Ready
