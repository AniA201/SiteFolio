"""The rules reproduce every number the demo shows, from verified measurements alone."""
import pytest

from app import money
from app.fixtures import CLAIMS

BY_ID = {c["id"]: c for c in CLAIMS}


def test_roof_bill_pays_verified_share():  # CLM-2207
    roof = money.check_roof(9820, 0, 14500)
    assert roof.inflated
    split = money.pay_verified_share(87000, 14500, roof.surface, roof.allowed)
    assert (split.pay, split.hold) == (58920, 28080)
    assert BY_ID["CLM-2207"]["outcome"]["a"][1] == split.pay


def test_hvac_units():  # CLM-2214
    split = money.pay_verified_share(96000, 12, 8)
    assert (split.pay, split.hold) == (64000, 32000)


def test_honest_paint_bill_paid_in_full():  # CLM-2219: 4,600 claimed vs 4,620 measured
    split = money.pay_verified_share(37200, 4600, 4620)
    assert (split.pay, split.hold) == (37200, 0)


def test_new_bank_account_is_blocked():  # CLM-2223
    checks = money.payment_checks("••9914", "••4421", already_paid=False)
    assert checks.blocked and not checks.account_matches


def test_matching_account_passes():
    assert not money.payment_checks("••4421", "••4421", already_paid=False).blocked


def test_duplicate_payment_blocked():
    assert money.payment_checks("••4421", "••4421", already_paid=True).blocked


def test_sloped_roof_gets_waste_allowance():
    roof = money.check_roof(2000, 26.57, 2500)  # 6/12 pitch: factor ~1.118 -> 2,236 sq ft; +15% = 2,571
    assert not roof.inflated
    assert "slope factor" in roof.formula


def test_wilshire_court_rent():  # RSO-3104
    claimed = money.rent_surcharge(90400, 24)
    verified = money.rent_surcharge(money.verified_cost([(10800, 64800, 7200), (3200, 25600, 1920)]), 24)
    assert (claimed, verified) == (31.39, 20.33)
    rent = BY_ID["RSO-3104"]["rent"]
    assert (rent["claimed"], rent["verified"]) == (claimed, verified)
    assert money.tenant_savings(claimed, verified) == 664  # the Tenant page's "$664 less over 5 years"


def test_vermont_gardens_rent_rounds_half_up():  # RSO-3110: 23.125 -> 23.13
    assert money.rent_surcharge(44400, 16) == BY_ID["RSO-3110"]["rent"]["claimed"] == 23.13


def test_rent_cap():
    assert money.rent_surcharge(1_000_000, 10) == 55.00


def test_draw_release():  # DRW-0412
    split = money.release_draw(400000, 9, 12)
    assert (split.pay, split.hold) == (300000, 100000)
    assert money.release_draw(250000, 1, 1).pay == 250000  # DRW-0415


def test_units_must_be_positive():
    with pytest.raises(ValueError):
        money.rent_surcharge(1000, 0)


def test_pitch_from_vexcel_shape():
    assert money.pitch_for_shape("flat") == (0.0, False) and money.pitch_for_shape(None) == (0.0, False)
    assert money.pitch_for_shape("gable") == (money.STANDARD_PITCH_DEG, True)
    hip = money.check_roof(2000, 0, 2500, shape="hip")      # 2,000 × 1.118 = 2,236; +15% waste = 2,572
    assert not hip.inflated and "assumed 6/12 pitch" in hip.formula and round(hip.allowed) == 2572
    flat = money.check_roof(2000, 0, 2500, shape="flat")    # 2,000 +5% = 2,100
    assert flat.inflated and "flat roof, 0°" in flat.formula
