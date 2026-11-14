import httpx
import pyzipper
import pytest

from app.integrations.costar import LISTING_ID_COLS, PROPERTY_ID_COLS, CostarError, CostarKit

COMMERCIAL = "PropertyID,Property Name,Building SF,Number Of Stories\n48213,Westheimer Commons,29460,3\n77120,Wilshire Court,21600,3\n"
RESIDENTIAL = "homes_listing_id,address,beds\n221139020,5836 La Mirada Ave,3\n"


@pytest.fixture
def kit_zip(tmp_path):
    p = tmp_path / "kit.zip"
    with pyzipper.AESZipFile(p, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
        z.setpassword(b"pw")
        z.writestr("costar/commercial-properties.csv", COMMERCIAL + "".join(f"{i},Filler {i},1000,1\n" for i in range(1, 20000)))
        z.writestr("costar/residential-listings.csv", RESIDENTIAL)
    return p


def test_local_kit_lookup(kit_zip):
    kit = CostarKit.open(path=str(kit_zip), password="pw")
    name = kit.find("commercial")
    assert kit.columns(name)[:2] == ["propertyid", "property name"]
    rows = kit.lookup(name, {"48213"}, PROPERTY_ID_COLS)
    assert rows["48213"]["building sf"] == "29460"
    res = kit.lookup(kit.find("residential"), {"221139020"}, LISTING_ID_COLS)
    assert res["221139020"]["address"] == "5836 La Mirada Ave"


def test_wrong_password(kit_zip):
    kit = CostarKit.open(path=str(kit_zip), password="nope")
    with pytest.raises(CostarError, match="COSTAR_ZIP_PASSWORD"):
        list(kit.rows(kit.find("residential")))


def test_remote_kit_reads_by_range(kit_zip):
    data = kit_zip.read_bytes()

    def handler(req):
        start, end = map(int, req.headers["range"].removeprefix("bytes=").split("-"))
        chunk = data[start:end + 1]
        return httpx.Response(206, content=chunk, headers={"content-range": f"bytes {start}-{start + len(chunk) - 1}/{len(data)}"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    kit = CostarKit.open(url="https://kit.example/kit.zip", password="pw", http=http)
    assert kit.lookup(kit.find("residential"), {"221139020"}, LISTING_ID_COLS)
    assert kit.zip.fp.requests < 10  # read the table of contents and one file, not the whole zip


def test_missing_settings():
    with pytest.raises(CostarError, match="COSTAR_KIT"):
        CostarKit.open(password="pw")
    with pytest.raises(CostarError, match="COSTAR_ZIP_PASSWORD"):
        CostarKit(b"", "")
