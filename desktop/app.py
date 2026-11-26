"""
CleanGram Desktop Application (Windows Standalone GUI).
Berjalan 100% lokal di komputer pengguna tanpa server perantara atau batas waktu.
Mendukung Login Scan QR Telegram, Nomor HP + OTP, Verifikasi 2FA, dan Review Target.
"""

import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

import qrcode
import ttkbootstrap as ttk
from PIL import Image, ImageTk
from ttkbootstrap.constants import BOTH, DISABLED, END, LEFT, NORMAL, RIGHT, VERTICAL, X, Y
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.scrolled import ScrolledText

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine import (  # noqa: E402
    DesktopCleanerEngine,
    load_saved_credentials,
    save_credentials,
)


def resource_path(rel_path: str) -> Path:
    """Mendukung resolusi asset baik saat run script maupun setelah dibundle PyInstaller."""
    root = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return root / rel_path


class TwoFADialog(ttk.Toplevel):
    """Dialog input password 2FA Telegram bergaya gelap."""

    def __init__(self, parent: ttk.Window) -> None:
        super().__init__(parent)
        self.title("Verifikasi 2 Langkah (2FA)")
        self.geometry("380x195")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: Optional[str] = None
        container = ttk.Frame(self, padding=18)
        container.pack(fill=BOTH, expand=True)

        ttk.Label(
            container,
            text="Akun Anda dilindungi Password 2FA Telegram.\nMasukkan password Anda untuk melanjutkan:",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 10))

        self.pwd_var = ttk.StringVar()
        entry = ttk.Entry(container, textvariable=self.pwd_var, show="*")
        entry.pack(fill=X, pady=(0, 14))
        entry.focus_set()
        entry.bind("<Return>", lambda _e: self._submit())

        btn_row = ttk.Frame(container)
        btn_row.pack(fill=X)
        ttk.Button(btn_row, text="Batal", bootstyle="secondary-outline", command=self._cancel).pack(
            side=RIGHT, padx=(6, 0)
        )
        ttk.Button(btn_row, text="Konfirmasi", bootstyle="info", command=self._submit).pack(
            side=RIGHT
        )

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 380) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 195) // 2
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _submit(self) -> None:
        self.result = self.pwd_var.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class CleanGramDesktopApp:
    """Antarmuka utama CleanGram Desktop."""

    def __init__(self, root: ttk.Window) -> None:
        self.root = root
        self.root.title("CleanGram Desktop — Pembersih Massal Telegram")
        self.root.geometry("690x790")
        self.root.minsize(610, 700)

        ico_path = resource_path("assets/icon.ico")
        if ico_path.exists():
            try:
                self.root.iconbitmap(str(ico_path))
            except Exception:
                pass

        self.engine = DesktopCleanerEngine()
        self._qr_polling = False
        self._qr_after_id: Optional[str] = None
        self._qr_photo: Optional[ImageTk.PhotoImage] = None
        self._logo_photo: Optional[ImageTk.PhotoImage] = None

        self._targets: list[dict[str, Any]] = []
        self._protected: list[dict[str, Any]] = []
        self._selected_ids: set[int] = set()

        self._build_layout()
        self._load_config()
        self._show_step(1)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _run_ui(self, fn: Any) -> None:
        self.root.after(0, fn)

    def _build_layout(self) -> None:
        # Header Bar
        header = ttk.Frame(self.root, padding=(18, 12))
        header.pack(fill=X)

        logo_file = resource_path("assets/logo.png")
        if logo_file.exists():
            img = Image.open(logo_file).resize((32, 32), Image.Resampling.LANCZOS)
            self._logo_photo = ImageTk.PhotoImage(img)
            ttk.Label(header, image=self._logo_photo).pack(side=LEFT, padx=(0, 10))

        title_col = ttk.Frame(header)
        title_col.pack(side=LEFT)
        ttk.Label(title_col, text="CleanGram Desktop", font=("Segoe UI", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            title_col,
            text="100% Lokal di PC Anda • Bebas Limit & Anti-Blokir",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(anchor="w")

        ttk.Button(
            header,
            text="GitHub",
            bootstyle="secondary-outline",
            command=lambda: webbrowser.open("https://github.com/BenedichtusRW/cleangram"),
        ).pack(side=RIGHT)

        ttk.Separator(self.root).pack(fill=X)

        # Body Stack
        self.body = ttk.Frame(self.root, padding=(20, 14))
        self.body.pack(fill=BOTH, expand=True)

        self.step1_frame = ttk.Frame(self.body)
        self.step2_frame = ttk.Frame(self.body)
        self.step3_frame = ttk.Frame(self.body)

        self._build_step1()
        self._build_step2()
        self._build_step3()

        # Footer Watermark
        ttk.Separator(self.root).pack(fill=X)
        footer = ttk.Frame(self.root, padding=(16, 8))
        footer.pack(fill=X)
        ttk.Label(
            footer,
            text="CleanGram Open Source • Keluar Tanpa Blokir • Built by ben_dev",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(side=LEFT)

        gh_lbl = ttk.Label(
            footer,
            text="github.com/BenedichtusRW",
            font=("Consolas", 8),
            bootstyle="info",
            cursor="hand2",
        )
        gh_lbl.pack(side=RIGHT)
        gh_lbl.bind("<Button-1>", lambda _e: webbrowser.open("https://github.com/BenedichtusRW"))

    def _build_step1(self) -> None:
        # 1. API Telegram Card
        api_card = ttk.Labelframe(
            self.step1_frame,
            text=" 1. Kredensial API Telegram (Disimpan Lokal di PC Anda) ",
            padding=12,
        )
        api_card.pack(fill=X, pady=(0, 10))

        api_top = ttk.Frame(api_card)
        api_top.pack(fill=X, pady=(0, 8))
        ttk.Label(
            api_top,
            text="Ambil API ID & Hash gratis di my.telegram.org (hanya perlu 1x di awal):",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(side=LEFT)
        ttk.Button(
            api_top,
            text="Buka my.telegram.org",
            bootstyle="link",
            command=lambda: webbrowser.open("https://my.telegram.org"),
        ).pack(side=RIGHT)

        grid = ttk.Frame(api_card)
        grid.pack(fill=X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=2)

        ttk.Label(grid, text="API ID (Angka)", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Label(grid, text="API Hash", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=1, sticky="w"
        )

        self.api_id_var = ttk.StringVar()
        self.api_hash_var = ttk.StringVar()
        ttk.Entry(grid, textvariable=self.api_id_var).grid(
            row=1, column=0, sticky="ew", padx=(0, 8), pady=(3, 0)
        )
        ttk.Entry(grid, textvariable=self.api_hash_var).grid(
            row=1, column=1, sticky="ew", pady=(3, 0)
        )

        self.save_api_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            api_card,
            text="Simpan API di laptop ini agar tidak perlu ketik ulang",
            variable=self.save_api_var,
            bootstyle="round-toggle",
        ).pack(anchor="w", pady=(8, 0))

        # 2. Whitelist Card
        wl_card = ttk.Labelframe(
            self.step1_frame,
            text=" 2. Grup / Channel / Bot yang DILINDUNGI (Jangan Dihapus) ",
            padding=12,
        )
        wl_card.pack(fill=X, pady=(0, 10))

        ttk.Label(
            wl_card,
            text=(
                "Ketik sebagian kata/nama grup penting agar aman (pisahkan koma). Contoh: ketik 'keluarga'\n"
                "maka 'Grup Keluarga Besar' aman. Kontak HP & chat pribadi otomatis aman (boleh kosong)."
            ),
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(anchor="w", pady=(0, 6))

        self.whitelist_var = ttk.StringVar()
        wl_entry = ttk.Entry(wl_card, textvariable=self.whitelist_var)
        wl_entry.pack(fill=X)
        ttk.Label(
            wl_card,
            text="Contoh isi: kampus, kantor, keluarga, crypto, kerjaan",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(anchor="w", pady=(4, 0))

        # 3. Login Tabs (QR vs OTP)
        self.auth_tabs = ttk.Notebook(self.step1_frame, bootstyle="info")
        self.auth_tabs.pack(fill=BOTH, expand=True)

        # Tab QR
        qr_tab = ttk.Frame(self.auth_tabs, padding=14)
        self.auth_tabs.add(qr_tab, text="  Scan QR Telegram (Cepat)  ")

        self.qr_btn = ttk.Button(
            qr_tab,
            text="Buat QR Code Telegram",
            bootstyle="info",
            command=self._on_start_qr,
        )
        self.qr_btn.pack(fill=X, pady=(0, 8))

        self.qr_status_lbl = ttk.Label(
            qr_tab,
            text="Klik tombol di atas lalu scan dari Telegram HP: Settings -> Devices -> Link Desktop Device.",
            font=("Segoe UI", 8),
            bootstyle="secondary",
            wraplength=560,
            justify="center",
        )
        self.qr_status_lbl.pack(pady=(0, 8))

        self.qr_img_lbl = ttk.Label(qr_tab)
        self.qr_img_lbl.pack(pady=4)

        self.qr_cancel_btn = ttk.Button(
            qr_tab,
            text="Batalkan Scan QR",
            bootstyle="secondary-outline",
            command=self._stop_qr,
        )

        # Tab OTP
        otp_tab = ttk.Frame(self.auth_tabs, padding=14)
        self.auth_tabs.add(otp_tab, text="  Nomor HP & Kode OTP  ")

        ttk.Label(otp_tab, text="Nomor HP Telegram (contoh: +628123... atau 08123...)", font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        phone_row = ttk.Frame(otp_tab)
        phone_row.pack(fill=X, pady=(4, 12))
        self.phone_var = ttk.StringVar()
        ttk.Entry(phone_row, textvariable=self.phone_var).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.send_otp_btn = ttk.Button(
            phone_row, text="Kirim OTP", bootstyle="info", command=self._on_send_otp
        )
        self.send_otp_btn.pack(side=RIGHT)

        self.otp_info_lbl = ttk.Label(
            otp_tab,
            text="Kode OTP akan dikirim langsung ke chat resmi Telegram di HP Anda.",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        )
        self.otp_info_lbl.pack(anchor="w", pady=(0, 10))

        ttk.Label(otp_tab, text="Masukkan Kode OTP (5 Digit)", font=("Segoe UI", 9)).pack(anchor="w")
        otp_row = ttk.Frame(otp_tab)
        otp_row.pack(fill=X, pady=(4, 0))
        self.otp_var = ttk.StringVar()
        self.otp_entry = ttk.Entry(otp_row, textvariable=self.otp_var, state=DISABLED)
        self.otp_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.verify_otp_btn = ttk.Button(
            otp_row,
            text="Verifikasi & Pindai Akun",
            bootstyle="success",
            state=DISABLED,
            command=self._on_verify_otp,
        )
        self.verify_otp_btn.pack(side=RIGHT)

    def _build_step2(self) -> None:
        top = ttk.Frame(self.step2_frame)
        top.pack(fill=X, pady=(0, 10))

        self.acc_lbl = ttk.Label(top, text="Terhubung: -", font=("Segoe UI", 11, "bold"))
        self.acc_lbl.pack(side=LEFT)

        ttk.Button(
            top,
            text="Batalkan & Logout",
            bootstyle="danger-outline",
            command=self._cancel_and_reset,
        ).pack(side=RIGHT)

        # Stats
        stats = ttk.Frame(self.step2_frame)
        stats.pack(fill=X, pady=(0, 10))
        self.target_stat_lbl = ttk.Label(
            stats, text="Target Dihapus: 0", font=("Segoe UI", 10, "bold"), bootstyle="danger"
        )
        self.target_stat_lbl.pack(side=LEFT, padx=(0, 18))
        self.prot_stat_lbl = ttk.Label(
            stats, text="Dilindungi (Aman): 0", font=("Segoe UI", 10, "bold"), bootstyle="success"
        )
        self.prot_stat_lbl.pack(side=LEFT)

        # Tabs Target vs Protected
        review_tabs = ttk.Notebook(self.step2_frame)
        review_tabs.pack(fill=BOTH, expand=True, pady=(0, 10))

        target_tab = ttk.Frame(review_tabs, padding=8)
        prot_tab = ttk.Frame(review_tabs, padding=8)
        review_tabs.add(target_tab, text=" Target Dihapus (Klik baris untuk ubah centang) ")
        review_tabs.add(prot_tab, text=" Daftar Dilindungi (100% Aman) ")

        # Search + Select buttons
        ctrl = ttk.Frame(target_tab)
        ctrl.pack(fill=X, pady=(0, 6))
        self.search_var = ttk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._render_target_tree())
        search_entry = ttk.Entry(ctrl, textvariable=self.search_var)
        search_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Label(ctrl, text="Cari:", font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        ttk.Button(ctrl, text="Pilih Semua", bootstyle="secondary-outline", command=lambda: self._toggle_all(True)).pack(
            side=LEFT, padx=(0, 4)
        )
        ttk.Button(ctrl, text="Hapus Centang", bootstyle="secondary-outline", command=lambda: self._toggle_all(False)).pack(
            side=LEFT
        )

        # Target Treeview
        tree_wrap = ttk.Frame(target_tab)
        tree_wrap.pack(fill=BOTH, expand=True)
        self.target_tree = ttk.Treeview(
            tree_wrap,
            columns=("check", "name", "username", "type"),
            show="headings",
            selectmode="browse",
        )
        self.target_tree.heading("check", text="Hapus?")
        self.target_tree.heading("name", text="Nama Grup / Saluran / Bot")
        self.target_tree.heading("username", text="Username")
        self.target_tree.heading("type", text="Tipe")
        self.target_tree.column("check", width=62, anchor="center", stretch=False)
        self.target_tree.column("name", width=270, anchor="w")
        self.target_tree.column("username", width=150, anchor="w")
        self.target_tree.column("type", width=100, anchor="center", stretch=False)

        ysb = ttk.Scrollbar(tree_wrap, orient=VERTICAL, command=self.target_tree.yview)
        self.target_tree.configure(yscrollcommand=ysb.set)
        self.target_tree.pack(side=LEFT, fill=BOTH, expand=True)
        ysb.pack(side=RIGHT, fill=Y)
        self.target_tree.bind("<ButtonRelease-1>", self._on_tree_click)

        # Protected Treeview
        p_wrap = ttk.Frame(prot_tab)
        p_wrap.pack(fill=BOTH, expand=True)
        self.prot_tree = ttk.Treeview(
            p_wrap, columns=("name", "username", "reason"), show="headings"
        )
        self.prot_tree.heading("name", text="Nama Kontak / Grup Aman")
        self.prot_tree.heading("username", text="Username")
        self.prot_tree.heading("reason", text="Alasan Proteksi")
        self.prot_tree.column("name", width=280, anchor="w")
        self.prot_tree.column("username", width=170, anchor="w")
        self.prot_tree.column("reason", width=120, anchor="center", stretch=False)
        pysb = ttk.Scrollbar(p_wrap, orient=VERTICAL, command=self.prot_tree.yview)
        self.prot_tree.configure(yscrollcommand=pysb.set)
        self.prot_tree.pack(side=LEFT, fill=BOTH, expand=True)
        pysb.pack(side=RIGHT, fill=Y)

        # Action footer
        self.auto_logout_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.step2_frame,
            text="Otomatis Logout sesi CleanGram dari Telegram Devices setelah selesai (Disarankan)",
            variable=self.auto_logout_var,
        ).pack(anchor="w", pady=(0, 8))

        self.clean_btn = ttk.Button(
            self.step2_frame,
            text="Bersihkan Target Terpilih Sekarang",
            bootstyle="danger",
            command=self._start_cleaning,
        )
        self.clean_btn.pack(fill=X)

    def _build_step3(self) -> None:
        hdr = ttk.Frame(self.step3_frame)
        hdr.pack(fill=X, pady=(0, 8))
        self.clean_title_lbl = ttk.Label(
            hdr, text="Membersihkan Akun Telegram...", font=("Segoe UI", 12, "bold")
        )
        self.clean_title_lbl.pack(side=LEFT)
        self.clean_pct_lbl = ttk.Label(hdr, text="0%", font=("Consolas", 12, "bold"), bootstyle="info")
        self.clean_pct_lbl.pack(side=RIGHT)

        self.progress_bar = ttk.Progressbar(self.step3_frame, maximum=100, value=0, bootstyle="info-striped")
        self.progress_bar.pack(fill=X, pady=(0, 10))

        self.log_box = ScrolledText(self.step3_frame, height=18, font=("Consolas", 9), autohide=True)
        self.log_box.pack(fill=BOTH, expand=True, pady=(0, 10))

        btn_row = ttk.Frame(self.step3_frame)
        btn_row.pack(fill=X)
        self.stop_clean_btn = ttk.Button(
            btn_row,
            text="Hentikan Proses",
            bootstyle="warning-outline",
            command=self.engine.request_cancel,
        )
        self.stop_clean_btn.pack(side=LEFT)

        self.done_btn = ttk.Button(
            btn_row,
            text="Selesai & Kembali ke Awal",
            bootstyle="success",
            state=DISABLED,
            command=self._reset_all,
        )
        self.done_btn.pack(side=RIGHT)

    def _load_config(self) -> None:
        aid, ahash = load_saved_credentials()
        if aid:
            self.api_id_var.set(aid)
        if ahash:
            self.api_hash_var.set(ahash)

    def _get_api_credentials(self) -> Optional[tuple[int, str]]:
        raw_id = self.api_id_var.get().strip()
        raw_hash = self.api_hash_var.get().strip()
        if not raw_id.isdigit():
            Messagebox.show_error("API ID harus berupa angka dari my.telegram.org.", "Input Salah")
            return None
        if len(raw_hash) < 10:
            Messagebox.show_error("API Hash tidak valid. Salin lengkap dari my.telegram.org.", "Input Salah")
            return None

        api_id = int(raw_id)
        if self.save_api_var.get():
            save_credentials(api_id, raw_hash)
        return api_id, raw_hash

    def _show_step(self, step: int) -> None:
        self.step1_frame.pack_forget()
        self.step2_frame.pack_forget()
        self.step3_frame.pack_forget()
        if step == 1:
            self.step1_frame.pack(fill=BOTH, expand=True)
        elif step == 2:
            self.step2_frame.pack(fill=BOTH, expand=True)
        else:
            self.step3_frame.pack(fill=BOTH, expand=True)

    # ---- QR LOGIN FLOW ----
    def _on_start_qr(self) -> None:
        creds = self._get_api_credentials()
        if not creds:
            return
        api_id, api_hash = creds
        self._stop_qr(disconnect=False)
        self.qr_btn.configure(state=DISABLED, text="Membuat QR Code...")

        def on_ok(qr_url: str) -> None:
            def ui() -> None:
                self.qr_btn.configure(state=NORMAL, text="Buat Ulang QR Code")
                self._render_qr_image(qr_url)
                self.qr_status_lbl.configure(
                    text="Menunggu scan dari Telegram HP... (Settings -> Devices -> Link Desktop Device)"
                )
                self.qr_cancel_btn.pack(pady=(6, 0))
                self._qr_polling = True
                self._schedule_qr_poll()

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            self._run_ui(
                lambda: (
                    self.qr_btn.configure(state=NORMAL, text="Buat QR Code Telegram"),
                    Messagebox.show_error(str(exc), "Gagal Membuat QR"),
                )
            )

        self.engine.submit(self.engine.start_qr_login(api_id, api_hash), on_ok, on_err)

    def _render_qr_image(self, qr_url: str) -> None:
        qr = qrcode.QRCode(border=2, box_size=6)
        qr.add_data(qr_url)
        qr.make(fit=True)
        pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        pil_img = pil_img.resize((210, 210), Image.Resampling.NEAREST)
        self._qr_photo = ImageTk.PhotoImage(pil_img)
        self.qr_img_lbl.configure(image=self._qr_photo)

    def _schedule_qr_poll(self) -> None:
        if not self._qr_polling:
            return
        self._qr_after_id = self.root.after(2000, self._poll_qr_once)

    def _poll_qr_once(self) -> None:
        if not self._qr_polling:
            return

        def on_ok(res: dict[str, Any]) -> None:
            def ui() -> None:
                if not self._qr_polling:
                    return
                status = res.get("status")
                if status == "pending":
                    if res.get("qr_url"):
                        self._render_qr_image(res["qr_url"])
                    self._schedule_qr_poll()
                elif status == "2fa_required":
                    self._stop_qr(disconnect=False)
                    self._ask_2fa_and_scan()
                elif status == "authorized":
                    self._stop_qr(disconnect=False)
                    self._scan_now()

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            def ui() -> None:
                self._stop_qr(disconnect=True)
                Messagebox.show_error(str(exc), "QR Kedaluwarsa / Error")

            self._run_ui(ui)

        self.engine.submit(self.engine.poll_qr_status(), on_ok, on_err)

    def _stop_qr(self, disconnect: bool = True) -> None:
        self._qr_polling = False
        if self._qr_after_id:
            try:
                self.root.after_cancel(self._qr_after_id)
            except Exception:
                pass
            self._qr_after_id = None
        self.qr_img_lbl.configure(image="")
        self._qr_photo = None
        self.qr_cancel_btn.pack_forget()
        self.qr_status_lbl.configure(
            text="Klik tombol di atas lalu scan dari Telegram HP: Settings -> Devices -> Link Desktop Device."
        )
        if disconnect:
            self.engine.submit(self.engine.disconnect(logout=False))

    # ---- OTP LOGIN FLOW ----
    def _on_send_otp(self) -> None:
        creds = self._get_api_credentials()
        if not creds:
            return
        api_id, api_hash = creds
        phone = self.phone_var.get().strip()
        self.send_otp_btn.configure(state=DISABLED, text="Mengirim...")

        def on_ok(res: dict[str, str]) -> None:
            def ui() -> None:
                self.send_otp_btn.configure(state=NORMAL, text="Kirim Ulang OTP")
                self.otp_info_lbl.configure(
                    text=f"Kode OTP dikirim ke {res['phone']} melalui {res['delivery']}."
                )
                self.otp_entry.configure(state=NORMAL)
                self.verify_otp_btn.configure(state=NORMAL)
                self.otp_entry.focus_set()

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            self._run_ui(
                lambda: (
                    self.send_otp_btn.configure(state=NORMAL, text="Kirim OTP"),
                    Messagebox.show_error(str(exc), "Gagal Mengirim OTP"),
                )
            )

        self.engine.submit(self.engine.send_otp(api_id, api_hash, phone), on_ok, on_err)

    def _on_verify_otp(self) -> None:
        code = self.otp_var.get().strip()
        self.verify_otp_btn.configure(state=DISABLED, text="Memeriksa...")

        def on_ok(res: dict[str, Any]) -> None:
            def ui() -> None:
                self.verify_otp_btn.configure(state=NORMAL, text="Verifikasi & Pindai Akun")
                if res.get("status") == "2fa_required":
                    self._ask_2fa_and_scan()
                elif res.get("status") == "authorized":
                    self._scan_now()

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            self._run_ui(
                lambda: (
                    self.verify_otp_btn.configure(state=NORMAL, text="Verifikasi & Pindai Akun"),
                    Messagebox.show_error(str(exc), "Verifikasi Gagal"),
                )
            )

        self.engine.submit(self.engine.verify_otp(code), on_ok, on_err)

    def _ask_2fa_and_scan(self) -> None:
        dlg = TwoFADialog(self.root)
        self.root.wait_window(dlg)
        if not dlg.result:
            self.engine.submit(self.engine.disconnect(logout=False))
            return

        def on_ok(_res: Any) -> None:
            self._run_ui(self._scan_now)

        def on_err(exc: Exception) -> None:
            self._run_ui(lambda: Messagebox.show_error(str(exc), "2FA Salah"))

        self.engine.submit(self.engine.verify_2fa(dlg.result), on_ok, on_err)

    # ---- SCAN & REVIEW ----
    def _scan_now(self) -> None:
        wl = self.whitelist_var.get().strip()
        self.qr_status_lbl.configure(text="Berhasil login! Memindai seluruh chat & grup Anda...")

        def on_ok(data: dict[str, Any]) -> None:
            def ui() -> None:
                u = data["user"]
                full_name = f"{u['first_name']} {u['last_name']}".strip()
                uname = f" (@{u['username']})" if u.get("username") else ""
                self.acc_lbl.configure(text=f"Terhubung: {full_name}{uname}")

                self._targets = data["targets"]
                self._protected = data["protected"]
                self._selected_ids = {t["id"] for t in self._targets}

                self.target_stat_lbl.configure(text=f"Target Dihapus: {len(self._targets)}")
                self.prot_stat_lbl.configure(text=f"Dilindungi (Aman): {len(self._protected)}")

                self._render_target_tree()
                self._render_protected_tree()
                self._update_clean_btn()
                self._show_step(2)

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            self._run_ui(lambda: Messagebox.show_error(str(exc), "Gagal Memindai"))

        self.engine.submit(self.engine.scan_dialogs(wl), on_ok, on_err)

    def _render_target_tree(self) -> None:
        for row in self.target_tree.get_children():
            self.target_tree.delete(row)

        query = self.search_var.get().strip().lower()
        for t in self._targets:
            if query and (
                query not in t["name"].lower()
                and query not in (t["username"] or "").lower()
                and query not in t["type"].lower()
            ):
                continue
            mark = "[✓]" if t["id"] in self._selected_ids else "[  ]"
            uname = f"@{t['username']}" if t["username"] else "-"
            self.target_tree.insert("", END, iid=str(t["id"]), values=(mark, t["name"], uname, t["type"]))

    def _render_protected_tree(self) -> None:
        for row in self.prot_tree.get_children():
            self.prot_tree.delete(row)
        for p in self._protected:
            uname = f"@{p['username']}" if p["username"] else "-"
            self.prot_tree.insert("", END, values=(p["name"], uname, p["reason"]))

    def _on_tree_click(self, event: Any) -> None:
        iid = self.target_tree.identify_row(event.y)
        if not iid:
            return
        did = int(iid)
        if did in self._selected_ids:
            self._selected_ids.remove(did)
        else:
            self._selected_ids.add(did)
        self._render_target_tree()
        self._update_clean_btn()

    def _toggle_all(self, check: bool) -> None:
        if check:
            self._selected_ids = {t["id"] for t in self._targets}
        else:
            self._selected_ids.clear()
        self._render_target_tree()
        self._update_clean_btn()

    def _update_clean_btn(self) -> None:
        cnt = len(self._selected_ids)
        if cnt > 0:
            self.clean_btn.configure(state=NORMAL, text=f"Bersihkan {cnt} Target Terpilih Sekarang")
        else:
            self.clean_btn.configure(state=DISABLED, text="Pilih Minimal 1 Target untuk Dibersihkan")

    # ---- CLEANUP PROGRESS ----
    def _start_cleaning(self) -> None:
        ids = list(self._selected_ids)
        if not ids:
            return

        confirm = Messagebox.yesno(
            f"Yakin ingin KELUAR & HAPUS RIWAYAT {len(ids)} grup/saluran/bot terpilih?\n\n"
            "Kontak HP & grup yang dilindungi 100% aman. Tidak ada akun yang diblokir.",
            "Konfirmasi Pembersihan",
        )
        if confirm != "Yes":
            return

        self._show_step(3)
        self.progress_bar.configure(value=0)
        self.clean_pct_lbl.configure(text="0%")
        self.clean_title_lbl.configure(text="Membersihkan Akun Telegram...")
        self.stop_clean_btn.configure(state=NORMAL)
        self.done_btn.configure(state=DISABLED)
        self.log_box.text.delete("1.0", END)
        self._append_log(f"[MEMULAI] Memproses {len(ids)} target secara lokal (tanpa blokir)...\n")

        def on_progress(idx: int, total: int, name: str, tipe: str, status: str, msg: str) -> None:
            def ui() -> None:
                pct = int((idx / max(total, 1)) * 100)
                self.progress_bar.configure(value=pct)
                self.clean_pct_lbl.configure(text=f"{pct}%")
                icon = "✓" if status == "ok" else ("⏳" if status == "wait" else "✗")
                self._append_log(f"{icon} [{idx}/{total}] {name} ({tipe}) — {msg}\n")

            self._run_ui(ui)

        def on_done(res: dict[str, Any]) -> None:
            def ui() -> None:
                self.progress_bar.configure(value=100)
                self.clean_pct_lbl.configure(text="100%")
                self.stop_clean_btn.configure(state=DISABLED)
                self.done_btn.configure(state=NORMAL)

                status_txt = "Dibatalkan Pengguna" if res["cancelled"] else "Pembersihan Selesai Total!"
                self.clean_title_lbl.configure(text=status_txt)
                logout_note = "Sesi CleanGram telah di-logout permanen." if res["logged_out"] else "Koneksi diputus."
                self._append_log(
                    f"\n=== {status_txt} ===\n"
                    f"✓ Berhasil dibersihkan : {res['sukses']} item\n"
                    f"✗ Dilewati             : {res['gagal']} item\n"
                    f"🔒 Status Sesi         : {logout_note}\n"
                )

            self._run_ui(ui)

        def on_err(exc: Exception) -> None:
            self._run_ui(
                lambda: (
                    self.stop_clean_btn.configure(state=DISABLED),
                    self.done_btn.configure(state=NORMAL),
                    self._append_log(f"\n❌ ERROR: {exc}\n"),
                    Messagebox.show_error(str(exc), "Kesalahan Pembersihan"),
                )
            )

        self.engine.submit(
            self.engine.clean_targets(ids, self.auto_logout_var.get(), on_progress),
            on_done,
            on_err,
        )

    def _append_log(self, text: str) -> None:
        self.log_box.text.insert(END, text)
        self.log_box.text.see(END)

    def _cancel_and_reset(self) -> None:
        self.engine.submit(self.engine.disconnect(logout=True))
        self._reset_all()

    def _reset_all(self) -> None:
        self._stop_qr(disconnect=False)
        self.otp_var.set("")
        self.otp_entry.configure(state=DISABLED)
        self.verify_otp_btn.configure(state=DISABLED)
        self._targets.clear()
        self._protected.clear()
        self._selected_ids.clear()
        self._show_step(1)

    def _on_close(self) -> None:
        self._stop_qr(disconnect=True)
        self.root.destroy()


def main() -> None:
    root = ttk.Window(themename="darkly")
    CleanGramDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
