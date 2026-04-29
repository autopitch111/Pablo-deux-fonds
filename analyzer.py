"""AI analysis — OpenAI GPT-4o vision"""
import base64, json, os
from typing import Optional
import cv2
from openai import OpenAI

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client

def _encode_frame(path):
    with open(path,"rb") as f:
        return base64.standard_b64encode(f.read()).decode()

def extract_frame(video_path, timestamp=2.0):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * timestamp))
    ret, frame = cap.read()
    if not ret:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0); ret, frame = cap.read()
    cap.release()
    out = video_path + "_tmp.jpg"
    cv2.imwrite(out, frame)
    return out

def analyze_video(video_path):
    fp = extract_frame(video_path, 2.0)
    b64 = _encode_frame(fp)
    os.remove(fp)
    r = _get_client().chat.completions.create(
        model="gpt-4o",
        max_tokens=300,
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text":'Tu es expert TikTok/Reels. Analyse cette frame et réponds UNIQUEMENT en JSON:\n{"hook":"Hook viral max 8 mots EN MAJUSCULES","topic":"sujet en 3 mots","description":"1 phrase"}'}
        ]}]
    )
    txt = r.choices[0].message.content.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(txt)
    except:
        return {"hook":"REGARDE JUSQU'AU BOUT !","topic":"contenu viral","description":"Vidéo virale"}

def pick_best_meme(memes_dir, video_info):
    memes = [f for f in os.listdir(memes_dir) if f.lower().endswith((".mp4",".mov",".avi",".mkv"))]
    if not memes: return None
    thumbs = []
    for mf in memes:
        try:
            fp = extract_frame(os.path.join(memes_dir, mf), 1.0)
            thumbs.append((mf, fp))
        except: pass
    if not thumbs: return memes[0]

    content = [{"type":"text","text":f"Vidéo sur: {video_info.get('topic','')}. {video_info.get('description','')}\nChoisis le mème le plus drôle/pertinent. Réponds UNIQUEMENT avec le numéro."}]
    for i,(fn,fp) in enumerate(thumbs,1):
        b64 = _encode_frame(fp); os.remove(fp)
        content += [{"type":"text","text":f"Mème {i}: {fn}"},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]

    r = _get_client().chat.completions.create(model="gpt-4o", max_tokens=5, messages=[{"role":"user","content":content}])
    try:
        idx = int(r.choices[0].message.content.strip()) - 1
        return thumbs[idx][0]
    except:
        return thumbs[0][0]
