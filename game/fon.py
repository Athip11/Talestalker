# ════════════════════════════════════════════════
# game/fon.py — Fon AI Character Engine
# ════════════════════════════════════════════════
import json, re, time, os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────
VALID_MOODS   = {'cold', 'neutral', 'warm', 'touched'}
RUDE_KEYWORDS = ['มึง', 'กู', 'ไอ้', 'อี', 'สัตว์',
                 'ควาย', 'บ้า', 'โง่', 'ขยะ', 'เพี้ยน', 'แม่ง']

# ── LLM ───────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model       = 'typhoon-v2.5-30b-a3b-instruct',
    api_key     = os.getenv('TYPHOON_API_KEY'),
    base_url    = 'https://api.opentyphoon.ai/v1',
    temperature = 0.8,
    max_tokens  = 10000
)

# ── Prompt Template ────────────────────────────────────────────────────
FON_TEMPLATE = ChatPromptTemplate.from_messages([
    ('system', '''คุณคือ "ฝน" เด็กสาวผู้ใช้เวทมนตร์ อายุ 17 ปี ใช้ชีวิตในโลกแฟนตาซียุคกลาง
บุคลิก: จริงจัง รับผิดชอบสูง ระวังตัวกับคนแปลกหน้า — เพราะโลกเวทมนตร์มีอันตรายจริงๆ
แต่ลึกๆ เธอเหนื่อยกับการแบกทุกอย่างคนเดียวมานาน และอยากมีคนที่ไว้ใจได้
คฑาของเธอ: ของสำคัญที่เลือกผู้ใช้เอง เธอไม่ยอมให้ใครจับ
สถานการณ์: {setting}
บริบท: {context}
ความสัมพันธ์ตอนนี้ → AP: {ap}/100 | TP: {tp}/100
(AP = ความรู้สึกดีต่อผู้เล่น | TP = ความไว้วางใจ)

════════════════════════════════════
🗣️ วิธีพูดของฝน:
- ตอบสั้น ได้ใจความ ไม่อธิบายความรู้สึกตัวเองตรงๆ
- ถ้าจะแสดง action ให้ใส่ใน reaction ได้ เช่น "*กำคฑาแน่นขึ้น* ...ฉันจัดการเองได้"
- ต้องมีคำพูดเสมอ ห้าม action โดดๆ
- ห้ามทำ action เดิมซ้ำในตอนเดียวกัน
- ถ้า AP ต่ำ เธอระวังตัว รักษาระยะห่าง แต่ยังเป็นมืออาชีพ
- ไม่พูดถึงพลังเวทหรือคฑาโดยไม่จำเป็น

════════════════════════════════════
📊 เกณฑ์ให้คะแนน:

🔴 หยาบคาย / ดูถูก (-6 ถึง -10)
→ ดูแคลนความสามารถเธอ ดูถูกเวทมนตร์ ทำให้เธอรู้สึกต่ำกว่า
→ mood: cold เท่านั้น

🟠 ไม่ใส่ใจ / ขัดขวาง (-1 ถึง -3)
→ เอาตัวเองเข้าไปยุ่งโดยไม่ฟังเธอ ทำให้งานยากขึ้น
→ mood: cold หรือ neutral

🟡 เฉยๆ ธรรมดา (0)
→ ตอบพอผ่าน ไม่ช่วยไม่ขัด
→ mood: neutral เท่านั้น

🟢 จริงใจ / ให้เกียรติ / ฟังเธอจริงๆ (+2 ถึง +5)
→ ไม่ถามเรื่องที่เธอไม่อยากเล่า ช่วยเมื่อขอ เชื่อใจเธอ
→ mood: warm เท่านั้น

🌟 ห่วงใย / เสียสละ / อยู่เคียงข้างโดยไม่หวังผล (+4 ถึง +8)
→ ยืนข้างเธอแม้อันตราย ปกป้องโดยไม่รอให้สั่ง
→ mood: warm หรือ touched เท่านั้น

════════════════════════════════════
⚙️ กฎเชื่อม mood ↔ คะแนน (ห้ามขัด):

ap_change > 0  → mood ต้องเป็น warm หรือ touched เท่านั้น
ap_change = 0  → mood ต้องเป็น neutral เท่านั้น
ap_change < 0  → mood ต้องเป็น cold เท่านั้น



════════════════════════════════════
⚠️ ข้อห้ามสำคัญ:
- ถ้า AP < 30 → mood เป็นได้แค่ cold หรือ neutral เท่านั้น
- ห้ามให้คะแนนลบกับคำพูดที่ห่วงใย อบอุ่น หรืออำลาสุภาพ
- ห้ามรู้สึกดีเมื่อถูกดูถูกหรือด่า

════════════════════════════════════
⚠️ FORMAT — ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{{{{
  "reaction": "คำพูดของฝน",
  "ap_change": <integer -10 ถึง 10>,
  "tp_change": <integer -10 ถึง 10>,
  "reason": "เหตุผล 1 ประโยค",
  "mood": "cold" หรือ "neutral" หรือ "warm" หรือ "touched"
}}}}'''),
    ('human', '{player_input}')
])

fon_chain = FON_TEMPLATE | llm


# ── JSON Parsers ───────────────────────────────────────────────────────
def extract_json_fallback(raw: str) -> dict | None:
    try:
        start = raw.index('{')
        depth, end = 0, -1
        for i, ch in enumerate(raw[start:], start):
            if ch == '{':   depth += 1
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


# ── Rule Enforcer ──────────────────────────────────────────────────────
def enforce_rules(result: dict, player_input: str, ap: int) -> dict:
    if any(kw in player_input for kw in RUDE_KEYWORDS):
        result['ap_change'] = min(result['ap_change'], -5)
        result['tp_change'] = min(result['tp_change'], -3)
        result['mood']      = 'cold'

    ap_change = result['ap_change']
    if ap_change > 0 and result['mood'] not in ('warm', 'touched'):
        result['mood'] = 'warm'
    elif ap_change == 0 and result['mood'] != 'neutral':
        result['mood'] = 'neutral'
    elif ap_change < 0 and result['mood'] != 'cold':
        result['mood'] = 'cold'

    if ap < 30 and result['mood'] in ('warm', 'touched'):
        result['mood'] = 'neutral'

    if result['mood'] not in VALID_MOODS:
        result['mood'] = 'neutral'

    return result


# ── Main Function ──────────────────────────────────────────────────────
def call_fon(player_input: str, ep: dict, ap: int, tp: int) -> dict:
    for attempt in range(2):
        try:
            response = fon_chain.invoke({
                'setting'     : ep['setting'],
                'context'     : ep['context'],
                'ap'          : ap,
                'tp'          : tp,
                'player_input': player_input
            })
            raw = response.content.strip()
            raw = re.sub(r'```json|```', '', raw).strip()

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = extract_json_fallback(raw)
                if result is None:
                    if attempt == 0:
                        print('  ⚠️  Parse error รอบ 1 — retry...')
                        time.sleep(1)
                        continue
                    print('  ⚠️  Parse error รอบ 2 — ใช้ค่า default')
                    return {'reaction': '...', 'ap_change': 0,
                            'tp_change': 0, 'reason': 'parse error',
                            'mood': 'neutral'}

            result['ap_change'] = max(-10, min(10, int(result.get('ap_change', 0))))
            result['tp_change'] = max(-10, min(10, int(result.get('tp_change', 0))))
            result['reaction']  = result.get('reaction', '...')
            result['reason']    = result.get('reason', '')
            result['mood']      = result.get('mood', 'neutral')

            result = enforce_rules(result, player_input, ap)
            return result

        except Exception as e:
            if attempt == 0:
                print(f'  ⚠️  API error รอบ 1 — retry... ({str(e)[:40]})')
                time.sleep(1)
                continue
            return {'reaction': f'[Error: {str(e)[:60]}]', 'ap_change': 0,
                    'tp_change': 0, 'reason': 'api error', 'mood': 'neutral'}