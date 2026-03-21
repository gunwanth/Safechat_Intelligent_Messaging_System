# Methodology, NLU Analysis, Metadata Analysis, Meta Models, and Accuracy Details

## 1. Project Methodology

The project follows a layered phishing-detection methodology instead of depending on one model or one rule engine. The main idea is to process the same incoming email through multiple analysis paths, compare the outputs, and then use the strongest decision support from the combined system.

### 1.1 Email Intake and Normalization

The pipeline begins when incoming emails are fetched from the connected Gmail account. Each email is read with its important fields such as:

- `subject`
- `content`
- `sender`
- `date`
- embedded URL and message structure information

Before learning starts, the message text is normalized. This step removes unnecessary noise while preserving the content needed for downstream analysis. Two different text-preparation styles are used:

- one for standard machine learning on raw text
- one for NLU and metadata extraction where URL evidence and structural indicators are preserved

This separation is important because plain text models and metadata-aware models need different representations of the same message.

### 1.2 Rule-Based Risk Screening

After intake, the system applies an initial phishing screening step using the rule-based detector. This produces:

- a numeric phishing `score`
- a `level` such as `Low`, `Medium`, or `High`
- a list of detected `threats`

The rule layer acts as the first pass. It is useful because it reacts quickly to obvious phishing indicators such as urgent account prompts, payment claims, verification cues, and suspicious language patterns. It also provides a stable fallback even when learned models are weak or unavailable.

### 1.3 NLU-Driven Pattern Analysis

The next stage performs NLU-style message analysis. This layer is not a general conversational language model. Instead, it is a phishing-intent analysis layer built specifically for email risk detection.

Its role is to understand the behavior of the message, not just count isolated words. For example, the project does not simply react to a word like `verify`. It checks whether the message creates an account-security narrative, credential-harvesting intent, urgency pressure, or reward-based manipulation.

This makes the system significantly stronger than a keyword-only detector.

### 1.4 Metadata Conversion

The project then converts incoming email content into structured metadata. This is one of the most important design improvements in the project.

Metadata conversion means that the email is no longer viewed only as plain text. It is also represented as measurable structural and behavioral phishing signals such as:

- how many URLs are present
- whether URL shorteners are used
- whether IP-host URLs appear
- how many action words appear
- whether payment or billing markers are present
- how aggressive the writing style is

This conversion creates a second, more structured representation of the email.

### 1.5 Machine Learning Branches

The system then applies multiple learning branches:

- a raw-text baseline model
- a metadata-aware model
- a stacked meta-learning branch

Each branch learns from the same live inbox emails but from a different representation.

### 1.6 Comparative Evaluation on Live Data

The project does not stop after making predictions. It compares multiple branches on the same dynamic inbox dataset:

- raw text accuracy
- metadata-aware accuracy
- stacked ensemble accuracy

This is a critical methodological strength because many systems report only static benchmark scores. This project evaluates on live incoming emails and shows the effect of transformation and fusion directly.

### 1.7 Explainability and Proof Layer

A final explainability and proof layer is built on top of the detection system. This includes:

- XAI and SHAP-based explanation support
- per-email transition tracking
- confusion matrices
- state-change analysis
- dynamic proof charts on live data

This allows the project to justify how predictions were made and how accuracy improved after metadata conversion and meta-learning.

## 2. NLU Analysis

### 2.1 What NLU Means in This Project

NLU in this project refers to a phishing-oriented natural language understanding layer. It does not perform full open-domain semantic understanding. Instead, it analyzes phishing intent patterns in a more meaningful way than plain keyword counting.

The NLU layer focuses on how the message behaves:

- Does it try to harvest credentials?
- Does it pressure the user to act urgently?
- Does it involve financial manipulation?
- Does it create a false account-security situation?
- Does it use reward or lure narratives?
- Does it trigger the user to click or act on links?

This means the NLU layer looks at grouped phishing behavior rather than only isolated tokens.

### 2.2 NLU Patterns Used

The project tracks several major phishing signal families:

#### 2.2.1 Credential Harvesting Intent

This pattern group identifies language that attempts to make the user reveal:

- passwords
- OTPs
- PINs
- login credentials
- personal verification details

Examples include combined patterns such as:

- verify account and enter password
- confirm login details
- submit OTP or reset credentials

#### 2.2.2 Urgency Pressure

This pattern group captures emails that try to rush the user into acting without thinking. It looks for:

- urgent requests
- limited-time pressure
- immediate action demands
- warnings about suspension or blockage

This is important because urgency is one of the strongest phishing manipulation tactics.

#### 2.2.3 Financial Manipulation

This pattern group detects money-related phishing behavior such as:

- fake invoice notices
- refund traps
- billing issues
- payment requests
- reward or cash lure messages

This helps catch phishing emails that target payment actions instead of only credential theft.

#### 2.2.4 Account Security Narrative

This group detects messages pretending that:

- the account has unusual activity
- security is at risk
- login is blocked
- the account needs confirmation

This is a common phishing strategy because it creates fear and urgency together.

#### 2.2.5 Reward or Lure Narrative

This group captures phishing emails that offer:

- prizes
- rewards
- bonuses
- gifts
- winning claims

These are social-engineering narratives designed to attract quick clicks.

#### 2.2.6 Link Action Trigger

This group detects action-oriented prompts such as:

- click here
- confirm now
- update information
- login immediately
- open the secure link

This is especially useful when phishing is hidden behind action language rather than explicit threat words.

### 2.3 How NLU Scoring Works

The NLU layer computes a `risk_score` between `0.0` and `1.0`.

Each signal family contributes to the score based on:

- number of hits
- signal weight
- impact strength

The scoring is saturated so one signal group does not dominate unfairly. This improves stability and reduces false inflation from repeated patterns in one category.

### 2.4 NLU Output

The NLU output includes:

- overall `risk_score`
- top phishing signals
- hit counts
- weighted impact values

This output is shown in the inbox and ML dashboards so the user can understand what major patterns were detected in a message.

### 2.5 Why the NLU Layer Matters

This NLU stage reduces the project’s dependence on exact keywords. Earlier systems and simpler detectors often fail when attackers slightly change wording. By looking for grouped intent behavior, the project handles paraphrased phishing messages better than a word-list-only system.

## 3. Metadata Analysis

### 3.1 What Metadata Means in This Project

Metadata in this project means structured phishing evidence extracted from raw emails. It is not limited to sender metadata or email headers. Instead, it includes behavioral, textual, structural, and URL-based indicators derived from the email body and subject.

This metadata becomes a machine-learning-ready feature representation.

### 3.2 Types of Metadata Used

The project extracts multiple types of metadata.

#### 3.2.1 URL and Network Metadata

This includes:

- URL count
- domain extraction
- URL shortener count
- IP-host URL count

This type of metadata is important because phishing emails often hide malicious destinations behind shortened links or direct IP-based URLs.

#### 3.2.2 Call-to-Action Metadata

This includes action-prompt markers such as:

- click
- verify
- reset
- confirm
- update
- login
- claim
- pay

This type of metadata measures how strongly the email is pushing the user to act.

#### 3.2.3 Financial Metadata

This includes financial or billing markers such as:

- payment
- refund
- invoice
- billing
- currency indicators like `USD`, `INR`, `Rs`, or dollar amounts

This helps identify phishing emails that manipulate payment behavior.

#### 3.2.4 Text-Shape Metadata

This includes:

- token count
- uppercase ratio
- digit ratio
- exclamation count

This is useful because phishing emails often use:

- abnormal formatting
- excessive capitalization
- many digits
- aggressive punctuation

#### 3.2.5 Optional Transformer-Intent Metadata

When transformer support is available, the system can enrich metadata with zero-shot intent scores such as:

- credential theft
- payment fraud
- account takeover
- social engineering

This adds higher-level semantic signals on top of the engineered features.

### 3.3 Why Metadata Conversion Improves Detection

Raw text alone does not always capture phishing behavior effectively. For example:

- a suspicious URL may not be important enough in plain TF-IDF text space
- a payment lure may be subtle in wording but obvious in feature combinations
- action pressure may appear through style, not one explicit term

Metadata conversion solves this by turning weak raw signals into measurable features. This is one of the reasons the metadata-aware model performs better than the raw-text baseline on live inbox data.

### 3.4 Metadata Pre-Score

The project produces a `metadata pre-score`, which is a structured phishing risk score created before the final dashboard decision stage.

This score combines:

- NLU risk
- metadata evidence
- optional transformer intent signals
- optional rule contribution

The metadata pre-score is useful because it gives an early risk estimate based on transformed, structured phishing evidence.

### 3.5 Metadata Levels

The project maps metadata risk into levels such as:

- `Low`
- `Medium`
- `High`

These levels make it easier to use metadata outputs in training, comparison, and report generation.

## 4. Meta Models

### 4.1 Baseline Raw-Text Model

The first learning branch is the raw-text baseline model.

#### Architecture

- `TfidfVectorizer`
- `LogisticRegression`

#### Input

- normalized email text
- mainly `subject + content`

#### Purpose

This model provides the baseline machine-learning result on live incoming emails without metadata conversion.

#### Strength

It learns useful word and phrase patterns from the email content and acts as a strong reference point for comparison.

#### Limitation

It can miss phishing behavior that is more structural than lexical, especially in live inbox conditions.

### 4.2 Metadata-Aware Model

The second learning branch is the metadata-aware model.

#### Architecture

- TF-IDF on NLU-preserved text
- engineered numeric metadata features
- `StandardScaler`
- sparse feature fusion using `hstack`
- `LogisticRegression(class_weight="balanced")`

#### Input

- NLU-preserved message text
- metadata numeric feature vector

#### Purpose

This model learns from both text and structured phishing evidence. It is designed to be stronger than the baseline on dynamic and behavior-rich emails.

#### Why It Helps

Because it combines lexical and structural signals, it can detect phishing more reliably when raw text alone is not enough.

### 4.3 Meta-Learner or Stacked Model

The third branch is the meta-learning layer.

#### Input

It uses the prediction strengths of the first two branches:

- baseline model phishing probability
- metadata model phishing probability

#### Purpose

Instead of trusting one branch, the system learns how to combine them.

#### Why It Matters

One branch may underperform on some emails:

- raw text may miss structural manipulation
- metadata may underuse textual context in some cases

The stacked learner improves reliability by fusing both strengths.

## 5. Meta Scores and Risk Measures

### 5.1 Rule Score

This is the initial phishing score generated by the rule engine. It reflects direct threat indicators detected in the message.

### 5.2 NLU Score

This is the NLU phishing-intent risk score. It reflects how strongly the message matches phishing behavior patterns such as urgency, credential harvesting, or financial manipulation.

### 5.3 Metadata Pre-Score

This score combines metadata and NLU evidence into a structured phishing risk before the final model decision path.

### 5.4 Meta-Learning Score

This is the ensemble phishing probability generated by combining the raw-text model and metadata model.

### 5.5 Fused Risk

The project also supports optional fused risk:

`final_risk = alpha * ml_risk + beta * nlu_risk`

This is used for controlled experiments and enhanced decision support when enabled.

### 5.6 Score Interpretation

All these scores are monotonic risk indicators. That means:

- as phishing evidence increases, the score is expected to rise
- higher values indicate stronger phishing suspicion
- values closer to `1.0` indicate stronger risk

## 6. Learning Methodology on Live Data

### 6.1 Why Live Data Is Harder

Live inbox data is harder than benchmark datasets because:

- class balance is unstable
- content style changes over time
- users receive mixed personal, promotional, and transactional emails
- phishing language changes dynamically

This is known as distribution shift.

### 6.2 How the Project Learns from Live Data

The project addresses this by:

- storing live incoming emails
- deriving labels using configurable live label modes
- retraining and evaluating on the same current inbox state
- comparing raw, metadata, and ensemble branches

This is a major strength of the project because many systems do not evaluate on true live data.

### 6.3 Label Modes Used

The project supports configurable label conversion:

- `strict_high`
- `medium_high`

In `strict_high`, only `High` is treated as phishing.  
In `medium_high`, both `Medium` and `High` are treated as phishing.

This improves trainability in live inboxes where high-risk emails may be fewer.

## 7. Accuracy Gains

### 7.1 Benchmark Dataset Accuracy

On the balanced benchmark-style metadata training setup, the project observed results such as:

- baseline accuracy: about `94.44%`
- metadata-aware accuracy: about `98.10%`

#### Gain

The metadata-aware representation improved accuracy by about:

- `+3.66 percentage points`

This shows that metadata transformation improves the quality of phishing detection on cleaner benchmark data.

### 7.2 Live Inbox Accuracy

On dynamic live inbox data, the project generated proof results such as:

- raw text accuracy: `83.82%`
- metadata-aware accuracy: `88.24%`
- meta-learner accuracy: `97.79%`

#### Gains

- metadata over raw: `+4.42 percentage points`
- ensemble over metadata: `+9.55 percentage points`
- ensemble over raw: `+13.97 percentage points`

These are important because live data is much harder than benchmark data.

### 7.3 Why Accuracy Improves

The gains happen because:

- the raw model learns text patterns
- the metadata model captures structural and behavioral phishing evidence
- the meta-learner combines both strengths
- live label configuration avoids one-class training failures

So the project improves detection not only by using more data, but by using better representations of the same data.

## 8. Sparse Weightage and Feature Density

### 8.1 What Sparse Weightage Means

Sparse weightage refers to how many model coefficients are actively used in the linear model. It helps estimate whether the model is very sparse or very dense.

The project measured:

- non-zero coefficients
- sparsity percentage
- L1 norm
- L2 norm

### 8.2 Observed Sparse Weightage

Recent runs showed:

- baseline model: nearly `100%` non-zero weights
- metadata model: around `99.94%` to `99.98%` non-zero weights

### 8.3 Interpretation

This means:

- both models are very dense
- metadata gains are not mainly coming from high sparsity
- improvements are coming from stronger feature representation and better branch fusion

## 9. Strengths of the Complete Design

The full methodology is strong because it:

- reduces heavy dependence on simple keywords
- improves handling of live inbox variation
- preserves URL and structural evidence
- compares multiple branches on the same live data
- supports explainability and proof generation
- provides dynamic evidence of how accuracy changes after transformation

## 10. Current Limitations

Even with the improvements, some limitations remain:

- live labels are still derived from risk levels unless manually curated
- transformer NLU depends on backend availability
- some NLU logic is still pattern-based rather than fully semantic
- live performance can vary when inbox distributions change heavily

These limitations should be stated clearly in the report because they define the current boundary of the system.

## 11. Final Summary

The project uses a complete phishing-analysis pipeline built from:

- rule-based detection
- NLU intent analysis
- metadata conversion
- raw-text machine learning
- metadata-aware machine learning
- meta-learning
- explainable AI support

The central contribution of the project is that it does not treat emails only as plain text. It transforms live emails into meaningful metadata, compares raw and transformed learning paths, and uses a stacked learner to improve phishing detection accuracy. This is why the system performs better on live inbox data and why it can justify its results more clearly than a basic text-only phishing detector.
