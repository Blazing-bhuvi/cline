"""Detection engine for MyVote-D: DSD + PSD.

Two complementary signals:
  * DSD — Demographic Similarity Detection: name, age, relative-name, address.
  * PSD — Photo Similarity Detection: mock cosine similarity on 128-d vectors.

Both are combined into a confidence score, bucketed into a LOW/MEDIUM/HIGH tier,
and rendered with a plain-language explanation of the legal basis.

Design principles:
  * Conservative on common names (a shared common name is NOT a duplicate).
  * Transliteration variants (Kumar/Coomar) get a *boost*, never an auto-verdict.
  * Nothing here mutates an Elector; it only produces detection scores.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Config, get_config
from .enums import ConfidenceTier, FlagCategory
from .eronet import QUALIFYING_DATE


# --------------------------------------------------------------------------- #
#  Low-level similarity helpers
# --------------------------------------------------------------------------- #
def _ratio(a: str, b: str) -> float:
    """Normalised similarity in [0,1] via difflib.SequenceMatcher."""
    import difflib
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _token_sort_ratio(a: str, b: str) -> float:
    """Similarity ignoring word order ('Kumar Rajesh' == 'Rajesh Kumar')."""
    a = " ".join(sorted((a or "").lower().split()))
    b = " ".join(sorted((b or "").lower().split()))
    return _ratio(a, b)


def name_similarity(a: str, b: str) -> float:
    """Best of raw and token-sorted similarity (handles reordered names)."""
    return max(_ratio(a, b), _token_sort_ratio(a, b))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [0,1]. Empty/mismatched inputs -> 0.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    cos = dot / (na * nb)
    # Clamp to [0,1]; faces are positive-embedding space in this prototype.
    return max(0.0, min(1.0, cos))


def age_on(dob, on=QUALIFYING_DATE) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _transliteration_clusters(config: Config) -> list[list[str]]:
    clusters = config.get("detection.dsd.transliteration_clusters", [])
    return [[str(x).lower() for x in cluster] for cluster in clusters]


def _in_same_cluster(name_a: str, name_b: str, clusters) -> bool:
    """True if any token pair from the two names shares a variant cluster."""
    ta = set((name_a or "").lower().split())
    tb = set((name_b or "").lower().split())
    for cluster in clusters:
        members = set(cluster)
        if (ta & members) and (tb & members):
            return True
    return False


# --------------------------------------------------------------------------- #
#  Signal scores
# --------------------------------------------------------------------------- #
@dataclass
class DSDResult:
    name: float = 0.0
    age: float = 0.0
    relative: float = 0.0
    address: float = 0.0
    transliteration_boost: bool = False
    composite: float = 0.0


def compute_dsd(elector_a, elector_b, config: Config) -> DSDResult:
    """Demographic similarity between two electors in [0,1]."""
    weights = config.get("detection.dsd.weights", {})
    w_name = float(weights.get("name", 0.45))
    w_age = float(weights.get("age", 0.25))
    w_rel = float(weights.get("relative_name", 0.20))
    w_addr = float(weights.get("address", 0.10))

    name = name_similarity(elector_a.name, elector_b.name)
    rel = name_similarity(elector_a.relative_name, elector_b.relative_name)

    age_a = age_on(elector_a.dob)
    age_b = age_on(elector_b.dob)
    age_diff = abs(age_a - age_b)
    # 0 diff -> 1.0; >= 5 yrs -> 0.0; linear in between.
    age = max(0.0, 1.0 - (age_diff / 5.0))

    # Address: house number exact + locality/constituency overlap.
    house = 1.0 if elector_a.house_number == elector_b.house_number else 0.0
    geo = _ratio(elector_a.locality, elector_b.locality)
    const = 1.0 if elector_a.constituency == elector_b.constituency else 0.0
    address = 0.4 * house + 0.3 * geo + 0.3 * const

    clusters = _transliteration_clusters(config)
    translit = _in_same_cluster(elector_a.name, elector_b.name, clusters)

    composite = w_name * name + w_age * age + w_rel * rel + w_addr * address
    # Transliteration variants: nudge the composite up so they aren't missed,
    # but never auto-confirm (still needs PSD + BLO verification).
    if translit and name < 0.9:
        composite = min(1.0, composite + 0.10)

    return DSDResult(name=name, age=age, relative=rel, address=address,
                     transliteration_boost=translit, composite=composite)


def compute_psd(elector_a, elector_b, config: Config) -> float:
    """Mock photo cosine similarity in [0,1]."""
    va = elector_a.photo_vector
    vb = elector_b.photo_vector
    if not va or not vb:
        return 0.0
    return cosine_similarity(va, vb)


# --------------------------------------------------------------------------- #
#  Confidence tiering
# --------------------------------------------------------------------------- #
def tier_for(confidence: float, config: Config) -> ConfidenceTier:
    tiers = config.get("detection.confidence.tiers", {})
    low = float(tiers.get("low", 0.0))
    medium = float(tiers.get("medium", 0.5))
    high = float(tiers.get("high", 0.75))
    if confidence >= high:
        return ConfidenceTier.HIGH
    if confidence >= medium:
        return ConfidenceTier.MEDIUM
    if confidence >= low:
        return ConfidenceTier.LOW
    return ConfidenceTier.LOW


@dataclass
class Detection:
    elector_a_id: int
    elector_b_id: int
    category: FlagCategory
    dsd: float
    psd: float
    confidence: float
    tier: ConfidenceTier
    explanation: str = ""
    legal_basis: str = ""
    transliteration: bool = False
    extra: dict = field(default_factory=dict)



# --------------------------------------------------------------------------- #
#  Pair analysis (duplicate / transliteration)
# --------------------------------------------------------------------------- #
def analyze_pair(elector_a, elector_b, config: Config) -> Detection | None:
    """Analyse two electors for a possible duplicate. Returns a Detection or
    None if there is no meaningful signal.

    Common-name guard: if the names match strongly but demographics AND photo
    are weak, we treat it as a coincidental common-name match and DO NOT flag.
    """
    dsd_res = compute_dsd(elector_a, elector_b, config)
    psd = compute_psd(elector_a, elector_b, config)

    blend = config.get("detection.confidence.blend_weights", {})
    w_dsd = float(blend.get("dsd", 0.6))
    w_psd = float(blend.get("psd", 0.4))
    confidence = w_dsd * dsd_res.composite + w_psd * psd
    confidence = max(0.0, min(1.0, confidence))

    # --- Common-name false-positive guard ------------------------------- #
    # Strong name match but weak everything else => probably two different
    # people who happen to share a common name. Do NOT flag.
    name_strong = dsd_res.name >= 0.92
    demographics_weak = dsd_res.composite < 0.55
    photo_weak = psd < float(config.get("detection.psd.possible_threshold", 0.80))
    if name_strong and demographics_weak and photo_weak:
        return None

    # --- Photo/demographic gate ----------------------------------------- #
    # A duplicate verdict needs EITHER a photo match (same face) OR an
    # exceptionally strong demographic match. Two different-looking people
    # (orthogonal face vectors) with merely coincidental demographic overlap
    # (e.g. a shared common name) are NOT flagged. This is the primary guard
    # against common-name false positives.
    possible_thr = float(config.get("detection.psd.possible_threshold", 0.80))
    photo_ok = psd >= possible_thr
    demographics_strong = dsd_res.composite >= 0.85
    if not (photo_ok or demographics_strong):
        return None

    # --- Threshold to emit a flag at all -------------------------------- #
    min_conf = float(config.get("detection.confidence.tiers.medium", 0.5))
    if confidence < min_conf:
        return None

    tier = tier_for(confidence, config)

    # Category: transliteration variant vs true duplicate.
    translit = dsd_res.transliteration_boost and dsd_res.name < 0.95
    if translit:
        category = FlagCategory.TRANSLITERATION
    else:
        category = FlagCategory.DUPLICATE

    dup_threshold = float(config.get("detection.psd.duplicate_threshold", 0.92))
    explanation = _explain_pair(dsd_res, psd, confidence, tier, category,
                                elector_a, elector_b, dup_threshold)
    legal_basis = ("Sec. 17 RP Act 1950 (correction of entries); "
                   "Sec. 18 (supervision of electoral rolls). "
                   "No automatic deletion — flag requires BLO physical verification.")

    return Detection(
        elector_a_id=elector_a.id,
        elector_b_id=elector_b.id,
        category=category,
        dsd=round(dsd_res.composite, 4),
        psd=round(psd, 4),
        confidence=round(confidence, 4),
        tier=tier,
        explanation=explanation,
        legal_basis=legal_basis,
        transliteration=translit,
        extra={
            "dsd_components": {
                "name": round(dsd_res.name, 4),
                "age": round(dsd_res.age, 4),
                "relative": round(dsd_res.relative, 4),
                "address": round(dsd_res.address, 4),
            },
            "cross_constituency": elector_a.constituency != elector_b.constituency,
        },
    )


def _explain_pair(dsd_res, psd, confidence, tier, category, a, b, dup_thr):
    parts = []
    parts.append(f"Name similarity {dsd_res.name:.0%}")
    parts.append(f"age match {dsd_res.age:.0%}")
    parts.append(f"relative-name match {dsd_res.relative:.0%}")
    parts.append(f"address match {dsd_res.address:.0%}")
    parts.append(f"photo similarity {psd:.0%} (dup threshold {dup_thr:.0%})")
    if a.constituency != b.constituency:
        parts.append(f"enrolled in two constituencies ({a.constituency} / {b.constituency})")
    if category == FlagCategory.TRANSLITERATION:
        parts.append("names appear to be transliteration variants of each other")
    head = f"{tier.value} confidence ({confidence:.0%}). "
    return head + "Signals: " + "; ".join(parts) + "."



# --------------------------------------------------------------------------- #
#  Underage detection
# --------------------------------------------------------------------------- #
def detect_underage(elector, config: Config) -> Detection | None:
    min_age = int(config.get("detection.underage.minimum_age", 18))
    age = age_on(elector.dob)
    if age >= min_age:
        return None
    confidence = 0.95 if age <= (min_age - 1) else 0.7
    tier = tier_for(confidence, config)
    explanation = (
        f"Enrolled elector is {age} years old as of the qualifying date "
        f"({QUALIFYING_DATE.isoformat()}); the minimum age for enrolment is "
        f"{min_age} (Art. 326 Constitution of India; Sec. 16 RP Act 1950)."
    )
    return Detection(
        elector_a_id=elector.id,
        elector_b_id=elector.id,
        category=FlagCategory.UNDERAGE,
        dsd=None,
        psd=None,
        confidence=round(confidence, 4),
        tier=tier,
        explanation=explanation,
        legal_basis="Art. 326 Constitution of India; Sec. 16 RP Act 1950 (qualification for enrolment).",
        extra={"age": age, "minimum_age": min_age},
    )


# --------------------------------------------------------------------------- #
#  Form 7 abuse detection (bulk deletion pattern)
# --------------------------------------------------------------------------- #
def detect_form7_abuse(session, config: Config) -> list[Detection]:
    """Flag objectors who filed Form 7 deletions beyond the configured cap.

    This is a per-objector aggregate anomaly, not a per-voter duplicate.
    """
    from .models import Elector, FormSubmission
    from .enums import FormType

    cap = int(config.get("form_rules.form7.max_deletions_per_objector_per_day", 5))
    threshold = int(config.get("form_rules.form7.bulk_abuse_threshold", 5))

    counts: dict[str, list[FormSubmission]] = {}
    for form in session.query(FormSubmission).filter(
        FormSubmission.form_type == FormType.FORM_7.value
    ).all():
        counts.setdefault(form.objector_epic, []).append(form)

    detections: list[Detection] = []
    for objector_epic, forms in counts.items():
        if len(forms) <= cap and len(forms) < threshold:
            continue
        # Anchor the flag on the first target elector (subject of the pattern).
        first = next((f for f in forms if f.target_elector_id), None)
        if first is None:
            continue
        over = len(forms) - cap
        confidence = min(1.0, 0.6 + 0.05 * len(forms))
        tier = tier_for(confidence, config)
        explanation = (
            f"Objector {objector_epic} filed {len(forms)} Form 7 deletion requests "
            f"(cap is {cap}/day; abuse threshold {threshold}), exceeding the cap by "
            f"{over}. This bulk pattern is flagged for BLO verification of EACH "
            f"targeted entry. No entry is deleted."
        )
        detections.append(Detection(
            elector_a_id=first.target_elector_id,
            elector_b_id=first.target_elector_id,
            category=FlagCategory.FORM7_ABUSE,
            dsd=None,
            psd=None,
            confidence=round(confidence, 4),
            tier=tier,
            explanation=explanation,
            legal_basis=("Sec. 18 RP Act 1950 (supervision); Form 7 filings are "
                         "allegations only and require physical verification."),
            extra={
                "objector_epic": objector_epic,
                "form_count": len(forms),
                "cap": cap,
                "target_elector_ids": [f.target_elector_id for f in forms if f.target_elector_id],
            },
        ))
    return detections


# --------------------------------------------------------------------------- #
#  Orchestrator
# --------------------------------------------------------------------------- #
def detect_all(session, config: Config | None = None) -> list[Detection]:
    """Run the full detection pass over the synthetic roll.

    Returns a list of Detection candidates (NOT yet persisted as flags — the
    workflow layer turns these into DiscrepancyFlag rows).
    """
    from .models import Elector

    config = config or get_config()
    detections: list[Detection] = []

    # 1. Underage.
    for elector in session.query(Elector).all():
        d = detect_underage(elector, config)
        if d is not None:
            detections.append(d)

    # 2. Pairwise duplicate / transliteration.
    electors = session.query(Elector).all()
    # Cheap pre-filter: only compare within the same last-name token OR when a
    # transliteration cluster could apply, to keep the O(n^2) pass small.
    for i in range(len(electors)):
        for j in range(i + 1, len(electors)):
            a, b = electors[i], electors[j]
            if not _candidate_pair(a, b, config):
                continue
            d = analyze_pair(a, b, config)
            if d is not None:
                detections.append(d)

    # 3. Form 7 abuse.
    detections.extend(detect_form7_abuse(session, config))
    return detections


def _candidate_pair(a, b, config: Config) -> bool:
    """Cheap gate to avoid comparing every pair (name overlap or cluster)."""
    clusters = _transliteration_clusters(config)
    ta = set((a.name or "").lower().split())
    tb = set((b.name or "").lower().split())
    if ta & tb:
        return True
    for cluster in clusters:
        members = set(cluster)
        if (ta & members) and (tb & members):
            return True
    return False

