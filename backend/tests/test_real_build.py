from app.real.build import plan_code


def test_plan_codes_from_matterport_names():
    assert plan_code("B2 2BR, 2BA - 933SF") == "B2"
    assert plan_code("A1 1BR, 1BA - 578SF") == "A1"
    assert plan_code("Essex Properties at Miracle Mile - Plan 1A - 1 Bed / 1 Bath") == "1A"
    assert plan_code("Clubhouse") is None
