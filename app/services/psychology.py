CAUTION_WORDS = ["wait", "avoid", "danger", "risk", "trap", "choppy", "sideways", "uncertain", "caution"]
CONVICTION_WORDS = ["strong", "high conviction", "clear", "trend", "continuation", "breakout", "strength"]
PATIENCE_WORDS = ["patience", "wait", "stay away", "no trade", "observe", "let it come"]


def extract_psychology(text: str | None) -> dict:
    if not text:
        return {"conviction": 0.0, "caution": 0.0, "patience": 0.0, "raw_counts": {}}

    lower = text.lower()
    caution = sum(1 for w in CAUTION_WORDS if w in lower)
    conviction = sum(1 for w in CONVICTION_WORDS if w in lower)
    patience = sum(1 for w in PATIENCE_WORDS if w in lower)

    total = max(caution + conviction + patience, 1)
    return {
        "conviction": round(conviction / total, 3),
        "caution": round(caution / total, 3),
        "patience": round(patience / total, 3),
        "raw_counts": {"conviction": conviction, "caution": caution, "patience": patience},
    }
