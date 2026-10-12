"""MockERONET — a fully SYNTHETIC electoral-roll data adapter.

This class fabricates 100% synthetic electors and Form submissions. It NEVER
contacts any network, and NEVER uses or requests real voter data (Constraint
#1). It exists only to give the detection engine realistic-shaped input,
including deliberately planted edge cases:

  * true duplicates           - one real person enrolled in two constituencies
  * transliteration variants  - Kumar / Coomar spelling of the same person
  * common-name FP traps      - DIFFERENT people who share a common name
                                (names match, but photo + demographics differ,
                                so the engine must NOT auto-flag them)
  * underage voters           - enrolled below the legal age of 18
  * bulk Form 7 abuse         - one objector files many deletion requests
  * fake Form 7 deletions     - suspicious deletion requests against real voters

``seed()`` returns a ground-truth summary so the detection engine and tests can
measure precision/recall against what was actually planted.
"""
from __future__ import annotations

import math
import random
from datetime import date

from sqlalchemy.orm import Session

from .config import Config, get_config
from .enums import FormType
from .models import Elector, FormSubmission

# The qualifying date used for age computations across the prototype.
# (Sec. 16 / Art. 326 - enrolment age is assessed as of 1st January.)
QUALIFYING_DATE = date(2024, 1, 1)

# Some synthetic constituencies / districts.
CONSTITUENCIES = [
    ("AC-001", "Northfield", "District A"),
    ("AC-002", "Riverside", "District A"),
    ("AC-003", "Hilltop", "District B"),
    ("AC-004", "Lakeside", "District B"),
    ("AC-005", "Old Town", "District C"),
]


class MockERONET:
    """Deterministic synthetic data generator (seeded RNG)."""

    def __init__(self, config: Config | None = None, seed: int | None = None):
        self.config = config or get_config()
        self.rng_seed = seed if seed is not None else int(
            self.config.get("mock_eronet.seed", 42)
        )
        self.rng = random.Random(self.rng_seed)
        self.dim = int(self.config.get("detection.psd.vector_dimension", 128))

        self.first_names = list(self.config.get(
            "mock_eronet.first_names",
            ["Aarav", "Vivaan", "Diya", "Ananya", "Kabir", "Meera"]))
        self.last_names = list(self.config.get(
            "mock_eronet.last_names",
            ["Sharma", "Iyer", "Nair", "Reddy", "Khan"]))

        self._epic_counter = 0

    # ------------------------------------------------------------------ #
    #  Low-level helpers
    # ------------------------------------------------------------------ #
    def _next_epic(self) -> str:
        """Fabricate a unique, clearly-synthetic EPIC like 'SYN0123456'."""
        self._epic_counter += 1
        return f"SYN{self._epic_counter:07d}"

    def _random_unit_vector(self) -> list[float]:
        """A random unit vector of length ``self.dim`` (mock face embedding)."""
        vec = [self.rng.gauss(0.0, 1.0) for _ in range(self.dim)]
        return self._normalise(vec)

    @staticmethod
    def _normalise(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def _similar_vector(self, base: list[float], jitter: float = 0.06) -> list[float]:
        """A vector close to ``base`` (high cosine) - simulates the same face."""
        vec = [x + self.rng.gauss(0.0, jitter) for x in base]
        return self._normalise(vec)

    def _name(self) -> str:
        return f"{self.rng.choice(self.first_names)} {self.rng.choice(self.last_names)}"

    def _adult_dob(self, min_age: int = 22, max_age: int = 70) -> date:
        age = self.rng.randint(min_age, max_age)
        return date(QUALIFYING_DATE.year - age, self.rng.randint(1, 12),
                    self.rng.randint(1, 28))

    def _underage_dob(self) -> date:
        age = self.rng.randint(14, 17)
        return date(QUALIFYING_DATE.year - age, self.rng.randint(1, 12),
                    self.rng.randint(1, 28))

    def _make_elector(self, session: Session, *, name: str, dob: date,
                      gender: str, relative_name: str, relation_type: str,
                      constituency: str, district: str, locality: str,
                      house_number: str, photo_vector: list[float] | None,
                      part_number: int | None = None,
                      serial_number: int | None = None) -> Elector:
        """Persist one synthetic elector and return it (does NOT commit)."""
        constituency_code, _, district_name = self._resolve_geo(constituency, district)
        elector = Elector(
            epic_id=self._next_epic(),
            name=name,
            dob=dob,
            gender=gender,
            relative_name=relative_name,
            relation_type=relation_type,
            house_number=house_number,
            locality=locality,
            district=district_name,
            constituency=constituency_code,
            part_number=part_number if part_number is not None else self.rng.randint(1, 40),
            serial_number=serial_number if serial_number is not None else self.rng.randint(1, 900),
            address_line=f"{house_number}, {locality}, {district_name}",
        )
        elector.photo_vector = photo_vector
        session.add(elector)
        return elector

    def _resolve_geo(self, constituency: str, district: str):
        """If caller passes a code present in CONSTITUENCIES, use its names;
        otherwise treat the passed strings as already-resolved."""
        for code, _name, dname in CONSTITUENCIES:
            if constituency == code:
                return code, _name, dname
        return constituency, district, district

    def _add_form(self, session: Session, *, form_type: FormType,
                  objector_name: str, objector_epic: str,
                  target: Elector | None, reason: str) -> FormSubmission:
        form = FormSubmission(
            form_type=form_type,
            objector_name=objector_name,
            objector_epic=objector_epic,
            target_elector_id=target.id if target is not None else None,
            reason=reason,
        )
        session.add(form)
        return form

    # ------------------------------------------------------------------ #
    #  Main seeding routine
    # ------------------------------------------------------------------ #
    def seed(self, session: Session) -> dict:
        """Populate the DB with synthetic electors + forms.

        Returns a ground-truth summary describing what was planted so callers
        (detection engine, tests) can score precision/recall.
        """
        truth: dict = {
            "true_duplicates": [],       # list[tuple[epic_a, epic_b]]
            "transliteration_pairs": [],  # list[tuple[epic_a, epic_b]]
            "common_name_fp_traps": [],   # list[list[epic, ...]] same name, diff person
            "underage": [],               # list[epic]
            "form7_bulk_objector": None,  # objector epic
            "form7_bulk_targets": [],     # list[epic] hit by bulk objector
            "fake_deletions": [],         # list[epic] targeted by suspicious Form 7
            "counts": {},
        }

        # ---- 1. Clean baseline population -------------------------------- #
        population = int(self.config.get("mock_eronet.population", 60))
        clean: list[Elector] = []
        for _ in range(population):
            constituency, locality, district = self.rng.choice(CONSTITUENCIES)
            elector = self._make_elector(
                session,
                name=self._name(),
                dob=self._adult_dob(),
                gender=self.rng.choice(["M", "F"]),
                relative_name=self._name(),
                relation_type=self.rng.choice(["father", "husband", "mother"]),
                constituency=constituency,
                district=district,
                locality=locality,
                house_number=f"H{self.rng.randint(1, 300)}",
                photo_vector=self._random_unit_vector(),
            )
            clean.append(elector)
        session.flush()  # assign IDs so we can reference them


        # ---- 2. TRUE duplicates across constituencies --------------------- #
        # Same person (same face vector, same DOB/relative) enrolled in TWO
        # different constituencies. This is the case DSD+PSD MUST catch.
        n_dup = int(self.config.get("mock_eronet.true_duplicate_pairs", 3))
        for _ in range(n_dup):
            name = self._name()
            dob = self._adult_dob()
            relative = self._name()
            gender = self.rng.choice(["M", "F"])
            base_vec = self._random_unit_vector()

            c1, loc1, dist1 = self.rng.choice(CONSTITUENCIES)
            c2, loc2, dist2 = self.rng.choice(CONSTITUENCIES)
            while c2 == c1:  # ensure cross-constituency
                c2, loc2, dist2 = self.rng.choice(CONSTITUENCIES)

            a = self._make_elector(session, name=name, dob=dob, gender=gender,
                                   relative_name=relative, relation_type="father",
                                   constituency=c1, district=dist1, locality=loc1,
                                   house_number="H7", photo_vector=base_vec)
            # Slightly different photo + address, but same person.
            b = self._make_elector(session, name=name, dob=dob, gender=gender,
                                   relative_name=relative, relation_type="father",
                                   constituency=c2, district=dist2, locality=loc2,
                                   house_number="H19",
                                   photo_vector=self._similar_vector(base_vec, 0.03))
            truth["true_duplicates"].append((a.epic_id, b.epic_id))

        # ---- 3. Transliteration variants (Kumar / Coomar) ----------------- #
        # SAME person, surname spelled differently (e.g. Kumar vs Coomar),
        # possibly across constituencies. Names differ textually, faces match.
        n_trans = int(self.config.get("mock_eronet.transliteration_pairs", 3))
        translit_sets = [
            ("Rajesh Kumar", "Rajesh Coomar"),
            ("Mohammad Iqbal", "Mohamed Iqbal"),
            ("Vishnu Prasad", "Bishnu Prasad"),
        ]
        for i in range(n_trans):
            base, variant = translit_sets[i % len(translit_sets)]
            dob = self._adult_dob()
            relative = self._name()
            face = self._random_unit_vector()
            c1, loc1, dist1 = self.rng.choice(CONSTITUENCIES)
            c2, loc2, dist2 = self.rng.choice(CONSTITUENCIES)
            while c2 == c1:
                c2, loc2, dist2 = self.rng.choice(CONSTITUENCIES)
            a = self._make_elector(session, name=base, dob=dob, gender="M",
                                   relative_name=relative, relation_type="father",
                                   constituency=c1, district=dist1, locality=loc1,
                                   house_number="H3", photo_vector=face)
            b = self._make_elector(session, name=variant, dob=dob, gender="M",
                                   relative_name=relative, relation_type="father",
                                   constituency=c2, district=dist2, locality=loc2,
                                   house_number="H3",
                                   photo_vector=self._similar_vector(face, 0.05))
            truth["transliteration_pairs"].append((a.epic_id, b.epic_id))

        # ---- 4. Common-name FALSE-POSITIVE traps -------------------------- #
        # Distinct people who HAPPEN to share a very common name. Different
        # DOB, different relative, different (orthogonal) face vector. The
        # engine must NOT flag these as duplicates despite the name match.
        n_fp = int(self.config.get("mock_eronet.common_name_fp_traps", 4))
        for _ in range(n_fp):
            shared_name = "Rahul Sharma"  # a deliberately common synthetic name
            group_epics = []
            for _ in range(3):  # three DIFFERENT people, same name
                constituency, locality, district = self.rng.choice(CONSTITUENCIES)
                elector = self._make_elector(
                    session, name=shared_name, dob=self._adult_dob(),
                    gender="M", relative_name=self._name(),
                    relation_type="father", constituency=constituency,
                    district=district, locality=locality,
                    house_number=f"H{self.rng.randint(1, 300)}",
                    photo_vector=self._random_unit_vector())  # orthogonal faces
                group_epics.append(elector.epic_id)
            truth["common_name_fp_traps"].append(group_epics)

        # ---- 5. Underage voters ------------------------------------------- #
        n_under = int(self.config.get("mock_eronet.underage_count", 4))
        for _ in range(n_under):
            constituency, locality, district = self.rng.choice(CONSTITUENCIES)
            elector = self._make_elector(
                session, name=self._name(), dob=self._underage_dob(),
                gender=self.rng.choice(["M", "F"]), relative_name=self._name(),
                relation_type="father", constituency=constituency,
                district=district, locality=locality,
                house_number=f"H{self.rng.randint(1, 300)}",
                photo_vector=self._random_unit_vector())
            truth["underage"].append(elector.epic_id)

        session.flush()


        # ---- 6. Bulk Form 7 abuse from a SINGLE objector ------------------ #
        # One objector files MANY Form 7 deletion requests (more than the
        # configured cap) targeting unrelated clean voters -> abuse pattern.
        bulk_epic = self._next_epic()
        bulk_name = "Suspicious Objector"
        truth["form7_bulk_objector"] = bulk_epic
        n_targets = int(self.config.get("mock_eronet.form7_bulk_targets", 8))
        for target in clean[:n_targets]:
            self._add_form(session, form_type=FormType.FORM_7,
                           objector_name=bulk_name, objector_epic=bulk_epic,
                           target=target, reason="Requests deletion - bulk pattern")
            truth["form7_bulk_targets"].append(target.epic_id)

        # ---- 7. Fake / suspicious Form 7 deletions ------------------------ #
        # A handful of plausible-looking Form 7 deletions aimed at real,
        # legitimate (young adult) voters - the classic "fake deletion" abuse.
        # These overlap conceptually with underage/duplicate review queues.
        n_fake = int(self.config.get("mock_eronet.fake_deletion_pairs", 2))
        fake_objector = self._next_epic()
        for target in clean[n_targets:n_targets + n_fake]:
            self._add_form(session, form_type=FormType.FORM_7,
                           objector_name="Anon Objector", objector_epic=fake_objector,
                           target=target, reason="Claims voter has shifted out")
            truth["fake_deletions"].append(target.epic_id)

        # ---- 8. Some benign Form 6 / Form 8 filings for realism ----------- #
        for target in clean[n_targets + n_fake:n_targets + n_fake + 5]:
            self._add_form(session, form_type=FormType.FORM_8,
                           objector_name="Correction Requester",
                           objector_epic=self._next_epic(), target=target,
                           reason="Requests address correction")

        session.commit()

        # ---- Ground-truth counts ------------------------------------------ #
        truth["counts"] = {
            "electors": session.query(Elector).count(),
            "form_submissions": session.query(FormSubmission).count(),
            "true_duplicate_pairs": len(truth["true_duplicates"]),
            "transliteration_pairs": len(truth["transliteration_pairs"]),
            "common_name_fp_groups": len(truth["common_name_fp_traps"]),
            "underage": len(truth["underage"]),
            "form7_bulk_targets": len(truth["form7_bulk_targets"]),
            "fake_deletions": len(truth["fake_deletions"]),
        }
        return truth

