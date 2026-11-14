from app.settings import Settings


def test_integrations_report_only_booleans():
    flags = Settings().integrations()
    assert set(flags) >= {"matterport", "vexcel", "costar", "ai_model", "tiger"}
    assert all(isinstance(v, bool) for v in flags.values())
