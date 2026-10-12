"""Detection-engine tests validated against MockERONET ground truth."""
from __future__ import annotations

from myvote.config import get_config
from myvote.detection import (analyze_pair, compute_dsd, compute_psd,
                              detect_all, detect_underage, name_similarity,
                              cosine_similarity, age_on)
from myvote.eronet import QUALIFYING_DATE
from myvote.models import Elector


def _by_epic(session):
    return {e.epic_id: e for e in session.query(Elector).all()}


def test_name_similarity_basic():
    assert name_similarity("Rajesh Kumar", "Rajesh Kumar") == 1.0
    assert name_similarity("Rajesh Kumar", "Rajesh Coomar") > 0.5
    assert name_similarity("Kumar Rajesh", "Rajesh Kumar") == 1.0  # reordered
    assert name_similarity("Alice", "Bob") < 0.5


def test_cosine_similarity_bounds():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == 1.0
    assert cosine_similarity(v, [0.0, 1.0, 0.0]) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0


def test_detect_all_flags_true_duplicates(seeded):
    session, truth = seeded
    cfg = get_config()
    detections = detect_all(session, cfg)
    flagged_pairs = {
        tuple(sorted((d.elector_a_id, d.elector_b_id)))
        for d in detections
        if d.category.value == "DUPLICATE"
    }
    by_epic = _by_epic(session)
    # Every planted true-duplicate pair should be detected.
    for a_epic, b_epic in truth["true_duplicates"]:
        pair = tuple(sorted((by_epic[a_epic].id, by_epic[b_epic].id)))
        assert pair in flagged_pairs, f"missed true duplicate {a_epic}/{b_epic}"


def test_detect_all_flags_transliteration(seeded):
    session, truth = seeded
    cfg = get_config()
    detections = detect_all(session, cfg)
    translit = {d.category.value for d in detections}
    assert "TRANSLITERATION" in translit


def test_common_name_fp_traps_not_flagged_as_duplicates(seeded):
    session, truth = seeded
    cfg = get_config()
    detections = detect_all(session, cfg)
    by_epic = _by_epic(session)
    flagged_pairs = {
        tuple(sorted((d.elector_a_id, d.elector_b_id)))
        for d in detections
        if d.category.value in ("DUPLICATE", "TRANSLITERATION")
    }
    for group in truth["common_name_fp_traps"]:
        ids = [by_epic[ep].id for ep in group]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair = tuple(sorted((ids[i], ids[j])))
                assert pair not in flagged_pairs, \
                    "common-name different people must NOT be flagged as duplicates"


def test_detect_all_flags_underage(seeded):
    session, truth = seeded
    cfg = get_config()
    detections = detect_all(session, cfg)
    underage_flagged = {d.elector_a_id for d in detections
                        if d.category.value == "UNDERAGE"}
    by_epic = _by_epic(session)
    for epic in truth["underage"]:
        assert by_epic[epic].id in underage_flagged


def test_detect_all_flags_form7_abuse(seeded):
    session, truth = seeded
    cfg = get_config()
    detections = detect_all(session, cfg)
    abuse = [d for d in detections if d.category.value == "FORM7_ABUSE"]
    assert abuse, "bulk Form 7 objector should be flagged"
    # One aggregate Detection per abusive objector, carrying all target IDs.
    total_targets = sum(len(d.extra.get("target_elector_ids", [])) for d in abuse)
    assert total_targets == len(truth["form7_bulk_targets"])


def test_form7_abuse_detection_expands_to_per_voter_flags(seeded):
    # flags.create_flags_from_detections expands the aggregate into one flag
    # per targeted elector.
    session, truth = seeded
    from myvote.flags import create_flags_from_detections
    from myvote.detection import detect_all
    from myvote.models import DiscrepancyFlag
    cfg = get_config()
    detections = detect_all(session, cfg)
    create_flags_from_detections(session, detections, cfg)
    abuse_flags = (session.query(DiscrepancyFlag)
                   .filter(DiscrepancyFlag.category == "FORM7_ABUSE").all())
    assert len(abuse_flags) == len(truth["form7_bulk_targets"])


def test_underage_confidence_and_legal_basis(seeded):
    session, truth = seeded
    by_epic = _by_epic(session)
    cfg = get_config()
    epic = truth["underage"][0]
    d = detect_underage(by_epic[epic], cfg)
    assert d is not None
    assert d.confidence >= 0.7
    assert "RP Act 1950" in d.legal_basis or "Constitution" in d.legal_basis


def test_analyze_pair_returns_none_for_orthogonal_common_name(session):
    # Two different people, same name, orthogonal faces, different DOB.
    cfg = get_config()
    a = Elector(epic_id="A1", name="Rahul Sharma", dob=QUALIFYING_DATE.replace(year=1990),
                gender="M", relative_name="X", relation_type="father",
                house_number="1", locality="L1", district="D", constituency="AC-001",
                part_number=1, serial_number=1, address_line="1, L1, D")
    a.photo_vector = [1.0] + [0.0] * 127
    b = Elector(epic_id="B1", name="Rahul Sharma", dob=QUALIFYING_DATE.replace(year=1985),
                gender="M", relative_name="Y", relation_type="father",
                house_number="99", locality="L9", district="D", constituency="AC-002",
                part_number=2, serial_number=2, address_line="99, L9, D")
    b.photo_vector = [0.0, 1.0] + [0.0] * 126
    from sqlalchemy.orm import Session
    # analyze_pair doesn't need persistence; just the objects.
    assert analyze_pair(a, b, cfg) is None
