"""The real buildings the demo uses, one per story. Chosen with scripts/scan_candidates.py because CoStar's floor
plate and Vexcel's roof footprint agree, and Matterport scans with room areas exist."""

SELECTION = {
    # Owner: low-rise Houston office; Suite 201 and the lobby are scanned.
    "vine": {"costar_id": "235123", "suite_model": "GicaHwHVx8e", "lobby_model": "EXBCDf5VFiT"},
    # City reviewer: LA apartment building; floor plans scanned.
    "cochran": {"costar_id": "4139744"},
    # City reviewer, double-charge case.
    "westmoreland": {"costar_id": "891796"},
    # Lender: new Houston apartment building; floor plans scanned.
    "lenox": {"costar_id": "15121287"},
}
