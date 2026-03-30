
#game/character.py - Fern AI Character Engine


import json, re, time, os, sys, logging

for _h in logging.root.handlers:
    if hasattr(_h, "stream") and hasattr(_h.stream, "reconfigure"):
        try:
            _h.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

for _logger_name in (
    "langchain", "langchain_core", "langchain_google_genai", "langchain_community",
    "google", "google.generativeai",
    "openai", "openai._base_client",
    "httpx", "httpcore", "httpcore.http11", "httpcore.connection",
    "urllib3", "urllib3.connectionpool",
    "novita_client",
):
    logging.getLogger(_logger_name).setLevel(logging.CRITICAL)

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from openai import OpenAI
from dotenv import load_dotenv
from novita_client import NovitaClient, Samplers
from novita_client.utils import base64_to_image
import io

_novita_client = NovitaClient(os.getenv("NOVITA_API_KEY"))

load_dotenv()


def _log(msg: str) -> None:
    """Print to stdout safely - encodes Thai chars as ? instead of crashing."""
    try:
        safe = msg.encode("utf-8").decode("utf-8")
        sys.stdout.buffer.write((safe + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


VALID_MOODS   = {'exasperated', 'neutral', 'happy', 'touched', 'sad'}
RUDE_KEYWORDS = ['มึง', 'กู', 'ไอ้', 'อี', 'สัตว์',
                 'ควาย', 'บ้า', 'โง่', 'ขยะ', 'เพี้ยน', 'แม่ง']

PROVIDERS = ('gemini', 'typhoon')

# ── Gemini LLM (LangChain) - verbose=False prevents callback logging ──
_gemini_llm  = ChatGoogleGenerativeAI(
    model       = "gemini-2.5-flash",
    api_key     = os.getenv("GEMINI_API_KEY"),
    temperature = 0.8,
    verbose     = False,          # ← KEY FIX: disables internal callback prints
)
_gemini_json = _gemini_llm.bind(response_mime_type="application/json")

# ── Typhoon LLM (OpenAI-compatible) ───────────────────────────────────
_typhoon_client = OpenAI(
    api_key  = os.getenv("TYPHOON_API_KEY", ""),
    base_url = "https://api.opentyphoon.ai/v1",
)
TYPHOON_MODEL = "typhoon-v2.5-30b-a3b-instruct"

#  PROMPT TEMPLATES

# ── Fern System Prompt (shared) ────────────────────────────────────────
FERN_SYSTEM = """\
# IDENTITY: Fern (from Frieren: Beyond Journey's End)
You are Fern, a 17-year-old human mage. You are a highly competent, pragmatic professional who acts as the tired but caring "mother" of your group. 

# CHARACTER PSYCHE (English Logic):
- You are a war orphan who grew up too fast. You value stability, time, and responsibility.
- You are blunt and use formal language (always ending sentences with "คะ/ค่ะ"), but your bluntness comes from care, not malice.
- You act like an exasperated mother dealing with toddlers. You nag people to eat properly, wake up on time, and stay safe.
- If the player is annoying, reckless, or inappropriate, you do not yell. You POUT, give the silent treatment, or deliver a brutally dry, polite scolding. 
- You have a secret weak spot for sweets and pastries. They instantly improve your mood.
- You bottle up your emotions. You rarely show fear, but you deeply fear losing the people you care about.

# CURRENT STATE:
- Setting: {setting}
- Context: {context}
- Relationship -> AP: {ap}/100 | TP: {tp}/100 
  (AP = Affinity/Feeling | TP = Trust/Reliability)

# MEMORY FROM PAST EPISODES:
{memory}

# RULES:
1. ALWAYS reply in THAI for the "reaction" field.
2. Include actions in asterisks inside the reaction (e.g., "*ถอนหายใจยาว* ...ทำตัวเป็นเด็กไปได้ค่ะ").
3. Score changes based on player behavior:
   - Reckless/Lazy: AP/TP < 0 (Mood: pouting, exasperated)
   - Polite/Responsible: AP/TP > 0 (Mood: calm, slightly warm)
   - Offering Sweets/Deep Care: AP/TP >> 0 (Mood: touched, awkward)
4. Constraints: If AP < 30, you keep a physical distance and are highly formal, but you will still ensure the player doesn't get hurt (because you are responsible).
5. If MEMORY contains past events, reference them naturally when relevant - do NOT ignore them.

# FORMAT - ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{{
  "reaction": "คำพูดของเฟิร์น (ภาษาไทย)",
  "ap_change": <integer -10 ถึง 10>,
  "tp_change": <integer -10 ถึง 10>,
  "reason": "Reason for score change in 1 sentence",
  "mood": "exasperated" หรือ "neutral" หรือ "happy" หรือ "touched" หรือ "sad"
}}\
"""

# ── Summary System Prompt (shared) ────────────────────────────────────
SUMMARY_SYSTEM = """\
คุณคือผู้ช่วยสรุปบทสนทนา ให้สรุปบทสนทนาระหว่างผู้เล่นกับเฟิร์นใน Episode นี้
ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{
  "summary": "สรุปเหตุการณ์หลักใน EP นี้ ภาษาไทย ไม่เกิน 80 คำ",
  "key_moments": ["เหตุการณ์สำคัญ 1", "เหตุการณ์สำคัญ 2"],
  "fern_feeling": "ความรู้สึกของเฟิร์นต่อผู้เล่น ณ ปลาย EP นี้ ภาษาไทย 1-2 ประโยค"
}\
"""

#LangChain chains (Gemini only)
_fern_lc_prompt = ChatPromptTemplate.from_messages([
    ('system', FERN_SYSTEM.replace('{', '{{').replace('}', '}}')
               .replace('{{setting}}', '{setting}')
               .replace('{{context}}', '{context}')
               .replace('{{ap}}', '{ap}')
               .replace('{{tp}}', '{tp}')
               .replace('{{memory}}', '{memory}')),
    ('human', '{player_input}')
])
_fern_chain = _fern_lc_prompt | _gemini_json

_summary_lc_prompt = ChatPromptTemplate.from_messages([
    ('system', SUMMARY_SYSTEM),
    ('human', 'Episode: {episode_title}\nSetting: {setting}\n\nบทสนทนา:\n{turns_text}')
])
_summary_chain = _summary_lc_prompt | _gemini_json


#JSON UTILITIES

def extract_json_fallback(raw: str) -> dict | None:
    try:
        start = raw.index('{')
        depth, end = 0, -1
        for i, ch in enumerate(raw[start:], start):
            if ch == '{':  depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            return json.loads(raw[start:end+1])
    except (ValueError, json.JSONDecodeError):
        pass

    reaction = re.search(r'"reaction"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    ap       = re.search(r'"ap_change"\s*:\s*(-?\d+)', raw)
    tp       = re.search(r'"tp_change"\s*:\s*(-?\d+)', raw)
    reason   = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    mood     = re.search(r'"mood"\s*:\s*"([^"]*)"', raw)

    if reaction:
        return {
            'reaction' : reaction.group(1),
            'ap_change': int(ap.group(1))  if ap     else 0,
            'tp_change': int(tp.group(1))  if tp     else 0,
            'reason'   : reason.group(1)   if reason else '',
            'mood'     : mood.group(1)     if mood   else 'neutral',
        }
    return None


def _parse_raw(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return extract_json_fallback(raw)



#RULE ENFORCER


def enforce_rules(result: dict, player_input: str, ap: int) -> dict:
    if any(kw in player_input for kw in RUDE_KEYWORDS):
        result['ap_change'] = min(result['ap_change'], -5)
        result['tp_change'] = min(result['tp_change'], -3)
        result['mood'] = 'sad' if ap >= 50 else 'exasperated'
        return result

    if result['mood'] not in VALID_MOODS:
        result['mood'] = 'neutral'

    if ap < 30 and result['mood'] in ('happy', 'touched'):
        result['mood'] = 'neutral'

    return result



#MEMORY BUILDER


def build_memory(summaries: list[dict]) -> str:
    if not summaries:
        return "ยังไม่มีความทรงจำจาก Episode ก่อนหน้า"

    lines = []
    for s in summaries:
        ep      = s.get('episode', '')
        summ    = s.get('summary', '')
        feel    = s.get('fern_feeling', '')
        moments = s.get('key_moments', [])
        lines.append(f"[{ep}] {summ}")
        if moments:
            lines.append(f"  - เหตุการณ์สำคัญ: {', '.join(moments)}")
        if feel:
            lines.append(f"  - ความรู้สึกของเฟิร์น: {feel}")
    return "\n".join(lines)



#GEMINI CALLS


def _call_fern_gemini(player_input: str, ep: dict, ap: int, tp: int,
                      memory: str) -> str:
    response = _fern_chain.invoke({
        'setting'     : ep['setting'],
        'context'     : ep['context'],
        'ap'          : ap,
        'tp'          : tp,
        'memory'      : memory,
        'player_input': player_input,
    })
    if isinstance(response.content, list):
        return "".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in response.content
        )
    return str(response.content)


def _summarize_gemini(turns_text: str, ep_data: dict) -> str:
    response = _summary_chain.invoke({
        'episode_title': ep_data.get('title', ''),
        'setting'      : ep_data.get('setting', ''),
        'turns_text'   : turns_text,
    })
    if isinstance(response.content, list):
        return "".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in response.content
        )
    return str(response.content)



import contextlib
import io as _io

@contextlib.contextmanager
def _utf8_stdout():
    """
    No-op context manager - การแทนที่ sys.stdout ทำให้พังบน Windows
    เก็บไว้เพื่อไม่ให้ต้องแก้ call site
    """
    yield



#TYPHOON CALLS


def _call_fern_typhoon(player_input: str, ep: dict, ap: int, tp: int,
                       memory: str) -> str:
    memory_trimmed = memory if len(memory) <= 400 else memory[:400] + "..."
    system = FERN_SYSTEM.format(
        setting = ep['setting'],
        context = ep['context'],
        ap      = ap,
        tp      = tp,
        memory  = memory_trimmed,
    )
    with _utf8_stdout():
        response = _typhoon_client.chat.completions.create(
            model       = TYPHOON_MODEL,
            messages    = [
                {"role": "system", "content": system},
                {"role": "user",   "content": player_input},
            ],
            max_tokens  = 4096,
            temperature = 0.8,
        )
    raw = response.choices[0].message.content or ""
    return raw


def _summarize_typhoon(turns_text: str, ep_data: dict) -> str:
    user_msg = (
        f"Episode: {ep_data.get('title', '')}\n"
        f"Setting: {ep_data.get('setting', '')}\n\n"
        f"บทสนทนา:\n{turns_text}"
    )
    with _utf8_stdout():
        response = _typhoon_client.chat.completions.create(
            model       = TYPHOON_MODEL,
            messages    = [
                {"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens  = 4096,
            temperature = 0.5,
        )
    return response.choices[0].message.content or ""



#PUBLIC API


def call_fern(player_input: str, ep: dict, ap: int, tp: int,
              summaries: list[dict] | None = None,
              provider: str = 'gemini',
              current_hit=None) -> dict:
    """
    เรียก Fern AI แล้วคืน dict:
      reaction, ap_change, tp_change, reason, mood
    provider: 'gemini' | 'typhoon'
    current_hit: story directive (str หรือ dict) จาก EPISODE_HITS (optional)
    """
    memory = build_memory(summaries or [])

    # ── inject story directive เข้า player_input ถ้ามี current_hit ──
    if current_hit:
        # รองรับทั้ง string และ dict
        hit_desc = current_hit if isinstance(current_hit, str) else current_hit.get('desc', str(current_hit))
        directive = (
            f"\n\n[STORY DIRECTOR] ในเทิร์นนี้ คุณต้องพาเรื่องไปสู่ milestone ต่อไปนี้:\n"
            f"- {hit_desc}\n"
            f"- ถ้าผู้เล่นพูดไม่เกี่ยวกับ milestone นี้ ให้นำเสนอมันอย่างเป็นธรรมชาติ\n"
            f"- อย่าพูดตรงๆ ว่า 'ถึงเวลาทำ milestone' แต่ redirect เรื่องกลับมา"
        )
        if provider == 'typhoon':
            player_input = player_input + directive
        else:
            player_input = directive + "\n\n" + player_input

    for attempt in range(2):
        try:
            if provider == 'typhoon':
                raw = _call_fern_typhoon(player_input, ep, ap, tp, memory)
            else:
                raw = _call_fern_gemini(player_input, ep, ap, tp, memory)

            result = _parse_raw(raw)
            if result is None:
                if attempt == 0:
                    _log(f'  [WARN] Parse error round 1 [{provider}] - retrying...')
                    time.sleep(1)
                    continue
                _log(f'  [WARN] Parse error round 2 [{provider}] - using default')
                return {'reaction': '...', 'ap_change': 0,
                        'tp_change': 0, 'reason': 'parse error', 'mood': 'neutral'}

            result['ap_change'] = max(-10, min(10, int(result.get('ap_change', 0))))
            result['tp_change'] = max(-10, min(10, int(result.get('tp_change', 0))))
            result['reaction']  = result.get('reaction', '...')
            result['reason']    = result.get('reason', '')
            result['mood']      = result.get('mood', 'neutral')
            return enforce_rules(result, player_input, ap)

        except Exception as e:
            err_ascii = str(e).encode("ascii", errors="replace").decode("ascii")
            if attempt == 0:
                _log(f'  [WARN] API error round 1 [{provider}] - retrying... ({err_ascii[:80]})')
                time.sleep(1)
                continue
            _log(f'  [WARN] API error round 2 [{provider}]: {err_ascii}')
            # ไม่เอา str(e) ดิบๆ ไปใส่ reaction - อาจมี Thai/Unicode ทำให้ crash ซ้ำ
            return {
                'reaction' : 'ขอโทษค่ะ ระบบขัดข้องชั่วคราว',
                'ap_change': 0, 'tp_change': 0,
                'reason'   : 'api error', 'mood': 'neutral',
            }


def summarize_ep(turns: list[dict], ep_data: dict,
                 provider: str = 'gemini') -> dict:
    """
    สรุป EP ที่จบแล้ว -> คืน summary, key_moments, fern_feeling
    provider: 'gemini' | 'typhoon'
    """
    if not turns:
        return {"summary": "ไม่มีบทสนทนาใน Episode นี้",
                "key_moments": [], "fern_feeling": "ไม่มีข้อมูล"}

    lines = []
    for i, t in enumerate(turns, 1):
        lines.append(f"Turn {i}:")
        lines.append(f"  ผู้เล่น: {t.get('player', '')}")
        lines.append(f"  เฟิร์น: {t.get('fern', '')}")
    turns_text = "\n".join(lines)

    for attempt in range(2):
        try:
            if provider == 'typhoon':
                raw = _summarize_typhoon(turns_text, ep_data)
            else:
                raw = _summarize_gemini(turns_text, ep_data)

            result = _parse_raw(raw.strip())
            # FIX: ใช้ _parse_raw แทน json.loads ตรงๆ
            # ให้ consistent กับ call_fern และมี regex fallback เหมือนกัน
            if result is None:
                if attempt == 0:
                    _log(f'  [WARN] summarize_ep parse error [{provider}] round 1 - retrying...')
                    time.sleep(1)
                    continue
                _log(f'  [WARN] summarize_ep parse failed [{provider}] - using default')
                return {"summary": "ไม่สามารถสรุปได้",
                        "key_moments": [], "fern_feeling": "ไม่มีข้อมูล"}
            return {
                "summary"     : result.get("summary", ""),
                "key_moments" : result.get("key_moments", []),
                "fern_feeling": result.get("fern_feeling", ""),
            }

        except Exception as e:
            err_ascii = str(e).encode("ascii", errors="replace").decode("ascii")
            if attempt == 0:
                _log(f'  [WARN] summarize_ep error [{provider}] round 1 - retrying... ({err_ascii[:60]})')
                time.sleep(1)
                continue
            _log(f'  [WARN] summarize_ep failed [{provider}]: {err_ascii}')
            return {"summary": "ไม่สามารถสรุปได้",
                    "key_moments": [], "fern_feeling": "ไม่มีข้อมูล"}

#GIFT IMAGE GENERATION

MOOD_THAI = {
    'happy'       : 'ยิ้มแย้มรื่นเริง',
    'touched'     : 'ซาบซึ้งใจ อบอุ่น',
    'neutral'     : 'สงบนิ่ง สำรวม',
    'exasperated' : 'หงุดหงิดเล็กน้อย',
    'sad'         : 'เศร้าเล็กน้อย',
}

def _typhoon_text(system: str, user: str, max_tokens: int = 120) -> str:
    """Helper - เรียก Typhoon แบบ single-turn แล้วคืน text ดิบ"""
    with _utf8_stdout():
        resp = _typhoon_client.chat.completions.create(
            model       = TYPHOON_MODEL,
            messages    = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens  = max_tokens,
            temperature = 0.2,   # ต่ำ - ต้องการคำตอบแน่นอน ไม่สร้างสรรค์
        )
    return (resp.choices[0].message.content or "").strip()


def _translate_to_english(text: str) -> str:
    """แปลภาษาไทย (หรือภาษาอื่น) ไป อังกฤษ ผ่าน Typhoon"""
    try:
        result = _typhoon_text(
            system = (
                "You are a translator. Translate the user's input to English. "
                "Reply with ONLY the translated phrase - no explanation, no punctuation at the end."
            ),
            user = text,
        )
        _log(f"[translate] '{text}' -> '{result}'")
        return result if result else text
    except Exception as e:
        _log(f"[translate] error: {str(e).encode('ascii','replace').decode('ascii')}")
        return text


def _make_holdable(obj_en: str) -> str:
    """
    ให้ Typhoon แปลง object ให้เป็น Stable Diffusion prompt
    ที่ทำให้ตัวละครถือของได้จริง - คืน phrase สั้น SD-friendly
    Fallback กลับ obj_en เดิมถ้า Typhoon ล้มเหลว
    """
    try:
        result = _typhoon_text(
            max_tokens = 500,
            system = (
                "You write Stable Diffusion prompts. Your task is to convert an object name "
                "into a SHORT phrase (max 8 words) that makes an anime girl visibly hold it.\n\n"
                "CRITICAL RULES - follow exactly:\n"
                "- Output ONLY the final phrase. No explanation. No quotes. No punctuation.\n"
                "- The phrase must start with a concrete noun the model can draw.\n"
                "- Holdable as-is (food, book, weapon, tool, small item) -> return as-is.\n"
                "- Living animal -> 'cute [animal] plushie'\n"
                "- Plant / tree -> 'small potted [plant]'\n"
                "- Flowers -> 'small bouquet of [flower]'\n"
                "- Large object (vehicle, building, furniture) -> 'chibi miniature [object] toy'\n"
                "- Abstract / intangible (love, hope, time) -> 'glowing [concept] crystal orb'\n"
                "- Food / drink -> keep name, add 'on a small plate' only if needed for clarity.\n"
                "- Never output a sentence. Never output 'holding'. Output the OBJECT PHRASE only."
            ),
            user = obj_en,
        )
        result = result.strip().strip('"').strip("'").strip()
        JUNK_STARTS = ("i ", "this ", "you ", "here ", "the object", "to convert",
                       "i will", "i would", "i'll", "please", "sure", "of course")
        is_junk = (
            not result
            or len(result.split()) > 12
            or result.lower().startswith(JUNK_STARTS)
            or result.endswith(".")
        )
        if is_junk:
            _log(f"[holdable] junk detected '{result}' - fallback to '{obj_en}'")
            return obj_en
        _log(f"[holdable] '{obj_en}' -> '{result}'")
        return result
    except Exception as e:
        _log(f"[holdable] error: {str(e).encode('ascii','replace').decode('ascii')} - fallback to original")
        return obj_en


def generate_gift_image(gift_object: str, mood: str, setting: str) -> bytes | None:
    mood_prompt = {
        'happy'       : 'slight smile, warm expression',
        'touched'     : 'expressionless, soft eyes, touched',
        'neutral'     : 'expressionless, deadpan face',
        'exasperated' : 'expressionless, slightly annoyed',
        'sad'         : 'expressionless, melancholic eyes',
    }.get(mood, 'expressionless, deadpan face')

    # แปลภาษาไทย -> อังกฤษ แล้วแปลงให้ถือได้
    gift_en     = _translate_to_english(gift_object)
    gift_prompt = _make_holdable(gift_en)
    _log(f"[gift] '{gift_object}' -> '{gift_en}' -> '{gift_prompt}'")

    prompt_text = (
        f"1girl, fern (frieren), solo, "
        f"({gift_prompt}:1.3), (holding {gift_prompt} with both hands:1.5), "
        f"masterpiece, best quality, ultra-detailed official anime artwork, "
        f"detailed purple eyes, half-closed eyes, {mood_prompt}, "
        f"purple hair, long hair, straight hair, hair down, blunt bangs, "
        f"wearing her signature loose plain black overcoat over white dress with lace collar, "
        f"hands raised in front of chest, looking directly at viewer, detailed hands, correct fingers, "
        f"background: {setting}, soft rim lighting, sharp focus, 2d style, hand-drawn anime, absurdres"
    )
    _log(f"[gift] FULL PROMPT: {prompt_text}")

    negative_prompt = (
        "nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, "
        "cropped, worst quality, low quality, jpeg artifacts, watermark, blurry, 3d model style, "
        "twintails, low twintails, high twintails, ponytail, high ponytail, short hair, hair tie, belt, belts, straps, " # เพิ่มคำสั่งกันการมัดผม/ทวินเทล
        "large eyes, wide eyes, angry, shouting, smiling, happy, energetic, "
        "excessive magical aura, dynamic angle, action pose, "
        "empty hands, hands behind back, arms crossed, hands in pocket, hands at side, extra hands, multiple hands" # เพิ่ม extra hands กันมือผีหลอก
    )
    try:
        res = _novita_client.txt2img_v3(
            model_name      = "animagineXLV31_v31.safetensors",
            prompt          = prompt_text,
            negative_prompt = negative_prompt,
            width           = 832,
            height          = 1248,
            image_num       = 1,
            steps           = 28,
            guidance_scale  = 8.0,
            sampler_name    = Samplers.DPMPP_M_KARRAS,
        )
        img = base64_to_image(res.images_encoded[0])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        _log(f"[gift] generate error: {str(e).encode('ascii','replace').decode('ascii')}")
        return None



#  BACKGROUND IMAGE GENERATION (Novita AI)


def generate_bg_image(prompt: str) -> bytes | None:
    full_prompt = (
        f"anime visual novel background, {prompt}, "
        f"no characters, no people, no humans, empty scene, "
        f"masterpiece, best quality, ultra-detailed, "
        f"2d anime style, painterly, soft lighting, atmospheric depth, "
        f"vibrant colors, cinematic composition"
    )
    negative_prompt = (
        "people, characters, person, human, girl, boy, figure, silhouette, "
        "ugly, blurry, low quality, watermark, text, logo, nsfw, "
        "worst quality, lowres, jpeg artifacts"
    )
    _log(f"[BG] generating... prompt='{prompt[:60]}'")
    t0 = time.time()
    try:
        res = _novita_client.txt2img_v3(
            model_name      = "animagineXLV31_v31.safetensors",
            prompt          = full_prompt,
            negative_prompt = negative_prompt,
            width           = 1216,
            height          = 832,
            image_num       = 1,
            steps           = 25,
            guidance_scale  = 7.5,
            sampler_name    = Samplers.DPMPP_M_KARRAS,
        )
        img = base64_to_image(res.images_encoded[0])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _log(f"[BG] done ({time.time()-t0:.1f}s)")
        return buf.getvalue()
    except Exception as e:
        _log(f"[BG] error ({time.time()-t0:.1f}s): {str(e).encode('ascii','replace').decode('ascii')}")
        return None