import html
import json
import os
import random
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "saved_sessions.json")

DEFAULT_CONFIG = {
    "provider": "free_no_key",  # "free_no_key" or "gemini_free"
    "gemini_api_key": "",
    "pollinations_api_key": "",
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_config():
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


def extract_json_object(raw_text):
    text = raw_text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Could not parse structured routine from AI response.")


def build_prompt(age_group, goal, pose_count, custom_note):
    note_line = f"Special user note/limitation: {custom_note}." if custom_note else "No special limitations noted."
    return f"""
You are a certified, compassionate Yoga & Mobility Coach creating a safe, easy-to-follow routine for a non-technical user.

Target Age Group: {age_group}
Primary Goal / Focus: {goal}
Number of Poses Required: {pose_count}
{note_line}

Rules:
1. Tailor every pose, hold time, and safety cue specifically for {age_group}.
2. Keep instructions simple, encouraging, jargon-free, and safe to practice at home without special equipment (a sturdy chair or wall is okay if helpful for seniors/kids).
3. Return ONLY valid JSON matching this exact schema (no markdown, no extra commentary):

{{
  "session_title": "Encouraging title for this routine",
  "age_group": "{age_group}",
  "goal": "{goal}",
  "safety_note": "One clear, friendly age-appropriate safety reminder before starting",
  "breathing_warmup": {{
    "name": "Simple breathing exercise name",
    "duration": "2 minutes",
    "steps": [
      "Step 1 in plain English",
      "Step 2 in plain English",
      "Step 3 in plain English"
    ]
  }},
  "poses": [
    {{
      "english_name": "Simple Pose Name",
      "sanskrit_name": "Traditional Name",
      "pose_category": "one of: mountain, tree, cat_cow, seated_twist, child, warrior, cobra, chair, legs_wall",
      "duration_seconds": 30,
      "duration_label": "30 seconds (about 4 slow breaths)",
      "benefit": "Clear 1-sentence benefit",
      "easy_steps": [
        "Step 1: Starting position",
        "Step 2: Gentle movement into the pose",
        "Step 3: How to hold and breathe comfortably"
      ],
      "age_modification": "Specific tip or prop modification for {age_group}",
      "image_prompt": "friendly educational yoga illustration of a {age_group} person safely practicing [pose], peaceful sunlit room, soft pastel watercolor and clean vector art style, full body clear posture, no text"
    }}
  ],
  "daily_wellness_tip": "One practical, uplifting daily habit or hydration/posture tip for {age_group}"
}}
""".strip()


def call_gemini_free(prompt, api_key):
    models = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "responseMimeType": "application/json",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_err = None

    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={urllib.parse.quote(api_key.strip())}"
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return extract_json_object(text)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Gemini API request failed: {last_err}")


def call_pollinations_free(prompt):
    encoded = urllib.parse.quote(prompt[:1800])
    endpoints = [
        f"https://gen.pollinations.ai/text/{encoded}?json=true",
        f"https://text.pollinations.ai/{encoded}?json=true",
    ]
    last_err = None
    for url in endpoints:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DailyYogaAIAgent/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                raw = resp.read().decode("utf-8")
                return extract_json_object(raw)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Free AI endpoint busy: {last_err}")


def built_in_curated_routine(age_group, goal, pose_count, custom_note):
    """Reliable offline/fallback routine bank tailored by age group."""
    is_senior = "Senior" in age_group or "75+" in age_group
    is_kid = "Kids" in age_group

    pose_library = [
        {
            "english_name": "Seated Mountain & Overhead Reach" if is_senior else "Mountain Pose with Gentle Reach",
            "sanskrit_name": "Tadasana",
            "pose_category": "mountain",
            "duration_seconds": 30,
            "duration_label": "30 seconds (4 slow breaths)",
            "benefit": "Improves upright posture, opens the chest, and awakens spinal alignment.",
            "easy_steps": [
                "Sit tall on a sturdy chair with feet flat on the floor (or stand with feet hip-width apart)." if is_senior else "Stand tall with your feet hip-width apart and shoulders relaxed away from your ears.",
                "Inhale slowly as you sweep both arms out to the sides and comfortably overhead.",
                "Exhale softly, lengthen through your spine, and lower your arms back down with control."
            ],
            "age_modification": "Keep hands at shoulder height or rest hands on thighs if raising arms overhead feels tight." if is_senior else ("Pretend you are a tall tree stretching branches up to touch the clouds!" if is_kid else "Micro-bend your knees to avoid locking your joints."),
            "image_prompt": f"clean educational yoga illustration of {age_group} person doing gentle mountain pose overhead stretch, peaceful sunlit studio, soft pastel colors, full body posture, no text"
        },
        {
            "english_name": "Gentle Cat-Cow Spine Flow",
            "sanskrit_name": "Marjaryasana-Bitilasana",
            "pose_category": "cat_cow",
            "duration_seconds": 40,
            "duration_label": "40 seconds (5 gentle rounds)",
            "benefit": "Relieves back and neck stiffness while lubricating the spine.",
            "easy_steps": [
                "Sit near the front edge of a chair with hands resting on your knees (or come onto hands and knees on a soft mat)." if is_senior else "Start on hands and knees with wrists under shoulders and knees under hips (or hands on knees while seated).",
                "Inhale: gently lift your chest, roll shoulders back, and look slightly forward (Cow).",
                "Exhale: slowly round your upper back and tuck your chin gently toward your chest (Cat)."
            ],
            "age_modification": "Seated Cat-Cow on a sturdy chair gives the exact same spine relief with zero knee pressure." if is_senior else ("Moo like a happy cow on inhale and arch like a stretching kitten on exhale!" if is_kid else "Place a folded towel under your knees if practicing on a hard floor."),
            "image_prompt": f"clean educational yoga illustration of {age_group} person practicing gentle cat cow spine stretch, calm wellness room, soft pastel vector illustration, no text"
        },
        {
            "english_name": "Playful Tree Balance" if is_kid else "Supported Tree Balance",
            "sanskrit_name": "Vrksasana",
            "pose_category": "tree",
            "duration_seconds": 25,
            "duration_label": "25 seconds each side",
            "benefit": "Builds ankle stability, leg strength, and calm mental focus.",
            "easy_steps": [
                "Stand near a wall or chair back for light fingertip support, shifting weight onto your left foot.",
                "Place your right heel gently against your left ankle with toes still touching the floor like a kickstand.",
                "Bring hands together at your heart or keep one hand on the chair, breathing steadily."
            ],
            "age_modification": "Keep toes on the floor as a kickstand and hold a chair back for steady confidence." if is_senior else ("See how steady you can stand like a strong oak tree in the breeze!" if is_kid else "Rest your foot on your calf (never directly on the knee joint) for deeper balance."),
            "image_prompt": f"clean educational yoga illustration of {age_group} person practicing beginner tree pose balance with kickstand foot, serene room, soft watercolor style, no text"
        },
        {
            "english_name": "Easy Seated Spinal Twist",
            "sanskrit_name": "Bharadvajasana",
            "pose_category": "seated_twist",
            "duration_seconds": 30,
            "duration_label": "30 seconds each side",
            "benefit": "Eases lower-back tension, aids digestion, and refreshes tired shoulders.",
            "easy_steps": [
                "Sit comfortably tall on a chair or cross-legged on a cushion with your spine straight.",
                "Inhale to lengthen upward; exhale and gently turn your torso to the right.",
                "Rest your left hand on your outer right thigh and look softly over your right shoulder without forcing."
            ],
            "age_modification": "Move slowly from the ribs rather than pulling with your arms; keep neck neutral if stiff." if is_senior else ("Twist gently like looking over your shoulder to spot a rainbow!" if is_kid else "Lengthen your spine on every inhale before deepening the twist slightly on exhale."),
            "image_prompt": f"clean educational yoga illustration of {age_group} person doing gentle seated spinal twist, warm minimalist studio, soft pastel art, no text"
        },
        {
            "english_name": "Resting Child's Stretch" if not is_senior else "Seated Forward Rest",
            "sanskrit_name": "Balasana",
            "pose_category": "child",
            "duration_seconds": 45,
            "duration_label": "45 seconds (5 deep breaths)",
            "benefit": "Calms the nervous system and gently stretches the hips, shoulders, and upper back.",
            "easy_steps": [
                "Sit comfortably on a chair and rest your forearms on your thighs (or kneel on a mat with big toes touching)." if is_senior else "Kneel on a soft mat, bring big toes together, and sit your hips back toward your heels.",
                "Fold your torso gently forward, resting your forehead on stacked hands, a pillow, or your forearms.",
                "Let your shoulders melt downward and take slow, quiet breaths into your back."
            ],
            "age_modification": "Resting forearms on thighs while seated gives a safe, dizzy-free forward release." if is_senior else ("Curl up cozy like a sleeping turtle resting in its shell!" if is_kid else "Place a cushion between your calves and thighs for extra knee comfort."),
            "image_prompt": f"clean educational yoga illustration of {age_group} person resting in gentle child pose on mat, peaceful lighting, soft pastel illustration, no text"
        }
    ]

    selected = pose_library[: max(3, min(5, int(pose_count)))]
    return {
        "session_title": f"{goal} — Tailored for {age_group}",
        "age_group": age_group,
        "goal": goal,
        "safety_note": (
            f"Move slowly within a pain-free range. Keep a sturdy chair or wall nearby for balance"
            + (f" — tailored with your note in mind: '{custom_note}'." if custom_note else ".")
        ),
        "breathing_warmup": {
            "name": "Balloon Belly Breathing" if is_kid else "Calm 4-4 Box Rhythm Breathing",
            "duration": "2 minutes",
            "steps": [
                "Sit comfortably upright with both feet grounded and shoulders relaxed.",
                "Breathe in gently through your nose for a slow count of 4, feeling your belly expand.",
                "Exhale softly through your nose or pursed lips for a count of 4 to release tension."
            ],
        },
        "poses": selected,
        "daily_wellness_tip": (
            "Drink a glass of water after your session and take two 60-second stretch breaks whenever you sit for more than an hour."
        ),
    }


def generate_yoga_routine(age_group, goal, pose_count, custom_note):
    cfg = get_config()
    prompt = build_prompt(age_group, goal, pose_count, custom_note)
    source_used = "Built-In Smart Yoga Coach"

    if cfg.get("provider") == "gemini_free" and cfg.get("gemini_api_key", "").strip():
        try:
            routine = call_gemini_free(prompt, cfg["gemini_api_key"])
            source_used = "Google Gemini Free Tier"
            routine["_source"] = source_used
            return routine
        except Exception:
            pass

    try:
        routine = call_pollinations_free(prompt)
        if isinstance(routine, dict) and "poses" in routine and len(routine["poses"]) > 0:
            routine["_source"] = "Free Open AI Agent"
            return routine
    except Exception:
        pass

    routine = built_in_curated_routine(age_group, goal, pose_count, custom_note)
    routine["_source"] = source_used
    return routine


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Daily Yoga AI Agent — Easy Poses for Every Age</title>
  <style>
    :root {
      --bg: #f6f8f5;
      --card: #ffffff;
      --primary: #2f6f5e;
      --primary-dark: #215245;
      --accent: #e8f2ee;
      --warm: #fdf6ec;
      --warm-border: #f0d7b4;
      --text: #1f2d29;
      --muted: #5a6d67;
      --border: #dce5e0;
      --font-scale: 1;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: calc(16px * var(--font-scale));
      line-height: 1.55;
    }
    header {
      background: linear-gradient(135deg, #24594b 0%, #3a826f 100%);
      color: #fff;
      padding: 22px 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    }
    .header-inner {
      max-width: 1040px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .brand h1 {
      margin: 0;
      font-size: 1.55em;
      letter-spacing: -0.01em;
    }
    .brand p {
      margin: 4px 0 0;
      opacity: 0.92;
      font-size: 0.95em;
    }
    .top-controls {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .pill-btn {
      background: rgba(255,255,255,0.16);
      color: #fff;
      border: 1px solid rgba(255,255,255,0.35);
      padding: 8px 13px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.9em;
    }
    .pill-btn:hover { background: rgba(255,255,255,0.28); }
    .container {
      max-width: 1040px;
      margin: 24px auto 60px;
      padding: 0 18px;
    }
    .tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .tab-btn {
      padding: 11px 18px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--text);
      font-weight: 600;
      cursor: pointer;
      font-size: 0.98em;
    }
    .tab-btn.active {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 22px;
      box-shadow: 0 4px 16px rgba(31,45,41,0.04);
      margin-bottom: 20px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
    }
    label {
      display: block;
      font-weight: 700;
      margin-bottom: 6px;
      font-size: 0.95em;
    }
    select, input[type="text"], input[type="password"] {
      width: 100%;
      padding: 11px 13px;
      border-radius: 10px;
      border: 1px solid #c6d4cd;
      font-size: 1em;
      background: #fff;
      color: var(--text);
    }
    .primary-btn {
      background: var(--primary);
      color: #fff;
      border: none;
      padding: 14px 24px;
      border-radius: 12px;
      font-size: 1.05em;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 16px;
    }
    .primary-btn:hover { background: var(--primary-dark); }
    .primary-btn:disabled { opacity: 0.65; cursor: wait; }
    .secondary-btn {
      background: var(--accent);
      color: var(--primary-dark);
      border: 1px solid #bfd7ce;
      padding: 9px 15px;
      border-radius: 10px;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.92em;
    }
    .safety-box {
      background: var(--warm);
      border: 1px solid var(--warm-border);
      border-radius: 12px;
      padding: 14px 16px;
      margin: 14px 0;
    }
    .warmup-box {
      background: var(--accent);
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 20px;
    }
    .pose-card {
      display: grid;
      grid-template-columns: 310px 1fr;
      gap: 22px;
      align-items: start;
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
      margin-bottom: 18px;
      background: #fff;
    }
    @media (max-width: 780px) {
      .pose-card { grid-template-columns: 1fr; }
    }
    .pose-visual {
      width: 100%;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      background: #eef5f1;
      aspect-ratio: 3 / 2;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .pose-visual img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .badge {
      display: inline-block;
      background: var(--accent);
      color: var(--primary-dark);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.84em;
      font-weight: 700;
    }
    .steps-list {
      padding-left: 20px;
      margin: 10px 0;
    }
    .steps-list li {
      margin-bottom: 7px;
    }
    .mod-tip {
      background: #f4f8f6;
      border-left: 4px solid var(--primary);
      padding: 10px 12px;
      border-radius: 6px;
      font-size: 0.94em;
      margin-top: 10px;
    }
    .timer-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 12px;
      flex-wrap: wrap;
    }
    .timer-display {
      font-weight: 800;
      font-variant-numeric: tabular-nums;
      color: var(--primary-dark);
      font-size: 1.05em;
    }
    .hidden { display: none; }
    .saved-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 10px;
    }
    @media print {
      header, .tabs, #generator-card, .timer-bar, .no-print { display: none !important; }
      body { background: #fff; }
      .card, .pose-card { box-shadow: none; border: 1px solid #ccc; break-inside: avoid; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="brand">
        <h1>🧘 Daily Yoga AI Agent</h1>
        <p>Free, gentle, step-by-step Yoga routines with pose illustrations for every age</p>
      </div>
      <div class="top-controls">
        <button class="pill-btn" onclick="changeFontSize(-0.1)" title="Smaller text">A-</button>
        <button class="pill-btn" onclick="changeFontSize(0.1)" title="Larger text for easy reading">A+</button>
        <button class="pill-btn" onclick="switchTab('settings')">⚙️ Free AI Settings</button>
      </div>
    </div>
  </header>

  <div class="container">
    <div class="tabs">
      <button id="tab-practice" class="tab-btn active" onclick="switchTab('practice')">✨ Create & Practice Yoga</button>
      <button id="tab-saved" class="tab-btn" onclick="switchTab('saved')">📚 Saved Routines (<span id="saved-count">0</span>)</button>
      <button id="tab-settings" class="tab-btn" onclick="switchTab('settings')">🔑 Free API Setup (Optional)</button>
    </div>

    <!-- PRACTICE TAB -->
    <div id="view-practice">
      <div id="generator-card" class="card">
        <h2 style="margin-top:0;">Personalize Today's Yoga Session</h2>
        <div class="form-grid">
          <div>
            <label for="age-group">1. Select Age Group</label>
            <select id="age-group">
              <option value="Kids (Ages 5-12)">Kids (Ages 5–12) — Fun & Playful</option>
              <option value="Teens (Ages 13-19)">Teens (Ages 13–19) — Focus & Posture</option>
              <option value="Adults (Ages 20-55)" selected>Adults (Ages 20–55) — Everyday Balance</option>
              <option value="Seniors (Ages 56-75)">Seniors (Ages 56–75) — Joint & Balance Care</option>
              <option value="Gentle Senior / Assisted (75+)">Gentle Care (Ages 75+) — Chair & Supported</option>
            </select>
          </div>
          <div>
            <label for="goal">2. Choose Your Wellness Goal</label>
            <select id="goal">
              <option value="Morning Energy & Wake-Up">☀️ Morning Energy & Wake-Up</option>
              <option value="Stress & Anxiety Relief">🌿 Stress & Anxiety Relief</option>
              <option value="Back, Neck & Desk Posture Relief">🪑 Back, Neck & Desk Posture Relief</option>
              <option value="Flexibility & Joint Mobility">🤸 Flexibility & Joint Mobility</option>
              <option value="Chair Yoga (Zero Floor Work)">💺 Chair Yoga (Zero Floor Work)</option>
              <option value="Relaxing Bedtime Wind-Down">🌙 Relaxing Bedtime Wind-Down</option>
            </select>
          </div>
          <div>
            <label for="pose-count">3. Session Length</label>
            <select id="pose-count">
              <option value="3">Quick 5-Min Flow (3 Poses)</option>
              <option value="4" selected>Balanced 12-Min Flow (4 Poses)</option>
              <option value="5">Full 20-Min Flow (5 Poses)</option>
            </select>
          </div>
        </div>
        <div style="margin-top:14px;">
          <label for="custom-note">4. Optional Comfort Note (e.g., "stiff knees", "beginner", "tight shoulders")</label>
          <input type="text" id="custom-note" placeholder="Leave blank or type any comfort preference..." />
        </div>
        <button id="generate-btn" class="primary-btn" onclick="generateRoutine()">
          🧘 Generate My Yoga Routine & Illustrations
        </button>
      </div>

      <div id="routine-output" class="hidden"></div>
    </div>

    <!-- SAVED ROUTINES TAB -->
    <div id="view-saved" class="hidden">
      <div class="card">
        <h2 style="margin-top:0;">Saved Yoga Routines</h2>
        <p style="color:var(--muted);">Revisit your favorite age-tailored routines anytime—even offline.</p>
        <div id="saved-list"></div>
      </div>
    </div>

    <!-- SETTINGS TAB -->
    <div id="view-settings" class="hidden">
      <div class="card">
        <h2 style="margin-top:0;">100% Free AI Configuration</h2>
        <p>
          <strong>Good news:</strong> This app already works out of the box with <strong>$0 cost and no API key required</strong>.
          If you want faster responses or higher daily limits, you can optionally connect a free Google Gemini API key (no credit card required).
        </p>
        <div style="margin-bottom:14px;">
          <label for="cfg-provider">AI Engine Mode</label>
          <select id="cfg-provider">
            <option value="free_no_key">Zero-Key Free Mode (Recommended — Ready Immediately)</option>
            <option value="gemini_free">Google Gemini Free Tier Key (Optional)</option>
          </select>
        </div>
        <div style="margin-bottom:14px;">
          <label for="cfg-gemini">Optional Free Google Gemini API Key</label>
          <input type="password" id="cfg-gemini" placeholder="AIzaSy... (Get one free at aistudio.google.com)" />
          <small style="color:var(--muted);">Saved locally on your computer only (`config.json`). Never shared.</small>
        </div>
        <div style="margin-bottom:16px;">
          <label for="cfg-pollinations">Optional Free Pollinations Key (for extra image quota)</label>
          <input type="password" id="cfg-pollinations" placeholder="pk_... (Optional — leave blank for built-in free images)" />
        </div>
        <button class="primary-btn" style="margin-top:0;" onclick="saveSettings()">💾 Save Settings</button>
        <span id="settings-status" style="margin-left:12px;font-weight:600;color:var(--primary);"></span>
      </div>
    </div>
  </div>

  <script>
    let currentFontScale = 1.0;
    let currentRoutine = null;
    let activeTimers = {};

    function changeFontSize(delta) {
      currentFontScale = Math.min(1.4, Math.max(0.85, +(currentFontScale + delta).toFixed(2)));
      document.documentElement.style.setProperty("--font-scale", currentFontScale);
    }

    function switchTab(name) {
      ["practice", "saved", "settings"].forEach(t => {
        document.getElementById("view-" + t).classList.toggle("hidden", t !== name);
        document.getElementById("tab-" + t).classList.toggle("active", t === name);
      });
      if (name === "saved") loadSavedRoutines();
      if (name === "settings") loadSettings();
    }

    function escapeHtml(str) {
      return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function buildFallbackSvgDataUri(pose, index) {
      const cat = (pose.pose_category || "mountain").toLowerCase();
      const title = escapeHtml(pose.english_name || "Yoga Pose");
      const colors = ["#d8ebe4", "#e3eef8", "#f6ead9", "#e9e4f5", "#dcefe6"];
      const bg = colors[index % colors.length];

      // Clean vector stick-figure yoga illustrations per pose category
      const figures = {
        mountain: `<circle cx="150" cy="48" r="12" fill="#2f6f5e"/><path d="M150 62 L150 112 M150 74 L125 40 M150 74 L175 40 M150 112 L136 162 M150 112 L164 162" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        tree: `<circle cx="150" cy="48" r="12" fill="#2f6f5e"/><path d="M150 62 L150 112 M150 75 L132 58 L150 44 M150 75 L168 58 L150 44 M150 112 L150 164 M150 112 L174 132 L152 142" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        cat_cow: `<circle cx="96" cy="95" r="11" fill="#2f6f5e"/><path d="M108 102 Q150 78 192 104 M115 103 L112 152 M186 105 L190 152" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        seated_twist: `<circle cx="150" cy="56" r="12" fill="#2f6f5e"/><path d="M150 70 L150 124 M150 86 L122 104 M150 86 L180 96 M150 124 L118 148 L155 154 M150 124 L182 148 L145 154" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        child: `<circle cx="102" cy="136" r="11" fill="#2f6f5e"/><path d="M114 136 Q152 114 186 138 L164 152 L198 152 M112 144 L76 148" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        warrior: `<circle cx="150" cy="52" r="12" fill="#2f6f5e"/><path d="M150 66 L150 112 M102 80 L198 80 M150 112 L116 132 L112 164 M150 112 L192 164" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`
      };
      const figure = figures[cat] || figures.mountain;
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200">
        <rect width="300" height="200" fill="${bg}"/>
        <line x1="65" y1="168" x2="235" y2="168" stroke="#8fb3a7" stroke-width="4" stroke-linecap="round"/>
        ${figure}
        <text x="150" y="190" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#215245">${title}</text>
      </svg>`;
      return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    }

    function handlePoseImgError(imgEl, index) {
      if (!currentRoutine || !currentRoutine.poses[index]) return;
      imgEl.onerror = null;
      imgEl.src = buildFallbackSvgDataUri(currentRoutine.poses[index], index);
    }

    function startPoseTimer(index, totalSeconds) {
      if (activeTimers[index]) {
        clearInterval(activeTimers[index]);
        delete activeTimers[index];
      }
      let remaining = totalSeconds || 30;
      const display = document.getElementById("timer-val-" + index);
      display.textContent = remaining + "s remaining";

      activeTimers[index] = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearInterval(activeTimers[index]);
          delete activeTimers[index];
          display.textContent = "✅ Complete! Great job!";
          playGentleChime();
        } else {
          display.textContent = remaining + "s remaining";
        }
      }, 1000);
    }

    function playGentleChime() {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine