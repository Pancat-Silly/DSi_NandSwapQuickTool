"""tkinter 기반 GUI."""

import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import config, tools, winutil
from .swapper import SwapOptions, NandSwapper

WARNING_TEXT = (
    "시작하기 전에 꼭 읽어주세요\n"
    "• 이 프로그램은 DSi 낸드 덤프(nand.bin)를 직접 수정합니다. 잘못되면 DSi 가 벽돌이 될 수 있습니다.\n"
    "• Unlaunch가 설치되어 있는 상태의 낸드를 SafeNANDManager로 낸드를 덤프 한 뒤 4번 항목에 넣어주세요.\n"
    "• 덤프한 nand.bin 과 nand.bin.sha1 원본은 다른 곳에 따로 백업해 두는것을 추천합니다."
)


class Settings:
    def __init__(self):
        self.path = os.path.join(winutil.app_data_dir(config.APP_ID), "settings.json")
        self.data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class Tooltip:
    """마우스를 올리면 작은 설명(여기서는 링크 주소)을 보여준다."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg="#ffffe1", relief="solid", borderwidth=1,
                 padx=4, pady=2).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{config.APP_NAME} v{config.VERSION}")
        self.minsize(820, 760)
        self.settings = Settings()
        self.q: "queue.Queue" = queue.Queue()
        self.busy = False
        self.swapper = None
        self.log_file = None

        self._init_style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_queue)
        self.refresh_tools()

    # ------------------------------------------------------------------ UI
    def _init_style(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base = ("Malgun Gothic", 9) if winutil.IS_WINDOWS else ("TkDefaultFont", 10)
        self.option_add("*Font", base)
        style.configure("Ok.TLabel", foreground="#1a7f37")
        style.configure("Bad.TLabel", foreground="#cf222e")
        style.configure("Big.TButton", padding=(16, 8))
        link_font = ("Malgun Gothic", 9, "underline") if winutil.IS_WINDOWS else ("TkDefaultFont", 10, "underline")
        style.configure("Link.TLabel", foreground="#0969da", font=link_font)

    def _build(self):
        pad = {"padx": 10, "pady": 5}

        # 경고 배너
        banner = tk.Frame(self, bg="#fff4ce", highlightbackground="#e3b341", highlightthickness=1)
        banner.pack(fill="x", **pad)
        tk.Label(banner, text="⚠", bg="#fff4ce", fg="#9a6700", font=("Segoe UI", 18)).pack(
            side="left", padx=(10, 4), anchor="n", pady=6)
        tk.Label(banner, text=WARNING_TEXT, bg="#fff4ce", fg="#3d2c00", justify="left",
                 wraplength=600, anchor="w").pack(side="left", fill="x", expand=True, pady=6)
        ttk.Button(banner, text="SafeNANDManager 받기",
                   command=lambda: winutil.open_url(config.SAFENANDMANAGER_URL)).pack(
            side="right", padx=10, pady=6)

        # 1. 필수 도구
        f1 = ttk.LabelFrame(self, text=" 1. 필수 도구 ")
        f1.pack(fill="x", **pad)
        self.tool_labels = {}
        self._winfsp_missing = False
        rows = [("ninfs", "ninfs + WinFsp", self.install_ninfs, self.manual_ninfs, self.pick_ninfs,
                 f"ninfs : {config.NINFS_RELEASES_URL}\nWinFsp : {config.WINFSP_HOMEPAGE}"),
                ("OSFMount", "OSFMount", self.install_osfmount, self.manual_osfmount, self.pick_osfmount,
                 config.OSFMOUNT_HOMEPAGE)]
        for r, (key, title, inst, manual, pick, manual_url) in enumerate(rows):
            ttk.Label(f1, text=title, width=16).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            lbl = ttk.Label(f1, text="확인 중...", width=60)
            lbl.grid(row=r, column=1, sticky="w")
            self.tool_labels[key] = lbl
            ttk.Button(f1, text="자동 설치", command=inst).grid(row=r, column=2, padx=3)
            mb = ttk.Button(f1, text="수동 설치", command=manual)
            mb.grid(row=r, column=3, padx=3)
            Tooltip(mb, manual_url)
            ttk.Button(f1, text="경로 지정", command=pick).grid(row=r, column=4, padx=(3, 8))
        ttk.Button(f1, text="새로 고침", command=self.refresh_tools).grid(
            row=2, column=2, columnspan=3, sticky="e", padx=8, pady=(0, 5))
        f1.columnconfigure(1, weight=1)

        # 2. A 낸드
        f2 = ttk.LabelFrame(self, text=" 2. 패치에 사용할 낸드 ")
        f2.pack(fill="x", **pad)
        self.a_source = tk.StringVar(value=self.settings.get("a_source", "download"))
        r0 = ttk.Frame(f2)
        r0.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=2)
        ttk.Radiobutton(r0, text="한글판 DSi 낸드 자동 다운로드 (archive.org 에서)",
                        variable=self.a_source, value="download").pack(side="left")
        self._link(r0, "주소 열기 ↗", config.KOREAN_NAND_ZIP_URL).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(f2, text="내 컴퓨터의 nand.bin 또는 zip:", variable=self.a_source,
                        value="local").grid(row=1, column=0, sticky="w", padx=8)
        self.a_path = tk.StringVar(value=self.settings.get("a_path", ""))
        ttk.Entry(f2, textvariable=self.a_path).grid(row=1, column=1, sticky="ew", padx=3)
        ttk.Button(f2, text="찾아보기", command=self._browse_a).grid(row=1, column=2, padx=(3, 8))
        ttk.Label(f2, text="Console ID (선택, 보통 비워둠):").grid(row=2, column=0, sticky="w", padx=8, pady=3)
        self.a_cid = tk.StringVar()
        ttk.Entry(f2, textvariable=self.a_cid, width=24).grid(row=2, column=1, sticky="w", padx=3)
        f2.columnconfigure(1, weight=1)

        # 3. Unlaunch TMD
        f3 = ttk.LabelFrame(self, text=" 3. Unlaunch TMD")
        f3.pack(fill="x", **pad)
        self.tmd_source = tk.StringVar(value=self.settings.get("tmd_source", "download"))
        r0 = ttk.Frame(f3)
        r0.grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=2)
        ttk.Radiobutton(r0, text="gbatemp 에서 자동 다운로드", variable=self.tmd_source,
                        value="download").pack(side="left")
        self._link(r0, "주소 열기 ↗", config.UNLAUNCH_TMD_ZIP_URL).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(f3, text="내 컴퓨터의 zip/폴더 사용:", variable=self.tmd_source,
                        value="local").grid(row=1, column=0, sticky="w", padx=8)
        self.tmd_path = tk.StringVar(value=self.settings.get("tmd_path", ""))
        ttk.Entry(f3, textvariable=self.tmd_path).grid(row=1, column=1, sticky="ew", padx=3)
        ttk.Button(f3, text="zip 선택", command=self._browse_tmd_zip).grid(row=1, column=2, padx=3)
        ttk.Button(f3, text="폴더 선택", command=self._browse_tmd_dir).grid(row=1, column=3, padx=(3, 8))
        f3.columnconfigure(1, weight=1)

        # 4. B 낸드
        f4 = ttk.LabelFrame(self, text=" 4. 수정할 nand.bin")
        f4.pack(fill="x", **pad)
        ttk.Label(f4, text="내 컴퓨터의 nand.bin:").grid(row=0, column=0, sticky="w", padx=8, pady=3)
        self.b_path = tk.StringVar(value=self.settings.get("b_path", ""))
        ttk.Entry(f4, textvariable=self.b_path).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(f4, text="찾아보기", command=self._browse_b).grid(row=0, column=2, padx=(3, 8))
        ttk.Label(f4, text="Console ID (선택, 보통 비워둠):").grid(row=1, column=0, sticky="w", padx=8, pady=3)
        self.b_cid = tk.StringVar()
        ttk.Entry(f4, textvariable=self.b_cid, width=24).grid(row=1, column=1, sticky="w", padx=3)
        opts = ttk.Frame(f4)
        opts.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 4))
        self.make_backup = tk.BooleanVar(value=True)
        self.restore_on_fail = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="작업 전 백업 (권장)", variable=self.make_backup).pack(side="left")
        ttk.Checkbutton(opts, text="실패하면 백업으로 자동 복원", variable=self.restore_on_fail).pack(
            side="left", padx=16)
        f4.columnconfigure(1, weight=1)

        # 실행
        f5 = ttk.Frame(self)
        f5.pack(fill="x", **pad)
        self.start_btn = ttk.Button(f5, text="패치 시작", style="Big.TButton", command=self.start_swap)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(f5, text="취소", command=self.cancel_swap, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        right = ttk.Frame(f5)
        right.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.status = tk.StringVar(value="대기 중")
        ttk.Label(right, textvariable=self.status).pack(anchor="w")
        self.pbar = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.pbar.pack(fill="x")

        # 로그
        self.log_box = ScrolledText(self, height=12, state="disabled", wrap="word",
                                    font=("Consolas", 9) if winutil.IS_WINDOWS else ("TkFixedFont", 9))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _link(self, parent, text, url):
        """클릭하면 브라우저로 url 을 여는 하이퍼링크 라벨."""
        lbl = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2")
        lbl.bind("<Button-1>", lambda e: winutil.open_url(url))
        Tooltip(lbl, url)
        return lbl

    # ------------------------------------------------------------- 파일 선택
    def _browse_a(self):
        p = filedialog.askopenfilename(title="패치에 사용할 낸드 선택 (nand.bin 또는 특정 형식의 zip)",
                                       filetypes=[("NAND 또는 zip", ("*.bin", "*.zip")), ("모든 파일", "*.*")])
        if p:
            self.a_path.set(os.path.normpath(p))
            self.a_source.set("local")

    def _browse_b(self):
        p = filedialog.askopenfilename(title="수정할 낸드 선택", filetypes=[("NAND", "*.bin"), ("모든 파일", "*.*")])
        if p:
            self.b_path.set(os.path.normpath(p))

    def _browse_tmd_zip(self):
        p = filedialog.askopenfilename(title="unlaunch-tmd.zip 선택", filetypes=[("zip", "*.zip"), ("모든 파일", "*.*")])
        if p:
            self.tmd_path.set(os.path.normpath(p))
            self.tmd_source.set("local")

    def _browse_tmd_dir(self):
        p = filedialog.askdirectory(title="unlaunch TMD 폴더 선택 (00030017 이 들어있는 폴더)")
        if p:
            self.tmd_path.set(os.path.normpath(p))
            self.tmd_source.set("local")

    # ------------------------------------------------------------- 도구 관리
    def refresh_tools(self):
        def work():
            st = tools.check_all(self.settings.get("ninfs_path"), self.settings.get("osfmount_path"))
            self.q.put(("tools", st))
        threading.Thread(target=work, daemon=True).start()

    def _show_tools(self, statuses):
        by = {s.name: s for s in statuses}
        n, w, o = by["ninfs"], by["WinFsp"], by["OSFMount"]
        self._winfsp_missing = n.found and not w.found
        if n.found and w.found:
            self.tool_labels["ninfs"].configure(text=f"✔ 설치됨  {n.path}", style="Ok.TLabel")
        elif n.found:
            self.tool_labels["ninfs"].configure(text="✖ ninfs 는 있지만 WinFsp 가 없습니다 → 자동 설치",
                                                style="Bad.TLabel")
        else:
            self.tool_labels["ninfs"].configure(text="✖ 설치되지 않음", style="Bad.TLabel")
        if o.found:
            self.tool_labels["OSFMount"].configure(text=f"✔ 설치됨  {o.path}", style="Ok.TLabel")
        else:
            self.tool_labels["OSFMount"].configure(text="✖ 설치되지 않음", style="Bad.TLabel")

    def pick_ninfs(self):
        p = filedialog.askopenfilename(title="ninfs.exe 선택", filetypes=[("ninfs", "ninfs*.exe"), ("모든 파일", "*.*")])
        if p:
            self.settings.set("ninfs_path", os.path.normpath(p))
            self.refresh_tools()

    def pick_osfmount(self):
        p = filedialog.askopenfilename(title="OSFMount.com 선택 (OSFMount 설치 폴더)",
                                       filetypes=[("OSFMount", ("OSFMount.com", "OSFMount.exe")),
                                                  ("모든 파일", "*.*")])
        if p:
            self.settings.set("osfmount_path", os.path.normpath(p))
            self.refresh_tools()

    def install_ninfs(self):
        msg = ("ninfs 공식 Windows 설치 파일(GitHub, WinFsp 포함)을 내려받아 설치합니다.\n\n"
               "• ninfs: MIT 라이선스 (Ian Burgwin)\n"
               "• WinFsp: GPLv3 + FLOSS 예외 (Bill Zissimopoulos)\n\n"
               "설치를 진행하면 위 라이선스에 동의하는 것으로 봅니다. 계속할까요?")
        if messagebox.askyesno("ninfs 설치", msg):
            self._run_bg_task("ninfs 설치", tools.install_ninfs)

    def install_osfmount(self):
        msg = ("PassMark 공식 사이트에서 OSFMount 설치 파일을 내려받아 설치합니다.\n\n"
               "OSFMount 는 PassMark Software 의 무료(프리웨어) 프로그램이며, 이 프로그램에 포함되어 "
               "배포되지 않습니다. 설치를 진행하면 PassMark 의 사용권 계약에 동의하는 것으로 봅니다.\n"
               f"{config.OSFMOUNT_HOMEPAGE}\n\n계속할까요?")
        if messagebox.askyesno("OSFMount 설치", msg):
            self._run_bg_task("OSFMount 설치", tools.install_osfmount)

    def manual_ninfs(self):
        """ninfs 공식 릴리스 페이지(설치 파일에 WinFsp 포함)를 연다.
        ninfs 는 있는데 WinFsp 만 없으면 WinFsp 공식 사이트를 연다."""
        if self._winfsp_missing:
            winutil.open_url(config.WINFSP_HOMEPAGE)
        else:
            winutil.open_url(config.NINFS_RELEASES_URL)

    def manual_osfmount(self):
        """OSFMount 공식 사이트(PassMark)를 연다."""
        winutil.open_url(config.OSFMOUNT_HOMEPAGE)

    def _run_bg_task(self, title, fn):
        if self.busy:
            return
        self._set_busy(True, cancellable=False)
        self._log(f"--- {title} ---")

        def progress(done, total):
            if total:
                self.q.put(("progress", f"{title}: {done / 1048576:.1f}/{total / 1048576:.1f} MB", done / total))

        def work():
            try:
                ok = fn(lambda s: self.q.put(("log", s)), progress)
                self.q.put(("log", f"{title} {'완료' if ok else '실패 (경로 지정으로 직접 선택할 수 있습니다)'}"))
            except Exception as e:
                self.q.put(("log", f"[오류] {title}: {e}"))
            self.q.put(("idle", None))
            st = tools.check_all(self.settings.get("ninfs_path"), self.settings.get("osfmount_path"))
            self.q.put(("tools", st))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------- 패치 실행
    def start_swap(self):
        if self.busy:
            return
        b = self.b_path.get().strip()
        if not b:
            messagebox.showwarning("수정할 낸드", "수정할 낸드(nand.bin)를 선택하세요.")
            return

        if not messagebox.askokcancel(
            "경고",
            "패치를 시작하기 전에 안내 사항을 확인해 주십시오.\n\n"
            "본 패치의 적용으로 인해 발생할 수 있는 모든 문제 및 불이익은 사용자에게 있습니다.\n"
            "계속 진행할 경우 위 사항에 동의한 것으로 간주됩니다."
        ):
            return
        if not messagebox.askyesno(
            "확인",
            f"다음 파일이 직접 수정됩니다:\n\n{b}\n{b}.sha1\n\n"
            "Unlaunch가 설치된 상태의 낸드를 SafeNANDManager로 백업해 두셨나요?"
        ):
            return
        for k, v in (("a_source", self.a_source.get()), ("a_path", self.a_path.get()),
                     ("tmd_source", self.tmd_source.get()), ("tmd_path", self.tmd_path.get()),
                     ("b_path", b)):
            self.settings.set(k, v)

        opts = SwapOptions(
            b_path=b,
            a_source=self.a_source.get(), a_local_path=self.a_path.get().strip(),
            tmd_source=self.tmd_source.get(), tmd_local_path=self.tmd_path.get().strip(),
            a_console_id=self.a_cid.get().strip(), b_console_id=self.b_cid.get().strip(),
            make_backup=self.make_backup.get(), restore_on_fail=self.restore_on_fail.get(),
            ninfs_path=self.settings.get("ninfs_path"), osfmount_path=self.settings.get("osfmount_path"),
        )
        log_dir = os.path.join(winutil.app_data_dir(config.APP_ID), "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, time.strftime("patch-%Y%m%d-%H%M%S.log"))

        import platform
        self._set_busy(True, cancellable=True)
        self._log(f"{config.APP_NAME} v{config.VERSION} / {platform.platform()} / "
                  f"Python {platform.python_version()}")
        self.swapper = NandSwapper(opts, log=lambda s: self.q.put(("log", s)),
                               progress=lambda t, f: self.q.put(("progress", t, f)))

        def work():
            ok = False
            try:
                ok = self.swapper.run()
            except Exception as e:
                self.q.put(("log", f"[오류] {e!r}"))
            self.q.put(("done", ok))

        threading.Thread(target=work, daemon=True).start()

    def cancel_swap(self):
        if self.swapper:
            self.swapper.cancel()
            self._log("취소 요청됨 (마운트 전 단계에서만 취소됩니다)")

    # ------------------------------------------------------------- 공통
    def _set_busy(self, busy, cancellable=False):
        self.busy = busy
        self.start_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if (busy and cancellable) else "disabled")
        if not busy:
            self.pbar.stop()
            self.pbar.configure(mode="determinate")

    def _log(self, s):
        if s.strip():
            s = time.strftime("[%H:%M:%S] ") + s
        self.log_box.configure(state="normal")
        self.log_box.insert("end", s + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        if self.log_file and self.busy:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(s + "\n")
            except Exception:
                pass

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log(item[1])
                elif kind == "progress":
                    _, text, frac = item
                    self.status.set(text)
                    if frac is None:
                        if str(self.pbar.cget("mode")) != "indeterminate":
                            self.pbar.configure(mode="indeterminate", value=0)
                            self.pbar.start(25)
                    else:
                        if str(self.pbar.cget("mode")) != "determinate":
                            self.pbar.stop()
                            self.pbar.configure(mode="determinate")
                        self.pbar["value"] = max(0.0, min(100.0, frac * 100))
                elif kind == "tools":
                    self._show_tools(item[1])
                elif kind == "idle":
                    self._set_busy(False)
                    self.status.set("대기 중")
                elif kind == "done":
                    ok = item[1]
                    self._set_busy(False)
                    self.pbar["value"] = 100 if ok else 0
                    self.status.set("완료" if ok else "실패 - 로그를 확인하세요")
                    if self.log_file:
                        self._log(f"(로그 파일: {self.log_file})")
                    self.log_file = None
                    if ok:
                        messagebox.showinfo("완료", "패치가 완료되었습니다.\n수정된 nand.bin과 nand.bin.sha1을 "
                                                   "SafeNANDManager로 복원하세요.")
                    else:
                        messagebox.showerror("실패", "패치에 실패했습니다. 아래 로그를 확인하세요.")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_close(self):
        if self.busy:
            messagebox.showwarning("작업 중", "작업이 진행 중입니다. 끝난 뒤 닫아 주세요.\n"
                                            "(마운트된 상태에서 강제로 닫으면 낸드 파일이 손상될 수 있습니다)")
            return
        self.destroy()


def run():
    winutil.enable_dpi_awareness()
    winutil.ensure_hidden_console()
    app = App()
    if winutil.IS_WINDOWS and not winutil.is_admin():
        app._log("[경고] 관리자 권한이 아닙니다. 마운트가 실패할 수 있습니다.")
    app.mainloop()
