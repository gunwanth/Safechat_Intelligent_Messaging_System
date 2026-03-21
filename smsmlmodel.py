import os
import pickle
from flask import Blueprint, render_template, session

try:
    from live_trainer import LiveTrainer
    _trainer_available = True
except Exception:
    _trainer_available = False


sms_ml_bp = Blueprint("sms_ml_bp", __name__)


def _prediction_confidence_pct(trainer, pred_val, proba_row):
    try:
        classes = list(getattr(trainer.model, "classes_", []))
        if classes:
            pred_idx = classes.index(pred_val)
            return round(float(proba_row[pred_idx]) * 100, 2)
    except Exception:
        pass
    return round(float(max(proba_row)) * 100, 2)


@sms_ml_bp.route("/sms-ml")
def sms_ml_dashboard():
    sms_file_path = "ML_model/sms_incoming.pkl"
    sms_messages = []

    if os.path.exists(sms_file_path):
        try:
            with open(sms_file_path, "rb") as f:
                sms_messages = pickle.load(f) or []
        except Exception:
            sms_messages = []

    # Batch-classify all SMS with existing LogisticRegression model
    if _trainer_available and sms_messages:
        user_email = session.get("user_email", "default_user")
        trainer = LiveTrainer(user_email)

        texts = []
        index_map = []  # map from batch index to sms_messages index
        for idx, sms in enumerate(sms_messages):
            content = (sms or {}).get("content", "")
            if not content:
                sms.setdefault("ml_prediction", "N/A")
                sms.setdefault("confidence", 0)
                continue
            texts.append(content)
            index_map.append(idx)

        if texts:
            try:
                preds, probas = trainer.predict_with_proba(texts)
                for i, sms_idx in enumerate(index_map):
                    sms = sms_messages[sms_idx]
                    pred_val = preds[i]
                    confidence = _prediction_confidence_pct(trainer, pred_val, probas[i])

                    # Normalize label for binary numeric models; otherwise keep string label
                    if isinstance(pred_val, (int, float)):
                        if int(pred_val) == 1:
                            pred_label = "Spam"
                        else:
                            pred_label = "Safe"
                    else:
                        pred_label = str(pred_val)

                    sms["ml_prediction"] = pred_label
                    sms["confidence"] = confidence
            except Exception:
                for sms_idx in index_map:
                    sms_messages[sms_idx]["ml_prediction"] = "⚠️ ML Error"
                    sms_messages[sms_idx]["confidence"] = 0

    # Render using existing template
    return render_template("sms_dashboard.html", sms_messages=sms_messages)


