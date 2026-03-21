# Quick Reference: XAI Explainer Integration

## What Was Added

### 1. New REST API Endpoint
**Route:** `POST /api/explain_prediction`
**Location:** [app.py](app.py#L669)
**Purpose:** Returns SHAP explanations for email phishing detection

```python
# Example usage in frontend:
fetch('/api/explain_prediction', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({content: email_text})
})
```

### 2. Enhanced ML Dashboard Route
**Route:** `GET /ml_dashboard`
**Location:** [app.py](app.py#L339)
**Changes:**
- Initializes XAI explainer for user
- Generates SHAP explanations only for phishing predictions
- Passes `xai_explanations` to template
- Passes `xai_available` flag to template

### 3. Enhanced ML Dashboard Template
**File:** [templates/ml_dashboard.html](templates/ml_dashboard.html)
**Changes:**
- Added SHAP explanation section (lines 213-241)
- Added CSS styling (lines 74-159)
- Shows word-level analysis for phishing emails
- Displays "Analysis Unavailable" fallback for untrained models

---

## Key Features

✨ **Intelligent Display:**
- Only generates XAI for phishing predictions (not safe emails)
- Skips XAI if user model not trained
- Graceful error handling with logging

🎨 **Beautiful UI:**
- Blue info box for SHAP analysis
- Word tokens with impact scores
- Direction badges (red for phishing, green for safe)
- Responsive grid layout

🔐 **Non-Intrusive:**
- Isolated from existing code
- New API endpoint doesn't affect other routes
- No changes to data structures or pipelines

---

## Integration Points

### XAI Explainer Usage
The code uses the existing `XAIExplainer` class from [ML_model/xai_explainer.py](ML_model/xai_explainer.py):

```python
# Initialization (per user)
explainer = XAIExplainer(user_email)

# Get explanations for email text
explanations = explainer.explain_text(email_content, top_k=8)

# Returns list of dicts:
# [
#   {"token": "urgent", "impact": 0.0456, "direction": "phishing"},
#   {"token": "verify", "impact": 0.0382, "direction": "phishing"},
#   ...
# ]
```

### Data Flow
```
ML Dashboard Route
    ↓
Live Trainer (predictions)
    ↓
XAI Explainer (for phishing only)
    ↓
Template (displays both rule-based + SHAP)
```

---

## Configuration & Customization

### Adjust Top-K Words
To show more/fewer words in SHAP analysis:
```python
# In app.py line 395
xai_expl = xai_explainer.explain_text(email.get("content", ""), top_k=15)  # Change 8 to 15
```

### Change SHAP Box Colors
Edit CSS in [ml_dashboard.html](templates/ml_dashboard.html):
```css
.xai-shap-box {
    background: #f0f9ff;  /* Change this color */
    border: 2px solid #0284c7;  /* Change border color */
}
```

### Add Custom SHAP Visualization
The template can be extended with:
- Force plots (SHAP)
- Decision plots
- Waterfall charts
- Interaction plots

---

## REST Pipeline Preservation

✅ **Unchanged Routes:**
- Login/Signup/Logout
- Inbox/Mail/Mark Spam
- SMS Dashboard/Receiver
- Spam Dashboard
- Original Explain Endpoint

✅ **Unchanged Processing:**
- Gmail client
- Live trainer
- Email processor
- Phishing detector
- SMS ML model

---

## Error Handling

| Scenario | Response | Code |
|----------|----------|------|
| User not logged in | `{error: "Not logged in"}` | 401 |
| No email content | `{error: "No email content provided"}` | 400 |
| Model not found | `{error: "User model not found..."}` | 404 |
| XAI failure | Logged, falls back to no explanation | N/A |
| General error | `{error: "error message"}` | 500 |

---

## Performance Considerations

⚡ **Optimizations:**
- XAI only runs on phishing predictions (not safe)
- Uses existing trained model (no retraining)
- SHAP linear explainer (fast compared to SHAP deep)
- Top-K filtering (only show 8 important words)

---

## Testing the Integration

### 1. Login and train model
Navigate to `/ml_dashboard` with some emails

### 2. Test API endpoint
```bash
curl -X POST http://localhost:5000/api/explain_prediction \
  -H "Content-Type: application/json" \
  -d '{"content": "URGENT: Verify account or lose access"}'
```

### 3. Check ML Dashboard
- Phishing emails should show SHAP section
- Safe emails should NOT show SHAP
- Look for word-level analysis cards

### 4. Check logs
Should see messages like:
```
[XAI WARNING] XAI Explainer initialized successfully
[XAI WARNING] Successfully explained 3 phishing emails
```

---

## Integration with Other Systems

The new API endpoint can be used by:
- **Email forwarding services**: Get XAI explanations
- **Webhook consumers**: Receive SHAP analysis
- **Mobile apps**: Request explanations for alerts
- **Analytics dashboards**: Track which words flag phishing

Example webhook:
```python
def send_explanation_webhook(email_id, xai_explanations):
    webhook_data = {
        "email_id": email_id,
        "phishing_indicators": xai_explanations,
        "timestamp": datetime.now().isoformat()
    }
    # POST to webhook URL
```

---

## Files Modified Summary

| File | Lines | Changes |
|------|-------|---------|
| [app.py](app.py#L669) | 669-703 | New XAI API endpoint |
| [app.py](app.py#L339) | 339-460 | Enhanced ml_dashboard route |
| [ml_dashboard.html](templates/ml_dashboard.html#L74) | 74-159 | CSS styling for SHAP |
| [ml_dashboard.html](templates/ml_dashboard.html#L213) | 213-241 | SHAP explanation template |

---

## Next Steps

1. ✅ Test the integration with real emails
2. ✅ Monitor XAI performance with multiple users
3. ✅ Gather user feedback on explanations
4. Consider: Caching XAI results
5. Consider: Adding export functionality
6. Consider: Custom SHAP visualizations

---

## Documentation

See [XAI_INTEGRATION_SUMMARY.md](XAI_INTEGRATION_SUMMARY.md) for detailed architecture.
