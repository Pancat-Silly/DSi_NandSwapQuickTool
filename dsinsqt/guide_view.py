"""가이드 창: dsinsqt/guides/*.md 파일을 읽어 글·사진·하이퍼링크를 새 창에 보여준다.

가이드 내용은 코드가 아니라 guides 폴더의 .md 파일에서 고치면 된다.
지원하는 문법 (마크다운의 아주 작은 부분집합):

    # 큰 제목
    ## 소제목
    일반 문단. **굵게**, [링크 글자](https://주소)
    - 글머리표 항목
    1. 번호 항목
    > 노란 상자로 강조되는 안내/주의 문구
    ![사진 설명](images/파일이름.png)      ← 한 줄을 통째로 차지해야 함 (PNG/GIF)
    ---                                     ← 구분선

빈 줄은 문단 사이 간격이 된다.
"""

import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk

from . import winutil


@dataclass(frozen=True)
class Guide:
    key: str
    title: str        # 창 제목
    button_text: str  # 메인 화면 버튼 글자
    filename: str     # guides 폴더 안의 .md 파일


GUIDES = (
    Guide("extract", "DSi에서 낸드 추출하기", "① DSi에서 낸드 추출하기", "extract_nand.md"),
    Guide("apply", "수정한 낸드를 기기에 적용하기", "② 수정한 낸드 기기에 적용하기", "apply_nand.md"),
)

# 색상 (메인 화면의 가이드 배너와 공유)
BANNER_BG = "#ddf4ff"
BANNER_BORDER = "#54aeff"
BOOK_COVER = "#0969da"
BOOK_PAGE = "#ffffff"
BOOK_LINE = "#9cc3f5"
LINK_FG = "#0969da"
NOTE_BG = "#fff4ce"
MUTED_FG = "#57606a"


def guides_dir() -> str:
    """가이드 .md/이미지 폴더. PyInstaller onefile 빌드에서는 압축이 풀린 임시 폴더 안에 있다."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "dsinsqt", "guides")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "guides")


# ------------------------------------------------------------------ 파서
_INLINE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\((\S+?)\)")
_IMAGE = re.compile(r"^!\[([^\]]*)\]\((\S+?)\)$")
_NUM = re.compile(r"^(\d+)[.)]\s+(.*)$")


def parse_inline(text):
    """문장을 (글자, 종류, 링크주소) 조각 목록으로 나눈다. 종류: text / bold / link."""
    spans, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            spans.append((text[pos:m.start()], "text", None))
        if m.group(1) is not None:
            spans.append((m.group(1), "bold", None))
        else:
            spans.append((m.group(2), "link", m.group(3)))
        pos = m.end()
    if pos < len(text):
        spans.append((text[pos:], "text", None))
    return spans


def parse_guide(source):
    """가이드 원문을 블록 목록으로 바꾼다 (Tk 없이 테스트 가능)."""
    blocks = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            if blocks and blocks[-1][0] != "gap":
                blocks.append(("gap",))
            continue
        if line == "---":
            blocks.append(("hr",))
        elif line.startswith("## "):
            blocks.append(("h2", parse_inline(line[3:].strip())))
        elif line.startswith("# "):
            blocks.append(("h1", parse_inline(line[2:].strip())))
        elif line.startswith(("- ", "* ")):
            blocks.append(("bullet", parse_inline(line[2:].strip())))
        elif line.startswith(">"):
            blocks.append(("note", parse_inline(line[1:].strip())))
        elif _IMAGE.match(line):
            m = _IMAGE.match(line)
            blocks.append(("img", m.group(2), m.group(1)))
        elif _NUM.match(line):
            m = _NUM.match(line)
            blocks.append(("num", m.group(1), parse_inline(m.group(2))))
        else:
            blocks.append(("p", parse_inline(line)))
    while blocks and blocks[-1][0] == "gap":
        blocks.pop()
    return blocks


# ------------------------------------------------------------------ 책 아이콘
def book_icon(parent, size=32, bg=BANNER_BG):
    """책(펼친 책) 모양 아이콘을 그린 Canvas. 이모지는 Windows Tk 에서 깨질 수 있어 직접 그린다."""
    s = size / 32.0
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)

    def P(*pts):
        return [v * s for v in pts]

    # 표지 (뒤)
    c.create_polygon(P(1, 9, 16, 11, 31, 9, 31, 28, 16, 30, 1, 28), fill=BOOK_COVER, outline=BOOK_COVER)
    # 왼쪽/오른쪽 페이지
    c.create_polygon(P(3, 6, 15, 8.5, 15, 27, 3, 24.5), fill=BOOK_PAGE, outline=BOOK_COVER, width=max(1, s))
    c.create_polygon(P(17, 8.5, 29, 6, 29, 24.5, 17, 27), fill=BOOK_PAGE, outline=BOOK_COVER, width=max(1, s))
    # 글줄
    for off in (4, 7.5, 11, 14.5):
        c.create_line(P(5.5, 7 + off, 12.5, 8.5 + off), fill=BOOK_LINE, width=max(1, 1.4 * s))
        c.create_line(P(19.5, 8.5 + off, 26.5, 7 + off), fill=BOOK_LINE, width=max(1, 1.4 * s))
    return c


# ------------------------------------------------------------------ 가이드 창
class GuideWindow(tk.Toplevel):
    MAX_IMAGE_WIDTH = 640

    def __init__(self, master, guide: Guide):
        super().__init__(master)
        self.guide = guide
        self.title(f"가이드 - {guide.title}")
        self.geometry("760x680")
        self.minsize(520, 400)
        self._images = []  # PhotoImage 참조 유지 (안 하면 사진이 사라짐)
        self._link_count = 0
        self._init_fonts()
        self._build()
        self.load()
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_set()

    def _init_fonts(self):
        base = tkfont.nametofont("TkDefaultFont").actual()
        family = "Malgun Gothic" if winutil.IS_WINDOWS else base["family"]
        size = 10 if winutil.IS_WINDOWS else max(10, abs(base["size"]))
        self.f_body = tkfont.Font(self, family=family, size=size)
        self.f_bold = tkfont.Font(self, family=family, size=size, weight="bold")
        self.f_h1 = tkfont.Font(self, family=family, size=size + 7, weight="bold")
        self.f_h2 = tkfont.Font(self, family=family, size=size + 3, weight="bold")
        self.f_small = tkfont.Font(self, family=family, size=size - 1)
        self.f_link = tkfont.Font(self, family=family, size=size, underline=True)

    def _build(self):
        head = tk.Frame(self, bg=BANNER_BG, highlightbackground=BANNER_BORDER, highlightthickness=1)
        head.pack(fill="x", padx=10, pady=(10, 0))
        book_icon(head, 32).pack(side="left", padx=(12, 8), pady=8)
        tk.Label(head, text=self.guide.title, bg=BANNER_BG, fg="#0a3069",
                 font=self.f_h2).pack(side="left", pady=8)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        self.text = tk.Text(body, wrap="word", font=self.f_body, padx=18, pady=14, bd=0,
                            relief="flat", highlightthickness=1, highlightbackground="#d0d7de",
                            cursor="arrow", spacing1=2, spacing3=2, bg="#ffffff", fg="#1f2328")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        t = self.text
        t.tag_configure("h1", font=self.f_h1, spacing1=4, spacing3=10)
        t.tag_configure("h2", font=self.f_h2, spacing1=14, spacing3=6, foreground="#0a3069")
        t.tag_configure("bold", font=self.f_bold)
        t.tag_configure("bullet", lmargin1=8, lmargin2=26)
        t.tag_configure("num", lmargin1=8, lmargin2=30)
        t.tag_configure("note", background=NOTE_BG, lmargin1=10, lmargin2=10, rmargin=10,
                        spacing1=6, spacing3=6)
        t.tag_configure("center", justify="center")
        t.tag_configure("caption", font=self.f_small, foreground=MUTED_FG, justify="center", spacing3=8)
        t.tag_configure("missing", foreground="#cf222e", justify="center")
        t.tag_configure("hr", font=tkfont.Font(self, size=1), background="#d0d7de", spacing1=0, spacing3=0)
        t.tag_configure("link", foreground=LINK_FG, font=self.f_link)
        t.tag_bind("link", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.configure(cursor="arrow"))

        foot = ttk.Frame(self)
        foot.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(foot, text="닫기", command=self.destroy).pack(side="right")

    # -------------------------------------------------------------- 내용
    def load(self):
        path = os.path.join(guides_dir(), self.guide.filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            source = f"# {self.guide.title}\n\n> 가이드 파일을 열 수 없습니다: {e}"
        self.render(parse_guide(source), os.path.dirname(path))

    def render(self, blocks, base_dir):
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._images.clear()
        for b in blocks:
            kind = b[0]
            if kind == "gap":
                t.insert("end", "\n")
            elif kind == "hr":
                t.insert("end", "\n")
                t.insert("end", " \n", "hr")
                t.insert("end", "\n")
            elif kind in ("h1", "h2", "p", "note"):
                self._spans(b[1], kind if kind != "p" else ())
                t.insert("end", "\n", kind if kind != "p" else ())
            elif kind == "bullet":
                t.insert("end", "•  ", "bullet")
                self._spans(b[1], "bullet")
                t.insert("end", "\n", "bullet")
            elif kind == "num":
                t.insert("end", f"{b[1]}.  ", ("num", "bold"))
                self._spans(b[2], "num")
                t.insert("end", "\n", "num")
            elif kind == "img":
                self._image(os.path.join(base_dir, b[1]), b[2])
        t.configure(state="disabled")

    def _spans(self, spans, base_tags):
        base = (base_tags,) if isinstance(base_tags, str) else tuple(base_tags)
        for text, kind, url in spans:
            if kind == "link":
                self._link_count += 1
                tag = f"link{self._link_count}"
                self.text.insert("end", text, base + ("link", tag))
                self.text.tag_bind(tag, "<Button-1>", lambda e, u=url: winutil.open_url(u))
            elif kind == "bold":
                self.text.insert("end", text, base + ("bold",))
            else:
                self.text.insert("end", text, base)

    def _image(self, path, caption):
        t = self.text
        try:
            img = tk.PhotoImage(master=self, file=path)
            factor = -(-img.width() // self.MAX_IMAGE_WIDTH)  # 올림 나눗셈
            if factor > 1:
                img = img.subsample(factor, factor)
            self._images.append(img)
            t.image_create("end", image=img, padx=4, pady=4)
            t.tag_add("center", "end-2c", "end-1c")
            t.insert("end", "\n", "center")
        except (tk.TclError, OSError):
            t.insert("end", f"[사진을 불러올 수 없습니다: {os.path.basename(path)}]\n", "missing")
        if caption:
            t.insert("end", caption + "\n", "caption")
