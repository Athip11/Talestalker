# ════════════════════════════════════════════════
# game/fon.py — Fon AI Character Engine
# ════════════════════════════════════════════════

import json, re, time, os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────
VALID_MOODS = {'exasperated', 'neutral', 'warm', 'touched'}
RUDE_KEYWORDS = ['มึง', 'กู', 'ไอ้', 'อี', 'สัตว์',
                 'ควาย', 'บ้า', 'โง่', 'ขยะ', 'เพี้ยน', 'แม่ง']

# ── LLM ───────────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model       = "gemini-2.5-flash",
    api_key     = os.getenv("GEMINI_API_KEY"),
    temperature = 0.8,
)

# Bind the JSON mime type so the model physically cannot output Markdown
json_llm = llm.bind(response_mime_type="application/json")

# ── Prompt Template ────────────────────────────────────────────────────
prompt = ChatPromptTemplate.from_messages([
    ('system', '''
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
- Relationship → AP: {ap}/100 | TP: {tp}/100 
  (AP = Affinity/Feeling | TP = Trust/Reliability)

# RULES:
1. ALWAYS reply in THAI for the "reaction" field.
2. Include actions in asterisks inside the reaction (e.g., "*ถอนหายใจยาว* ...ทำตัวเป็นเด็กไปได้ค่ะ").
3. Score changes based on player behavior:
   - Reckless/Lazy: AP/TP < 0 (Mood: pouting, exasperated)
   - Polite/Responsible: AP/TP > 0 (Mood: calm, slightly warm)
   - Offering Sweets/Deep Care: AP/TP >> 0 (Mood: touched, awkward)
4. Constraints: If AP < 30, you keep a physical distance and are highly formal, but you will still ensure the player doesn't get hurt (because you are responsible).

# FORMAT — ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{{{{
  "reaction": "คำพูดของเฟิร์น (ภาษาไทย)",
  "ap_change": <integer -10 ถึง 10>,
  "tp_change": <integer -10 ถึง 10>,
  "reason": "Reason for score change in 1 sentence",
  "mood": "exasperated" หรือ "neutral" หรือ "warm" หรือ "touched"
}}}}'''),
    ('human', '{player_input}')
])

# Update your chain to use the bound LLM
fon_chain = prompt | json_llm

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
        result['mood']      = 'exasperated'

    ap_change = result['ap_change']
    if ap_change > 0 and result['mood'] not in ('warm', 'touched'):
        result['mood'] = 'warm'
    elif ap_change == 0 and result['mood'] != 'neutral':
        result['mood'] = 'neutral'
    elif ap_change < 0 and result['mood'] != 'exasperated':
        result['mood'] = 'exasperated'
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

            if isinstance(response.content, list):
                raw = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in response.content])
            else:
                raw = str(response.content)
            raw = raw.strip()

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
                # DO NOT access 'response' here, it might not exist!
                time.sleep(1)
                continue
           
            # Final failure return
            return {
                'reaction': f'[Error: {str(e)[:60]}]',
                'ap_change': 0,
                'tp_change': 0,
                'reason': 'api error',
                'mood': 'neutral'
            }
