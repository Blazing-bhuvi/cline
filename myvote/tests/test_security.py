"""Security tests: TOTP auth, session timeouts, DPDP PII masking."""
from __future__ import annotations

import time

import pytest

from myvote.enums import FormType
from myvote.eronet import QUALIFYING_DATE
from myvote.models import Elector
from myvote.security import (BLOSessionManager, PIIMasker, TOTPAuthenticator,
                             mask_elector_public)


# ---- TOTP ---------------------------------------------------------------- #
def test_totp_provision_and_verify():
    auth = TOTPAuthenticator()
    auth.provision("BLO-1")
    code = auth.current_code("BLO-1")
    assert auth.verify("BLO-1", code)


def test_totp_rejects_wrong_code():
    auth = TOTPAuthenticator()
    auth.provision("BLO-1")
    assert not auth.verify("BLO-1", "000000")


def test_totp_unprovisioned_blo_rejected():
    auth = TOTPAuthenticator()
    assert not auth.verify("ghost", "123456")


# ---- Session timeouts ---------------------------------------------------- #
def test_session_valid_initially():
    mgr = BLOSessionManager()
    s = mgr.create("BLO-1")
    assert mgr.get_valid(s.session_id) is not None


def test_session_idle_timeout():
    mgr = BLOSessionManager()
    # Force a tiny idle timeout for the test.
    mgr.idle_timeout = 1
    s = mgr.create("BLO-1")
    time.sleep(1.1)
    assert mgr.get_valid(s.session_id) is None


def test_session_absolute_timeout():
    mgr = BLOSessionManager()
    mgr.absolute_timeout = 1
    mgr.idle_timeout = 1000
    s = mgr.create("BLO-1")
    time.sleep(1.1)
    # touch keeps it active but absolute cap still expires it.
    assert mgr.get_valid(s.session_id) is None


def test_session_end_removes():
    mgr = BLOSessionManager()
    s = mgr.create("BLO-1")
    mgr.end(s.session_id)
    assert mgr.get_valid(s.session_id) is None


def test_default_timeouts_are_15_and_5_minutes():
    mgr = BLOSessionManager()
    assert mgr.absolute_timeout == 15 * 60
    assert mgr.idle_timeout == 5 * 60


# ---- PII masking --------------------------------------------------------- #
def _sample_elector():
    e = Elector(epic_id="SYN0123456", name="Rajesh Kumar",
                dob=QUALIFYING_DATE.replace(year=1990),
                gender="M", relative_name="S Kumar", relation_type="father",
                house_number="42", locality="Northfield", district="District A",
                constituency="AC-001", part_number=1, serial_number=1,
                address_line="42, Northfield")
    return e


def test_mask_epic_reveals_first_and_last():
    m = PIIMasker()
    masked = m.mask_epic("SYN0123456")
    assert masked.startswith("S")
    assert masked.endswith("56")
    assert "*" in masked


def test_mask_name_reveals_initials_only():
    m = PIIMasker()
    assert m.mask_name("Rajesh Kumar") == "R***** K****"


def test_mask_dob_reveals_age_band_only():
    m = PIIMasker()
    band = m.mask_dob_to_age_band(QUALIFYING_DATE.replace(year=1990))
    assert "yrs" in band
    assert "1990" not in band


def test_mask_address_hides_locality_name():
    m = PIIMasker()
    addr = m.mask_address("42", "Northfield")
    assert "42" in addr
    assert "Northfield" not in addr


def test_public_view_masks_all_pii():
    e = _sample_elector()
    view = mask_elector_public(e)
    assert view["epic_id"].startswith("S") and "*" in view["epic_id"]
    assert view["name"] == "R***** K****"
    assert "1990" not in view["age_band"]
