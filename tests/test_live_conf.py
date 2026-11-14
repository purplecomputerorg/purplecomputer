"""The 32-bit Key's boot script hands the app its paths through /run/purple-live.conf.
casper never writes that file, so the 64-bit stick keeps its paths."""

from purplecomputer import constants


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


def _fake_mounts(tmp_path, monkeypatch, src):
    mounts = tmp_path / "mounts"
    mounts.write_text(f"/dev/loop0 /rofs squashfs ro 0 0\n{src} /cdrom iso9660 ro 0 0\n")
    sys_block = tmp_path / "block"
    (sys_block / "sdb1").mkdir(parents=True)
    monkeypatch.setattr(constants, "MOUNTS_PATH", str(mounts))
    monkeypatch.setattr(constants, "SYS_BLOCK_DIR", str(sys_block))
    monkeypatch.setattr(constants, "_FAKE_USB", "")
    monkeypatch.setattr(constants.is_usb_present, "_dev", None, raising=False)
    return sys_block


def test_usb_present_follows_the_stick_not_the_stale_mount(tmp_path, monkeypatch):
    sys_block = _fake_mounts(tmp_path, monkeypatch, "/dev/sdb1")
    assert constants.is_usb_present()
    (sys_block / "sdb1").rmdir()
    assert not constants.is_usb_present()


def test_squashfs_off_a_block_device_falls_back_to_the_file(tmp_path, monkeypatch):
    _fake_mounts(tmp_path, monkeypatch, "tmpfs")
    monkeypatch.setattr(constants, "SQUASHFS_PATH", str(tmp_path / "filesystem.squashfs"))
    assert not constants.is_usb_present()


def test_a_stick_put_back_reads_as_reinserted_not_present(tmp_path, monkeypatch):
    sys_block = _fake_mounts(tmp_path, monkeypatch, "/dev/sdb1")
    by_label = tmp_path / "by-label"
    by_label.mkdir()
    monkeypatch.setattr(constants, "DISK_BY_LABEL_DIR", str(by_label))
    (by_label / "PURPLE_INSTALLER").touch()
    assert constants.is_usb_present() and not constants.is_usb_reinserted()
    (sys_block / "sdb1").rmdir()
    assert not constants.is_usb_present() and constants.is_usb_reinserted()
    (by_label / "PURPLE_INSTALLER").unlink()
    assert not constants.is_usb_reinserted()
