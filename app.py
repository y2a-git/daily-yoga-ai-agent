import json
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "saved_sessions.json")
MEMORY_FILE = os.path.join(BASE_DIR, "agent_memory.json")

DEFAULT_CONFIG = {
    "provider": "free_no_key",
    "gemini_api_key": "",
    "pollinations_api_key": "",
}

DEFAULT_MEMORY = {
    "total_sessions": 0,
    "progression_level": "Gentle Starter",
    "recent_poses": [],
    "remembered_sensitivities": [],
    "feedback_history": [],
}


def load_json(path, default):
    if not os.path.exists(path):
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_config():
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


def get_memory():
    mem = json.loads(json.dumps(DEFAULT_MEMORY))
    mem.update(load_json(MEMORY_FILE, {}))
    return mem


def extract_json_object(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Could not parse structured JSON from AI response.")


# Safe verified substitution pool used during self-revision or offline fallback
SAFE_POSE_POOL = [
    {
        "english_name": "Seated Mountain & Overhead Reach",
        "sanskrit_name": "Tadasana",
        "pose_category": "mountain",
        "duration_seconds": 30,
        "duration_label": "30 seconds (4 slow breaths)",
        "benefit": "Improves upright posture, opens the chest, and relieves upper-back stiffness.",
        "easy_steps": [
            "Sit tall near the front of a sturdy chair with feet flat on the floor (or stand hip-width apart).",
            "Inhale slowly as you sweep both arms out to the sides and comfortably overhead.",
            "Exhale softly, lengthen through your spine, and lower your arms back down with control.",
        ],
        "age_modification": "Keep hands at shoulder height or rest hands on thighs if raising arms overhead feels tight.",
        "tags": ["chair_safe", "knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person doing gentle seated mountain pose overhead stretch, sunlit studio, soft pastel vector art, no text",
    },
    {
        "english_name": "Gentle Cat-Cow Spine Flow",
        "sanskrit_name": "Marjaryasana-Bitilasana",
        "pose_category": "cat_cow",
        "duration_seconds": 40,
        "duration_label": "40 seconds (5 gentle rounds)",
        "benefit": "Lubricates the spine and eases neck, shoulder, and lower-back tension.",
        "easy_steps": [
            "Sit upright on a sturdy chair with hands resting on your knees (or start on hands and knees on a soft mat).",
            "Inhale: gently lift your chest, roll shoulders back, and look slightly forward (Cow).",
            "Exhale: slowly round your upper back and tuck your chin gently toward your chest (Cat).",
        ],
        "age_modification": "Practicing Cat-Cow seated in a chair delivers full spinal relief with zero knee or wrist pressure.",
        "tags": ["chair_safe", "knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person practicing gentle cat cow spine stretch, calm wellness room, soft pastel art, no text",
    },
    {
        "english_name": "Supported Wall or Chair Tree Balance",
        "sanskrit_name": "Vrksasana",
        "pose_category": "tree",
        "duration_seconds": 25,
        "duration_label": "25 seconds each side",
        "benefit": "Builds ankle stability, hip strength, and calm focus safely.",
        "easy_steps": [
            "Stand beside a sturdy chair back or wall with one hand resting lightly for balance.",
            "Shift weight onto your left foot and rest your right heel against your left ankle with toes on the floor like a kickstand.",
            "Stand tall, breathe smoothly, and switch sides after 25 seconds.",
        ],
        "age_modification": "Keep toes grounded like a kickstand and hold a chair back for steady, fall-free support.",
        "tags": ["knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person practicing beginner tree pose balance with kickstand foot, serene room, soft watercolor style, no text",
    },
    {
        "english_name": "Easy Seated Spinal Twist",
        "sanskrit_name": "Bharadvajasana",
        "pose_category": "seated_twist",
        "duration_seconds": 30,
        "duration_label": "30 seconds each side",
        "benefit": "Releases mid-back tightness, aids digestion, and refreshes tired shoulders.",
        "easy_steps": [
            "Sit comfortably tall on a chair with both feet flat on the floor.",
            "Inhale to lengthen your spine upward; exhale and gently rotate your ribs to the right.",
            "Rest your left hand on your outer right thigh and gaze softly to the side without straining your neck.",
        ],
        "age_modification": "Rotate gently from the ribcage rather than pulling with your arms; keep neck neutral if stiff.",
        "tags": ["chair_safe", "knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person doing gentle seated spinal twist on chair, warm minimalist studio, soft pastel art, no text",
    },
    {
        "english_name": "Seated Forward Rest",
        "sanskrit_name": "Balasana Variation",
        "pose_category": "child",
        "duration_seconds": 40,
        "duration_label": "40 seconds (5 slow breaths)",
        "benefit": "Calms the nervous system and gently releases the lower back and shoulders.",
        "easy_steps": [
            "Sit comfortably on a chair with feet wider than hip-width apart.",
            "Hinge gently forward from your hips and rest your forearms across your thighs.",
            "Let your shoulders relax downward and take slow, quiet breaths into your upper back.",
        ],
        "age_modification": "Resting forearms on thighs avoids dizziness and removes all pressure from knees and ankles.",
        "tags": ["chair_safe", "knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person resting calmly in seated forward fold with forearms on thighs, peaceful room, soft pastel art, no text",
    },
    {
        "english_name": "Gentle Seated Ankle & Calf Circles",
        "sanskrit_name": "Goolf Chakra",
        "pose_category": "seated_twist",
        "duration_seconds": 30,
        "duration_label": "30 seconds (15s each foot)",
        "benefit": "Boosts lower-leg circulation and eases stiff ankles and feet.",
        "easy_steps": [
            "Sit tall in a chair and extend your right leg slightly forward with the heel lifted off the floor.",
            "Slowly draw 5 gentle circles with your toes in one direction, then 5 in the opposite direction.",
            "Lower your right foot and repeat smoothly with your left foot.",
        ],
        "age_modification": "Support the back of your thigh with both hands if holding the leg lifted feels tiring.",
        "tags": ["chair_safe", "knee_safe", "back_safe", "senior_safe", "kid_friendly"],
        "image_prompt": "clean educational yoga illustration of person seated in chair doing gentle ankle mobility stretch, sunlit room, soft pastel art, no text",
    },
]


class YogaCoachAgent:
    """
    Multi-step autonomous Yoga Coach Agent:
      1. Memory Recall Tool -> loads progression level, recent poses, and joint sensitivities.
      2. Plan & Draft Tool  -> generates an age-tailored routine via Gemini/Pollinations/Curated Engine.
      3. Safety & Memory Critic Tool -> audits poses for biomechanical risks & repetition.
      4. Self-Revision Tool -> replaces any flagged pose with a verified safe alternative.
      5. Memory Update Tool -> persists session history & sensitivities for future adaptation.
    """

    def __init__(self):
        self.cfg = get_config()
        self.memory = get_memory()
        self.trace = []

    def log_step(self, phase, detail):
        self.trace.append({"phase": phase, "detail": detail})

    # --- TOOL 1: AGENT MEMORY RECALL & UPDATE ---
    def tool_recall_memory(self, age_group, custom_note):
        note_clean = (custom_note or "").strip()
        sensitivities = list(self.memory.get("remembered_sensitivities", []))
        if note_clean and note_clean.lower() not in [s.lower() for s in sensitivities]:
            sensitivities.append(note_clean)
            self.memory["remembered_sensitivities"] = sensitivities[-6:]

        recent_poses = self.memory.get("recent_poses", [])[-8:]
        level = self.memory.get("progression_level", "Gentle Starter")
        total = self.memory.get("total_sessions", 0)

        summary = (
            f"Sessions completed: {total} | Level: {level} | "
            f"Avoid repeating: {', '.join(recent_poses[-4:]) if recent_poses else 'None yet'} | "
            f"Active comfort notes: {', '.join(sensitivities) if sensitivities else 'None'}"
        )
        self.log_step("1. Memory Recall", summary)
        return {
            "progression_level": level,
            "recent_poses": recent_poses,
            "sensitivities": sensitivities,
            "total_sessions": total,
        }

    def update_memory_after_session(self, routine):
        poses_used = [p.get("english_name", "") for p in routine.get("poses", []) if p.get("english_name")]
        recent = self.memory.get("recent_poses", []) + poses_used
        self.memory["recent_poses"] = recent[-12:]
        self.memory["total_sessions"] = int(self.memory.get("total_sessions", 0)) + 1

        if self.memory["total_sessions"] >= 6 and self.memory.get("progression_level") == "Gentle Starter":
            self.memory["progression_level"] = "Steady Explorer"
        save_json(MEMORY_FILE, self.memory)

    # --- LLM TRANSPORT HELPERS ---
    def _call_gemini(self, prompt):
        api_key = self.cfg.get("gemini_api_key", "").strip()
        if not api_key:
            raise RuntimeError("No Gemini API key configured.")
        models = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.55, "responseMimeType": "application/json"},
        }
        body = json.dumps(payload).encode("utf-8")
        last_err = None
        for model in models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={urllib.parse.quote(api_key)}"
            )
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return extract_json_object(text)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Gemini call failed: {last_err}")

    def _call_pollinations(self, prompt):
        encoded = urllib.parse.quote(prompt[:1900])
        for base in ("https://gen.pollinations.ai/text/", "https://text.pollinations.ai/"):
            url = f"{base}{encoded}?json=true"
            req = urllib.request.Request(url, headers={"User-Agent": "DailyYogaAIAgent/2.0"}, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=22) as resp:
                    return extract_json_object(resp.read().decode("utf-8"))
            except Exception:
                continue
        raise RuntimeError("Free AI endpoint temporarily busy.")

    # --- TOOL 2: PLAN & DRAFT ROUTINE ---
    def tool_draft_routine(self, age_group, goal, pose_count, mem_ctx):
        avoid_str = ", ".join(mem_ctx["recent_poses"][-5:]) or "none"
        sens_str = ", ".join(mem_ctx["sensitivities"]) or "none"
        level = mem_ctx["progression_level"]

        prompt = f"""
You are an autonomous, safety-first Yoga & Mobility Coach Agent.
Plan a personalized routine using the user's memory profile:
- Age Group: {age_group}
- Wellness Goal: {goal}
- Number of Poses: {pose_count}
- User Progression Level: {level}
- Sensitivities / Comfort Notes to Protect: {sens_str}
- Recently Practiced Poses (avoid repeating if possible): {avoid_str}

Return ONLY valid JSON matching this schema:
{{
  "session_title": "Encouraging routine title",
  "age_group": "{age_group}",
  "goal": "{goal}",
  "safety_note": "Clear safety guidance tailored to {age_group} and sensitivities ({sens_str})",
  "breathing_warmup": {{
    "name": "Breathing exercise name",
    "duration": "2 minutes",
    "steps": ["Step 1", "Step 2", "Step 3"]
  }},
  "poses": [
    {{
      "english_name": "Pose Name",
      "sanskrit_name": "Sanskrit Name",
      "pose_category": "one of: mountain, tree, cat_cow, seated_twist, child, warrior",
      "duration_seconds": 30,
      "duration_label": "30 seconds (4 slow breaths)",
      "benefit": "1-sentence benefit",
      "easy_steps": ["Step 1", "Step 2", "Step 3"],
      "age_modification": "Specific modification for {age_group}",
      "image_prompt": "clean educational yoga illustration of {age_group} person practicing pose, sunlit room, soft pastel art, no text"
    }}
  ],
  "daily_wellness_tip": "Practical daily habit tip"
}}
""".strip()

        source = "Built-In Smart Yoga Coach"
        routine = None

        if self.cfg.get("provider") == "gemini_free" and self.cfg.get("gemini_api_key", "").strip():
            try:
                routine = self._call_gemini(prompt)
                source = "Google Gemini Free Tier (Agentic)"
            except Exception:
                routine = None

        if routine is None:
            try:
                candidate = self._call_pollinations(prompt)
                if isinstance(candidate, dict) and candidate.get("poses"):
                    routine = candidate
                    source = "Free Open AI Agent"
            except Exception:
                routine = None

        if routine is None:
            routine = self._curated_draft(age_group, goal, pose_count, mem_ctx)

        routine["_source"] = source
        self.log_step("2. Draft Generation", f"Created {len(routine.get('poses', []))} candidate poses via {source}.")
        return routine

    def _curated_draft(self, age_group, goal, pose_count, mem_ctx):
        count = max(3, min(5, int(pose_count)))
        recent_lower = {p.lower() for p in mem_ctx["recent_poses"][-4:]}
        fresh = [p for p in SAFE_POSE_POOL if p["english_name"].lower() not in recent_lower]
        pool = fresh + [p for p in SAFE_POSE_POOL if p not in fresh]
        chosen = json.loads(json.dumps(pool[:count]))

        # Adjust hold times based on progression level and age
        scale = 0.8 if "Kids" in age_group else (1.15 if mem_ctx["progression_level"] == "Steady Explorer" else 1.0)
        for p in chosen:
            secs = max(15, int(round((p["duration_seconds"] * scale) / 5.0) * 5))
            p["duration_seconds"] = secs
            p["duration_label"] = f"{secs} seconds"

        sens_text = f" (protecting: {', '.join(mem_ctx['sensitivities'])})" if mem_ctx["sensitivities"] else ""
        return {
            "session_title": f"{goal} — {age_group}",
            "age_group": age_group,
            "goal": goal,
            "safety_note": f"Move within a comfortable, pain-free range{sens_text}. Keep a sturdy chair nearby for support.",
            "breathing_warmup": {
                "name": "Balloon Belly Breathing" if "Kids" in age_group else "Calm 4-4 Box Rhythm Breathing",
                "duration": "2 minutes",
                "steps": [
                    "Sit upright with both feet grounded on the floor and shoulders relaxed.",
                    "Inhale gently through your nose for a slow count of 4.",
                    "Exhale softly for a count of 4, letting jaw and shoulder tension melt away.",
                ],
            },
            "poses": chosen,
            "daily_wellness_tip": "Take a 60-second posture reset and sip water every hour during the day.",
        }

    # --- TOOL 3: SAFETY & MEMORY SELF-CRITIC ---
    def tool_safety_and_memory_critic(self, routine, age_group, goal, mem_ctx):
        issues = []
        poses = routine.get("poses", [])
        sens_joined = " ".join(mem_ctx["sensitivities"]).lower()
        is_senior = "Senior" in age_group or "75+" in age_group
        is_chair = "Chair" in goal
        is_kid = "Kids" in age_group
        has_knee_issue = any(k in sens_joined for k in ["knee", "knees", "joint", "arthritis", "hip"])
        has_back_issue = any(k in sens_joined for k in ["back", "spine", "neck", "dizzy", "vertigo"])

        # High-risk keywords for vulnerable groups
        risky_for_knees_or_seniors = ["kneel", "lunge", "warrior", "pigeon", "squat", "crow", "wheel", "headstand", "plow"]
        risky_for_chair = ["floor", "mat", "kneel", "stand", "standing", "lie down", "lying"]
        risky_for_back = ["deep backbend", "wheel", "plow", "headstand", "shoulderstand"]

        recent_lower = {p.lower() for p in mem_ctx["recent_poses"][-4:]}

        for idx, pose in enumerate(poses):
            blob = (
                f"{pose.get('english_name', '')} {' '.join(pose.get('easy_steps', []))}"
            ).lower()

            if (is_senior or has_knee_issue) and any(w in blob for w in risky_for_knees_or_seniors):
                issues.append((idx, f"'{pose.get('english_name')}' places excess load on knees/balance for {age_group}."))
            elif is_chair and any(w in blob for w in risky_for_chair) and "chair" not in blob:
                issues.append((idx, f"'{pose.get('english_name')}' is not chair-based for Chair Yoga mode."))
            elif has_back_issue and any(w in blob for w in risky_for_back):
                issues.append((idx, f"'{pose.get('english_name')}' risks spinal/neck strain given comfort notes."))
            elif pose.get("english_name", "").lower() in recent_lower and len(poses) > 2:
                issues.append((idx, f"'{pose.get('english_name')}' was practiced recently—swapping for variety."))

            # Enforce safe hold duration bounds
            secs = int(pose.get("duration_seconds", 30) or 30)
            if is_kid and secs > 30:
                pose["duration_seconds"] = 20
                pose["duration_label"] = "20 seconds (fun & active)"
            elif is_senior and secs > 45:
                pose["duration_seconds"] = 35
                pose["duration_label"] = "35 seconds (gentle pace)"

        # Optional LLM second-opinion safety critique when Gemini Free key is active
        if self.cfg.get("provider") == "gemini_free" and self.cfg.get("gemini_api_key", "").strip() and not issues:
            try:
                critic_prompt = (
                    f"Audit this yoga routine JSON for safety for '{age_group}', goal '{goal}', "
                    f"sensitivities '{sens_joined}'. Reply ONLY JSON: "
                    f'{{"safe": true/false, "flagged_index": -1, "reason": "..."}}.\n'
                    f"Routine: {json.dumps(poses)[:2200]}"
                )
                verdict = self._call_gemini(critic_prompt)
                if isinstance(verdict, dict) and verdict.get("safe") is False:
                    f_idx = int(verdict.get("flagged_index", 0))
                    if 0 <= f_idx < len(poses):
                        issues.append((f_idx, verdict.get("reason", "Flagged by AI Safety Critic.")))
            except Exception:
                pass

        if issues:
            self.log_step("3. Safety & Memory Critic", f"Flagged {len(issues)} item(s): " + "; ".join(r for _, r in issues))
        else:
            self.log_step("3. Safety & Memory Critic", "Passed all age-safety, sensitivity, and novelty checks.")
        return issues

    # --- TOOL 4: SELF-REVISION LOOP ---
    def tool_revise_routine(self, routine, issues):
        if not issues:
            self.log_step("4. Self-Revision", "No revisions needed — routine approved.")
            return routine

        poses = routine.get("poses", [])
        used_names = {p.get("english_name", "").lower() for p in poses}
        replacements_made = []

        for idx, reason in issues:
            if not (0 <= idx < len(poses)):
                continue
            old_name = poses[idx].get("english_name", "Pose")
            # Pick an unused verified chair/joint-safe replacement pose
            replacement = None
            for candidate in SAFE_POSE_POOL:
                if candidate["english_name"].lower() not in used_names:
                    replacement = json.loads(json.dumps(candidate))
                    break
            if replacement is None:
                replacement = json.loads(json.dumps(SAFE_POSE_POOL[idx % len(SAFE_POSE_POOL)]))

            poses[idx] = replacement
            used_names.add(replacement["english_name"].lower())
            replacements_made.append(f"Replaced '{old_name}' -> '{replacement['english_name']}'")

        routine["poses"] = poses
        self.log_step("4. Self-Revision", " | ".join(replacements_made))
        return routine

    # --- MAIN AGENT ORCHESTRATOR ---
    def run(self, age_group, goal, pose_count, custom_note):
        mem_ctx = self.tool_recall_memory(age_group, custom_note)
        routine = self.tool_draft_routine(age_group, goal, pose_count, mem_ctx)
        issues = self.tool_safety_and_memory_critic(routine, age_group, goal, mem_ctx)
        routine = self.tool_revise_routine(routine, issues)
        self.update_memory_after_session(routine)

        routine["agent_trace"] = self.trace
        routine["memory_snapshot"] = {
            "total_sessions": self.memory["total_sessions"],
            "progression_level": self.memory["progression_level"],
            "remembered_sensitivities": self.memory["remembered_sensitivities"],
        }
        return routine


def record_session_feedback(rating, session_title):
    mem = get_memory()
    mem.setdefault("feedback_history", []).append(
        {"time": time.strftime("%Y-%m-%d %H:%M"), "session": session_title, "rating": rating}
    )
    mem["feedback_history"] = mem["feedback_history"][-20:]

    if rating == "too_hard":
        mem["progression_level"] = "Gentle Starter"
    elif rating == "too_easy" and mem.get("total_sessions", 0) >= 2:
        mem["progression_level"] = "Steady Explorer"

    save_json(MEMORY_FILE, mem)
    return mem


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Daily Yoga AI Agent — Autonomous Coach for Every Age</title>
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
    .brand h1 { margin: 0; font-size: 1.55em; }
    .brand p { margin: 4px 0 0; opacity: 0.92; font-size: 0.95em; }
    .top-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
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
    .container { max-width: 1040px; margin: 24px auto 60px; padding: 0 18px; }
    .tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
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
    .tab-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 22px;
      box-shadow: 0 4px 16px rgba(31,45,41,0.04);
      margin-bottom: 20px;
    }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; }
    label { display: block; font-weight: 700; margin-bottom: 6px; font-size: 0.95em; }
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
    .agent-trace-box {
      background: #f0f5f9;
      border: 1px solid #c8d8e6;
      border-radius: 12px;
      padding: 12px 16px;
      margin: 14px 0;
      font-size: 0.92em;
    }
    .agent-trace-box summary {
      cursor: pointer;
      font-weight: 700;
      color: #1f4666;
    }
    .trace-step {
      margin-top: 8px;
      padding-left: 10px;
      border-left: 3px solid #4a7ea8;
    }
    .warmup-box { background: var(--accent); border-radius: 12px; padding: 16px 18px; margin-bottom: 20px; }
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
    @media (max-width: 780px) { .pose-card { grid-template-columns: 1fr; } }
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
    }
    .pose-visual img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .badge {
      display: inline-block;
      background: var(--accent);
      color: var(--primary-dark);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.84em;
      font-weight: 700;
    }
    .steps-list { padding-left: 20px; margin: 10px 0; }
    .steps-list li { margin-bottom: 7px; }
    .mod-tip {
      background: #f4f8f6;
      border-left: 4px solid var(--primary);
      padding: 10px 12px;
      border-radius: 6px;
      font-size: 0.94em;
      margin-top: 10px;
    }
    .timer-bar { display: flex; align-items: center; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
    .timer-display { font-weight: 800; font-variant-numeric: tabular-nums; color: var(--primary-dark); font-size: 1.05em; }
    .feedback-bar {
      background: #f7faf8;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
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
      header, .tabs, #generator-card, .timer-bar, .feedback-bar, .no-print { display: none !important; }
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
        <p>Autonomous Yoga &amp; Mobility Coach with Memory &amp; Safety Self-Review</p>
      </div>
      <div class="top-controls">
        <button class="pill-btn" onclick="changeFontSize(-0.1)" title="Smaller text">A-</button>
        <button class="pill-btn" onclick="changeFontSize(0.1)" title="Larger text">A+</button>
        <button class="pill-btn" onclick="switchTab('memory')">🧠 Agent Memory</button>
        <button class="pill-btn" onclick="switchTab('settings')">⚙️ Settings</button>
      </div>
    </div>
  </header>

  <div class="container">
    <div class="tabs">
      <button id="tab-practice" class="tab-btn active" onclick="switchTab('practice')">✨ Create &amp; Practice Yoga</button>
      <button id="tab-saved" class="tab-btn" onclick="switchTab('saved')">📚 Saved Routines (<span id="saved-count">0</span>)</button>
      <button id="tab-memory" class="tab-btn" onclick="switchTab('memory')">🧠 Agent Memory &amp; Progress</button>
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
              <option value="Kids (Ages 5-12)">Kids (Ages 5–12) — Fun &amp; Playful</option>
              <option value="Teens (Ages 13-19)">Teens (Ages 13–19) — Focus &amp; Posture</option>
              <option value="Adults (Ages 20-55)" selected>Adults (Ages 20–55) — Everyday Balance</option>
              <option value="Seniors (Ages 56-75)">Seniors (Ages 56–75) — Joint &amp; Balance Care</option>
              <option value="Gentle Senior / Assisted (75+)">Gentle Care (Ages 75+) — Chair &amp; Supported</option>
            </select>
          </div>
          <div>
            <label for="goal">2. Choose Your Wellness Goal</label>
            <select id="goal">
              <option value="Morning Energy & Wake-Up">☀️ Morning Energy &amp; Wake-Up</option>
              <option value="Stress & Anxiety Relief">🌿 Stress &amp; Anxiety Relief</option>
              <option value="Back, Neck & Desk Posture Relief">🪑 Back, Neck &amp; Desk Posture Relief</option>
              <option value="Flexibility & Joint Mobility">🤸 Flexibility &amp; Joint Mobility</option>
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
          <label for="custom-note">4. Comfort Note (Agent remembers this across future sessions)</label>
          <input type="text" id="custom-note" placeholder="e.g., stiff knees, lower back tightness, beginner..." />
        </div>
        <button id="generate-btn" class="primary-btn" onclick="generateRoutine()">
          🧘 Generate &amp; Safety-Audit My Routine
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

    <!-- AGENT MEMORY TAB -->
    <div id="view-memory" class="hidden">
      <div class="card">
        <h2 style="margin-top:0;">🧠 Autonomous Agent Memory</h2>
        <p style="color:var(--muted);">
          The agent uses this local memory before generating every session to avoid repetitive poses, protect joint sensitivities, and adapt difficulty.
        </p>
        <div id="memory-view-content"></div>
        <button class="secondary-btn" style="margin-top:14px;" onclick="resetAgentMemory()">🔄 Reset Agent Memory</button>
      </div>
    </div>

    <!-- SETTINGS TAB -->
    <div id="view-settings" class="hidden">
      <div class="card">
        <h2 style="margin-top:0;">100% Free AI Configuration</h2>
        <p>
          <strong>Ready Out of the Box:</strong> Works immediately at <strong>$0 cost with no API key required</strong>.
          Optionally connect a free Google Gemini API key (no credit card required) for LLM-powered critique &amp; planning.
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
        </div>
        <div style="margin-bottom:16px;">
          <label for="cfg-pollinations">Optional Free Pollinations Key</label>
          <input type="password" id="cfg-pollinations" placeholder="pk_... (Leave blank for built-in free images)" />
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
      ["practice", "saved", "memory", "settings"].forEach(t => {
        document.getElementById("view-" + t).classList.toggle("hidden", t !== name);
        document.getElementById("tab-" + t).classList.toggle("active", t === name);
      });
      if (name === "saved") loadSavedRoutines();
      if (name === "memory") loadMemoryView();
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
      const figures = {
        mountain: `<circle cx="150" cy="48" r="12" fill="#2f6f5e"/><path d="M150 62 L150 112 M150 74 L125 40 M150 74 L175 40 M150 112 L136 162 M150 112 L164 162" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        tree: `<circle cx="150" cy="48" r="12" fill="#2f6f5e"/><path d="M150 62 L150 112 M150 75 L132 58 L150 44 M150 75 L168 58 L150 44 M150 112 L150 164 M150 112 L174 132 L152 142" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        cat_cow: `<circle cx="96" cy="95" r="11" fill="#2f6f5e"/><path d="M108 102 Q150 78 192 104 M115 103 L112 152 M186 105 L190 152" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        seated_twist: `<circle cx="150" cy="56" r="12" fill="#2f6f5e"/><path d="M150 70 L150 124 M150 86 L122 104 M150 86 L180 96 M150 124 L118 148 L155 154 M150 124 L182 148 L145 154" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`,
        child: `<circle cx="102" cy="136" r="11" fill="#2f6f5e"/><path d="M114 136 Q152 114 186 138 L164 152 L198 152 M112 144 L76 148" stroke="#2f6f5e" stroke-width="6" stroke-linecap="round" fill="none"/>`
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
        osc.type = "sine";
        osc.frequency.setValueAtTime(528, ctx.currentTime);
        gain.gain.setValueAtTime(0.12, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.1);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 1.1);
      } catch (e) {}
    }

    function renderRoutine(routine) {
      currentRoutine = routine;
      const container = document.getElementById("routine-output");
      container.classList.remove("hidden");

      const traceHtml = (routine.agent_trace || []).map(step => `
        <div class="trace-step">
          <strong>${escapeHtml(step.phase)}:</strong> ${escapeHtml(step.detail)}
        </div>
      `).join("");

      const warmupSteps = (routine.breathing_warmup?.steps || [])
        .map(s => `<li>${escapeHtml(s)}</li>`).join("");

      const posesHtml = (routine.poses || []).map((pose, idx) => {
        const imgPrompt = pose.image_prompt || `gentle yoga pose ${pose.english_name} for ${routine.age_group}, soft watercolor illustration`;
        const imgUrl = `/api/pose-image?prompt=${encodeURIComponent(imgPrompt)}&seed=${idx + 101}`;
        const steps = (pose.easy_steps || []).map(st => `<li>${escapeHtml(st)}</li>`).join("");
        const secs = parseInt(pose.duration_seconds, 10) || 30;

        return `
          <div class="pose-card">
            <div class="pose-visual">
              <img src="${imgUrl}" alt="${escapeHtml(pose.english_name)}" onerror="handlePoseImgError(this, ${idx})" />
            </div>
            <div>
              <span class="badge">Pose ${idx + 1} • ${escapeHtml(pose.duration_label || secs + " seconds")}</span>
              <h3 style="margin:8px 0 4px;">${escapeHtml(pose.english_name)} <span style="font-weight:400;color:var(--muted);">(${escapeHtml(pose.sanskrit_name || "")})</span></h3>
              <p style="margin:4px 0 8px;color:var(--primary-dark);font-weight:600;">✨ ${escapeHtml(pose.benefit)}</p>
              <ol class="steps-list">${steps}</ol>
              <div class="mod-tip">
                <strong>Age-Friendly Tip:</strong> ${escapeHtml(pose.age_modification)}
              </div>
              <div class="timer-bar no-print">
                <button class="secondary-btn" onclick="startPoseTimer(${idx}, ${secs})">⏱️ Start ${secs}s Hold Timer</button>
                <span id="timer-val-${idx}" class="timer-display"></span>
              </div>
            </div>
          </div>
        `;
      }).join("");

      container.innerHTML = `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
            <div>
              <span class="badge">${escapeHtml(routine.age_group)} • ${escapeHtml(routine._source || "AI Yoga Coach")}</span>
              <h2 style="margin:8px 0 4px;">${escapeHtml(routine.session_title)}</h2>
            </div>
            <div class="no-print" style="display:flex;gap:8px;flex-wrap:wrap;">
              <button class="secondary-btn" onclick="saveCurrentRoutine()">💾 Save Routine</button>
              <button class="secondary-btn" onclick="window.print()">🖨️ Print / PDF</button>
            </div>
          </div>

          ${traceHtml ? `
          <details class="agent-trace-box no-print" open>
            <summary>🧠 Agent Reasoning, Memory &amp; Safety Self-Review Log (${routine.agent_trace.length} steps)</summary>
            ${traceHtml}
          </details>` : ""}

          <div class="safety-box">
            <strong>🛡️ Safety First:</strong> ${escapeHtml(routine.safety_note)}
          </div>

          <div class="warmup-box">
            <h3 style="margin:0 0 6px;">🌬️ Warm-Up: ${escapeHtml(routine.breathing_warmup?.name || "Calm Breathing")} (${escapeHtml(routine.breathing_warmup?.duration || "2 mins")})</h3>
            <ol class="steps-list" style="margin-bottom:0;">${warmupSteps}</ol>
          </div>

          ${posesHtml}

          <div class="safety-box" style="background:#eef6f3;border-color:#c2ddd3;margin-bottom:0;">
            <strong>🌱 Daily Wellness Tip:</strong> ${escapeHtml(routine.daily_wellness_tip)}
          </div>

          <div class="feedback-bar no-print">
            <span><strong>Teach the Agent:</strong> How did today's difficulty feel?</span>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button class="secondary-btn" onclick="sendFeedback('too_easy')">🌱 Too Gentle</button>
              <button class="secondary-btn" onclick="sendFeedback('just_right')">😊 Just Right</button>
              <button class="secondary-btn" onclick="sendFeedback('too_hard')">⚠️ Too Intense</button>
            </div>
            <span id="feedback-status" style="font-weight:700;color:var(--primary);"></span>
          </div>
        </div>
      `;
      container.scrollIntoView({ behavior: "smooth" });
    }

    async function generateRoutine() {
      const btn = document.getElementById("generate-btn");
      btn.disabled = true;
      btn.textContent = "🧠 Agent checking memory, drafting & auditing safety...";

      try {
        const res = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            age_group: document.getElementById("age-group").value,
            goal: document.getElementById("goal").value,
            pose_count: document.getElementById("pose-count").value,
            custom_note: document.getElementById("custom-note").value.trim()
          })
        });
        const data = await res.json();
        renderRoutine(data);
      } catch (err) {
        alert("Could not generate routine. Please try again.");
      } finally {
        btn.disabled = false;
        btn.textContent = "🧘 Generate & Safety-Audit My Routine";
      }
    }

    async function sendFeedback(rating) {
      if (!currentRoutine) return;
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: rating, session_title: currentRoutine.session_title })
      });
      const st = document.getElementById("feedback-status");
      if (st) st.textContent = "✅ Memory updated for next session!";
    }

    async function loadMemoryView() {
      const res = await fetch("/api/memory");
      const mem = await res.json();
      const el = document.getElementById("memory-view-content");
      el.innerHTML = `
        <div class="safety-box" style="background:#f4f8f6;border-color:#c6dcd3;">
          <p style="margin:4px 0;"><strong>Total Sessions Guided:</strong> ${mem.total_sessions || 0}</p>
          <p style="margin:4px 0;"><strong>Current Adaptive Level:</strong> ${escapeHtml(mem.progression_level || "Gentle Starter")}</p>
          <p style="margin:4px 0;"><strong>Remembered Comfort / Joint Notes:</strong> ${escapeHtml((mem.remembered_sensitivities || []).join(", ") || "None recorded yet")}</p>
          <p style="margin:4px 0;"><strong>Recent Poses Tracked (for Variety):</strong> ${escapeHtml((mem.recent_poses || []).slice(-6).join(", ") || "None yet")}</p>
        </div>
      `;
    }

    async function resetAgentMemory() {
      await fetch("/api/memory/reset", { method: "POST" });
      loadMemoryView();
      alert("✅ Agent memory cleared.");
    }

    async function saveCurrentRoutine() {
      if (!currentRoutine) return;
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentRoutine)
      });
      const data = await res.json();
      document.getElementById("saved-count").textContent = data.count;
      alert("✅ Routine saved!");
    }

    async function loadSavedRoutines() {
      const res = await fetch("/api/saved");
      const list = await res.json();
      document.getElementById("saved-count").textContent = list.length;
      const el = document.getElementById("saved-list");
      if (!list.length) {
        el.innerHTML = "<p>No saved routines yet. Create one and click <strong>Save Routine</strong>!</p>";
        return;
      }
      el.innerHTML = list.map((item, idx) => `
        <div class="saved-item">
          <div>
            <strong>${escapeHtml(item.session_title)}</strong><br/>
            <small style="color:var(--muted);">${escapeHtml(item.age_group)} • ${escapeHtml(item.saved_at || "")}</small>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="secondary-btn" onclick="openSaved(${idx})">▶️ Open</button>
            <button class="secondary-btn" onclick="deleteSaved(${idx})">🗑️</button>
          </div>
        </div>
      `).join("");
      window._savedCache = list;
    }

    function openSaved(idx) {
      const item = window._savedCache[idx];
      switchTab("practice");
      renderRoutine(item);
    }

    async function deleteSaved(idx) {
      await fetch("/api/delete-saved", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: idx })
      });
      loadSavedRoutines();
    }

    async function loadSettings() {
      const res = await fetch("/api/config");
      const cfg = await res.json();
      document.getElementById("cfg-provider").value = cfg.provider || "free_no_key";
      document.getElementById("cfg-gemini").value = cfg.gemini_api_key || "";
      document.getElementById("cfg-pollinations").value = cfg.pollinations_api_key || "";
    }

    async function saveSettings() {
      const payload = {
        provider: document.getElementById("cfg-provider").value,
        gemini_api_key: document.getElementById("cfg-gemini").value.trim(),
        pollinations_api_key: document.getElementById("cfg-pollinations").value.trim()
      };
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const st = document.getElementById("settings-status");
      st.textContent = "✅ Settings saved!";
      setTimeout(() => (st.textContent = ""), 3000);
    }

    loadSavedRoutines();
  </script>
</body>
</html>
"""


class YogaAgentHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            page = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif parsed.path == "/api/config":
            self.send_json(get_config())
        elif parsed.path == "/api/saved":
            self.send_json(load_json(SESSIONS_FILE, []))
        elif parsed.path == "/api/memory":
            self.send_json(get_memory())
        elif parsed.path == "/api/pose-image":
            params = urllib.parse.parse_qs(parsed.query)
            prompt = params.get("prompt", ["gentle yoga pose illustration"])[0]
            seed = params.get("seed", ["42"])[0]
            self.proxy_free_image(prompt, seed)
        else:
            self.send_response(404)
            self.end_headers()

    def proxy_free_image(self, prompt, seed):
        cfg = get_config()
        encoded = urllib.parse.quote(prompt[:400])
        pk = cfg.get("pollinations_api_key", "").strip()

        if pk:
            url = f"https://gen.pollinations.ai/image/{encoded}?model=flux&width=768&height=512&seed={seed}&nologo=true"
            headers = {"Authorization": f"Bearer {pk}", "User-Agent": "DailyYogaAIAgent/2.0"}
        else:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=512&seed={seed}&nologo=true"
            headers = {"User-Agent": "DailyYogaAIAgent/2.0"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=22) as resp:
                ctype = resp.headers.get("Content-Type", "image/jpeg")
                if not ctype.startswith("image/"):
                    raise ValueError("Non-image response")
                img_bytes = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(img_bytes)))
                self.end_headers()
                self.wfile.write(img_bytes)
        except Exception:
            self.send_response(502)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        body = self.read_json_body()

        if parsed.path == "/api/generate":
            agent = YogaCoachAgent()
            routine = agent.run(
                age_group=body.get("age_group", "Adults (Ages 20-55)"),
                goal=body.get("goal", "Morning Energy & Wake-Up"),
                pose_count=body.get("pose_count", 4),
                custom_note=body.get("custom_note", ""),
            )
            self.send_json(routine)
        elif parsed.path == "/api/feedback":
            mem = record_session_feedback(
                rating=body.get("rating", "just_right"),
                session_title=body.get("session_title", ""),
            )
            self.send_json({"ok": True, "memory": mem})
        elif parsed.path == "/api/memory/reset":
            save_json(MEMORY_FILE, DEFAULT_MEMORY)
            self.send_json({"ok": True})
        elif parsed.path == "/api/config":
            cfg = get_config()
            cfg.update(body)
            save_json(CONFIG_FILE, cfg)
            self.send_json({"ok": True})
        elif parsed.path == "/api/save":
            saved = load_json(SESSIONS_FILE, [])
            body["saved_at"] = time.strftime("%Y-%m-%d %H:%M")
            saved.insert(0, body)
            save_json(SESSIONS_FILE, saved[:50])
            self.send_json({"ok": True, "count": len(saved)})
        elif parsed.path == "/api/delete-saved":
            saved = load_json(SESSIONS_FILE, [])
            idx = int(body.get("index", -1))
            if 0 <= idx < len(saved):
                saved.pop(idx)
                save_json(SESSIONS_FILE, saved)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


def find_free_port(start=8765):
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


if __name__ == "__main__":
    port = find_free_port(8765)
    url = f"http://127.0.0.1:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), YogaAgentHandler)

    print("=" * 56)
    print("  Daily Yoga AI Agent v2 (Agentic Memory + Safety Critic)")
    print(f"  Open in your browser: {url}")
    print("  Keep this window open while practicing. Close to stop.")
    print("=" * 56)

    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Daily Yoga AI Agent. Namaste!")
        server.server_close()

# === END OF app.py ===