"""Money and rent math. Plain code with fixed rules: the AI never decides an amount.

All inputs are verified measurements produced by the checks; every function is pure.
"""
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

FLAT_TOLERANCE = 0.05      # measurement noise allowed on a flat roof or a plain area
SLOPED_WASTE = 0.15        # standard waste allowance on pitched roofs (10-15%)
LA_TENANT_SHARE = 0.5      # LAHD capital improvement: tenants pay 50%
LA_MONTHS = 60             # spread over 60 months
LA_MONTHLY_CAP = 55.00     # generally capped at $55 per unit per month


def cents(x: float) -> float:
    """Round to cents, half up (never banker's rounding on money)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def dollars(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------- roof ----------
def slope_factor(pitch_deg: float) -> float:
    """Roof surface area per unit of footprint for a given pitch."""
    return 1 / math.cos(math.radians(pitch_deg))


@dataclass(frozen=True)
class RoofCheck:
    footprint: float
    pitch_deg: float
    surface: float      # footprint x slope factor
    allowed: float      # surface plus tolerance or waste allowance
    claimed: float
    inflated: bool
    formula: str        # shown on screen so judges can see the adjustment


def check_roof(footprint_sqft: float, pitch_deg: float, claimed_sqft: float) -> RoofCheck:
    factor = slope_factor(pitch_deg)
    surface = footprint_sqft * factor
    allowance = FLAT_TOLERANCE if pitch_deg < 2 else SLOPED_WASTE
    allowed = surface * (1 + allowance)
    formula = (f"{footprint_sqft:,.0f} sq ft footprint × {factor:.3f} slope factor ({pitch_deg:g}°)"
               f" = {surface:,.0f} sq ft; +{allowance:.0%} {'tolerance' if pitch_deg < 2 else 'waste'}"
               f" = {allowed:,.0f} sq ft allowed")
    return RoofCheck(footprint_sqft, pitch_deg, surface, allowed, claimed_sqft, claimed_sqft > allowed, formula)


# ---------- bills ----------
@dataclass(frozen=True)
class Split:
    pay: int
    hold: int


def pay_verified_share(amount: float, claimed_qty: float, verified_qty: float, allowed_qty: float | None = None) -> Split:
    """Pay in full if the claim is within what was verified (plus allowance); otherwise pay the verified share."""
    limit = verified_qty if allowed_qty is None else allowed_qty
    if claimed_qty <= 0 or claimed_qty <= limit:
        return Split(dollars(amount), 0)
    pay = dollars(amount * verified_qty / claimed_qty)
    return Split(pay, dollars(amount) - pay)


@dataclass(frozen=True)
class PaymentChecks:
    approved_contractor: bool
    account_matches: bool
    not_paid_before: bool

    @property
    def blocked(self) -> bool:
        return not (self.approved_contractor and self.account_matches and self.not_paid_before)


def payment_checks(pay_to: str, approved_acct: str | None, already_paid: bool) -> PaymentChecks:
    """Accounts only change through a phone call to the number on file, never through a bill."""
    return PaymentChecks(approved_acct is not None, approved_acct is not None and pay_to == approved_acct, not already_paid)


# ---------- rent (Los Angeles capital improvement surcharge) ----------
def rent_surcharge(cost: float, units: int, share: float = LA_TENANT_SHARE, months: int = LA_MONTHS,
                   cap: float | None = LA_MONTHLY_CAP) -> float:
    """Per unit, per month: share of the cost, spread over `months`, split across `units`, capped."""
    if units <= 0:
        raise ValueError("units must be positive")
    monthly = cents(cost * share / months / units)
    return min(monthly, cap) if cap is not None else monthly


def verified_cost(lines: list[tuple[float, float, float]]) -> float:
    """Sum of (claimed_qty, claimed_amount, verified_qty) lines, re-priced at each line's claimed unit price,
    never paying for more than was claimed."""
    total = 0.0
    for claimed_qty, amount, verified in lines:
        unit_price = amount / claimed_qty if claimed_qty else 0
        total += unit_price * min(verified, claimed_qty)
    return total


def tenant_savings(claimed_monthly: float, verified_monthly: float, months: int = LA_MONTHS) -> int:
    return dollars((claimed_monthly - verified_monthly) * months)


# ---------- construction draws ----------
def release_draw(requested: float, done: int, claimed_done: int) -> Split:
    """Release the share of requested money matching verified progress; hold the rest."""
    if claimed_done <= 0:
        return Split(0, dollars(requested))
    share = min(done, claimed_done) / claimed_done
    release = dollars(requested * share)
    return Split(release, dollars(requested) - release)
