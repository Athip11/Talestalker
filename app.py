# ════════════════════════════════════════════════
# app.py — Flask Server
# ════════════════════════════════════════════════
import requests, os, threading, uuid, time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from game.state import GameState

# ── Init app ─────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static')
CORS(app)

# BG_SERVER: ตอน local ใช้ localhost, ตอน deploy ใส่ ngrok URL ใน env var
BG_SERVER = os.getenv('BG_SERVER', 'http://localhost:5001/generate')

# ── In-memory stores ─────────────────────────────────────────────────
sessions:  dict[str, dict]  = {}   # sid → {gs: GameState, last_seen: float}
bg_jobs:   dict[str, dict]  = {}   # job_id → {status, image, created_at}

SESSION_TTL = 3600      # ลบ session ที่ไม่ active > 1 ชั่วโมง
BG_JOB_TTL  = 1800      # ลบ bg job ที่เก่า > 30 นาที


# ── Background cleanup thread ────────────────────────────────────────
def _cleanup_loop():
    while True:
        time.sleep(300)   # ทำงานทุก 5 นาที
        now = time.time()

        expired_sessions = [
            sid for sid, v in list(sessions.items())
            if now - v['last_seen'] > SESSION_TTL
        ]
        for sid in expired_sessions:
            sessions.pop(sid, None)

        expired_jobs = [
            jid for jid, v in list(bg_jobs.items())
            if now - v.get('created_at', 0) > BG_JOB_TTL
        ]
        for jid in expired_jobs:
            bg_jobs.pop(jid, None)

        if expired_sessions or expired_jobs:
            print(f'[cleanup] removed {len(expired_sessions)} sessions, '
                  f'{len(expired_jobs)} bg jobs')

threading.Thread(target=_cleanup_loop, daemon=True).start()


# ── Helpers ───────────────────────────────────────────────────────────
def _get_or_create_session(sid: str, force_new: bool = False) -> GameState:
    if sid not in sessions or force_new:
        sessions[sid] = {'gs': GameState(), 'last_seen': time.time()}
    else:
        sessions[sid]['last_seen'] = time.time()
    return sessions[sid]['gs']


# ── Routes ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/motion_viewer')
def motion_viewer():
    return send_from_directory('.', 'motion_viewer.html')


@app.route('/api/start', methods=['POST'])
def start():
    data      = request.get_json(silent=True) or {}
    sid       = data.get('session_id', 'default')
    force_new = data.get('force_new', False)

    gs = _get_or_create_session(sid, force_new)
    ep = gs.current_ep()

    return jsonify({
        'episode'      : gs.current_ep_id,
        'episode_label': gs.episode_label(),
        'intro_text'   : ep['fon_intro'],
        'ap'           : gs.ap,
        'tp'           : gs.tp,
        'turn'         : gs.turn,
        'context'      : ep.get('context', ''),
        'narrative'    : ep['narrative'],
        'hint'         : ep['hint'],
        'bg_prompt'    : ep.get('bg_prompt', ''),
    })


@app.route('/api/talk', methods=['POST'])
def talk():
    data = request.get_json(silent=True) or {}
    sid  = data.get('session_id', 'default')
    text = data.get('text', '').strip()

    if not text:
        return jsonify({'error': 'empty text'}), 400

    gs     = _get_or_create_session(sid)
    result = gs.process_turn(text)
    return jsonify(result)


@app.route('/api/bg', methods=['POST'])
def generate_bg():
    data   = request.get_json(silent=True) or {}
    prompt = data.get('prompt', 'rainy night atmospheric')

    full_prompt = (
        f"{prompt}, visual novel background, anime style, "
        "masterpiece, best quality, highly detailed, "
        "no characters, no people, no text, "
        "cinematic lighting, atmospheric, 8k"
    )

    job_id = str(uuid.uuid4())[:8]
    bg_jobs[job_id] = {
        'status'    : 'pending',
        'image'     : None,
        'created_at': time.time()
    }

    def run():
        try:
            resp = requests.post(BG_SERVER, json={'prompt': full_prompt}, timeout=600)
            if resp.status_code == 200:
                bg_jobs[job_id].update({'status': 'done', 'image': resp.json().get('image')})
            else:
                bg_jobs[job_id].update({'status': 'error'})
        except Exception as e:
            print(f'BG job {job_id} failed: {e}')
            bg_jobs[job_id].update({'status': 'error'})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'job_id': job_id})   # ตอบทันที ไม่รอ GPU


@app.route('/api/bg/status/<job_id>', methods=['GET'])
def bg_status(job_id):
    job = bg_jobs.get(job_id)
    if not job:
        return jsonify({'status': 'not_found'}), 404
    return jsonify({'status': job['status'], 'image': job['image']})


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=5000, use_reloader=False)