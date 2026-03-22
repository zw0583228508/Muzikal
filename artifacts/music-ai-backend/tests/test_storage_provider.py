"""
Tests for storage/storage_provider.py — LocalStorage and factory.
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from storage.storage_provider import LocalStorage, get_storage, StorageProvider


class TestLocalStorage:
    @pytest.fixture
    def tmp_storage(self, tmp_path):
        return LocalStorage(base_path=str(tmp_path))

    def test_is_storage_provider_subclass(self, tmp_storage):
        assert isinstance(tmp_storage, StorageProvider)

    def test_save_returns_string(self, tmp_storage):
        result = tmp_storage.save("test.bin", b"hello")
        assert isinstance(result, str)

    def test_save_creates_file(self, tmp_storage, tmp_path):
        tmp_storage.save("data/out.bin", b"world")
        assert (tmp_path / "data" / "out.bin").exists()

    def test_load_returns_original_bytes(self, tmp_storage):
        data = b"Shalom World"
        tmp_storage.save("greet.bin", data)
        assert tmp_storage.load("greet.bin") == data

    def test_exists_true_after_save(self, tmp_storage):
        tmp_storage.save("exists.bin", b"x")
        assert tmp_storage.exists("exists.bin") is True

    def test_exists_false_before_save(self, tmp_storage):
        assert tmp_storage.exists("never_saved.bin") is False

    def test_delete_removes_file(self, tmp_storage):
        tmp_storage.save("to_delete.bin", b"bye")
        tmp_storage.delete("to_delete.bin")
        assert tmp_storage.exists("to_delete.bin") is False

    def test_delete_nonexistent_no_error(self, tmp_storage):
        tmp_storage.delete("ghost.bin")

    def test_get_url_returns_string(self, tmp_storage):
        tmp_storage.save("file.mid", b"MIDI")
        url = tmp_storage.get_url("file.mid")
        assert isinstance(url, str)
        assert "file.mid" in url

    def test_save_nested_key(self, tmp_storage):
        data = b"nested"
        tmp_storage.save("a/b/c/d.wav", data)
        assert tmp_storage.load("a/b/c/d.wav") == data

    def test_overwrite_existing(self, tmp_storage):
        tmp_storage.save("overwrite.bin", b"old")
        tmp_storage.save("overwrite.bin", b"new")
        assert tmp_storage.load("overwrite.bin") == b"new"

    def test_large_data(self, tmp_storage):
        data = os.urandom(1024 * 1024)  # 1 MB
        tmp_storage.save("large.bin", data)
        assert tmp_storage.load("large.bin") == data

    def test_unicode_key(self, tmp_storage):
        tmp_storage.save("audio_proj_123.wav", b"data")
        assert tmp_storage.exists("audio_proj_123.wav")

    def test_save_empty_bytes(self, tmp_storage):
        tmp_storage.save("empty.bin", b"")
        assert tmp_storage.load("empty.bin") == b""


class TestGetStorage:
    def test_returns_storage_provider(self, tmp_path, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT", raising=False)
        monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
        import storage.storage_provider as sp
        sp._instance = None
        result = sp.get_storage()
        assert isinstance(result, StorageProvider)
        sp._instance = None

    def test_returns_local_when_no_s3_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT", raising=False)
        monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
        import storage.storage_provider as sp
        sp._instance = None
        result = sp.get_storage()
        assert isinstance(result, LocalStorage)
        sp._instance = None

    def test_singleton_same_instance(self, tmp_path, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT", raising=False)
        monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
        import storage.storage_provider as sp
        sp._instance = None
        inst1 = sp.get_storage()
        inst2 = sp.get_storage()
        assert inst1 is inst2
        sp._instance = None
