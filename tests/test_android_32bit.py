"""The 32-bit Android edition has no Pillow, psutil or fpdf2: Gink must still work."""
import base64, io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def no_pillow_or_fpdf(monkeypatch):
    for mod in ("PIL", "PIL.Image", "PIL.ImageOps", "fpdf", "fpdf.fonts", "psutil"):
        monkeypatch.setitem(sys.modules, mod, None)          # "import PIL" now raises ImportError


def jpeg_bytes():
    from PIL import Image                                     # made before the fixture blocks Pillow
    buf = io.BytesIO(); Image.new("RGB", (64, 48), (168, 240, 60)).save(buf, "JPEG"); return buf.getvalue()


def test_photos_attach_without_pillow(monkeypatch):
    raw = jpeg_bytes()
    for mod in ("PIL", "PIL.Image", "PIL.ImageOps"):
        monkeypatch.setitem(sys.modules, mod, None)
    from ginkassistant.services import attachments
    att = attachments.load_data_url("data:image/jpeg;base64," + base64.b64encode(raw).decode(), "photo.jpg")
    assert att.kind == "image" and att.data_url.startswith("data:image/jpeg;base64,") and att.thumb == att.data_url
    with pytest.raises(attachments.AttachmentError, match="JPEG or PNG"):
        attachments._image_without_pillow(b"not an image at all", "x.jpg")


def test_pdfs_without_fpdf2(no_pillow_or_fpdf, tmp_path):
    from ginkassistant.services import file_maker
    md = "# Weekly plan\n\nIntro with **bold** and a [link](https://example.com).\n\n## Tasks\n" + \
         "\n".join(f"- Task number {i}: " + "word " * 25 for i in range(60))
    path = str(tmp_path / "plan.pdf")
    file_maker.make_pdf(path, "Gink plan", md)
    sys.modules.pop("pypdf", None)
    from pypdf import PdfReader
    reader = PdfReader(path)
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) >= 2 and reader.metadata.title == "Gink plan"
    assert "Weekly plan" in text and "Task number 59" in text and "link (https://example.com)" in text and "**" not in text


def test_generated_images_show_without_pillow(tmp_path, monkeypatch):
    raw = jpeg_bytes()
    from ginkassistant.services.image_service import ImageService
    svc = ImageService.__new__(ImageService); svc.files_dir = str(tmp_path)
    (tmp_path / "pic.jpg").write_bytes(raw)
    monkeypatch.setitem(sys.modules, "PIL", None)
    url = svc.thumb_data_url("pic.jpg")
    assert url.startswith("data:image/jpeg;base64,") and base64.b64decode(url.split(",", 1)[1]) == raw


def test_profile_photo_message_without_pillow(monkeypatch, tmp_path):
    raw = jpeg_bytes()
    from ginkassistant.services import profile
    monkeypatch.setitem(sys.modules, "PIL", None)
    store = profile.ProfileStore.__new__(profile.ProfileStore)
    store.get = lambda: {}
    with pytest.raises(ValueError, match="can't be changed on this device"):
        store.set_photo(raw)


def test_update_notice_offers_the_32bit_apk(monkeypatch):
    from ginkassistant.services import updates, platform_utils
    monkeypatch.setattr(platform_utils, "is_android", lambda: True)
    monkeypatch.setattr(updates.platform, "machine", lambda: "armv8l")
    assert updates.asset_name() == "Gink-android-32bit.apk"
    monkeypatch.setattr(updates.platform, "machine", lambda: "armv7l")
    assert updates.asset_name() == "Gink-android-32bit.apk"
    for m in ("aarch64", "x86_64"):
        monkeypatch.setattr(updates.platform, "machine", lambda m=m: m)
        assert updates.asset_name() == "Gink-android.apk"
