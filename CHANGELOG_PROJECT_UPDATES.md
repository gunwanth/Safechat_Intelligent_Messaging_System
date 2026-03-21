# Project Update Log

This file captures major changes implemented in recent and older iterations.

## Recent Updates (Latest Work)

### Robust ML Detection + NLU Enhancements
- Added robust message analysis for ML detection using NLU-style signal tracking instead of only keyword-level indicators.
- Added `analyze_message_nlu()` and integrated it into ML dashboard result processing.
- Added URL-preserving NLU preprocessing (`sanitize_text_for_nlu`) to keep raw URL evidence for analysis.
- Tightened regex grouping in NLU patterns to reduce false matches.
- Added optional fused risk scoring for controlled experiments:
  - `fused_risk = alpha * ml_risk + beta * nlu_risk`
  - Controlled by environment variables:
    - `ENABLE_FUSED_RISK`
    - `FUSED_RISK_ALPHA`
    - `FUSED_RISK_BETA`
- Updated ML dashboard UI to display:
  - NLU risk score
  - Major NLU signals (impact + hit count)
  - Optional fused risk (when enabled)

Files:
- `app.py`
- `templates/ml_dashboard.html`

## Older Updates (Earlier Iterations)

### Metadata Pipeline Timeline (From Start to Current)
- **Phase 1: NLU Signal Layer Added**
  - Introduced `analyze_message_nlu()` for intent-pattern risk scoring.
  - Added major phishing signal groups (credential theft, urgency, financial manipulation, security narrative, lure narrative, link trigger).
  - Added `nlu_summary` into ML dashboard result objects.

- **Phase 2: URL-Aware NLU + Regex Hardening**
  - Added `sanitize_text_for_nlu()` to preserve URL evidence and URL-derived tokens.
  - Tightened regex grouping to reduce false positive matches.
  - Added `phishing_probability_pct()` to map confidence to phishing-class probability more consistently.

- **Phase 3: Fused Risk (Optional)**
  - Added optional `fused_risk = alpha * ml_risk + beta * nlu_risk`.
  - Added env controls:
    - `ENABLE_FUSED_RISK`
    - `FUSED_RISK_ALPHA`
    - `FUSED_RISK_BETA`
  - Displayed fused risk on ML dashboard when enabled.

- **Phase 4: Metadata Enrichment + Optional Transformer NLU**
  - Added metadata extraction (`_extract_nlu_metadata`) with URL, shortener, IP-host, money, CTA, and text-shape features.
  - Added optional transformer NLU intent inference (`_transformer_nlu_inference`) with local model fallback behavior.
  - Added model-vs-baseline-vs-enhanced accuracy strip in ML dashboard.

- **Phase 5: Receive-Time Metadata Persistence**
  - In `/inbox`, each incoming email now stores:
    - `nlu_summary`
    - `metadata_score`
    - `metadata_level`
  - Backfilled missing metadata fields for previously stored emails in inbox state.
  - Added metadata score + major pattern analysis display directly on inbox cards.

- **Phase 6: Metadata-First Scoring Before Dashboard**
  - Added `metadata_first_score()` that combines NLU score + metadata heuristics (+ optional transformer signals and rule score).
  - Added optional metadata-first decision behavior in ML dashboard:
    - Can override low-confidence Safe to Phishing when metadata risk is very high.
  - Added env controls:
    - `ENABLE_METADATA_FIRST_SCORING`
    - `METADATA_FORCE_PHISH_THRESHOLD`
    - `METADATA_FORCE_PHISH_MAX_CONF`

- **Phase 7: Metadata Trainer + Artifact Persistence + Reports**
  - Added `ML_model/metadata_trainer.py` for training and persistence of:
    - baseline text model artifacts
    - metadata-augmented model artifacts
    - metadata scaler/config artifacts
  - Added JSON + Markdown metrics reports per user:
    - `ML_model/metrics_report_<user>.json`
    - `ML_model/metrics_report_<user>.md`
  - Added optional auto-train trigger in dashboard flow:
    - `AUTO_TRAIN_METADATA_ARTIFACTS`

- **Phase 8: Configurable Labeling Mode (Latest)**
  - Added label mode support to avoid single-class skips on live inbox:
    - `strict_high`: only High => phishing
    - `medium_high`: Medium/High => phishing
  - Default set to `medium_high` in app + metadata trainer.
  - Reports now include `label_mode` for traceability.

Files:
- `app.py`
- `ML_model/metadata_trainer.py`
- `templates/ml_dashboard.html`
- `templates/inbox.html`

### Login/Signup UI Cleanup
- Removed unwanted header/nav bar around login screen.
- Removed unwanted background characters near login panel.
- Removed navbar/header in signup page.

Files:
- `templates/login.html`
- `templates/signup.html` (if present in this project layout)

### Inbox Layout + Column Handling
- Fixed inbox message overflow where email text crossed inner column boundaries.
- Improved message fitting in inbox and column bars to reduce extra spacing.
- Added Gmail-like column structure:
  - Primary
  - Promotions
  - Social
  - Purchases
- Added routing logic to place incoming emails into relevant columns automatically.
- Ensured Primary contains all emails while secondary tabs contain category-specific subsets.
- Added delete-email routing behavior in columns:
  - Delete from a secondary column removes from that column view.
  - Delete from Primary deletes email from storage/database state.

Files:
- `app.py`
- `templates/inbox.html`
- `email_column_router.py`

### Message Routing / Classification Utility
- Created/updated separate routing logic file for incoming messages to improve column assignment quality based on message content.

Files:
- `email_column_router.py`

### SMS Generation + ML Pipeline
- Improved SMS generation to reduce repeated template patterns.
- Ensured generated SMS passes through ML prediction flow.
- Worked on preserving/validating model accuracy behavior for generated and saved messages.

Files:
- `sms_generator.py`
- `smsmlmodel.py`

### Accuracy / Evaluation Tasks
- Ran checks for:
  - Base model accuracy
  - ML model accuracy
  - Labeled plug/sample alignment checks
  - SHAP/XAI-related explanation quality checks
- Performed repeated validation runs against saved and real-time email data.

Files:
- `ML_model/xai_explainer.py`
- `app.py`

### Auth Flow Improvement: Forgot Password
- Added forgot-password flow to update credentials.
- Added password policy:
  - Minimum 8 characters
  - At least one uppercase letter
- Included invalidation/removal logic for old auth token/session state during reset flow.

Files:
- `app.py`
- `templates/forgot_password.html`

### Dependency / Runtime Fixes
- Investigated runtime error:
  - `ModuleNotFoundError: No module named 'google_auth_oauthlib'`
- Adjusted setup guidance/workflow for Gmail client dependency handling.

Files:
- `gmail_client.py`
- `app.py`

### SHAP + Confidence Rendering Fixes
- Fixed confidence rendering to use model metadata/probabilities instead of a fixed value.
- Improved SHAP integration and added SHAP check support for both phishing and legit emails.
- Improved SHAP button wiring and rendering behavior in dashboard.

Files:
- `app.py`
- `ML_model/xai_explainer.py`
- `templates/ml_dashboard.html`

### Model Artifact Hygiene
- Reviewed `.pkl` file reuse and removed/flagged unnecessary artifacts after validating reusability constraints.

Files:
- `ML_model/*.pkl` (project-specific artifacts)

## Notes
- Some older updates were incremental and may span multiple patches/iterations.
- This document is intentionally implementation-focused so future contributors can quickly locate relevant files.
