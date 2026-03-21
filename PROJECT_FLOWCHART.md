# Project Flowchart

This document gives a high-level flowchart for the phishing detection project, including authentication, inbox ingestion, metadata analysis, ML/XAI processing, SMS handling, and storage artifacts.

## 1. Full System Flow

```mermaid
flowchart TD
    A[User Opens App] --> B{Authenticated?}
    B -- No --> C[Login / Signup / Forgot Password]
    C --> D[users.json]
    C --> B
    B -- Yes --> E[Home Redirect]
    E --> F[Inbox]

    F --> G[GmailClient Authenticate]
    G --> H[Fetch Recent Emails]
    H --> I[PhishingDetector Rule Scan]
    I --> J[NLU + Metadata Extraction]
    J --> K[Column Routing]
    K --> L[Persist Inbox State + Email PKL]
    L --> M[Render Inbox Cards]

    M --> N[Explain Detection]
    N --> O[XAIExplainer / SHAP]

    M --> P[ML Dashboard]
    P --> Q[LiveTrainer Text Model]
    P --> R[Metadata Trainer]
    Q --> S[Predictions + Confidence]
    R --> T[Metadata Model + Meta Learner]
    O --> U[XAI Tokens / Impacts]
    S --> V[Dashboard Rendering]
    T --> V
    U --> V

    V --> W[Delete / Mark Spam / Review]
    W --> X[Spam Dashboard]

    B -- SMS Flow --> Y[SMS Dashboard]
    Y --> Z[SMS Generator / Receive SMS]
    Z --> AA[SMS ML Prediction + XAI]
    AA --> Y
```

## 2. Inbox Processing Flow

```mermaid
flowchart TD
    A[/inbox Route/] --> B[Load Session User]
    B --> C[GmailClient Authenticate]
    C --> D[Fetch Emails]
    D --> E[Load Inbox State PKL]
    E --> F[Loop Through Incoming Emails]

    F --> G[Rule-Based Risk Score]
    G --> H[Threat Detection]
    H --> I[Level Assignment]
    I --> J[Analyze Message NLU]
    J --> K[Metadata First Score]
    K --> L{Meta-Learning Enabled?}
    L -- Yes --> M[Predict Baseline + Metadata + Ensemble Risk]
    L -- No --> N[Keep Metadata Score]
    M --> O[Blend Metadata and Ensemble Risk]
    N --> P[Metadata Level]
    O --> P
    P --> Q[Secondary Column Classification]
    Q --> R[Attach XAI Summary]
    R --> S[Store Email Record]

    S --> T[Backfill Stored Emails]
    T --> U[Save inbox_state_*.pkl]
    U --> V[Save emails_*.pkl]
    V --> W[Render Primary / Promotions / Social / Purchases]
```

## 3. ML Dashboard Flow

```mermaid
flowchart TD
    A[/ml_dashboard Route/] --> B[Load Emails from Session or PKL]
    B --> C[Derive Labels]
    C --> D[Normalize Text for ML]
    D --> E[LiveTrainer train_user]
    E --> F[Predict With Probabilities]
    F --> G[Generate Text Explanations]
    G --> H[Generate SHAP/XAI Explanations]

    B --> I[Metadata Trainer train_and_report_metadata_models]
    I --> J[Baseline Model]
    I --> K[Metadata Model]
    I --> L[Meta Learner]
    J --> M[Accuracy Report]
    K --> M
    L --> M

    F --> N[ML Confidence / ML Risk]
    B --> O[NLU Summary + Metadata Score]
    O --> P{Metadata-First Enabled?}
    P -- Yes --> Q[Override Low-Confidence Safe if Needed]
    P -- No --> R[Keep ML Label]
    Q --> S{Fused Risk Enabled?}
    R --> S
    S -- Yes --> T[alpha*ML + beta*NLU]
    S -- No --> U[Direct ML Result]
    T --> V[Render Dashboard]
    U --> V
    H --> V
    M --> V
```

## 4. Metadata / Meta-Learning Architecture

```mermaid
flowchart LR
    A[Raw Email Text] --> B[sanitize_text_for_nlu]
    B --> C[TF-IDF Metadata Text Branch]
    B --> D[Engineered Metadata Features]
    B --> E{Transformers Available?}
    E -- Yes --> F[Zero-Shot Intent Scores]
    E -- No --> G[Skip Transformer Features]

    D --> H[StandardScaler]
    F --> H
    G --> H

    C --> I[Metadata Logistic Regression]
    H --> I

    A --> J[Lowercased Text]
    J --> K[Baseline TF-IDF]
    K --> L[Baseline Logistic Regression]

    L --> M[Baseline Phishing Probability]
    I --> N[Metadata Phishing Probability]
    M --> O[Meta Learner Stacker]
    N --> O
    O --> P[Ensemble Probability]
```

## 5. Storage / Artifacts Map

```mermaid
flowchart TD
    A[Runtime App] --> B[users.json]
    A --> C[token_*.pkl]
    A --> D[ML_model/emails_*.pkl]
    A --> E[ML_model/inbox_state_*.pkl]
    A --> F[ML_model/spam_*.pkl]
    A --> G[ML_model/sms_incoming.pkl]

    H[LiveTrainer] --> I[ML_model/model_*.pkl]
    H --> J[ML_model/vectorizer_*.pkl]
    H --> K[ML_model/base_model.pkl]
    H --> L[ML_model/base_vectorizer.pkl]

    M[Metadata Trainer] --> N[ML_model/baseline_model_*.pkl]
    M --> O[ML_model/baseline_vectorizer_*.pkl]
    M --> P[ML_model/metadata_model_*.pkl]
    M --> Q[ML_model/metadata_vectorizer_*.pkl]
    M --> R[ML_model/metadata_scaler_*.pkl]
    M --> S[ML_model/meta_learner_model_*.pkl]
    M --> T[ML_model/metadata_feature_config_*.json]
    M --> U[ML_model/metrics_report_*.json]
    M --> V[ML_model/metrics_report_*.md]
```

## 6. Main Components

- `app.py`: central Flask app, routes, inbox flow, ML dashboard flow, deletion, spam handling, SMS endpoints.
- `gmail_client.py`: Gmail OAuth + email fetch.
- `phishing_detector.py`: rule-based phishing scoring and threat extraction.
- `ML_model/live_trainer.py`: text-only ML training and prediction.
- `ML_model/metadata_trainer.py`: metadata model training, reports, and meta-learning ensemble.
- `ML_model/xai_explainer.py`: SHAP/XAI explanations.
- `email_column_router.py`: inbox secondary-column classification.
- `sms_generator.py` and `smsmlmodel.py`: SMS generation and SMS ML pipeline.

## 7. Key Decision Layers

- **Rule Layer**: `PhishingDetector` assigns base score, threats, and level.
- **NLU Layer**: intent-pattern analysis adds risk signals and structured metadata.
- **Metadata Layer**: engineered features + optional transformer intent scores.
- **ML Layer**: text-only classifier from `LiveTrainer`.
- **Meta-Learning Layer**: stacker combines baseline and metadata probabilities.
- **XAI Layer**: SHAP/token explanations for dashboard and explain routes.

## 8. Current Labeling Modes

- `strict_high`: only `High` emails are treated as phishing labels.
- `medium_high`: `Medium` and `High` emails are treated as phishing labels.
- Current live metadata training defaults to `medium_high`.

