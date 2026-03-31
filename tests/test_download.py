"""Tests for transformers_ocr.download"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transformers_ocr import config as tocr_config
from transformers_ocr import download as tocr_download


class TestPurge:
    @patch("shutil.rmtree")
    def test_purge(self, mock_rmtree, capsys):
        tocr_download.purge_manga_ocr_data()
        assert mock_rmtree.call_count == 2
        paths = [c[0][0] for c in mock_rmtree.call_args_list]
        assert tocr_config.MANGA_OCR_PREFIX in paths
        assert tocr_config.HUGGING_FACE_CACHE_PATH in paths
        assert "Purged" in capsys.readouterr().out
