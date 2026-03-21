# XAI Integration - Testing Guide

## Quick Start Testing

### 1. Test the ML Dashboard with SHAP Explanations

**Steps:**
1. Start the Flask app: `python app.py`
2. Navigate to `http://localhost:5000`
3. Login with your credentials
4. Go to **Inbox** → Get some emails
5. Navigate to **ML Dashboard**
6. Look for emails marked as "🚨 Phishing"

**Expected Results:**
- Phishing emails show two explanation sections:
  1. **Rule-based** (existing): "Why was this classified?"
  2. **SHAP-based** (new): "SHAP Word-Level Analysis"
- Safe emails show only rule-based section
- Words have impact scores and direction labels

---

## API Endpoint Testing

### 2. Test `/api/explain_prediction` Endpoint

#### Using cURL
```bash
# First, login and get session cookie
curl -c cookies.txt -d "email=test@example.com&password=yourpass" http://localhost:5000/login

# Then call the API with the session
curl -b cookies.txt \
  -X POST http://localhost:5000/api/explain_prediction \
  -H "Content-Type: application/json" \
  -d '{
    "content": "URGENT: Your PayPal account has been suspended. Click here immediately to verify your identity and restore access."
  }'
```

#### Expected Response
```json
{
  "success": true,
  "explanations": [
    {
      "token": "urgent",
      "impact": 0.0456,
      "direction": "phishing"
    },
    {
      "token": "suspended",
      "impact": 0.0382,
      "direction": "phishing"
    },
    {
      "token": "verify",
      "impact": 0.0298,
      "direction": "phishing"
    },
    {
      "token": "click",
      "impact": 0.0267,
      "direction": "phishing"
    }
  ]
}
```

#### Error Cases
```bash
# Not logged in
curl -X POST http://localhost:5000/api/explain_prediction \
  -H "Content-Type: application/json" \
  -d '{"content": "test"}'

# Response: 401 Unauthorized
# {"error": "Not logged in"}

# No content provided
curl -b cookies.txt \
  -X POST http://localhost:5000/api/explain_prediction \
  -H "Content-Type: application/json" \
  -d '{}'

# Response: 400 Bad Request
# {"error": "No email content provided"}

# Model not trained yet
# Response: 404 Not Found
# {"error": "User model not found. Train model first."}
```

---

## Manual Testing Scenarios

### Scenario 1: Phishing Email
**Input:** 
```
Subject: URGENT ACTION REQUIRED
Content: Your bank account has been compromised. Click here immediately to verify your identity. This is a security alert.
```

**Expected Output:**
- Prediction: 🚨 Phishing (high confidence)
- SHAP Section: Shows words like "urgent", "compromised", "verify", "security"
- Direction: All marked as "phishing" (red badges)

### Scenario 2: Legitimate Email
**Input:**
```
Subject: Your Order Confirmation
Content: Thank you for your purchase. Your order has been confirmed and will be shipped within 2 business days.
```

**Expected Output:**
- Prediction: ✅ Safe (high confidence)
- SHAP Section: NOT SHOWN (optimization - no XAI for safe emails)
- Efficiency: Dashboard loads faster

### Scenario 3: Untrained Model
**Input:** Fresh user account with no training data

**Expected Output:**
- Prediction: Generic prediction from base model
- SHAP Section: Shows "SHAP Analysis Unavailable"
- Message: "User model not yet trained with enough data"

---

## Visual Inspection Checklist

### ✅ Layout & Styling
- [ ] Email cards have light yellow background
- [ ] SHAP box has light blue background (#f0f9ff)
- [ ] Title is dark blue and bold
- [ ] Word tokens are in blue
- [ ] Impact scores are right-aligned
- [ ] Direction badges are clearly visible
- [ ] Phishing badges are red (#fecaca)
- [ ] Safe badges are green (#bbf7d0)
- [ ] Responsive on mobile view

### ✅ Functionality
- [ ] SHAP section only shows for phishing
- [ ] Safe emails don't have SHAP section
- [ ] Words sorted by impact (highest first)
- [ ] Top 8 words shown (configurable)
- [ ] No JavaScript errors in console
- [ ] No 404s in network tab
- [ ] Explanations load within 2 seconds

### ✅ Content Quality
- [ ] Words are real (not tokenization artifacts)
- [ ] Impact scores are reasonable (0.0001-0.5)
- [ ] Direction labels match word semantics
- [ ] Multiple high-impact words identified
- [ ] Explanations are human-readable

---

## Performance Testing

### Test 1: Load Time
```javascript
// Open browser console and run:
console.time('ml-dashboard');
fetch('/ml_dashboard').then(() => {
  console.timeEnd('ml-dashboard');
});

// Expected: < 2 seconds
```

### Test 2: SHAP Generation
```javascript
// Measure XAI generation time
console.time('xai-generation');
fetch('/api/explain_prediction', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({content: 'long email text here'})
}).then(() => {
  console.timeEnd('xai-generation');
});

// Expected: < 500ms per email
```

### Test 3: Memory Usage
```javascript
// Check memory before/after XAI
performance.memory.usedJSHeapSize;  // Before
// ... Generate explanations ...
performance.memory.usedJSHeapSize;  // After

// Expected: < 50MB increase
```

---

## Regression Testing

### ✅ Verify Existing Functionality Not Broken

#### Authentication
```bash
# Test login
curl -X POST http://localhost:5000/login \
  -d "email=test@example.com&password=testpass"
# Expected: Redirect to inbox or error page

# Test signup
curl -X POST http://localhost:5000/signup \
  -d "email=new@example.com&password=newpass"
# Expected: Redirect to login
```

#### Email Processing
```bash
# Load inbox
curl -b cookies.txt http://localhost:5000/inbox
# Expected: Email list loads

# Mark as spam
curl -b cookies.txt -X POST http://localhost:5000/mark_spam/email123
# Expected: Email removed from inbox
```

#### SMS Dashboard
```bash
# Load SMS dashboard
curl -b cookies.txt http://localhost:5000/sms_dashboard
# Expected: SMS list loads

# Receive SMS
curl -X POST http://localhost:5000/receive_sms \
  -H "Content-Type: application/json" \
  -d '{"sender":"+1234567890","content":"Test message"}'
# Expected: SMS saved and classified
```

#### Spam Dashboard
```bash
# Load spam dashboard
curl -b cookies.txt http://localhost:5000/spam_dashboard
# Expected: Spam list loads
```

---

## Debugging Guide

### Issue: SHAP Section Not Showing

**Checks:**
1. Is email predicted as "Phishing"?
   ```javascript
   // Check prediction in template
   email.prediction === "Phishing"  // Should be true
   ```

2. Is XAI available?
   ```javascript
   // Check in template
   xai_available === true  // Should be true
   ```

3. Are explanations present?
   ```javascript
   // Check in browser console
   email.xai_explanations.length > 0  // Should be > 0
   ```

**Solution:**
```python
# Check server logs
# Look for messages like:
# [XAI WARNING] XAI Explainer initialized
# [XAI WARNING] Successfully explained email X
# [XAI WARNING] XAI Explainer initialization failed: ...
```

### Issue: API Returns 404 Error

**Cause:** User model not trained

**Solution:**
1. Go to ML Dashboard first to train model
2. Then call API endpoint

```python
# In server logs you should see:
# [XAI WARNING] Successfully explained email 0
```

### Issue: Slow SHAP Generation

**Checks:**
1. Number of emails being explained
2. Email content length
3. Model complexity

**Solution:**
```python
# Reduce top_k to 5
xai_expl = xai_explainer.explain_text(content, top_k=5)

# Or skip SHAP for very long emails
if len(email_content) < 5000:  # Add length check
    xai_expl = xai_explainer.explain_text(content)
```

---

## Browser Console Monitoring

### Expected Logs
```javascript
// No errors
// No 404s for static assets
// No CORS issues
// No "undefined" references
```

### Check in DevTools Network Tab
```
✅ GET /ml_dashboard - 200 OK
✅ GET /static/css/style.css - 200 OK
✅ GET /static/js/script.js - 200 OK
```

---

## Test Email Samples

### High Confidence Phishing
```
Subject: VERIFY ACCOUNT NOW
Content: Your Amazon account has been limited due to unusual activity. 
Click here immediately to restore access: http://suspicious-link.com
Verification required within 24 hours or account will be suspended.
```

### High Confidence Legitimate
```
Subject: Order #12345 Confirmation
Content: Thank you for your order. Your payment has been received.
Your items will be shipped within 2 business days.
Order details: [Order info]
```

### Medium Confidence (Edge Case)
```
Subject: Important Update
Content: We're updating our security features to better protect your account.
You may need to verify your information again during login.
```

---

## Success Criteria

### ✅ All Tests Pass If:
1. Phishing emails show SHAP analysis
2. Safe emails hide SHAP section
3. SHAP words are readable and relevant
4. API endpoint returns correct JSON
5. Dashboard loads within 2 seconds
6. Existing routes still work
7. No JavaScript errors in console
8. No database errors in logs
9. Session management works
10. User can logout and login again

---

## Troubleshooting Commands

```bash
# Check Flask errors
python app.py 2>&1 | grep -i "error\|warning\|xai"

# Test XAI explainer directly
python -c "
from ML_model.xai_explainer import XAIExplainer
try:
    xai = XAIExplainer('test@example.com')
    result = xai.explain_text('urgent verify account now')
    print('XAI Working:', result)
except Exception as e:
    print('XAI Error:', e)
"

# Check model files exist
ls -la ML_model/model_*.pkl
ls -la ML_model/vectorizer_*.pkl

# Monitor logs in real-time
tail -f app.log | grep -i "xai\|warning"
```

---

## Sign-Off Checklist

- [ ] XAI displays on phishing emails
- [ ] Safe emails skip XAI (no overhead)
- [ ] API endpoint functional
- [ ] Existing routes work
- [ ] No console errors
- [ ] Styling matches design
- [ ] Performance acceptable
- [ ] Mobile responsive
- [ ] Error handling works
- [ ] Documentation complete

🎉 **Ready for Production!**
