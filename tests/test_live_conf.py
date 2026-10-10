"""The 32-bit Key's boot script hands the app its paths through /run/purple-live.conf.
casper never writes that file, so the 64-bit stick keeps its paths."""

from purple_tui import constants


def test_without_conf_the_casper_paths_stand():
    assert constants.SQUASHFS_PATH == "/cdrom/casper/filesystem.squashfs"
    assert constants.PAYLOAD_DIR == "/cdrom/purple"


def test_missing_conf_reads_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "LIVE_CONF_PATH", str(tmp_path / "none"))
    assert constants._live_conf() == {}


def test_conf_lines_become_paths(tmp_path, monkeypatch):
    conf = tmp_path / "purple-live.conf"
    conf.write_text("SQUASHFS=/cdrom/purple32/filesystem.squashfs\nPURPLE_PAYLOAD_DIR=/cdrom/purple32\n")
    monkeypatch.setattr(constants, "LIVE_CONF_PATH", str(conf))
    assert constants._live_conf() == {
        "SQUASHFS": "/cdrom/purple32/filesystem.squashfs",
        "PURPLE_PAYLOAD_DIR": "/cdrom/purple32",
    }
