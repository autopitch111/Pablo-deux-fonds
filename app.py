"""HookMeme Web App"""
import os, re, json, uuid, threading, time
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, send_file
import cv2
from PIL import Image

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
MEMES_DIR   = os.path.join(BASE_DIR, "memes")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
THUMBS_DIR  = os.path.join(BASE_DIR, "thumbs")
ENV_FILE    = os.path.join(BASE_DIR, ".env")
SCHED_FILE  = os.path.join(BASE_DIR, "schedule.json")
STATE_FILE  = os.path.join(BASE_DIR, "state.json")

for d in [UPLOADS_DIR, MEMES_DIR, OUTPUT_DIR, THUMBS_DIR]:
    os.makedirs(d, exist_ok=True)

if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

_jobs: dict = {}
_jobs_lock = threading.Lock()

DAYS_FR = {"lundi":0,"mardi":1,"mercredi":2,"jeudi":3,"vendredi":4,"samedi":5,"dimanche":6}


# ── helpers ───────────────────────────────────────────────────────────────

def _safe(name): return "".join(c for c in name if c.isalnum() or c in "._- ")

def _make_thumb(src, dst, ts=1.5):
    try:
        cap = cv2.VideoCapture(src)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((cap.get(cv2.CAP_PROP_FPS) or 30) * ts))
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0); ret, frame = cap.read()
        cap.release()
        if ret:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail((320, 568), Image.LANCZOS)
            img.save(dst, "JPEG", quality=85)
            return True
    except: pass
    return False

def _duration(path):
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        n   = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        return round(n / fps, 1)
    except: return 0.0

def _send_video(path):
    size = os.path.getsize(path)
    rng  = request.headers.get("Range", "")
    mime = "video/mp4"
    if rng:
        m = re.search(r"bytes=(\d+)-(\d*)", rng)
        start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1
        end = min(end, size-1); length = end-start+1
        with open(path,"rb") as f: f.seek(start); data = f.read(length)
        r = Response(data, 206, mimetype=mime)
        r.headers.update({"Content-Range":f"bytes {start}-{end}/{size}","Accept-Ranges":"bytes","Content-Length":length})
        return r
    r = Response(open(path,"rb"), 200, mimetype=mime)
    r.headers.update({"Content-Length":size,"Accept-Ranges":"bytes"})
    return r

def _update_job(jid, msg):
    with _jobs_lock:
        if jid in _jobs: _jobs[jid]["message"] = msg

def _load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f: return json.load(f)
    return {"processed": []}

def _save_state(s):
    with open(STATE_FILE,"w") as f: json.dump(s, f)

def _load_sched():
    if os.path.exists(SCHED_FILE):
        with open(SCHED_FILE) as f: return json.load(f)
    return {"enabled":False,"day":"mercredi","hour":9,"minute":0}

def _save_sched(s):
    with open(SCHED_FILE,"w") as f: json.dump(s, f)

HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

def _load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f: return json.load(f)
    return []

def _add_history(entry):
    h = _load_history()
    h.insert(0, entry)
    with open(HISTORY_FILE, "w") as f: json.dump(h, f, ensure_ascii=False)


# ── routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/settings", methods=["GET","POST"])
def settings():
    if request.method == "POST":
        key = (request.json or {}).get("api_key","").strip()
        if key:
            os.environ["OPENAI_API_KEY"] = key
            with open(ENV_FILE,"w") as f: f.write(f"OPENAI_API_KEY={key}\n")
            return jsonify({"ok":True})
        return jsonify({"ok":False}), 400
    return jsonify({"has_key": bool(os.environ.get("OPENAI_API_KEY"))})

@app.route("/api/schedule", methods=["GET","POST"])
def schedule():
    if request.method == "POST":
        _save_sched(request.json); return jsonify({"ok":True})
    return jsonify(_load_sched())

@app.route("/api/files/<kind>")
def list_files(kind):
    folder = UPLOADS_DIR if kind == "videos" else MEMES_DIR
    out = []
    for fname in sorted(os.listdir(folder)):
        if Path(fname).suffix.lower() not in VIDEO_EXTS: continue
        prefix = "" if kind == "videos" else "meme_"
        tn = prefix + fname + ".thumb.jpg"
        tp = os.path.join(THUMBS_DIR, tn)
        if not os.path.exists(tp): _make_thumb(os.path.join(folder, fname), tp)
        out.append({"filename":fname, "duration":_duration(os.path.join(folder,fname)),
                    "thumbnail":f"/api/thumb/{kind}/{tn}"})
    return jsonify(out)

@app.route("/api/files/outputs")
def list_outputs():
    out = []
    for fname in sorted(os.listdir(OUTPUT_DIR), key=lambda f: -os.path.getmtime(os.path.join(OUTPUT_DIR,f))):
        if Path(fname).suffix.lower() not in VIDEO_EXTS: continue
        tn = "out_" + fname + ".thumb.jpg"
        tp = os.path.join(THUMBS_DIR, tn)
        if not os.path.exists(tp): _make_thumb(os.path.join(OUTPUT_DIR, fname), tp)
        out.append({"filename":fname, "duration":_duration(os.path.join(OUTPUT_DIR,fname)),
                    "thumbnail":f"/api/thumb/outputs/{tn}"})
    return jsonify(out)

@app.route("/api/upload/<kind>", methods=["POST"])
def upload(kind):
    folder = UPLOADS_DIR if kind == "video" else MEMES_DIR
    prefix = "" if kind == "video" else "meme_"
    f = request.files.get("file")
    if not f or Path(f.filename).suffix.lower() not in VIDEO_EXTS:
        return jsonify({"error":"Format non supporté"}), 400
    name = _safe(f.filename); path = os.path.join(folder, name); f.save(path)
    tn = prefix + name + ".thumb.jpg"
    _make_thumb(path, os.path.join(THUMBS_DIR, tn))
    return jsonify({"filename":name, "duration":_duration(path),
                    "thumbnail":f"/api/thumb/{'videos' if kind=='video' else 'memes'}/{tn}"})

@app.route("/api/thumb/<kind>/<path:fn>")
def serve_thumb(kind, fn):
    p = os.path.join(THUMBS_DIR, fn)
    return send_file(p, mimetype="image/jpeg") if os.path.exists(p) else ("",404)

@app.route("/api/video/<kind>/<path:fn>")
def serve_video(kind, fn):
    folders = {"uploads":UPLOADS_DIR,"memes":MEMES_DIR,"outputs":OUTPUT_DIR}
    folder = folders.get(kind)
    if not folder: return "",404
    p = os.path.join(folder, fn)
    return _send_video(p) if os.path.exists(p) else ("",404)

@app.route("/api/download/<path:fn>")
def download(fn):
    p = os.path.join(OUTPUT_DIR, fn)
    return send_file(p, as_attachment=True, download_name=fn) if os.path.exists(p) else ("",404)

@app.route("/api/delete/<kind>/<path:fn>", methods=["DELETE"])
def delete_file(kind, fn):
    folders = {"videos":UPLOADS_DIR,"memes":MEMES_DIR,"outputs":OUTPUT_DIR}
    folder = folders.get(kind)
    if not folder: return jsonify({"error":"unknown"}),400
    p = os.path.join(folder, fn)
    if os.path.exists(p): os.remove(p)
    return jsonify({"ok":True})

@app.route("/api/process", methods=["POST"])
def start_process():
    data = request.json or {}
    videos           = data.get("videos", [])
    meme             = data.get("meme")
    hook             = data.get("hook","").strip()
    meme_mode        = data.get("meme_mode","fill")
    no_hook          = bool(data.get("no_hook", False))
    remove_watermark = bool(data.get("remove_watermark", False))
    if not videos: return jsonify({"error":"Aucune vidéo"}), 400

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status":"running","message":"Démarrage…","outputs":[],"total":len(videos),"done":0}

    def run():
        outputs = []
        for vf in videos:
            try:
                vpath = os.path.join(UPLOADS_DIR, vf)
                _update_job(job_id, f"Analyse de {vf}…")
                from analyzer import analyze_video, pick_best_meme
                info = analyze_video(vpath)
                h = hook if hook else info.get("hook","REGARDE JUSQU'AU BOUT !")

                mp = os.path.join(MEMES_DIR, meme) if meme else None
                if mp is None:
                    _update_job(job_id, f"Sélection mème pour {vf}…")
                    mf = pick_best_meme(MEMES_DIR, info)
                    mp = os.path.join(MEMES_DIR, mf) if mf else None

                out_name = Path(vf).stem + "_hookmeme.mp4"
                out_path = os.path.join(OUTPUT_DIR, out_name)
                from processor import process_video
                process_video(vpath, mp, h, out_path, lambda m: _update_job(job_id, m), meme_mode=meme_mode,
                              no_hook=no_hook, remove_watermark=remove_watermark)

                tn = "out_" + out_name + ".thumb.jpg"
                _make_thumb(out_path, os.path.join(THUMBS_DIR, tn))
                entry = {"id":str(uuid.uuid4()),"filename":out_name,"source":vf,
                         "hook":h,"meme":meme or "auto","meme_mode":meme_mode,
                         "thumbnail":f"/api/thumb/outputs/{tn}",
                         "generated_at":datetime.now().isoformat(),"auto":False}
                _add_history(entry)
                outputs.append({"filename":out_name,"hook":h,"thumbnail":f"/api/thumb/outputs/{tn}"})
                with _jobs_lock:
                    _jobs[job_id]["done"] += 1
            except Exception as e:
                _update_job(job_id, f"Erreur {vf}: {e}")

        with _jobs_lock:
            _jobs[job_id].update({"status":"done","message":f"{len(outputs)} vidéo(s) générée(s)","outputs":outputs})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/api/job/<jid>")
def job_status(jid):
    with _jobs_lock: j = _jobs.get(jid)
    return jsonify(j) if j else (jsonify({"error":"not found"}),404)


# ── scheduler background thread ──────────────────────────────────────────

def _process_all_auto():
    videos = [f for f in os.listdir(UPLOADS_DIR) if Path(f).suffix.lower() in VIDEO_EXTS]
    if not videos: return
    state = _load_state()
    to_do = [v for v in videos if v not in state.get("processed",[])]
    if not to_do: return

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status":"running","message":"Démarrage auto…","outputs":[],"total":len(to_do),"done":0}

    def run():
        outputs = []
        for vf in to_do:
            try:
                vpath = os.path.join(UPLOADS_DIR, vf)
                from analyzer import analyze_video, pick_best_meme
                info = analyze_video(vpath)
                h = info.get("hook","REGARDE JUSQU'AU BOUT !")
                mf = pick_best_meme(MEMES_DIR, info)
                mp = os.path.join(MEMES_DIR, mf) if mf else None
                out_name = Path(vf).stem + "_hookmeme.mp4"
                out_path = os.path.join(OUTPUT_DIR, out_name)
                from processor import process_video
                process_video(vpath, mp, h, out_path, lambda m: _update_job(job_id, m))
                tn = "out_" + out_name + ".thumb.jpg"
                _make_thumb(out_path, os.path.join(THUMBS_DIR, tn))
                entry = {"id":str(uuid.uuid4()),"filename":out_name,"source":vf,
                         "hook":h,"meme":mf or "auto","meme_mode":"fill",
                         "thumbnail":f"/api/thumb/outputs/{tn}",
                         "generated_at":datetime.now().isoformat(),"auto":True}
                _add_history(entry)
                outputs.append(out_name)
                s = _load_state(); s.setdefault("processed",[]).append(vf); _save_state(s)
                with _jobs_lock: _jobs[job_id]["done"] += 1
            except Exception as e:
                print(f"Auto error {vf}: {e}")
        with _jobs_lock:
            _jobs[job_id].update({"status":"done","message":f"{len(outputs)} vidéo(s) auto générées","outputs":outputs})

    threading.Thread(target=run, daemon=True).start()

def _scheduler():
    last = None
    while True:
        time.sleep(20)
        try:
            cfg = _load_sched()
            if not cfg.get("enabled"): continue
            now = datetime.now()
            target_day = DAYS_FR.get(cfg.get("day","mercredi"),2)
            if now.weekday()==target_day and now.hour==cfg.get("hour",9) and now.minute==cfg.get("minute",0):
                key = now.strftime("%Y%m%d%H%M")
                if last != key:
                    last = key
                    _process_all_auto()
        except: pass

threading.Thread(target=_scheduler, daemon=True).start()

@app.route("/api/reedit", methods=["POST"])
def reedit():
    data         = request.json or {}
    history_id   = data.get("history_id","").strip()
    hook_text    = data.get("hook_text","").strip()
    hook_position= data.get("hook_position","center")
    cut_seconds  = int(data.get("cut_seconds", 6))
    cut_seconds  = max(2, min(15, cut_seconds))

    history = _load_history()
    entry   = next((e for e in history if e.get("id") == history_id), None)
    if not entry:
        return jsonify({"error": "Entrée introuvable"}), 404

    source_path = os.path.join(UPLOADS_DIR, entry["source"])
    if not os.path.exists(source_path):
        return jsonify({"error": f"Vidéo source introuvable : {entry['source']}"}), 404

    meme_file = entry.get("meme")
    if meme_file and meme_file != "auto":
        meme_path = os.path.join(MEMES_DIR, meme_file)
        if not os.path.exists(meme_path): meme_path = None
    else:
        meme_path = None

    meme_mode = entry.get("meme_mode", "fill")
    hook_text = hook_text or entry.get("hook", "REGARDE JUSQU'AU BOUT !")

    stem     = Path(entry["source"]).stem
    out_name = f"{stem}_edit_{uuid.uuid4().hex[:6]}.mp4"
    out_path = os.path.join(OUTPUT_DIR, out_name)

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status":"running","message":"Démarrage…","outputs":[],"total":1,"done":0}

    def run():
        try:
            from processor import process_video
            process_video(source_path, meme_path, hook_text, out_path,
                          lambda m: _update_job(job_id, m),
                          meme_mode=meme_mode,
                          cut_seconds=cut_seconds,
                          hook_position=hook_position)
            tn = "out_" + out_name + ".thumb.jpg"
            _make_thumb(out_path, os.path.join(THUMBS_DIR, tn))
            new_entry = {"id": str(uuid.uuid4()), "filename": out_name,
                         "source": entry["source"], "hook": hook_text,
                         "meme": meme_file or "auto", "meme_mode": meme_mode,
                         "hook_position": hook_position, "cut_seconds": cut_seconds,
                         "thumbnail": f"/api/thumb/outputs/{tn}",
                         "generated_at": datetime.now().isoformat(), "auto": False,
                         "edited_from": history_id}
            _add_history(new_entry)
            with _jobs_lock:
                _jobs[job_id].update({"status":"done","message":"Terminé !",
                                      "outputs":[{"filename":out_name,
                                                  "thumbnail":f"/api/thumb/outputs/{tn}"}]})
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id].update({"status":"error","message":str(e)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/results")
def results_page(): return render_template("results.html")

@app.route("/team")
def team_page(): return render_template("team.html")

@app.route("/api/team/stats")
def team_stats():
    # Stock counts
    stock_videos = [f for f in os.listdir(UPLOADS_DIR) if Path(f).suffix.lower() in VIDEO_EXTS]
    stock_memes  = [f for f in os.listdir(MEMES_DIR)   if Path(f).suffix.lower() in VIDEO_EXTS]
    state        = _load_state()
    used_list    = state.get("processed", [])
    used_count   = len([v for v in used_list if v in stock_videos])

    # Cadence: how many scheduled runs in next 7 days
    cfg = _load_sched()
    needed_7days = 0
    forecast = []
    now = datetime.now()
    remaining_stock = len(stock_videos) - used_count
    stock_cursor = remaining_stock  # simulate consumption day by day

    for i in range(7):
        day = datetime.fromordinal(now.toordinal() + i)
        scheduled = False
        if cfg.get("enabled"):
            freq = cfg.get("freq", "weekly")
            target_day = DAYS_FR.get(cfg.get("day", "mercredi"), 2)
            if freq == "weekly" and day.weekday() == target_day:
                scheduled = True
            elif freq == "daily":
                scheduled = True
            elif freq == "biweekly" and day.weekday() == target_day and (i < 7):
                scheduled = True
        if scheduled:
            needed_7days += 1
        has_stock = stock_cursor > 0
        if scheduled and stock_cursor > 0:
            stock_cursor -= 1
        forecast.append({
            "date": day.strftime("%Y-%m-%d"),
            "is_today": i == 0,
            "scheduled": scheduled,
            "has_stock": has_stock if scheduled else True,
        })

    return jsonify({
        "stock_videos": len(stock_videos),
        "used_videos":  used_count,
        "remaining":    remaining_stock,
        "stock_memes":  len(stock_memes),
        "needed_7days": needed_7days,
        "used_list":    used_list,
        "forecast":     forecast,
    })

@app.route("/api/history")
def get_history(): return jsonify(_load_history())

@app.route("/api/history/<hid>", methods=["DELETE"])
def delete_history(hid):
    h = [e for e in _load_history() if e.get("id") != hid]
    with open(HISTORY_FILE,"w") as f: json.dump(h, f, ensure_ascii=False)
    p = next((e for e in _load_history() if e.get("id")==hid), None)
    return jsonify({"ok":True})

if __name__ == "__main__":
    print("\n🎬  HookMeme → http://127.0.0.1:5005\n")
    app.run(debug=False, host="127.0.0.1", port=5005, threaded=True)


# ── HOOK LIBRARY ─────────────────────────────────────────────────────────────

HOOKS_FILE = os.path.join(BASE_DIR, "hooks.json")

def _load_hooks():
    if os.path.exists(HOOKS_FILE):
        with open(HOOKS_FILE) as f: return json.load(f)
    return []

def _save_hooks(h):
    with open(HOOKS_FILE,"w") as f: json.dump(h, f)

@app.route("/api/hooks", methods=["GET"])
def get_hooks(): return jsonify(_load_hooks())

@app.route("/api/hooks", methods=["POST"])
def add_hook():
    text = (request.json or {}).get("text","").strip()
    if not text: return jsonify({"error":"empty"}), 400
    hooks = _load_hooks()
    h = {"id": str(uuid.uuid4()), "text": text}
    hooks.append(h); _save_hooks(hooks)
    return jsonify(h)

@app.route("/api/hooks/<hid>", methods=["DELETE"])
def del_hook(hid):
    _save_hooks([h for h in _load_hooks() if h["id"] != hid])
    return jsonify({"ok":True})
