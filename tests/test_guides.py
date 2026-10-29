"""가이드 파일/파서 검사 (창을 띄우지 않음).

    python -m pytest tests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsinsqt.guide_view import GUIDES, guides_dir, parse_guide, parse_inline  # noqa: E402


def test_parse_inline():
    spans = parse_inline("앞 **굵게** 중간 [링크](https://example.com) 끝")
    assert spans == [("앞 ", "text", None), ("굵게", "bold", None), (" 중간 ", "text", None),
                     ("링크", "link", "https://example.com"), (" 끝", "text", None)]


def test_parse_blocks():
    src = "# 제목\n\n\n## 소제목\n- 항목\n1. 하나\n> 주의\n![설명](images/a.png)\n---\n문단\n\n"
    kinds = [b[0] for b in parse_guide(src)]
    assert kinds == ["h1", "gap", "h2", "bullet", "num", "note", "img", "hr", "p"]
    img = [b for b in parse_guide(src) if b[0] == "img"][0]
    assert img == ("img", "images/a.png", "설명")


def test_guide_files_and_images_exist():
    base = guides_dir()
    for g in GUIDES:
        path = os.path.join(base, g.filename)
        assert os.path.isfile(path), path
        with open(path, encoding="utf-8") as f:
            blocks = parse_guide(f.read())
        assert blocks and blocks[0][0] == "h1", f"{g.filename}: 첫 줄은 '# 제목' 이어야 합니다"
        for b in blocks:
            if b[0] == "img":
                assert os.path.isfile(os.path.join(base, b[1])), f"{g.filename}: 사진 없음 {b[1]}"


if __name__ == "__main__":
    test_parse_inline()
    test_parse_blocks()
    test_guide_files_and_images_exist()
    print("OK")
