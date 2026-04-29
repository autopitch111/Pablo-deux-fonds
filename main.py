"""
HookMeme – Transforme tes vidéos TikTok/Reels :
  • Hook accrocheur en overlay
  • Coupe à 6 secondes
  • Mème automatique en fin de clip
"""
import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
MEMES_DIR   = os.path.join(BASE_DIR, "memes")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
ENV_FILE    = os.path.join(BASE_DIR, ".env")

# Load .env if present
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

for d in (UPLOADS_DIR, MEMES_DIR, OUTPUT_DIR):
    os.makedirs(d, exist_ok=True)

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── helpers ──────────────────────────────────────────────────────────────────

def get_thumbnail(video_path: str, size=(160, 90)):
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 1))
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img.thumbnail(size, Image.LANCZOS)
        # pad to fixed size
        padded = Image.new("RGB", size, (20, 20, 30))
        ox = (size[0] - img.width) // 2
        oy = (size[1] - img.height) // 2
        padded.paste(img, (ox, oy))
        return ImageTk.PhotoImage(padded)
    except Exception:
        return None


def list_videos(folder: str):
    return [
        f for f in os.listdir(folder)
        if f.lower().endswith(VIDEO_EXTS)
    ]


# ── main app ─────────────────────────────────────────────────────────────────

class HookMemeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HookMeme 🎬")
        self.geometry("900x700")
        self.resizable(True, True)

        self._selected_video = None
        self._thumb_refs = []   # keep PhotoImage refs alive
        self._processing = False

        self._build_ui()
        self._refresh_library()

    # ── UI layout ─────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        # ── top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 4))

        ctk.CTkLabel(top, text="HookMeme", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkLabel(
            top,
            text="Hook + Mème automatique pour tes Reels/TikToks",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(side="left", padx=12)
        ctk.CTkButton(top, text="⟳ Rafraîchir", width=110, command=self._refresh_library).pack(side="right")

        # ── API key banner (shown only if key missing)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            api_bar = ctk.CTkFrame(self, fg_color="#3a1a00", corner_radius=6)
            api_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(60, 0))
            ctk.CTkLabel(api_bar, text="⚠  Clé API Anthropic requise :", text_color="#ffaa44").pack(side="left", padx=10, pady=6)
            self._api_entry = ctk.CTkEntry(api_bar, placeholder_text="sk-ant-…", width=320, show="*")
            self._api_entry.pack(side="left", padx=4)
            ctk.CTkButton(api_bar, text="Enregistrer", width=100, command=self._save_api_key).pack(side="left", padx=8)

        # ── left: video library
        lib_frame = ctk.CTkFrame(self)
        lib_frame.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=8)
        lib_frame.grid_rowconfigure(1, weight=1)
        lib_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            lib_frame, text="📁  Vidéos (dossier uploads/)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self._scroll = ctk.CTkScrollableFrame(lib_frame)
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # ── right: preview + controls
        right = ctk.CTkFrame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right, text="Vidéo sélectionnée", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )

        self._preview_label = ctk.CTkLabel(
            right, text="Aucune vidéo\nsélectionnée",
            width=260, height=146,
            fg_color=("#1a1a2e", "#1a1a2e"),
            corner_radius=8,
        )
        self._preview_label.grid(row=1, column=0, padx=12, pady=4)

        self._video_name_lbl = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=12), text_color="gray", wraplength=240
        )
        self._video_name_lbl.grid(row=2, column=0, padx=12, pady=2)

        # hook override (optionnel)
        ctk.CTkLabel(right, text="Hook personnalisé (optionnel):", font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, sticky="w", padx=12, pady=(12, 2)
        )
        self._hook_entry = ctk.CTkEntry(
            right, placeholder_text="Laisse vide = IA automatique", width=240
        )
        self._hook_entry.grid(row=4, column=0, padx=12, pady=2)

        # process button
        self._process_btn = ctk.CTkButton(
            right,
            text="🚀  Générer la vidéo",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            command=self._start_processing,
            state="disabled",
        )
        self._process_btn.grid(row=5, column=0, padx=12, pady=(16, 4), sticky="ew")

        # status
        self._status_lbl = ctk.CTkLabel(
            right, text="Dépose tes vidéos dans\nuploads/ et tes mèmes dans memes/",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=240,
        )
        self._status_lbl.grid(row=6, column=0, padx=12, pady=4)

        # open output folder
        ctk.CTkButton(
            right,
            text="📂  Ouvrir le dossier output/",
            width=200,
            fg_color="transparent",
            border_width=1,
            command=lambda: os.system(f'open "{OUTPUT_DIR}"'),
        ).grid(row=7, column=0, padx=12, pady=(8, 12))

        # ── bottom: progress bar
        self._progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self._progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        self._progress.set(0)

    # ── library ───────────────────────────────────────────────────────────

    def _save_api_key(self):
        key = self._api_entry.get().strip()
        if not key.startswith("sk-"):
            messagebox.showerror("Clé invalide", "La clé doit commencer par sk-ant-…")
            return
        os.environ["ANTHROPIC_API_KEY"] = key
        with open(ENV_FILE, "w") as f:
            f.write(f"ANTHROPIC_API_KEY={key}\n")
        messagebox.showinfo("Clé enregistrée", "Clé API sauvegardée dans .env !")

    def _refresh_library(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        videos = list_videos(UPLOADS_DIR)
        if not videos:
            ctk.CTkLabel(
                self._scroll,
                text="Aucune vidéo trouvée.\nDépose des .mp4 / .mov dans le dossier uploads/",
                text_color="gray",
                wraplength=280,
            ).pack(pady=20)
            return

        for fname in sorted(videos):
            self._add_video_card(fname)

    def _add_video_card(self, fname: str):
        path = os.path.join(UPLOADS_DIR, fname)

        card = ctk.CTkFrame(self._scroll, corner_radius=8, cursor="hand2")
        card.pack(fill="x", padx=4, pady=4)
        card.grid_columnconfigure(1, weight=1)

        thumb = get_thumbnail(path)
        if thumb:
            self._thumb_refs.append(thumb)
            img_lbl = ctk.CTkLabel(card, image=thumb, text="")
        else:
            img_lbl = ctk.CTkLabel(card, text="🎬", font=ctk.CTkFont(size=32), width=80)
        img_lbl.grid(row=0, column=0, rowspan=2, padx=8, pady=8)

        name_lbl = ctk.CTkLabel(
            card, text=fname, font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        )
        name_lbl.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(8, 2))

        # duration
        try:
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            dur = frames / fps
            dur_txt = f"{int(dur//60)}:{int(dur%60):02d}"
        except Exception:
            dur_txt = "??:??"
        ctk.CTkLabel(card, text=f"⏱ {dur_txt}", text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=1, sticky="w", padx=(4, 8), pady=(0, 8)
        )

        for w in (card, img_lbl, name_lbl):
            w.bind("<Button-1>", lambda e, f=fname: self._select_video(f))

    # ── selection ─────────────────────────────────────────────────────────

    def _select_video(self, fname: str):
        self._selected_video = fname
        path = os.path.join(UPLOADS_DIR, fname)

        thumb = get_thumbnail(path, size=(260, 146))
        if thumb:
            self._thumb_refs.append(thumb)
            self._preview_label.configure(image=thumb, text="")
        else:
            self._preview_label.configure(image=None, text="Aperçu indisponible")

        self._video_name_lbl.configure(text=fname)
        self._process_btn.configure(state="normal")
        self._status_lbl.configure(text="Prêt à générer !", text_color="lightgreen")

    # ── processing ────────────────────────────────────────────────────────

    def _start_processing(self):
        if not self._selected_video or self._processing:
            return
        self._processing = True
        self._process_btn.configure(state="disabled", text="⏳  En cours…")
        self._progress.start()
        threading.Thread(target=self._process_thread, daemon=True).start()

    def _process_thread(self):
        try:
            from analyzer import analyze_video, pick_best_meme
            from processor import process_video

            video_path = os.path.join(UPLOADS_DIR, self._selected_video)
            custom_hook = self._hook_entry.get().strip()

            self._set_status("🔍  Analyse de la vidéo par l'IA…")
            video_info = analyze_video(video_path)

            hook = custom_hook if custom_hook else video_info.get("hook", "REGARDE JUSQU'AU BOUT !")

            self._set_status("🎭  Sélection du meilleur mème…")
            meme_file = pick_best_meme(MEMES_DIR, video_info)
            meme_path = os.path.join(MEMES_DIR, meme_file) if meme_file else None

            if meme_file:
                self._set_status(f"✅  Mème choisi : {meme_file}")
            else:
                self._set_status("⚠️  Aucun mème trouvé (dossier memes/ vide)")

            base = os.path.splitext(self._selected_video)[0]
            output_path = os.path.join(OUTPUT_DIR, f"{base}_hookmeme.mp4")

            process_video(
                video_path=video_path,
                meme_path=meme_path,
                hook_text=hook,
                output_path=output_path,
                progress_callback=self._set_status,
            )

            self.after(0, lambda: messagebox.showinfo(
                "Vidéo générée !",
                f"✅ Fichier sauvegardé dans :\n{output_path}\n\nHook utilisé : {hook}"
            ))
            self._set_status(f"✅  Terminé → output/{os.path.basename(output_path)}", color="lightgreen")

        except Exception as e:
            self._set_status(f"❌  Erreur : {e}", color="#ff6b6b")
            self.after(0, lambda: messagebox.showerror("Erreur", str(e)))

        finally:
            self._processing = False
            self.after(0, self._progress.stop)
            self.after(0, lambda: self._process_btn.configure(
                state="normal", text="🚀  Générer la vidéo"
            ))

    def _set_status(self, msg: str, color: str = "white"):
        self.after(0, lambda: self._status_lbl.configure(text=msg, text_color=color))


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = HookMemeApp()
    app.mainloop()
