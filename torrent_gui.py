import tkinter as tk
from tkinter import ttk
import threading
import webbrowser
import subprocess
import os
import re
import ast

import jackett_client
import data_store
from config import (JACKETT_URL, JELLYFIN_URL,
                    QBITTORRENT_PATH, QBITTORRENT_API_URL,
                    FOLDER_FILMS, FOLDER_SERIES, JACKETT_PATH)

try:
    from config import TMDB_API_KEY
except ImportError:
    TMDB_API_KEY = ""

try:
    from config import PREFERRED_QUALITY
except ImportError:
    PREFERRED_QUALITY = "1080p"

try:
    from PIL import Image, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

# ── Design tokens ──────────────────────────────────────────────────────────────

BG      = "#0F0F11"
SURFACE = "#1A1A1E"
SURF2   = "#252529"
BORDER  = "#32323A"
TEXT    = "#F0F0F5"
SUB     = "#86868F"
ACCENT  = "#4D8EF5"
ACCENT2 = "#2B6DD4"
RED     = "#EF4444"
AMBER   = "#F59E0B"
GREEN   = "#22C55E"
SEL     = "#1B3461"

F_TITLE  = ("Segoe UI", 15, "bold")
F_BODY   = ("Segoe UI", 10)
F_BOLD   = ("Segoe UI", 10, "bold")
F_SMALL  = ("Segoe UI", 9)
F_SEARCH = ("Segoe UI", 12)

_PLACEHOLDER   = "Rechercher un film, une serie, un jeu..."
_FIXED_COLS_W  = 95 + 110 + 100 + 100
_PADDING_W     = 32 * 2
_SCROLLBAR_W   = 22
_INFO_PANEL_W  = 214
_POSTER_W, _POSTER_H = 170, 255

_FALLBACK_MOVIE_GENRES = {
    28: "Action", 12: "Aventure", 16: "Animation", 35: "Comedie",
    80: "Crime", 99: "Documentaire", 18: "Drame", 10751: "Famille",
    14: "Fantastique", 27: "Horreur", 9648: "Mystere", 10749: "Romance",
    878: "Science-Fiction", 53: "Thriller", 10752: "Guerre", 37: "Western",
}
_FALLBACK_TV_GENRES = {
    10759: "Action et Aventure", 16: "Animation", 35: "Comedie",
    80: "Crime", 99: "Documentaire", 18: "Drame", 10751: "Famille",
    10765: "SF et Fantastique", 9648: "Mystere",
}

_QUALITY_KW = {
    "4K":    ["4k", "2160p", "uhd"],
    "1080p": ["1080p"],
    "720p":  ["720p"],
}


# ── Module-level helpers ───────────────────────────────────────────────────────

def _check_service(url, timeout=2):
    """Returns True if the URL responds (even with an HTTP error like 401)."""
    try:
        import urllib.request, urllib.error
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True   # service is up, just returned 4xx/5xx
    except Exception:
        return False


def _notify(title, msg):
    """Windows balloon-tip notification via PowerShell (no extra deps)."""
    try:
        t = title.replace('"', '').replace("\n", " ")[:60]
        m = msg.replace('"', '').replace("\n", " ")[:160]
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Application;"
            "$n.Visible=$true;"
            f'$n.ShowBalloonTip(5000,"{t}","{m}",'
            "[System.Windows.Forms.ToolTipIcon]::Info);"
            "Start-Sleep 6;$n.Visible=$false;$n.Dispose()"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            creationflags=0x08000000,
        )
    except Exception:
        pass


def _is_series(result):
    """Detect TV series from Jackett category or SxxExx title pattern."""
    cat = result.get("category", "").lower()
    if any(k in cat for k in ("tv", "serie", "episode", "television")):
        return True
    if any(k in cat for k in ("movie", "film", "cinema", "bluray", "blu-ray")):
        return False
    return bool(re.search(r'\bS\d{1,2}E\d{1,2}\b', result.get("title", ""), re.IGNORECASE))


def _save_path_for(result):
    return FOLDER_SERIES if _is_series(result) else FOLDER_FILMS


def _qbt_add(magnet, save_path):
    """Add torrent via qBittorrent Web API with a specific save path.
    Returns True on success, falls back to webbrowser on failure."""
    try:
        import urllib.request, urllib.parse
        payload = urllib.parse.urlencode({
            "urls":     magnet,
            "savepath": save_path,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{QBITTORRENT_API_URL}/api/v2/torrents/add",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().strip() == b"Ok."
    except Exception:
        return False


def _open_torrent(magnet, save_path):
    """Send to qBittorrent API; fallback to webbrowser if API unreachable."""
    if not _qbt_add(magnet, save_path):
        webbrowser.open(magnet)


def _detect_quality(title):
    t = title.upper()
    if any(k in t for k in ("2160P", "4K", "UHD")): return "4K"
    if "1080P" in t: return "1080p"
    if "720P"  in t: return "720p"
    return ""


def _best_result(results, quality_pref=PREFERRED_QUALITY):
    if not results:
        return None
    if not quality_pref:
        return results[0]
    keywords = _QUALITY_KW.get(quality_pref, [quality_pref.lower()])
    preferred = [r for r in results
                 if any(k in r.get("title", "").lower() for k in keywords)]
    return preferred[0] if preferred else results[0]


def _magnet_hash(magnet):
    if not magnet:
        return ""
    m = re.search(r"xt=urn:btih:([a-fA-F0-9]{40}|[A-Z2-7]{32})", magnet, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _seeds_fmt(n):
    sym = "▲" if n >= 50 else "◆" if n >= 10 else "▼"
    return f"{sym}  {n}"

def _seed_tag(n):
    return "high" if n >= 50 else "med" if n >= 10 else "low"

def _status_label(s):
    return {"pending": "En attente", "checking": "Verification...",
            "found": "Disponible", "not_found": "Non trouve"}.get(s, s)


# ── App ────────────────────────────────────────────────────────────────────────

class TorrentApp:
    def __init__(self, root):
        self.root           = root
        self.results        = []
        self._filtered      = []
        self._sort_col      = "seeds"
        self._sort_asc      = False
        self._loading       = False
        self._anim_id       = None
        self._resize_id     = None
        self._suggest_id    = None
        self._suggest_popup = None
        self._current_view  = None
        self._wish_map      = {}
        self._reco_results  = []
        self._poster_ref    = None
        self._status_dots   = {}   # populated in _build_topbar

        root.title("TorrentBot")
        root.configure(bg=BG)
        root.minsize(820, 540)
        root.geometry("1280x780")

        self._setup_styles()
        self._build_ui()
        self._load_icon()

        root.bind("<Configure>", self._on_resize)
        root.bind("<Control-f>", lambda e: self.entry.focus_set())

        threading.Thread(target=self._auto_check_wishlist, daemon=True).start()
        threading.Thread(target=self._load_genres_worker, daemon=True).start()
        threading.Thread(target=self._completion_watcher, daemon=True).start()
        threading.Thread(target=self._launch_jackett_if_needed, daemon=True).start()
        threading.Thread(target=self._service_watcher, daemon=True).start()

    # ── Styles ──────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview",
            background=SURFACE, foreground=TEXT,
            fieldbackground=SURFACE, rowheight=38,
            borderwidth=0, font=F_BODY)
        s.map("Treeview",
            background=[("selected", SEL)], foreground=[("selected", TEXT)])
        s.configure("Treeview.Heading",
            background=SURF2, foreground=SUB,
            font=("Segoe UI", 8, "bold"),
            borderwidth=0, relief="flat", padding=(10, 8))
        s.map("Treeview.Heading", background=[("active", SURF2)])
        s.configure("Vertical.TScrollbar",
            background=SURF2, troughcolor=SURFACE,
            bordercolor=SURFACE, arrowcolor=SUB,
            lightcolor=SURF2, darkcolor=SURF2)
        s.configure("TCombobox",
            fieldbackground=SURF2, background=SURF2,
            foreground=TEXT, selectbackground=SEL,
            selectforeground=TEXT, arrowcolor=SUB,
            bordercolor=BORDER, darkcolor=SURF2, lightcolor=SURF2)
        s.map("TCombobox",
            fieldbackground=[("readonly", SURF2)],
            foreground=[("readonly", TEXT)],
            background=[("active", SURF2)])

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_topbar()
        self._content = tk.Frame(self.root, bg=BG)
        self._content.pack(fill=tk.BOTH, expand=True)
        self._frame_search   = tk.Frame(self._content, bg=BG)
        self._frame_wishlist = tk.Frame(self._content, bg=BG)
        self._frame_reco     = tk.Frame(self._content, bg=BG)
        self._frame_history  = tk.Frame(self._content, bg=BG)
        self._build_search_view()
        self._build_wishlist_view()
        self._build_reco_view()
        self._build_history_view()
        self._build_suggestions_popup()
        self._switch_view("search")

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=SURFACE, height=54)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Label(bar, text="TorrentBot", font=F_TITLE,
                 bg=SURFACE, fg=TEXT).pack(side=tk.LEFT, padx=28)

        tabs = tk.Frame(bar, bg=SURFACE)
        tabs.pack(side=tk.LEFT, padx=12)
        self._tab_btns = {}
        for key, label in [("search", "Rechercher"), ("wishlist", "Wishlist"),
                            ("reco", "Recommandations"), ("history", "Historique")]:
            btn = tk.Button(tabs, text=label,
                            command=lambda k=key: self._switch_view(k),
                            bg=SURFACE, fg=SUB, font=F_BODY,
                            borderwidth=0, relief="flat", padx=14, pady=8,
                            cursor="hand2", activebackground=SURF2, activeforeground=TEXT)
            btn.pack(side=tk.LEFT, padx=2)
            self._tab_btns[key] = btn

        # Right-side: settings gear
        tk.Button(bar, text="⚙", command=self._open_settings,
                  bg=SURFACE, fg=SUB, font=("Segoe UI", 12),
                  borderwidth=0, relief="flat", padx=10, pady=5,
                  cursor="hand2", activebackground=SURF2, activeforeground=TEXT,
                  ).pack(side=tk.RIGHT, padx=(8, 0), pady=10)

        # Right-side: service buttons with status dots
        for key, text, cmd in [
            ("qbt",      "qBittorrent",  self.open_qbittorrent),
            ("jackett",  "Jackett",      self.open_jackett),
            ("jellyfin", "Bibliotheque", self.open_jellyfin),
        ]:
            sf = tk.Frame(bar, bg=SURFACE)
            sf.pack(side=tk.RIGHT, padx=4, pady=10)
            dot = tk.Label(sf, text="●", font=("Segoe UI", 7),
                           bg=SURFACE, fg=SUB)
            dot.pack(side=tk.LEFT, padx=(0, 2))
            tk.Button(sf, text=text, command=cmd,
                      bg=SURFACE, fg=SUB, font=F_SMALL,
                      borderwidth=0, relief="flat", padx=8, pady=7,
                      cursor="hand2", activebackground=SURF2, activeforeground=TEXT,
                      ).pack(side=tk.LEFT)
            self._status_dots[key] = dot

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

    def _switch_view(self, view):
        if self._current_view == view:
            return
        self._current_view = view
        for frame in (self._frame_search, self._frame_wishlist,
                      self._frame_reco, self._frame_history):
            frame.pack_forget()
        if view == "search":
            self._frame_search.pack(fill=tk.BOTH, expand=True)
        elif view == "wishlist":
            self._frame_wishlist.pack(fill=tk.BOTH, expand=True)
            self._refresh_wishlist()
        elif view == "reco":
            self._frame_reco.pack(fill=tk.BOTH, expand=True)
        elif view == "history":
            self._frame_history.pack(fill=tk.BOTH, expand=True)
            self._refresh_history()
        for v, btn in self._tab_btns.items():
            btn.config(fg=ACCENT if v == view else SUB)

    # ── Search view ──────────────────────────────────────────────────────────

    def _build_search_view(self):
        f = self._frame_search

        # Search bar
        row = tk.Frame(f, bg=BG, pady=18)
        row.pack(fill=tk.X, padx=32)
        outer = tk.Frame(row, bg=BORDER, padx=1, pady=1)
        outer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        inner = tk.Frame(outer, bg=SURFACE)
        inner.pack(fill=tk.X)
        self.entry = tk.Entry(inner, font=F_SEARCH, bg=SURFACE, fg=SUB,
                              insertbackground=ACCENT,
                              borderwidth=0, highlightthickness=0, relief="flat")
        self.entry.insert(0, _PLACEHOLDER)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=11, padx=16)
        self.entry.bind("<FocusIn>",    self._on_entry_focus)
        self.entry.bind("<Return>",     lambda e: self.start_search())
        self.entry.bind("<Escape>",     lambda e: self._clear_entry())
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>",   lambda e: self.root.after(150, self._hide_suggestions))
        self.entry.bind("<Down>",       self._suggest_nav_down)
        self.entry.bind("<Up>",         self._suggest_nav_up)
        self.btn_search = tk.Button(row, text="Rechercher", command=self.start_search,
                                    bg=ACCENT, fg="white", font=F_BOLD,
                                    borderwidth=0, relief="flat",
                                    padx=28, pady=11, cursor="hand2",
                                    activebackground=ACCENT2, activeforeground="white")
        self.btn_search.pack(side=tk.LEFT, padx=(14, 0))

        # Filter bar
        fbar = tk.Frame(f, bg=BG)
        fbar.pack(fill=tk.X, padx=36, pady=(0, 4))
        tk.Label(fbar, text="Qualite :", font=F_SMALL, bg=BG, fg=SUB).pack(side=tk.LEFT)
        self._quality_filter = tk.StringVar(value="Tous")
        qcb = ttk.Combobox(fbar, textvariable=self._quality_filter,
                           values=["Tous", "4K", "1080p", "720p"],
                           state="readonly", width=7, font=F_SMALL)
        qcb.pack(side=tk.LEFT, padx=(4, 18))
        qcb.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        tk.Label(fbar, text="Seeds min :", font=F_SMALL, bg=BG, fg=SUB).pack(side=tk.LEFT)
        self._seeds_filter = tk.StringVar(value="Tous")
        scb = ttk.Combobox(fbar, textvariable=self._seeds_filter,
                           values=["Tous", "10+", "50+", "100+"],
                           state="readonly", width=6, font=F_SMALL)
        scb.pack(side=tk.LEFT, padx=(4, 0))
        scb.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        self.lbl_status = tk.Label(fbar, text="", font=F_SMALL, bg=BG, fg=SUB, anchor="w")
        self.lbl_status.pack(side=tk.RIGHT)

        # Results table
        tbl = tk.Frame(f, bg=BG)
        tbl.pack(fill=tk.BOTH, expand=True, padx=32)
        self.tree = ttk.Treeview(tbl,
            columns=("cat", "src", "title", "seeds", "size"),
            show="headings", selectmode="browse")
        for col, head, w, anc in [
            ("cat",   "CATEGORIE", 95,  "w"),
            ("src",   "SOURCE",    110, "w"),
            ("title", "TITRE",     500, "w"),
            ("seeds", "SEEDS",     100, "center"),
            ("size",  "TAILLE",    100, "center"),
        ]:
            self.tree.heading(col, text=head, anchor=anc,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anc, stretch=False, minwidth=50)
        self.tree.tag_configure("high", foreground="#DDEEFF")
        self.tree.tag_configure("med",  foreground="#AAAABC")
        self.tree.tag_configure("low",  foreground="#636374")
        vsb = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self.download())

        # Footer
        tk.Frame(f, bg=BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(f, bg=SURFACE, pady=16)
        foot.pack(side=tk.BOTTOM, fill=tk.X)
        btn_row = tk.Frame(foot, bg=SURFACE)
        btn_row.pack()
        self.btn_dl = tk.Button(btn_row, text="Telecharger avec qBittorrent",
                                command=self.download, bg=ACCENT, fg="white", font=F_BOLD,
                                borderwidth=0, relief="flat", padx=36, pady=10, cursor="hand2",
                                activebackground=ACCENT2, activeforeground="white")
        self.btn_dl.pack(side=tk.LEFT, padx=4)
        self.btn_add_wish = tk.Button(btn_row, text="+ Wishlist",
                                      command=self._add_selected_to_wishlist,
                                      bg=SURF2, fg=TEXT, font=F_BOLD,
                                      borderwidth=0, relief="flat",
                                      padx=18, pady=10, cursor="hand2",
                                      activebackground=BORDER, activeforeground=TEXT)
        self.btn_add_wish.pack(side=tk.LEFT, padx=4)
        self.lbl_footer = tk.Label(foot, font=F_SMALL, bg=SURFACE, fg=SUB,
            text="Double-cliquez sur un resultat  ou  selectionnez puis cliquez Telecharger")
        self.lbl_footer.pack(pady=(6, 0))

    # ── Wishlist view ────────────────────────────────────────────────────────

    def _build_wishlist_view(self):
        f = self._frame_wishlist
        header = tk.Frame(f, bg=BG, pady=18)
        header.pack(fill=tk.X, padx=32)
        tk.Label(header, text="Wishlist", font=F_TITLE, bg=BG, fg=TEXT).pack(side=tk.LEFT)
        add_row = tk.Frame(f, bg=BG, pady=8)
        add_row.pack(fill=tk.X, padx=32)
        outer = tk.Frame(add_row, bg=BORDER, padx=1, pady=1)
        outer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        inner = tk.Frame(outer, bg=SURFACE)
        inner.pack(fill=tk.X)
        self.wish_entry = tk.Entry(inner, font=F_SEARCH, bg=SURFACE, fg=TEXT,
                                   insertbackground=ACCENT,
                                   borderwidth=0, highlightthickness=0, relief="flat")
        self.wish_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=11, padx=16)
        self.wish_entry.bind("<Return>", lambda e: self._add_to_wishlist())
        tk.Button(add_row, text="Ajouter", command=self._add_to_wishlist,
                  bg=ACCENT, fg="white", font=F_BOLD,
                  borderwidth=0, relief="flat", padx=24, pady=11, cursor="hand2",
                  activebackground=ACCENT2, activeforeground="white"
                  ).pack(side=tk.LEFT, padx=(14, 0))
        self.lbl_wish_status = tk.Label(f, text="", font=F_SMALL, bg=BG, fg=SUB, anchor="w")
        self.lbl_wish_status.pack(fill=tk.X, padx=36, pady=(0, 4))
        tbl = tk.Frame(f, bg=BG)
        tbl.pack(fill=tk.BOTH, expand=True, padx=32)
        self.wish_tree = ttk.Treeview(tbl,
            columns=("title", "found", "added", "status"), show="headings", selectmode="browse")
        for col, head, w, anc in [
            ("title",  "TITRE",          280, "w"),
            ("found",  "TORRENT TROUVE", 340, "w"),
            ("added",  "AJOUTE",         100, "center"),
            ("status", "STATUT",         110, "center"),
        ]:
            self.wish_tree.heading(col, text=head, anchor=anc)
            self.wish_tree.column(col, width=w, anchor=anc, stretch=False, minwidth=80)
        self.wish_tree.tag_configure("found",     foreground=GREEN)
        self.wish_tree.tag_configure("pending",   foreground=SUB)
        self.wish_tree.tag_configure("checking",  foreground=AMBER)
        self.wish_tree.tag_configure("not_found", foreground=RED)
        vsb2 = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.wish_tree.yview)
        self.wish_tree.configure(yscrollcommand=vsb2.set)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.wish_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Frame(f, bg=BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(f, bg=SURFACE, pady=16)
        foot.pack(side=tk.BOTTOM, fill=tk.X)
        btn_row = tk.Frame(foot, bg=SURFACE)
        btn_row.pack()
        tk.Button(btn_row, text="Telecharger", command=self._download_wish_item,
                  bg=ACCENT, fg="white", font=F_BOLD,
                  borderwidth=0, relief="flat", padx=28, pady=10, cursor="hand2",
                  activebackground=ACCENT2, activeforeground="white"
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Retirer", command=self._remove_wish_item,
                  bg=SURF2, fg=RED, font=F_BOLD,
                  borderwidth=0, relief="flat", padx=20, pady=10, cursor="hand2",
                  activebackground=BORDER, activeforeground=RED
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Verifier tout", command=self._check_all_wishlist,
                  bg=SURF2, fg=SUB, font=F_BOLD,
                  borderwidth=0, relief="flat", padx=20, pady=10, cursor="hand2",
                  activebackground=BORDER, activeforeground=TEXT
                  ).pack(side=tk.LEFT, padx=4)
        self.lbl_wish_footer = tk.Label(foot, font=F_SMALL, bg=SURFACE, fg=SUB,
                                        text="Selectionnez un element pour interagir")
        self.lbl_wish_footer.pack(pady=(6, 0))

    # ── Recommendations view ─────────────────────────────────────────────────

    def _build_reco_view(self):
        f = self._frame_reco
        header = tk.Frame(f, bg=BG, pady=18)
        header.pack(fill=tk.X, padx=32)
        tk.Label(header, text="Recommandations", font=F_TITLE, bg=BG, fg=TEXT).pack(side=tk.LEFT)
        filt = tk.Frame(f, bg=BG, pady=4)
        filt.pack(fill=tk.X, padx=32)
        tk.Label(filt, text="Type", font=F_SMALL, bg=BG, fg=SUB).pack(side=tk.LEFT)
        self._reco_type = tk.StringVar(value="Film")
        type_cb = ttk.Combobox(filt, textvariable=self._reco_type,
                               values=["Film", "Serie"], state="readonly", width=8, font=F_BODY)
        type_cb.pack(side=tk.LEFT, padx=(6, 22))
        type_cb.bind("<<ComboboxSelected>>", self._on_reco_type_change)
        tk.Label(filt, text="Genre", font=F_SMALL, bg=BG, fg=SUB).pack(side=tk.LEFT)
        self._reco_genre = tk.StringVar(value="Tous")
        self._genre_cb = ttk.Combobox(filt, textvariable=self._reco_genre,
                                      state="readonly", width=20, font=F_BODY)
        self._genre_cb.pack(side=tk.LEFT, padx=(6, 22))
        tk.Label(filt, text="Annee", font=F_SMALL, bg=BG, fg=SUB).pack(side=tk.LEFT)
        self._reco_year = tk.StringVar(value="Toutes")
        ttk.Combobox(filt, textvariable=self._reco_year,
                     values=["Toutes"] + [str(y) for y in range(2025, 1969, -1)],
                     state="readonly", width=8, font=F_BODY
                     ).pack(side=tk.LEFT, padx=(6, 22))
        self.btn_discover = tk.Button(filt, text="Decouvrir", command=self._discover_tmdb,
                                      bg=ACCENT, fg="white", font=F_BOLD,
                                      borderwidth=0, relief="flat", padx=20, pady=6,
                                      cursor="hand2", activebackground=ACCENT2, activeforeground="white")
        self.btn_discover.pack(side=tk.LEFT, padx=4)
        self.lbl_reco_status = tk.Label(f, font=F_SMALL, bg=BG, fg=SUB, anchor="w",
                                        text="  Choisissez vos filtres et cliquez Decouvrir.")
        self.lbl_reco_status.pack(fill=tk.X, padx=36, pady=(6, 4))
        split = tk.Frame(f, bg=BG)
        split.pack(fill=tk.BOTH, expand=True, padx=32)
        # Poster panel
        info = tk.Frame(split, bg=SURFACE, width=_INFO_PANEL_W)
        info.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
        info.pack_propagate(False)
        poster_wrap = tk.Frame(info, bg=SURF2, width=_POSTER_W, height=_POSTER_H)
        poster_wrap.pack(pady=(20, 12))
        poster_wrap.pack_propagate(False)
        self._poster_lbl = tk.Label(poster_wrap, bg=SURF2,
                                    text="Selectionnez\nun titre", fg=SUB,
                                    font=F_SMALL, justify="center")
        self._poster_lbl.pack(fill=tk.BOTH, expand=True)
        self._info_title    = tk.Label(info, text="", font=F_BOLD, bg=SURFACE, fg=TEXT,
                                       wraplength=_INFO_PANEL_W - 24, justify="left")
        self._info_title.pack(anchor="w", padx=12)
        self._info_meta     = tk.Label(info, text="", font=F_SMALL, bg=SURFACE, fg=ACCENT)
        self._info_meta.pack(anchor="w", padx=12, pady=(3, 8))
        self._info_overview = tk.Label(info, text="", font=("Segoe UI", 8), bg=SURFACE, fg=SUB,
                                       wraplength=_INFO_PANEL_W - 24, justify="left")
        self._info_overview.pack(anchor="w", padx=12)
        if not _PIL:
            tk.Label(info, text="pip install Pillow\npour les affiches",
                     font=("Segoe UI", 7), bg=SURFACE, fg=BORDER, justify="center"
                     ).pack(side=tk.BOTTOM, pady=8)
        # Table
        tbl = tk.Frame(split, bg=BG)
        tbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.reco_tree = ttk.Treeview(tbl,
            columns=("title", "year", "genre", "vote"),
            show="headings", selectmode="browse")
        for col, head, w, anc in [
            ("title", "TITRE", 440, "w"),
            ("year",  "ANNEE",  80, "center"),
            ("genre", "GENRE", 160, "w"),
            ("vote",  "NOTE",   80, "center"),
        ]:
            self.reco_tree.heading(col, text=head, anchor=anc)
            self.reco_tree.column(col, width=w, anchor=anc, stretch=False, minwidth=50)
        vsb3 = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.reco_tree.yview)
        self.reco_tree.configure(yscrollcommand=vsb3.set)
        vsb3.pack(side=tk.RIGHT, fill=tk.Y)
        self.reco_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.reco_tree.bind("<Double-1>",         lambda e: self._add_reco_to_wishlist())
        self.reco_tree.bind("<<TreeviewSelect>>", self._on_reco_select)
        tk.Frame(f, bg=BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(f, bg=SURFACE, pady=16)
        foot.pack(side=tk.BOTTOM, fill=tk.X)
        btn_row = tk.Frame(foot, bg=SURFACE)
        btn_row.pack()
        tk.Button(btn_row, text="+ Ajouter a la Wishlist", command=self._add_reco_to_wishlist,
                  bg=ACCENT, fg="white", font=F_BOLD,
                  borderwidth=0, relief="flat", padx=28, pady=10, cursor="hand2",
                  activebackground=ACCENT2, activeforeground="white"
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Rechercher sur Jackett", command=self._search_reco_on_jackett,
                  bg=SURF2, fg=TEXT, font=F_BOLD,
                  borderwidth=0, relief="flat", padx=20, pady=10, cursor="hand2",
                  activebackground=BORDER, activeforeground=TEXT
                  ).pack(side=tk.LEFT, padx=4)
        self.lbl_reco_footer = tk.Label(foot, font=F_SMALL, bg=SURFACE, fg=SUB,
            text="Double-cliquez ou selectionnez pour ajouter a la wishlist — telechargement auto si trouve")
        self.lbl_reco_footer.pack(pady=(6, 0))
        self._genre_movie = dict(_FALLBACK_MOVIE_GENRES)
        self._genre_tv    = dict(_FALLBACK_TV_GENRES)
        self._update_genre_combobox()

    # ── History view ──────────────────────────────────────────────────────────

    def _build_history_view(self):
        f = self._frame_history
        header = tk.Frame(f, bg=BG, pady=18)
        header.pack(fill=tk.X, padx=32)
        tk.Label(header, text="Historique", font=F_TITLE, bg=BG, fg=TEXT).pack(side=tk.LEFT)
        self.lbl_hist_status = tk.Label(f, text="", font=F_SMALL, bg=BG, fg=SUB, anchor="w")
        self.lbl_hist_status.pack(fill=tk.X, padx=36, pady=(0, 4))
        tbl = tk.Frame(f, bg=BG)
        tbl.pack(fill=tk.BOTH, expand=True, padx=32)
        self.hist_tree = ttk.Treeview(tbl,
            columns=("title", "quality", "date"), show="headings", selectmode="browse")
        for col, head, w, anc in [
            ("title",   "TITRE",   550, "w"),
            ("quality", "QUALITE",  90, "center"),
            ("date",    "DATE",    160, "center"),
        ]:
            self.hist_tree.heading(col, text=head, anchor=anc)
            self.hist_tree.column(col, width=w, anchor=anc, stretch=False, minwidth=60)
        vsb4 = ttk.Scrollbar(tbl, orient=tk.VERTICAL, command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=vsb4.set)
        vsb4.pack(side=tk.RIGHT, fill=tk.Y)
        self.hist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Frame(f, bg=BORDER, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(f, bg=SURFACE, pady=16)
        foot.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Button(foot, text="Effacer l'historique", command=self._clear_dl_history,
                  bg=SURF2, fg=RED, font=F_BOLD,
                  borderwidth=0, relief="flat", padx=24, pady=10, cursor="hand2",
                  activebackground=BORDER, activeforeground=RED
                  ).pack()

    # ── Suggestions popup ────────────────────────────────────────────────────

    def _build_suggestions_popup(self):
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=BORDER)
        self._suggest_listbox = tk.Listbox(popup,
            bg=SURFACE, fg=TEXT, font=F_BODY,
            selectbackground=SEL, selectforeground=TEXT,
            borderwidth=0, highlightthickness=0, relief="flat", activestyle="none")
        self._suggest_listbox.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._suggest_listbox.bind("<ButtonRelease-1>", self._on_suggest_select)
        self._suggest_popup = popup
        popup.withdraw()

    def _show_suggestions(self, items):
        if not items:
            self._hide_suggestions()
            return
        lb = self._suggest_listbox
        lb.delete(0, tk.END)
        for item in items[:8]:
            lb.insert(tk.END, f"  {item}")
        n = min(len(items), 8)
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 3
        w = self.entry.winfo_width()
        self._suggest_popup.geometry(f"{w}x{n * 32 + 4}+{x}+{y}")
        self._suggest_popup.deiconify()
        self._suggest_popup.lift()

    def _hide_suggestions(self):
        if not self._suggest_popup:
            return
        try:
            self._suggest_popup.withdraw()
        except tk.TclError:
            pass

    def _on_suggest_select(self, event):
        sel = self._suggest_listbox.curselection()
        if not sel:
            return
        text = self._suggest_listbox.get(sel[0]).strip()
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        self.entry.config(fg=TEXT)
        self._hide_suggestions()
        self.start_search()

    def _suggest_nav_down(self, event):
        if not self._suggest_popup or not self._suggest_popup.winfo_viewable():
            return
        lb = self._suggest_listbox
        size = lb.size()
        if size == 0:
            return
        cur = lb.curselection()
        idx = min((cur[0] + 1 if cur else 0), size - 1)
        lb.selection_clear(0, tk.END)
        lb.selection_set(idx)
        lb.see(idx)

    def _suggest_nav_up(self, event):
        if not self._suggest_popup or not self._suggest_popup.winfo_viewable():
            return
        lb = self._suggest_listbox
        size = lb.size()
        if size == 0:
            return
        cur = lb.curselection()
        idx = max((cur[0] - 1 if cur else size - 1), 0)
        lb.selection_clear(0, tk.END)
        lb.selection_set(idx)
        lb.see(idx)

    def _on_key_release(self, event):
        if event.keysym in ("Return", "Escape", "Up", "Down", "Left", "Right", "Tab"):
            return
        query = self.entry.get().strip()
        if not query or query == _PLACEHOLDER:
            self._hide_suggestions()
            return
        history = data_store.load_history()
        matches = [h for h in history if query.lower() in h.lower()]
        self._show_suggestions(matches)
        if self._suggest_id:
            self.root.after_cancel(self._suggest_id)
        if TMDB_API_KEY and len(query) >= 2:
            self._suggest_id = self.root.after(450, self._fetch_tmdb_suggest_async, query)

    def _fetch_tmdb_suggest_async(self, query):
        self._suggest_id = None
        threading.Thread(target=self._fetch_tmdb_suggest_worker, args=(query,), daemon=True).start()

    def _fetch_tmdb_suggest_worker(self, query):
        try:
            import urllib.request, urllib.parse, json as _json
            q   = urllib.parse.quote(query)
            url = (f"https://api.themoviedb.org/3/search/multi"
                   f"?api_key={TMDB_API_KEY}&query={q}&language=fr-FR")
            with urllib.request.urlopen(url, timeout=3) as r:
                data = _json.loads(r.read())
            titles = [t for t in (
                item.get("title") or item.get("name") or ""
                for item in data.get("results", [])[:6]) if t]
            self.root.after(0, self._on_tmdb_suggest_results, query, titles)
        except Exception:
            pass

    def _on_tmdb_suggest_results(self, query, tmdb_titles):
        if self.entry.get().strip() != query:
            return
        history  = data_store.load_history()
        hist     = [h for h in history if query.lower() in h.lower()]
        combined = list(dict.fromkeys(hist + tmdb_titles))
        self._show_suggestions(combined)

    # ── Responsive resize ────────────────────────────────────────────────────

    def _on_resize(self, event):
        if event.widget is not self.root:
            return
        if self._resize_id:
            self.root.after_cancel(self._resize_id)
        self._resize_id = self.root.after(60, self._apply_resize, event.width)

    def _apply_resize(self, width):
        self._resize_id = None
        avail = width - _PADDING_W - _SCROLLBAR_W
        self.tree.column("title",       width=max(150, avail - _FIXED_COLS_W))
        wish_avail = max(300, avail - 100 - 110)
        self.wish_tree.column("title", width=max(120, wish_avail // 2))
        self.wish_tree.column("found", width=max(120, wish_avail - wish_avail // 2))
        self.reco_tree.column("title", width=max(180, avail - _INFO_PANEL_W - 12 - 80 - 160 - 80))
        self.hist_tree.column("title", width=max(200, avail - 90 - 160))

    # ── Entry / status helpers ───────────────────────────────────────────────

    def _on_entry_focus(self, event):
        if self.entry.get() == _PLACEHOLDER:
            self.entry.delete(0, tk.END)
            self.entry.config(fg=TEXT)

    def _clear_entry(self):
        self.entry.delete(0, tk.END)
        self.entry.config(fg=TEXT)
        self._hide_suggestions()

    def _status(self, msg, color=None):
        self.lbl_status.config(text=f"  {msg}", fg=color or SUB)

    def _footer(self, msg, color=None):
        self.lbl_footer.config(text=msg, fg=color or SUB)

    # ── Loading animation ────────────────────────────────────────────────────

    def _animate(self, tick=0):
        if not self._loading:
            return
        frames = ["Recherche   ", "Recherche.  ", "Recherche.. ", "Recherche..."]
        self._status(frames[tick % 4], ACCENT)
        self._anim_id = self.root.after(350, self._animate, tick + 1)

    def _stop_animate(self):
        self._loading = False
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None

    # ── Search + filters + sort ──────────────────────────────────────────────

    def start_search(self):
        query = self.entry.get().strip()
        if not query or query == _PLACEHOLDER or self._loading:
            return
        self._hide_suggestions()
        data_store.add_to_history(query)
        self._loading = True
        self.btn_search.config(state=tk.DISABLED, bg=SURF2, fg=SUB)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._animate()
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query):
        try:
            fallback = self._tmdb_original_title(query) if TMDB_API_KEY else None
            results, label = jackett_client.search(query, fallback_title=fallback)
            self.root.after(0, self._on_search_done, results, label)
        except Exception as e:
            self.root.after(0, self._on_search_error, str(e))

    def _tmdb_original_title(self, query):
        """Return original (non-French) title from TMDB, or None."""
        try:
            import urllib.request, urllib.parse, json as _json
            q   = urllib.parse.quote(query)
            url = (f"https://api.themoviedb.org/3/search/multi"
                   f"?api_key={TMDB_API_KEY}&query={q}&language=fr-FR")
            with urllib.request.urlopen(url, timeout=4) as r:
                data = _json.loads(r.read())
            hits = data.get("results", [])
            if hits:
                orig = hits[0].get("original_title") or hits[0].get("original_name")
                fr   = hits[0].get("title") or hits[0].get("name") or ""
                # only return original if it differs from French title
                if orig and orig.lower() != fr.lower():
                    return orig
        except Exception:
            pass
        return None

    def _on_search_done(self, results, label="exacte"):
        self._stop_animate()
        self.results = results
        self.btn_search.config(state=tk.NORMAL, bg=ACCENT, fg="white")
        self._search_label = label
        self._apply_filters()

    def _on_search_error(self, msg):
        self._stop_animate()
        self.btn_search.config(state=tk.NORMAL, bg=ACCENT, fg="white")
        self._status(f"Erreur de connexion - {msg}", RED)
        self._footer("Verifiez que Jackett est lance sur 127.0.0.1:9117", RED)

    def _apply_filters(self):
        quality = self._quality_filter.get()
        min_s   = {"Tous": 0, "10+": 10, "50+": 50, "100+": 100}.get(
                    self._seeds_filter.get(), 0)

        results = self.results
        if quality != "Tous":
            kws = _QUALITY_KW.get(quality, [quality.lower()])
            results = [r for r in results
                       if any(k in r.get("title", "").lower() for k in kws)]
        if min_s > 0:
            results = [r for r in results if int(r.get("seeders", 0)) >= min_s]

        # Sort
        key_map = {
            "cat":   lambda r: r.get("category", "").lower(),
            "src":   lambda r: r.get("indexer", "").lower(),
            "title": lambda r: r.get("title", "").lower(),
            "seeds": lambda r: int(r.get("seeders", 0)),
            "size":  lambda r: r.get("size_bytes", 0),
        }
        fn  = key_map.get(self._sort_col, lambda r: 0)
        results = sorted(results, key=fn, reverse=not self._sort_asc)

        self._filtered = results
        self._render_tree()
        self._update_headings()

        n_all  = len(self.results)
        n_show = len(results)
        label  = getattr(self, "_search_label", "exacte")
        hint   = "" if label == "exacte" else f"  —  recherche {label}"
        if n_show == n_all:
            self._status(f"{n_all} resultats{hint}")
        else:
            self._status(f"{n_show} / {n_all} resultats  (filtres actifs){hint}")

    def _render_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        try:
            for i, r in enumerate(self._filtered[:100]):
                s = int(r.get("seeders", 0))
                self.tree.insert("", tk.END, iid=str(i), tags=(_seed_tag(s),),
                                 values=(
                                     str(r.get("category", "")),
                                     str(r.get("indexer", "")).upper(),
                                     str(r.get("title", "")),
                                     _seeds_fmt(s),
                                     str(r.get("size", "")),
                                 ))
        except Exception as e:
            self._status(f"Erreur d'affichage : {e}", RED)

    def _update_headings(self):
        labels = {"cat": "CATEGORIE", "src": "SOURCE", "title": "TITRE",
                  "seeds": "SEEDS", "size": "TAILLE"}
        for col, base in labels.items():
            if col == self._sort_col:
                ind = " ▲" if self._sort_asc else " ▼"
            else:
                ind = ""
            self.tree.heading(col, text=base + ind)

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col not in ("seeds", "size")
        self._apply_filters()

    # ── Download (search view) ───────────────────────────────────────────────

    def download(self):
        sel = self.tree.selection()
        if not sel:
            self._footer("Selectionnez un fichier dans la liste avant de telecharger.", AMBER)
            return
        try:
            idx      = int(sel[0])
            filtered = self._filtered
            if idx >= len(filtered):
                self._footer("Selection invalide, relancez la recherche.", RED)
                return
            r = filtered[idx]
        except (ValueError, IndexError):
            self._footer("Erreur de selection.", RED)
            return
        link = r.get("magnet")
        if link:
            save_path = _save_path_for(r)
            self._footer(
                f"Envoi vers {'Series TV' if _is_series(r) else 'Films'}...", GREEN)
            quality = _detect_quality(r.get("title", ""))
            data_store.add_to_dl_history(r.get("title", ""), r.get("title", ""), quality)
            _open_torrent(link, save_path)
        else:
            self._footer("Aucun lien de telechargement disponible.", RED)

    def _add_selected_to_wishlist(self):
        sel = self.tree.selection()
        if not sel:
            self._footer("Selectionnez un resultat pour l'ajouter a la wishlist.", AMBER)
            return
        try:
            idx      = int(sel[0])
            filtered = self._filtered
            if idx >= len(filtered):
                return
            title = filtered[idx].get("title", "")
        except (ValueError, IndexError):
            return
        item = data_store.add_to_wishlist(title)
        if item:
            self._footer(f"'{title[:40]}' ajoute a la wishlist.", GREEN)
        else:
            self._footer("Ce titre est deja dans la wishlist.", AMBER)

    # ── Wishlist ─────────────────────────────────────────────────────────────

    def _refresh_wishlist(self):
        wishlist = data_store.load_wishlist()
        self._wish_map.clear()
        for iid in self.wish_tree.get_children():
            self.wish_tree.delete(iid)
        for item in wishlist:
            iid = item["id"]
            found_title = str(item.get("found_title") or "")
            self.wish_tree.insert("", tk.END, iid=iid, tags=(item["status"],),
                                  values=(str(item.get("title", "")),
                                          found_title,
                                          str(item.get("added", "")),
                                          _status_label(item.get("status", "pending"))))
            self._wish_map[iid] = item
        n     = len(wishlist)
        found = sum(1 for w in wishlist if w.get("status") == "found")
        self.lbl_wish_status.config(
            text=f"  {n} titre{'s' if n != 1 else ''} en liste  —  "
                 f"{found} disponible{'s' if found != 1 else ''}",
            fg=SUB)

    def _add_to_wishlist(self):
        title = self.wish_entry.get().strip()
        if not title:
            return
        item = data_store.add_to_wishlist(title)
        if item:
            self.wish_entry.delete(0, tk.END)
            self._refresh_wishlist()
            self.lbl_wish_footer.config(
                text=f"'{title[:40]}' ajoute — recherche de torrent en cours...", fg=GREEN)
            threading.Thread(
                target=self._check_wishlist_worker, args=([item],), daemon=True).start()
        else:
            self.lbl_wish_footer.config(text="Ce titre est deja dans la liste.", fg=AMBER)

    def _remove_wish_item(self):
        sel = self.wish_tree.selection()
        if not sel:
            self.lbl_wish_footer.config(text="Selectionnez un titre a retirer.", fg=AMBER)
            return
        data_store.remove_from_wishlist(sel[0])
        self._refresh_wishlist()
        self.lbl_wish_footer.config(text="Titre retire.", fg=SUB)

    def _download_wish_item(self):
        sel = self.wish_tree.selection()
        if not sel:
            self.lbl_wish_footer.config(text="Selectionnez un titre a telecharger.", fg=AMBER)
            return
        item = self._wish_map.get(sel[0])
        if not item:
            return
        link = item.get("found_link")
        if link:
            found   = item.get("found_title", "")
            series  = bool(re.search(r'\bS\d{1,2}E\d{1,2}\b', found, re.IGNORECASE))
            sp      = FOLDER_SERIES if series else FOLDER_FILMS
            self.lbl_wish_footer.config(
                text=f"Envoi vers {'Series TV' if series else 'Films'}...", fg=GREEN)
            quality = _detect_quality(found)
            data_store.add_to_dl_history(item["title"], found, quality)
            _open_torrent(link, sp)
        else:
            self.lbl_wish_footer.config(
                text="Pas de lien — lancez 'Verifier tout' d'abord.", fg=AMBER)

    def _check_all_wishlist(self):
        wishlist = data_store.load_wishlist()
        pending  = [w for w in wishlist if w["status"] != "found"]
        if not pending:
            self.lbl_wish_footer.config(text="Tous les titres sont deja disponibles.", fg=GREEN)
            return
        for w in pending:
            data_store.update_wishlist_item(w["id"], status="checking")
        self._refresh_wishlist()
        self.lbl_wish_footer.config(
            text=f"Verification de {len(pending)} titre(s) — lancement auto si trouve...", fg=ACCENT)
        threading.Thread(
            target=self._check_wishlist_worker, args=(pending,), daemon=True).start()

    def _check_wishlist_worker(self, items):
        for item in items:
            try:
                fallback = self._tmdb_original_title(item["title"]) if TMDB_API_KEY else None
                results, _ = jackett_client.search(item["title"], fallback_title=fallback)
                if results:
                    best    = _best_result(results, PREFERRED_QUALITY)
                    link    = best.get("magnet")
                    quality = _detect_quality(best.get("title", ""))
                    data_store.update_wishlist_item(
                        item["id"], status="found",
                        found_link=link,
                        found_title=str(best.get("title", "")),
                        found_hash=_magnet_hash(link),
                    )
                    data_store.add_to_dl_history(item["title"], best.get("title", ""), quality)
                    if link:
                        sp = _save_path_for(best)
                        self.root.after(0, _open_torrent, link, sp)
                        _notify("TorrentBot — Telechargement lance",
                                f"{item['title']} ({quality or 'qualite inconnue'})")
                else:
                    data_store.update_wishlist_item(item["id"], status="not_found")
            except Exception:
                data_store.update_wishlist_item(item["id"], status="pending")
        self.root.after(0, self._on_check_done)

    def _on_check_done(self):
        wishlist = data_store.load_wishlist()
        n_found  = sum(1 for w in wishlist if w["status"] == "found")
        self._refresh_wishlist()
        if self._current_view == "wishlist":
            self.lbl_wish_footer.config(
                text=f"Verification terminee  —  {n_found} titre(s) trouves et lances.",
                fg=GREEN)

    def _auto_check_wishlist(self):
        wishlist = data_store.load_wishlist()
        pending  = [w for w in wishlist
                    if w["status"] in ("pending", "checking", "not_found")]
        if pending:
            self._check_wishlist_worker(pending)

    # ── qBittorrent completion watcher ───────────────────────────────────────

    def _completion_watcher(self):
        import time
        while True:
            time.sleep(45)
            try:
                import urllib.request, json as _json
                url = f"{QBITTORRENT_API_URL}/api/v2/torrents/info?filter=completed"
                with urllib.request.urlopen(url, timeout=5) as r:
                    torrents = _json.loads(r.read())
                completed = {t["hash"].lower() for t in torrents}
                wishlist  = data_store.load_wishlist()
                done      = [w for w in wishlist
                             if w.get("found_hash") and w["found_hash"] in completed]
                if done:
                    for w in done:
                        data_store.remove_from_wishlist(w["id"])
                    titles = [w["title"] for w in done]
                    self.root.after(0, self._on_download_complete, titles)
            except Exception:
                pass

    def _on_download_complete(self, titles):
        self._refresh_wishlist()
        n   = len(titles)
        msg = titles[0][:40] if n == 1 else f"{n} titres"
        _notify("TorrentBot — Telechargement termine", f"{msg} retire de la wishlist.")
        if self._current_view == "wishlist":
            self.lbl_wish_footer.config(
                text=f"Telechargement termine : {msg} — retire de la wishlist.", fg=GREEN)

    # ── Recommendations ───────────────────────────────────────────────────────

    def _load_genres_worker(self):
        if not TMDB_API_KEY:
            return
        try:
            import urllib.request, json as _json
            def fetch(mt):
                url = (f"https://api.themoviedb.org/3/genre/{mt}/list"
                       f"?api_key={TMDB_API_KEY}&language=fr-FR")
                with urllib.request.urlopen(url, timeout=5) as r:
                    return {g["id"]: g["name"] for g in _json.loads(r.read())["genres"]}
            self.root.after(0, self._on_genres_loaded, fetch("movie"), fetch("tv"))
        except Exception:
            pass

    def _on_genres_loaded(self, movie_genres, tv_genres):
        self._genre_movie = movie_genres
        self._genre_tv    = tv_genres
        self._update_genre_combobox()

    def _update_genre_combobox(self):
        genre_map = self._genre_movie if self._reco_type.get() == "Film" else self._genre_tv
        self._genre_cb["values"] = ["Tous"] + sorted(genre_map.values())
        self._reco_genre.set("Tous")

    def _on_reco_type_change(self, event):
        self._update_genre_combobox()

    def _discover_tmdb(self):
        if not TMDB_API_KEY:
            self.lbl_reco_status.config(
                text="  Configurez TMDB_API_KEY dans config.py.", fg=AMBER)
            return
        media_type = "movie" if self._reco_type.get() == "Film" else "tv"
        genre_name = self._reco_genre.get()
        year       = self._reco_year.get()
        genre_map  = self._genre_movie if media_type == "movie" else self._genre_tv
        genre_id   = next((k for k, v in genre_map.items() if v == genre_name), None)
        year_val   = year if year != "Toutes" else None
        self.btn_discover.config(state=tk.DISABLED, bg=SURF2, fg=SUB)
        self.lbl_reco_status.config(text="  Recherche en cours...", fg=ACCENT)
        for iid in self.reco_tree.get_children():
            self.reco_tree.delete(iid)
        self._clear_poster_panel()
        threading.Thread(
            target=self._discover_worker, args=(media_type, genre_id, year_val),
            daemon=True).start()

    def _discover_worker(self, media_type, genre_id, year):
        try:
            import urllib.request, urllib.parse, json as _json
            params = {"api_key": TMDB_API_KEY, "language": "fr-FR",
                      "sort_by": "popularity.desc", "page": "1"}
            if genre_id:
                params["with_genres"] = str(genre_id)
            if year:
                params["primary_release_year" if media_type == "movie"
                       else "first_air_date_year"] = year
            url = (f"https://api.themoviedb.org/3/discover/{media_type}?"
                   + urllib.parse.urlencode(params))
            with urllib.request.urlopen(url, timeout=8) as r:
                data = _json.loads(r.read())
            genre_map = self._genre_movie if media_type == "movie" else self._genre_tv
            results   = []
            for item in data.get("results", [])[:40]:
                title = item.get("title") or item.get("name") or ""
                date  = item.get("release_date") or item.get("first_air_date") or ""
                gids  = item.get("genre_ids", [])
                genre = ", ".join(genre_map.get(g, "") for g in gids[:2] if genre_map.get(g))
                vote  = item.get("vote_average", 0)
                results.append({
                    "title":       title,
                    "year":        date[:4] if date else "",
                    "genre":       genre,
                    "vote":        f"{vote:.1f}" if vote else "-",
                    "poster_path": item.get("poster_path") or "",
                    "overview":    item.get("overview") or "",
                })
            self.root.after(0, self._on_discover_done, results)
        except Exception as e:
            self.root.after(0, self._on_discover_error, str(e))

    def _on_discover_done(self, results):
        self._reco_results = results
        self.btn_discover.config(state=tk.NORMAL, bg=ACCENT, fg="white")
        try:
            for i, r in enumerate(results):
                self.reco_tree.insert("", tk.END, iid=str(i),
                                      values=(str(r["title"]), str(r["year"]),
                                              str(r["genre"]), str(r["vote"])))
        except Exception as e:
            self.lbl_reco_status.config(text=f"  Erreur d'affichage : {e}", fg=RED)
            return
        n = len(results)
        self.lbl_reco_status.config(
            text=f"  {n} titre{'s' if n != 1 else ''} trouves  -  "
                 "double-cliquez pour ajouter a la wishlist", fg=SUB)

    def _on_discover_error(self, msg):
        self.btn_discover.config(state=tk.NORMAL, bg=ACCENT, fg="white")
        self.lbl_reco_status.config(text=f"  Erreur TMDB : {msg}", fg=RED)

    def _on_reco_select(self, event):
        sel = self.reco_tree.selection()
        if not sel:
            return
        try:
            idx  = int(sel[0])
            data = self._reco_results[idx]
        except (ValueError, IndexError):
            return
        self._info_title.config(text=data["title"])
        meta = "  •  ".join(filter(None, [data["year"], data["genre"],
                                          f"{data['vote']} / 10" if data["vote"] != "-" else ""]))
        self._info_meta.config(text=meta)
        ov = data.get("overview", "")
        self._info_overview.config(text=(ov[:280] + "...") if len(ov) > 280 else ov)
        self._poster_lbl.config(image="", text="...", bg=SURF2)
        self._poster_ref = None
        poster_path = data.get("poster_path")
        if poster_path and _PIL:
            threading.Thread(
                target=self._fetch_poster_worker, args=(poster_path, idx),
                daemon=True).start()

    def _fetch_poster_worker(self, poster_path, idx):
        try:
            import urllib.request
            from io import BytesIO
            from PIL import Image, ImageTk
            url = f"https://image.tmdb.org/t/p/w200{poster_path}"
            with urllib.request.urlopen(url, timeout=6) as r:
                raw = r.read()
            img   = Image.open(BytesIO(raw)).resize((_POSTER_W, _POSTER_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, self._display_poster, photo, idx)
        except Exception:
            pass

    def _display_poster(self, photo, idx):
        sel = self.reco_tree.selection()
        if not sel or int(sel[0]) != idx:
            return
        self._poster_ref = photo
        self._poster_lbl.config(image=photo, text="", bg=SURF2)

    def _clear_poster_panel(self):
        self._poster_lbl.config(image="", text="Selectionnez\nun titre", bg=SURF2, fg=SUB)
        self._poster_ref = None
        self._info_title.config(text="")
        self._info_meta.config(text="")
        self._info_overview.config(text="")

    def _add_reco_to_wishlist(self):
        sel = self.reco_tree.selection()
        if not sel:
            self.lbl_reco_footer.config(text="Selectionnez un titre a ajouter.", fg=AMBER)
            return
        try:
            idx   = int(sel[0])
            title = self._reco_results[idx]["title"]
        except (ValueError, IndexError):
            return
        item = data_store.add_to_wishlist(title)
        if item:
            self.lbl_reco_footer.config(
                text=f"'{title[:40]}' ajoute — recherche de torrent en cours...", fg=GREEN)
            threading.Thread(
                target=self._check_wishlist_worker, args=([item],), daemon=True).start()
        else:
            self.lbl_reco_footer.config(text="Ce titre est deja dans la wishlist.", fg=AMBER)

    def _search_reco_on_jackett(self):
        sel = self.reco_tree.selection()
        if not sel:
            self.lbl_reco_footer.config(text="Selectionnez un titre a rechercher.", fg=AMBER)
            return
        try:
            idx   = int(sel[0])
            title = self._reco_results[idx]["title"]
        except (ValueError, IndexError):
            return
        self._switch_view("search")
        self.entry.delete(0, tk.END)
        self.entry.insert(0, title)
        self.entry.config(fg=TEXT)
        self.start_search()

    # ── History ───────────────────────────────────────────────────────────────

    def _refresh_history(self):
        history = data_store.load_dl_history()
        for iid in self.hist_tree.get_children():
            self.hist_tree.delete(iid)
        for i, entry in enumerate(history):
            self.hist_tree.insert("", tk.END, iid=str(i),
                                  values=(str(entry.get("title", "")),
                                          str(entry.get("quality", "")),
                                          str(entry.get("date", ""))))
        n = len(history)
        self.lbl_hist_status.config(
            text=f"  {n} telechargement{'s' if n != 1 else ''} enregistre{'s' if n != 1 else ''}",
            fg=SUB)

    def _clear_dl_history(self):
        data_store.clear_dl_history()
        self._refresh_history()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.py")
        current = {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    key, _, rest = line.partition("=")
                    key  = key.strip()
                    rest = rest.partition("#")[0].strip()
                    try:
                        current[key] = str(ast.literal_eval(rest))
                    except Exception:
                        current[key] = rest.strip("\"'")
        except Exception:
            pass

        popup = tk.Toplevel(self.root)
        popup.title("Parametres")
        popup.configure(bg=BG)
        popup.geometry("640x480")
        popup.resizable(False, False)
        popup.grab_set()

        tk.Label(popup, text="Parametres", font=F_TITLE, bg=BG, fg=TEXT
                 ).pack(pady=(20, 4), padx=32, anchor="w")
        tk.Frame(popup, bg=BORDER, height=1).pack(fill=tk.X, padx=32, pady=(0, 12))

        fields = {}
        settings = [
            ("JACKETT_URL",        "URL Jackett"),
            ("JACKETT_API_KEY",    "Cle API Jackett"),
            ("JELLYFIN_URL",       "URL Jellyfin"),
            ("TMDB_API_KEY",       "Cle API TMDB"),
            ("QBITTORRENT_PATH",   "Chemin qBittorrent"),
            ("QBITTORRENT_API_URL","API Web qBittorrent"),
            ("PREFERRED_QUALITY",  "Qualite preferee (1080p, 4K, 720p...)"),
        ]
        for key, label in settings:
            row = tk.Frame(popup, bg=BG)
            row.pack(fill=tk.X, padx=32, pady=5)
            tk.Label(row, text=label, font=F_SMALL, bg=BG, fg=SUB,
                     width=28, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=current.get(key, ""))
            tk.Entry(row, textvariable=var, font=F_BODY, bg=SURF2, fg=TEXT,
                     borderwidth=0, highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER,
                     insertbackground=ACCENT
                     ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(8, 0))
            fields[key] = var

        tk.Frame(popup, bg=BORDER, height=1).pack(fill=tk.X, padx=32, pady=(16, 0))
        foot = tk.Frame(popup, bg=BG)
        foot.pack(fill=tk.X, padx=32, pady=12)
        lbl_msg = tk.Label(foot, text="", font=F_SMALL, bg=BG, fg=SUB)
        lbl_msg.pack(side=tk.LEFT)
        tk.Button(foot, text="Sauvegarder",
                  command=lambda: self._save_settings(fields, config_path, lbl_msg),
                  bg=ACCENT, fg="white", font=F_BOLD,
                  borderwidth=0, relief="flat", padx=24, pady=8, cursor="hand2",
                  activebackground=ACCENT2, activeforeground="white"
                  ).pack(side=tk.RIGHT)

    def _save_settings(self, fields, config_path, lbl_msg):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                saved = False
                for key, var in fields.items():
                    if re.match(r"^\s*" + re.escape(key) + r"\s*=", line):
                        comment = ""
                        if "#" in line:
                            comment = "   #" + line.partition("#")[2].rstrip()
                        new_lines.append(f"{key} = {repr(var.get())}{comment}\n")
                        saved = True
                        break
                if not saved:
                    new_lines.append(line)
            with open(config_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            lbl_msg.config(
                text="Sauvegarde. Relancez l'app pour appliquer.", fg=GREEN)
        except Exception as e:
            lbl_msg.config(text=f"Erreur : {e}", fg=RED)

    # ── Service health ────────────────────────────────────────────────────────

    def _launch_jackett_if_needed(self):
        import time
        if _check_service(JACKETT_URL, timeout=2):
            return  # already running
        try:
            subprocess.Popen(
                [JACKETT_PATH],
                creationflags=0x08000000,   # CREATE_NO_WINDOW
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait up to 12 s for Jackett to be ready
            for _ in range(6):
                time.sleep(2)
                if _check_service(JACKETT_URL, timeout=2):
                    break
        except FileNotFoundError:
            pass  # JACKETT_PATH incorrect — user can fix in Settings
        except Exception:
            pass

    def _service_watcher(self):
        import time
        # First check right away so dots light up quickly at startup
        self._do_service_check()
        while True:
            time.sleep(15)
            self._do_service_check()

    def _do_service_check(self):
        statuses = {
            "jackett":  _check_service(JACKETT_URL),
            "jellyfin": _check_service(JELLYFIN_URL),
            "qbt":      _check_service(f"{QBITTORRENT_API_URL}/api/v2/app/version"),
        }
        self.root.after(0, self._update_status_dots, statuses)

    def _update_status_dots(self, statuses):
        for key, ok in statuses.items():
            dot = self._status_dots.get(key)
            if dot:
                dot.config(fg=GREEN if ok else RED)

    # ── Icon / navigation ────────────────────────────────────────────────────

    def _load_icon(self):
        path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
        if os.path.exists(path):
            try:
                self.root.iconbitmap(path)
            except Exception:
                pass

    def open_qbittorrent(self):
        try:
            subprocess.Popen([QBITTORRENT_PATH])
        except FileNotFoundError:
            try:
                subprocess.Popen(["qbittorrent"])
            except Exception:
                pass

    def open_jackett(self):   webbrowser.open(JACKETT_URL)
    def open_jellyfin(self):  webbrowser.open(JELLYFIN_URL)


if __name__ == "__main__":
    root = tk.Tk()
    TorrentApp(root)
    root.mainloop()
