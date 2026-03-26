# bg_server.py — Local Image Generation Server + ngrok Tunnel
# รันบนเครื่องตัวเอง: python bg_server.py
# ════════════════════════════════════════════

import torch, base64, io, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from diffusers import StableDiffusionPipeline
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── โหลด model ──────────────────────────────
print("⏳ Loading SD v1.5 on GPU...")
pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch.float16,
    safety_checker=None,
    requires_safety_checker=False
)
pipe = pipe.to("xpu") # NVIDIA: cuda | INTEL: xpu
pipe.enable_attention_slicing()
print("✅ Model ready!")


@app.route('/generate', methods=['POST'])
def generate():
    data   = request.get_json(silent=True) or {}
    # รับ prompt ที่ app.py สร้างมาแล้วโดยตรง ไม่ต่อเพิ่ม
    prompt = data.get('prompt', 'anime visual novel background')

    try:
        with torch.inference_mode():
            image = pipe(
                prompt,
                negative_prompt=(
                    "people, characters, person, human, ugly, blurry, "
                    "low quality, watermark, text, logo"
                ),
                width=512, height=512,
                num_inference_steps=20,
                guidance_scale=7.5,
            ).images[0]

        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        return jsonify({'image': f'data:image/png;base64,{img_b64}'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    ngrok_token = os.getenv('NGROK_TOKEN')

    if ngrok_token:
        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = ngrok_token
            tunnel = ngrok.connect(5001, "http")
            url = tunnel.public_url
            print(f"\n{'='*55}")
            print(f"🌐 BG Server URL (ngrok): {url}")
            print(f"📋 copy ไปใส่ใน environment variable:")
            print(f"   BG_SERVER={url}/generate")
            print(f"{'='*55}\n")
        except ImportError:
            print("❌ ไม่พบ pyngrok — ติดตั้งด้วย: pip install pyngrok")
        except Exception as e:
            print(f"❌ ngrok error: {e}")
    else:
        print("⚠️  ไม่พบ NGROK_TOKEN ใน .env — รันแบบ local only (port 5001)")

    from waitress import serve
    print("🚀 bg_server running on port 5001 (waitress)")
    serve(app, host='127.0.0.1', port=5001,
          channel_timeout=700,
          recv_bytes=65536)