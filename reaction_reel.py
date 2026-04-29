"""
Reaction Reel Generator — Flask web app
Lance : python3 reaction_reel.py
Ouvre  : http://localhost:5050
"""
import math
import os
import subprocess
import threading
import traceback
import uuid
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

app = Flask(__name__)
CORS(app)

jobs: dict[str, dict] = {}

HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reaction Reel Generator</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f0f1a;color:#eaeaea;font-family:'Segoe UI',Helvetica,sans-serif;
       display:flex;flex-direction:column;align-items:center;padding:40px 16px 80px;min-height:100vh}
  h1{font-size:26px;color:#e94560;margin-bottom:4px}
  .sub{color:#666;font-size:13px;margin-bottom:28px}
  .card{background:#16213e;border-radius:14px;padding:20px 24px;width:100%;max-width:580px;margin-bottom:14px}
  .card h2{font-size:13px;color:#aaa;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em}
  .drop-zone{border:2px dashed #e9456055;border-radius:10px;padding:24px;text-align:center;
             cursor:pointer;transition:.2s;position:relative}
  .drop-zone:hover,.drop-zone.over{border-color:#e94560;background:#1a2a4a}
  .drop-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
  .drop-zone .icon{font-size:28px;display:block;margin-bottom:4px}
  .drop-zone .hint{font-size:11px;color:#555}
  .drop-zone .name{font-size:12px;color:#4fc3f7;margin-top:6px;word-break:break-all}
  input[type=text],input[type=number]{background:#0f3460;border:none;border-radius:8px;
    color:#eee;font-size:14px;padding:10px 14px;outline:none}
  input[type=text]{width:100%}
  input[type=range]{width:100%;accent-color:#e94560}
  .row{display:flex;gap:10px;align-items:center;margin-top:8px}
  .row label{font-size:13px;color:#aaa;white-space:nowrap}
  .row span{font-size:13px;color:#e94560;min-width:36px}

  /* effects */
  .sfx-row{display:flex;flex-direction:column;gap:8px;margin-bottom:10px;background:#0f1e38;
           border-radius:12px;padding:12px 14px}
  .sfx-row-top{display:flex;gap:8px;align-items:center}
  .sfx-row input[type=number]{width:80px;flex-shrink:0}
  .sfx-file{flex:1;background:#0f3460;border:none;border-radius:8px;color:#4fc3f7;
            font-size:12px;padding:8px 10px;cursor:pointer;outline:none;min-width:0}
  .sfx-file::-webkit-file-upload-button{background:#e94560;color:#fff;border:none;
    border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px;margin-right:8px}
  .rec-btn{background:#1a3a6a;color:#eee;border:none;border-radius:8px;
           padding:7px 12px;cursor:pointer;font-size:13px;flex-shrink:0;white-space:nowrap;
           transition:.15s}
  .rec-btn.recording{background:#e94560;animation:pulse 1s infinite}
  .rec-btn.done{background:#00b894;color:#fff}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
  .sfx-preview{display:none;width:100%;margin-top:4px}
  .sfx-preview audio{width:100%;height:32px;border-radius:8px}
  .del-btn{background:#e9456033;color:#e94560;border:none;border-radius:6px;
           padding:4px 10px;cursor:pointer;font-size:16px;flex-shrink:0}
  .add-btn{background:#1a3a6a;color:#4fc3f7;border:none;border-radius:8px;
           padding:8px 16px;cursor:pointer;font-size:13px;width:100%;margin-top:4px}
  .add-btn:hover{background:#2a4a8a}
  .tag{display:inline-block;background:#e9456022;color:#e94560;border-radius:6px;
       padding:2px 8px;font-size:11px;margin-right:6px}

  button.primary{width:100%;max-width:580px;background:#e94560;color:#fff;border:none;
    border-radius:12px;font-size:17px;font-weight:700;padding:16px;cursor:pointer;
    transition:.15s;margin-top:8px}
  button.primary:hover{background:#ff6b81}
  button.primary:disabled{background:#444;cursor:not-allowed}
  .progress-wrap{width:100%;max-width:580px;background:#16213e;border-radius:99px;
                 height:12px;overflow:hidden;margin-top:20px;display:none}
  .progress-bar{height:100%;background:#e94560;border-radius:99px;width:0%;transition:width .4s}
  #status{font-size:13px;color:#888;text-align:center;margin-top:10px;min-height:18px}
  #download{display:none;width:100%;max-width:580px;background:#00b894;color:#fff;
            border:none;border-radius:12px;font-size:16px;font-weight:700;
            padding:14px;cursor:pointer;margin-top:10px}
</style>
</head>
<body>
<h1>🎬 Reaction Reel Generator</h1>
<p class="sub">Format Instagram / TikTok · 9:16 · 1080×1920</p>

<!-- Streamer -->
<div class="card">
  <h2>📹 Vidéo Streamer (haut)</h2>
  <div class="drop-zone" id="dz-streamer">
    <span class="icon">📹</span>
    Clique ou glisse la vidéo du streamer<br>
    <span class="hint">.mp4 .mov .avi .mkv</span>
    <div class="name" id="name-streamer"></div>
    <input type="file" id="file-streamer" accept="video/*">
  </div>
</div>

<!-- Modèle -->
<div class="card">
  <h2>💃 Vidéo Modèle / Créatrice (bas)</h2>
  <div class="drop-zone" id="dz-model">
    <span class="icon">💃</span>
    Clique ou glisse la vidéo de la modèle<br>
    <span class="hint">.mp4 .mov .avi .mkv</span>
    <div class="name" id="name-model"></div>
    <input type="file" id="file-model" accept="video/*">
  </div>
</div>

<!-- Texte -->
<div class="card">
  <h2>✏️ Texte POV</h2>
  <input type="text" id="pov-text" value="POV : You réagis à une vidéo de ">
</div>

<!-- Options -->
<div class="card">
  <h2>⚙️ Options</h2>
  <div class="row">
    <label>Taille texte :</label>
    <input type="range" id="font-size" min="28" max="90" value="52"
           oninput="document.getElementById('fs-val').textContent=this.value+'px'">
    <span id="fs-val">52px</span>
  </div>
  <div class="row" style="margin-top:14px">
    <label>Durée max (sec, 0 = auto) :</label>
    <input type="number" id="max-dur" value="0" min="0" max="300" style="width:90px;flex-shrink:0">
  </div>
</div>

<!-- Zoom -->
<div class="card">
  <h2>🔍 Zooms sur la modèle <span class="tag">optionnel</span></h2>
  <p style="font-size:12px;color:#666;margin-bottom:10px">
    Timestamps en secondes séparés par des virgules — ex: <code style="color:#4fc3f7">3.5, 8, 14.2</code>
  </p>
  <input type="text" id="zoom-times" placeholder="ex: 3.5, 8, 14.2">
  <div class="row" style="margin-top:12px">
    <label>Intensité zoom :</label>
    <input type="range" id="zoom-intensity" min="5" max="35" value="18"
           oninput="document.getElementById('zi-val').textContent=this.value+'%'">
    <span id="zi-val">18%</span>
  </div>
</div>

<!-- Effets sonores -->
<div class="card">
  <h2>🔊 Effets sonores <span class="tag">optionnel</span></h2>
  <p style="font-size:12px;color:#666;margin-bottom:12px">
    Ajoute un son à un moment précis de la vidéo
  </p>
  <div id="sfx-list"></div>
  <button class="add-btn" onclick="addSfx()">＋ Ajouter un effet sonore</button>
</div>

<button class="primary" id="generate-btn" onclick="generate()">🚀 Générer le Reel</button>

<div class="progress-wrap" id="progress-wrap">
  <div class="progress-bar" id="progress-bar"></div>
</div>
<div id="status">Prêt</div>
<button id="download" onclick="downloadResult()">⬇️ Télécharger le Reel</button>

<script>
let currentJobId = null;
let pollInterval = null;
let sfxCount = 0;

['streamer','model'].forEach(key => {
  const inp = document.getElementById('file-'+key);
  const dz  = document.getElementById('dz-'+key);
  const nm  = document.getElementById('name-'+key);
  inp.addEventListener('change', () => { if(inp.files[0]) nm.textContent = inp.files[0].name; });
  dz.addEventListener('dragover', e=>{e.preventDefault();dz.classList.add('over')});
  dz.addEventListener('dragleave', ()=>dz.classList.remove('over'));
  dz.addEventListener('drop', e=>{
    e.preventDefault();dz.classList.remove('over');
    if(e.dataTransfer.files[0]){ inp.files=e.dataTransfer.files; nm.textContent=e.dataTransfer.files[0].name; }
  });
});

// Per-row recorder state
const recorders = {};

function addSfx(){
  const id = sfxCount++;
  const row = document.createElement('div');
  row.className = 'sfx-row';
  row.id = 'sfx-row-'+id;
  row.innerHTML = `
    <div class="sfx-row-top">
      <label style="font-size:12px;color:#aaa;white-space:nowrap">à</label>
      <input type="number" id="sfx-time-${id}" placeholder="sec" min="0" step="0.1" value="0">
      <label style="font-size:12px;color:#aaa;white-space:nowrap">s —</label>
      <input type="file" class="sfx-file" id="sfx-file-${id}" accept="audio/*,.mp3,.wav,.m4a,.ogg"
             onchange="onFileChosen(${id})">
      <button class="rec-btn" id="rec-btn-${id}" onclick="toggleRecord(${id})">🎙 Enregistrer</button>
      <button class="del-btn" onclick="deleteSfxRow(${id})">✕</button>
    </div>
    <div class="sfx-preview" id="sfx-preview-${id}">
      <audio id="sfx-audio-${id}" controls></audio>
    </div>
  `;
  document.getElementById('sfx-list').appendChild(row);
  recorders[id] = { blob: null, mediaRecorder: null, chunks: [], stream: null };
}

function deleteSfxRow(id){
  const r = recorders[id];
  if(r && r.stream) r.stream.getTracks().forEach(t => t.stop());
  delete recorders[id];
  const el = document.getElementById('sfx-row-'+id);
  if(el) el.remove();
}

function onFileChosen(id){
  const f = document.getElementById('sfx-file-'+id).files[0];
  if(!f) return;
  const url = URL.createObjectURL(f);
  const audio = document.getElementById('sfx-audio-'+id);
  audio.src = url;
  document.getElementById('sfx-preview-'+id).style.display = 'block';
  recorders[id].blob = f;
  const btn = document.getElementById('rec-btn-'+id);
  btn.className = 'rec-btn done';
  btn.textContent = '✅ Fichier chargé';
}

async function toggleRecord(id){
  const r = recorders[id];
  const btn = document.getElementById('rec-btn-'+id);

  if(r.mediaRecorder && r.mediaRecorder.state === 'recording'){
    // Stop recording
    r.mediaRecorder.stop();
    return;
  }

  // Start recording
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    r.stream = stream;
    r.chunks = [];

    // Pick a MIME type Safari or Chrome supports
    const mimeType = ['audio/mp4','audio/aac','audio/webm;codecs=opus','audio/webm','']
      .find(m => !m || MediaRecorder.isTypeSupported(m)) || '';
    const mr = mimeType ? new MediaRecorder(stream, {mimeType}) : new MediaRecorder(stream);
    r.mediaRecorder = mr;
    r.mimeType = mr.mimeType || 'audio/mp4';

    mr.ondataavailable = e => { if(e.data.size) r.chunks.push(e.data); };
    mr.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(r.chunks, {type: r.mimeType});
      r.blob = blob;
      const url = URL.createObjectURL(blob);
      const audio = document.getElementById('sfx-audio-'+id);
      audio.src = url;
      audio.load();
      document.getElementById('sfx-preview-'+id).style.display = 'block';
      btn.className = 'rec-btn done';
      btn.textContent = '✅ Enregistré — Écouter ↑';
    };

    mr.start();
    btn.className = 'rec-btn recording';
    btn.textContent = '⏹ Stop';
  } catch(err){
    alert('Micro inaccessible : ' + err.message);
  }
}

async function generate(){
  const streamer = document.getElementById('file-streamer').files[0];
  const model    = document.getElementById('file-model').files[0];
  if(!streamer){alert('Sélectionne la vidéo du streamer.');return;}
  if(!model){alert('Sélectionne la vidéo de la modèle.');return;}

  const btn = document.getElementById('generate-btn');
  btn.disabled=true; btn.textContent='⏳ Génération en cours…';
  document.getElementById('download').style.display='none';
  document.getElementById('progress-wrap').style.display='block';
  setProgress(0,'Upload en cours…');

  const fd = new FormData();
  fd.append('streamer', streamer);
  fd.append('model', model);
  fd.append('pov_text', document.getElementById('pov-text').value);
  fd.append('font_size', document.getElementById('font-size').value);
  fd.append('max_dur', document.getElementById('max-dur').value);
  fd.append('zoom_times', document.getElementById('zoom-times').value);
  fd.append('zoom_intensity', document.getElementById('zoom-intensity').value);

  // collect SFX rows (file upload OR mic recording)
  let sfxIdx = 0;
  document.querySelectorAll('.sfx-row').forEach(row => {
    const id = row.id.replace('sfx-row-','');
    const timeInput = document.getElementById('sfx-time-'+id);
    const r = recorders[id];
    const blob = r && r.blob;
    if(blob){
      const t = blob.type || '';
      const ext = t.includes('mp4') || t.includes('aac') ? '.mp4'
                : t.includes('webm') ? '.webm'
                : blob.name ? '.'+blob.name.split('.').pop() : '.mp4';
      const filename = `sfx_${sfxIdx}${ext}`;
      fd.append(`sfx_time_${sfxIdx}`, timeInput ? timeInput.value : 0);
      fd.append(`sfx_file_${sfxIdx}`, blob, filename);
      sfxIdx++;
    }
  });
  fd.append('sfx_count', sfxIdx);

  const res = await fetch('/generate', {method:'POST', body:fd});
  const data = await res.json();
  if(data.error){setProgress(0,'Erreur: '+data.error);btn.disabled=false;btn.textContent='🚀 Générer le Reel';return;}
  currentJobId = data.job_id;
  pollInterval = setInterval(poll, 1500);
}

async function poll(){
  const res = await fetch('/status/'+currentJobId);
  const d = await res.json();
  setProgress(d.progress, d.message);
  if(d.done){
    clearInterval(pollInterval);
    const btn = document.getElementById('generate-btn');
    btn.disabled=false; btn.textContent='🚀 Générer le Reel';
    if(d.error){ setProgress(0,'❌ '+d.error); }
    else{ setProgress(1,'✅ Reel généré !'); document.getElementById('download').style.display='block'; }
  }
}

function setProgress(v, msg){
  document.getElementById('progress-bar').style.width=(v*100)+'%';
  document.getElementById('status').textContent=msg;
}

function downloadResult(){ window.location='/download/'+currentJobId; }
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/generate", methods=["POST"])
def generate():
    streamer = request.files.get("streamer")
    model = request.files.get("model")
    if not streamer or not model:
        return jsonify({"error": "Fichiers manquants"}), 400

    job_id = str(uuid.uuid4())[:8]
    s_path = UPLOAD_DIR / f"{job_id}_streamer{Path(streamer.filename).suffix}"
    m_path = UPLOAD_DIR / f"{job_id}_model{Path(model.filename).suffix}"
    streamer.save(s_path)
    model.save(m_path)

    pov_text      = request.form.get("pov_text", "POV : You réagis à une vidéo de ")
    font_size     = int(request.form.get("font_size", 52))
    max_dur       = float(request.form.get("max_dur", 0))
    zoom_times_raw = request.form.get("zoom_times", "")
    zoom_intensity = float(request.form.get("zoom_intensity", 18)) / 100.0
    sfx_count     = int(request.form.get("sfx_count", 0))

    zoom_times = []
    for part in zoom_times_raw.split(","):
        part = part.strip()
        if part:
            try:
                zoom_times.append(float(part))
            except ValueError:
                pass

    sfx_list = []
    for i in range(sfx_count):
        sfx_file = request.files.get(f"sfx_file_{i}")
        sfx_time = float(request.form.get(f"sfx_time_{i}", 0))
        if sfx_file:
            sfx_path = UPLOAD_DIR / f"{job_id}_sfx{i}{Path(sfx_file.filename).suffix}"
            sfx_file.save(sfx_path)
            sfx_list.append({"path": str(sfx_path), "time": sfx_time})

    jobs[job_id] = {"progress": 0.02, "message": "Job démarré…", "done": False, "error": None}

    threading.Thread(
        target=process_video,
        args=(job_id, str(s_path), str(m_path), pov_text, font_size,
              max_dur, zoom_times, zoom_intensity, sfx_list),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    j = jobs.get(job_id, {"progress": 0, "message": "Inconnu", "done": True, "error": "Job introuvable"})
    return jsonify(j)


@app.route("/download/<job_id>")
def download(job_id):
    out = OUTPUT_DIR / f"{job_id}.mp4"
    if not out.exists():
        return "Fichier introuvable", 404
    return send_file(str(out), as_attachment=True, download_name="reaction_reel.mp4")


def set_status(job_id, msg, progress):
    if job_id in jobs:
        jobs[job_id]["message"] = msg
        jobs[job_id]["progress"] = progress


def process_video(job_id, streamer_path, model_path, pov_text, font_size,
                  max_dur, zoom_times, zoom_intensity, sfx_list):
    tmp_path = str(OUTPUT_DIR / f"{job_id}_noaudio.mp4")
    out_path = str(OUTPUT_DIR / f"{job_id}.mp4")
    try:
        from moviepy import VideoFileClip, CompositeVideoClip, ColorClip, ImageClip

        W, H = 1080, 1920
        top_h = 800
        bot_h = H - top_h

        set_status(job_id, "Chargement des vidéos…", 0.08)
        sc = VideoFileClip(streamer_path)
        mc = VideoFileClip(model_path)

        duration = min(sc.duration, mc.duration)
        if max_dur and max_dur > 0:
            duration = min(duration, max_dur)

        sc = sc.subclipped(0, duration)
        mc = mc.subclipped(0, duration)

        set_status(job_id, "Mise en forme streamer…", 0.20)
        sc = crop_fill(sc, W, top_h).with_position((0, 0))

        set_status(job_id, "Mise en forme modèle…", 0.35)
        mc_raw = crop_fill(mc, W, bot_h).without_audio()

        if zoom_times:
            set_status(job_id, "Application des zooms…", 0.45)
            mc_raw = apply_zoom_effects(mc_raw, zoom_times, zoom_intensity)

        mc_raw = mc_raw.with_position((0, top_h))

        set_status(job_id, "Texte overlay…", 0.55)
        text_img = make_text_pill(pov_text, W, font_size)
        pill_h = text_img.height
        text_y = top_h - pill_h // 2
        text_clip = (ImageClip(np.array(text_img))
                     .with_duration(duration)
                     .with_position((0, text_y)))

        set_status(job_id, "Assemblage…", 0.62)
        bg = ColorClip(size=(W, H), color=(0, 0, 0)).with_duration(duration)
        final = CompositeVideoClip([bg, sc, mc_raw, text_clip], size=(W, H))

        set_status(job_id, "Export vidéo…", 0.68)
        final.write_videofile(tmp_path, fps=30, codec="libx264", audio=False, logger=None)

        set_status(job_id, "Mixage audio…", 0.88)
        _mux_audio(tmp_path, streamer_path, sfx_list, out_path, duration)
        os.remove(tmp_path)

        jobs[job_id].update({"progress": 1.0, "message": "Reel généré !", "done": True})

    except Exception as e:
        traceback.print_exc()
        jobs[job_id].update({"done": True, "error": str(e), "message": f"Erreur : {e}"})
    finally:
        for f in [streamer_path, model_path] + [s["path"] for s in sfx_list]:
            try:
                os.remove(f)
            except Exception:
                pass
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _mux_audio(video_path, streamer_path, sfx_list, out_path, duration):
    """Mix streamer audio + SFX via ffmpeg filter_complex, then mux with video."""
    inputs = [
        FFMPEG, "-y",
        "-i", video_path,      # 0:v
        "-i", streamer_path,   # 1:a (streamer audio)
    ]
    for sfx in sfx_list:
        inputs += ["-i", sfx["path"]]

    n_audio = 1 + len(sfx_list)

    if not sfx_list:
        # Simple mux — no re-encode of audio needed
        subprocess.run(
            inputs + [
                "-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", out_path,
            ],
            check=True, capture_output=True
        )
        return

    # Build filter_complex to delay & mix each SFX at its timestamp
    filter_parts = []
    filter_parts.append("[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[base]")

    mix_inputs = "[base]"
    for idx, sfx in enumerate(sfx_list):
        delay_ms = int(sfx["time"] * 1000)
        stream = idx + 2  # inputs 2, 3, 4…
        label = f"[sfx{idx}]"
        filter_parts.append(
            f"[{stream}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}{label}"
        )
        mix_inputs += label

    total = 1 + len(sfx_list)
    filter_parts.append(f"{mix_inputs}amix=inputs={total}:duration=first:dropout_transition=0[aout]")

    filter_complex = ";".join(filter_parts)

    cmd = inputs + [
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def apply_zoom_effects(clip, zoom_times, zoom_max=0.18, effect_duration=1.4):
    """Smooth zoom-in/out on the model clip at given timestamps."""
    half = effect_duration / 2

    def zoom_factor(t):
        best = 0.0
        for zt in zoom_times:
            dt = abs(t - zt)
            if dt < half:
                f = 0.5 * (1 - math.cos(math.pi * (1 - dt / half)))
                best = max(best, zoom_max * f)
        return 1.0 + best

    def filter_frame(get_frame, t):
        frame = get_frame(t)
        z = zoom_factor(t)
        if z <= 1.001:
            return frame
        h, w = frame.shape[:2]
        new_w = int(w / z)
        new_h = int(h / z)
        x1 = (w - new_w) // 2
        y1 = (h - new_h) // 2
        cropped = frame[y1:y1 + new_h, x1:x1 + new_w]
        img = Image.fromarray(cropped).resize((w, h), Image.LANCZOS)
        return np.array(img)

    return clip.transform(filter_frame)


def crop_fill(clip, tw, th):
    cw, ch = clip.size
    scale = max(tw / cw, th / ch)
    nw, nh = int(cw * scale), int(ch * scale)
    clip = clip.resized((nw, nh))
    x1, y1 = (nw - tw) // 2, (nh - th) // 2
    return clip.cropped(x1=x1, y1=y1, x2=x1 + tw, y2=y1 + th)


def make_text_pill(text, canvas_width, font_size):
    font = None
    for fp in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
    ]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                pass
    if not font:
        font = ImageFont.load_default()

    probe = Image.new("RGBA", (1, 1))
    dp = ImageDraw.Draw(probe)
    lines = wrap_text(text, dp, font, canvas_width - 160)
    line_h = font_size + 14
    total_h = len(lines) * line_h
    pad_x, pad_y = 52, 22
    max_lw = max(dp.textbbox((0, 0), l, font=font)[2] for l in lines)
    pill_w = min(canvas_width - 80, max_lw + pad_x * 2)
    pill_h = total_h + pad_y * 2

    img = Image.new("RGBA", (canvas_width, pill_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pill_x = (canvas_width - pill_w) // 2
    draw.rounded_rectangle([pill_x, 0, pill_x + pill_w, pill_h], radius=32, fill=(255, 255, 255, 245))

    y = pad_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = pill_x + (pill_w - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=(15, 15, 15, 255))
        y += line_h
    return img


def wrap_text(text, draw, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


if __name__ == "__main__":
    import webbrowser
    print("\n🎬  Reaction Reel Generator")
    print("─" * 40)
    print("➡  Ouvre dans ton navigateur : http://localhost:5050")
    print("   (Ctrl+C pour arrêter)\n")
    webbrowser.open("http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
