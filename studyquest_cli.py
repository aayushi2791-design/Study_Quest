#!/usr/bin/env python3
"""
StudyQuest CLI — AI-Powered Gamified Study Planner
A command-line version of the StudyQuest web app.
"""

import sqlite3
import os
import sys
import json
import random
import math
import pickle
from datetime import datetime, date, timedelta
from collections import defaultdict

# ─── Optional ML ──────────────────────────────────────────────────────────────
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import accuracy_score
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studyquest.db")

# ══════════════════════════════════════════════════════════════════════════════
#  COLOURS & DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# Colours
CYAN   = "\033[96m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
MAGENTA= "\033[95m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

def c(text, colour): return f"{colour}{text}{RESET}"
def bold(text):      return f"{BOLD}{text}{RESET}"
def header(title):
    w = 60
    print(f"\n{CYAN}{'═'*w}{RESET}")
    print(f"{CYAN}  {BOLD}{title}{RESET}")
    print(f"{CYAN}{'═'*w}{RESET}")

def sub(title):
    print(f"\n{BLUE}── {bold(title)} ──{RESET}")

def info(msg):   print(f"  {CYAN}ℹ {msg}{RESET}")
def ok(msg):     print(f"  {GREEN}✔ {msg}{RESET}")
def warn(msg):   print(f"  {YELLOW}⚠ {msg}{RESET}")
def err(msg):    print(f"  {RED}✘ {msg}{RESET}")
def ask(prompt): return input(f"  {YELLOW}▶ {prompt}{RESET}").strip()

def xp_bar(xp, next_lvl_xp, width=30):
    filled = int((xp / next_lvl_xp) * width) if next_lvl_xp else width
    bar = f"{GREEN}{'█'*filled}{GRAY}{'░'*(width-filled)}{RESET}"
    return f"[{bar}] {xp}/{next_lvl_xp} XP"

def prod_bar(score, width=20):
    filled = int((score / 100) * width)
    colour = GREEN if score >= 60 else YELLOW if score >= 40 else RED
    return f"{colour}{'█'*filled}{'░'*(width-filled)}{RESET} {score:.0f}/100"

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c_ = conn.cursor()
    c_.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY DEFAULT 1,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_study_date TEXT,
        badges TEXT DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS study_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        duration_minutes INTEGER,
        focus_level INTEGER,
        had_distractions INTEGER DEFAULT 0,
        sleep_hours REAL DEFAULT 7.0,
        productivity_score REAL,
        session_date TEXT,
        time_of_day TEXT
    );

    CREATE TABLE IF NOT EXISTS study_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        target_hours REAL,
        deadline TEXT,
        is_completed INTEGER DEFAULT 0,
        created_at TEXT,
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        subject TEXT,
        recommended_time TEXT,
        xp_reward INTEGER,
        is_completed INTEGER DEFAULT 0,
        confidence REAL,
        quest_date TEXT
    );

    CREATE TABLE IF NOT EXISTS q_table (
        state_key TEXT,
        action_key TEXT,
        q_value REAL DEFAULT 0.0,
        PRIMARY KEY (state_key, action_key)
    );

    INSERT OR IGNORE INTO users (id) VALUES (1);
    """)
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
#  GAMIFICATION
# ══════════════════════════════════════════════════════════════════════════════

LEVEL_XP = [0, 100, 250, 500, 850, 1300, 1900, 2700, 3700, 5000]

def xp_for_next_level(level):
    if level >= len(LEVEL_XP):
        return LEVEL_XP[-1]
    return LEVEL_XP[level]

def get_xp_reward(score):
    if score >= 80: return 100
    if score >= 60: return 60
    return 25

def award_xp_and_level_up(conn, xp_gain):
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    new_xp = user["xp"] + xp_gain
    new_level = user["level"]
    leveled_up = False
    while new_level < 10 and new_xp >= xp_for_next_level(new_level):
        new_xp -= xp_for_next_level(new_level)
        new_level += 1
        leveled_up = True
    conn.execute("UPDATE users SET xp=?, level=? WHERE id=1", (new_xp, new_level))
    return leveled_up, new_level

def update_streak(conn, session_date_str):
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    today = date.fromisoformat(session_date_str)
    last = date.fromisoformat(user["last_study_date"]) if user["last_study_date"] else None
    if last is None:
        new_streak = 1
    elif (today - last).days == 1:
        new_streak = user["streak"] + 1
    elif (today - last).days == 0:
        new_streak = user["streak"]
    else:
        new_streak = 1
    conn.execute("UPDATE users SET streak=?, last_study_date=? WHERE id=1",
                 (new_streak, session_date_str))
    return new_streak

BADGES = {
    "night_owl":          ("🦉 Night Owl",          "5+ sessions at night (9PM-12AM)"),
    "early_bird":         ("🐦 Early Bird",          "5+ sessions in the morning (6-10AM)"),
    "consistent_learner": ("📅 Consistent Learner",  "7-day study streak"),
    "productivity_master":("⚡ Productivity Master", "Average productivity > 80"),
    "scholar":            ("🎓 Scholar",             "Reached Level 5"),
    "marathon_studier":   ("🏃 Marathon Studier",    "20+ total sessions"),
}

def check_and_award_badges(conn):
    user   = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    badges = json.loads(user["badges"] or "[]")
    new_badges = []

    sessions = conn.execute("SELECT * FROM study_sessions").fetchall()
    total    = len(sessions)
    night    = sum(1 for s in sessions if s["time_of_day"] == "night")
    morning  = sum(1 for s in sessions if s["time_of_day"] == "morning")
    avg_prod = (sum(s["productivity_score"] for s in sessions) / total) if total else 0

    def award(badge_id):
        if badge_id not in badges:
            badges.append(badge_id)
            new_badges.append(badge_id)

    if night   >= 5:       award("night_owl")
    if morning >= 5:       award("early_bird")
    if user["streak"] >= 7: award("consistent_learner")
    if avg_prod > 80:      award("productivity_master")
    if user["level"] >= 5: award("scholar")
    if total >= 20:        award("marathon_studier")

    conn.execute("UPDATE users SET badges=? WHERE id=1", (json.dumps(badges),))
    return new_badges

# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTIVITY SCORE
# ══════════════════════════════════════════════════════════════════════════════

def calc_productivity(duration_minutes, focus_level, had_distractions):
    focus_score    = (focus_level / 5) * 50
    duration_score = min(duration_minutes / 120, 1) * 30
    penalty        = 20 if had_distractions else 0
    return max(0, min(100, focus_score + duration_score - penalty))

def time_of_day(hour):
    if 6  <= hour < 12: return "morning"
    if 12 <= hour < 18: return "afternoon"
    if 18 <= hour < 21: return "evening"
    return "night"

# ══════════════════════════════════════════════════════════════════════════════
#  GOAL TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def check_goal_completion(conn, subject):
    row = conn.execute(
        "SELECT SUM(duration_minutes)/60.0 as hrs FROM study_sessions WHERE subject=?",
        (subject,)).fetchone()
    hours_done = row["hrs"] or 0
    goals = conn.execute(
        "SELECT * FROM study_goals WHERE subject=? AND is_completed=0", (subject,)).fetchall()
    completed = []
    for g in goals:
        if hours_done >= g["target_hours"]:
            conn.execute(
                "UPDATE study_goals SET is_completed=1, completed_at=? WHERE id=?",
                (datetime.now().isoformat(), g["id"]))
            completed.append(g)
    return completed

# ══════════════════════════════════════════════════════════════════════════════
#  ML MODULE (Random Forest)
# ══════════════════════════════════════════════════════════════════════════════

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sq_model.pkl")

def train_model(conn):
    if not ML_AVAILABLE:
        return None, 0
    sessions = conn.execute("SELECT * FROM study_sessions ORDER BY id").fetchall()
    if len(sessions) < 5:
        return None, 0

    time_map = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3}
    subjects  = list({s["subject"] for s in sessions})
    subj_enc  = {s: i for i, s in enumerate(subjects)}

    X, y = [], []
    scores = [s["productivity_score"] for s in sessions]
    for i, s in enumerate(sessions):
        avg5 = sum(scores[max(0, i-5):i]) / max(1, min(5, i))
        X.append([
            time_map.get(s["time_of_day"], 1),
            subj_enc.get(s["subject"], 0),
            s["sleep_hours"],
            avg5
        ])
        y.append(1 if s["productivity_score"] >= 60 else 0)

    X, y = np.array(X), np.array(y)
    if len(set(y)) < 2:
        return None, 0

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    clf.fit(X_tr, y_tr)
    acc = accuracy_score(y_te, clf.predict(X_te))

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": clf, "subjects": subjects, "subj_enc": subj_enc}, f)
    return clf, acc

def load_model():
    if not ML_AVAILABLE or not os.path.exists(MODEL_PATH):
        return None, None, None
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
    return data["model"], data["subjects"], data["subj_enc"]

def predict_productivity(subject, tod, sleep_hours, avg_prod):
    model, subjects, subj_enc = load_model()
    if model is None:
        return 0.5
    time_map = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3}
    features = [[
        time_map.get(tod, 1),
        subj_enc.get(subject, 0),
        sleep_hours,
        avg_prod
    ]]
    proba = model.predict_proba(np.array(features))[0]
    return proba[1] if len(proba) > 1 else 0.5

# ══════════════════════════════════════════════════════════════════════════════
#  RL MODULE (Q-Learning)
# ══════════════════════════════════════════════════════════════════════════════

ALPHA = 0.3
GAMMA = 0.8
EPSILON = 0.2
TIMES = ["morning", "afternoon", "evening", "night"]

def energy_level(sleep_hours, avg_prod):
    sleep_s = min(sleep_hours / 8.0, 1.0)
    perf_s  = avg_prod / 100.0
    combined = (sleep_s + perf_s) / 2
    if combined >= 0.65: return "high"
    if combined >= 0.40: return "medium"
    return "low"

def get_q(conn, state, action):
    row = conn.execute(
        "SELECT q_value FROM q_table WHERE state_key=? AND action_key=?",
        (state, action)).fetchone()
    return row["q_value"] if row else 0.0

def set_q(conn, state, action, value):
    conn.execute(
        "INSERT OR REPLACE INTO q_table (state_key, action_key, q_value) VALUES (?,?,?)",
        (state, action, value))

def record_session_feedback(conn, subject, tod, sleep_hours, avg_prod, productivity_score):
    energy = energy_level(sleep_hours, avg_prod)
    state  = f"{tod}_{energy}"
    action = f"{subject}_{tod}"
    reward = productivity_score / 100.0

    current_q = get_q(conn, state, action)
    # Next state: same energy, next time slot
    next_tod   = TIMES[(TIMES.index(tod) + 1) % 4]
    next_state = f"{next_tod}_{energy}"

    # Get all known actions for next state
    rows = conn.execute(
        "SELECT q_value FROM q_table WHERE state_key=?", (next_state,)).fetchall()
    max_next = max((r["q_value"] for r in rows), default=0.0)
    new_q    = current_q + ALPHA * (reward + GAMMA * max_next - current_q)
    set_q(conn, state, action, new_q)

def get_rl_recommendations(conn, sleep_hours, avg_prod):
    tod    = time_of_day(datetime.now().hour)
    energy = energy_level(sleep_hours, avg_prod)
    state  = f"{tod}_{energy}"
    rows   = conn.execute(
        "SELECT action_key, q_value FROM q_table WHERE state_key=? ORDER BY q_value DESC LIMIT 5",
        (state,)).fetchall()
    return [(r["action_key"].split("_")[0], r["action_key"].split("_")[1], r["q_value"])
            for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
#  QUEST GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_quests(conn):
    today = date.today().isoformat()
    existing = conn.execute(
        "SELECT * FROM quests WHERE quest_date=?", (today,)).fetchall()
    if existing:
        return existing

    sessions = conn.execute("SELECT * FROM study_sessions ORDER BY id DESC LIMIT 20").fetchall()
    avg_sleep = (sum(s["sleep_hours"] for s in sessions) / len(sessions)) if sessions else 7.0
    avg_prod  = (sum(s["productivity_score"] for s in sessions) / len(sessions)) if sessions else 50.0

    rl_recs = get_rl_recommendations(conn, avg_sleep, avg_prod)

    # Time pattern analysis
    pattern = defaultdict(list)
    for s in sessions:
        pattern[(s["subject"], s["time_of_day"])].append(s["productivity_score"])
    pattern_sorted = sorted(pattern.items(),
                            key=lambda x: sum(x[1])/len(x[1]), reverse=True)

    candidates = []
    for (subj, tod), scores in pattern_sorted[:5]:
        candidates.append((subj, tod, sum(scores)/len(scores), "pattern"))
    for subj, tod, q_val in rl_recs[:3]:
        candidates.append((subj, tod, q_val * 100, "rl"))

    seen = set()
    quests = []
    rewards = [100, 50, 150]
    descs   = ["RL recommends", "Pattern shows", "AI recommends"]
    for i, (subj, tod, priority, src) in enumerate(candidates):
        key = (subj, tod)
        if key in seen or len(quests) >= 3: break
        seen.add(key)
        conf = predict_productivity(subj, tod, avg_sleep, avg_prod)
        xp   = rewards[len(quests)]
        title = f"Study {subj} during {tod.capitalize()}"
        conn.execute(
            "INSERT INTO quests (title,subject,recommended_time,xp_reward,confidence,quest_date)"
            " VALUES (?,?,?,?,?,?)",
            (title, subj, tod, xp, conf, today))
        quests.append({"title": title, "subject": subj, "recommended_time": tod,
                       "xp_reward": xp, "confidence": conf})

    # Fill up to 3 quests with subjects if needed
    if len(quests) < 3:
        subjects = conn.execute("SELECT DISTINCT subject FROM study_sessions").fetchall()
        tods = ["morning", "afternoon", "evening"]
        for row in subjects:
            if len(quests) >= 3: break
            subj = row["subject"]
            tod  = tods[len(quests) % 3]
            if (subj, tod) in seen: continue
            seen.add((subj, tod))
            conf = 0.5
            xp   = rewards[len(quests)]
            title = f"Study {subj} during {tod.capitalize()}"
            conn.execute(
                "INSERT INTO quests (title,subject,recommended_time,xp_reward,confidence,quest_date)"
                " VALUES (?,?,?,?,?,?)",
                (title, subj, tod, xp, conf, today))
            quests.append({"title": title, "subject": subj, "recommended_time": tod,
                           "xp_reward": xp, "confidence": conf})

    conn.commit()
    return conn.execute("SELECT * FROM quests WHERE quest_date=?", (today,)).fetchall()

# ══════════════════════════════════════════════════════════════════════════════
#  POMODORO SCHEDULE
# ══════════════════════════════════════════════════════════════════════════════

def pomodoro_schedule(conn, goal_id):
    goal = conn.execute("SELECT * FROM study_goals WHERE id=?", (goal_id,)).fetchone()
    if not goal:
        return None, "Goal not found"

    done_row = conn.execute(
        "SELECT SUM(duration_minutes)/60.0 as h FROM study_sessions WHERE subject=?",
        (goal["subject"],)).fetchone()
    done = done_row["h"] or 0
    remaining_hours = max(0, goal["target_hours"] - done)

    if remaining_hours <= 0:
        return None, "Goal already complete!"

    # Best time slot for this subject
    best_tod = "morning"
    rows = conn.execute(
        "SELECT time_of_day, AVG(productivity_score) as avg FROM study_sessions"
        " WHERE subject=? GROUP BY time_of_day ORDER BY avg DESC LIMIT 1",
        (goal["subject"],)).fetchone()
    if rows:
        best_tod = rows["time_of_day"]

    # Days until deadline
    if goal["deadline"]:
        deadline = date.fromisoformat(goal["deadline"])
        days_left = max(1, (deadline - date.today()).days)
    else:
        days_left = max(1, math.ceil(remaining_hours * 2))

    blocks_total = math.ceil(remaining_hours * 60 / 25)
    blocks_per_day = math.ceil(blocks_total / days_left)

    tod_start = {"morning": 7, "afternoon": 13, "evening": 18, "night": 21}
    start_h = tod_start.get(best_tod, 9)

    schedule = []
    remaining_blocks = blocks_total
    for day_offset in range(days_left):
        if remaining_blocks <= 0: break
        today_blocks = min(blocks_per_day, remaining_blocks)
        day_date = date.today() + timedelta(days=day_offset)
        day_schedule = []
        for b in range(today_blocks):
            block_start = start_h * 60 + b * 30  # 25 min work + 5 min break
            h, m = divmod(block_start, 60)
            end_m = block_start + 25
            eh, em = divmod(end_m, 60)
            day_schedule.append(f"  🍅 {h:02d}:{m:02d} - {eh:02d}:{em:02d}")
        schedule.append((day_date, day_schedule))
        remaining_blocks -= today_blocks

    return schedule, None

# ══════════════════════════════════════════════════════════════════════════════
#  MENU ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def menu_dashboard(conn):
    header("📊  STUDYQUEST DASHBOARD")
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    badges = json.loads(user["badges"] or "[]")
    next_xp = xp_for_next_level(user["level"])

    sub("Player Status")
    print(f"  Level    : {c(user['level'], MAGENTA)} {c('⭐', YELLOW)}")
    print(f"  XP       : {xp_bar(user['xp'], next_xp)}")
    streak_val = user["streak"]
    print(f"  Streak   : {c(f'{streak_val} days 🔥', CYAN)}")
    if badges:
        badge_labels = [BADGES[b][0] for b in badges if b in BADGES]
        print(f"  Badges   : {c(', '.join(badge_labels), YELLOW)}")
    else:
        print(f"  Badges   : {GRAY}none yet{RESET}")

    sub("Active Goals")
    goals = conn.execute(
        "SELECT g.*, (SELECT COALESCE(SUM(s.duration_minutes),0)/60.0"
        " FROM study_sessions s WHERE s.subject=g.subject) as hours_done"
        " FROM study_goals g WHERE g.is_completed=0").fetchall()
    if goals:
        for g in goals:
            pct = min(100, (g["hours_done"] / g["target_hours"]) * 100)
            filled = int(pct / 5)
            bar = f"{GREEN}{'█'*filled}{GRAY}{'░'*(20-filled)}{RESET}"
            dl  = f"  deadline {g['deadline']}" if g["deadline"] else ""
            print(f"  {BOLD}{g['subject']}{RESET}{dl}")
            print(f"    [{bar}] {g['hours_done']:.1f}/{g['target_hours']}h ({pct:.0f}%)")
    else:
        info("No active goals. Add one via the Goals menu.")

    sub("Today's Quests")
    today = date.today().isoformat()
    quests = conn.execute("SELECT * FROM quests WHERE quest_date=?", (today,)).fetchall()
    if not quests:
        info("No quests yet. Generate from the Quests menu.")
    else:
        for q in quests:
            status = f"{GREEN}✔ DONE{RESET}" if q["is_completed"] else f"{YELLOW}◌ TODO{RESET}"
            conf_pct = f"{q['confidence']*100:.0f}%"
            print(f"  [{status}] {q['title']} — {c(str(q['xp_reward'])+' XP', CYAN)}"
                  f"  {c('(' + conf_pct + ' conf)', GRAY)}")

    sub("Recent Sessions")
    sessions = conn.execute(
        "SELECT * FROM study_sessions ORDER BY id DESC LIMIT 5").fetchall()
    if not sessions:
        info("No sessions logged yet.")
    else:
        print(f"  {'Subject':<18} {'Duration':>8} {'Score':>7} {'Date'}")
        print(f"  {GRAY}{'─'*50}{RESET}")
        for s in sessions:
            score_col = GREEN if s["productivity_score"] >= 60 else YELLOW
            print(f"  {s['subject']:<18} {s['duration_minutes']:>6}m"
                  f"  {score_col}{s['productivity_score']:>5.0f}{RESET}"
                  f"  {GRAY}{s['session_date']}{RESET}")


def menu_log_session(conn):
    header("📝  LOG STUDY SESSION")

    # Subject
    subjects = [r["subject"] for r in
                conn.execute("SELECT DISTINCT subject FROM study_sessions").fetchall()]
    if subjects:
        print(f"\n  Known subjects: {c(', '.join(subjects), CYAN)}")
    subject = ask("Subject name: ")
    if not subject:
        err("Subject required."); return

    # Duration
    try:
        duration = int(ask("Duration (minutes): "))
    except ValueError:
        err("Invalid duration."); return

    # Focus
    print(f"\n  Focus level: {GRAY}1=very low … 5=maximum{RESET}")
    try:
        focus = int(ask("Focus level (1-5): "))
        focus = max(1, min(5, focus))
    except ValueError:
        err("Invalid focus."); return

    # Distractions
    dist_in = ask("Had distractions? (y/n): ").lower()
    had_dist = 1 if dist_in.startswith("y") else 0

    # Sleep
    try:
        sleep = float(ask("Hours of sleep last night: "))
    except ValueError:
        sleep = 7.0

    # Time of day
    tod_now = time_of_day(datetime.now().hour)
    tod_in  = ask(f"Time of day [{tod_now}] (morning/afternoon/evening/night): ").lower()
    tod = tod_in if tod_in in TIMES else tod_now

    # Calculate
    score    = calc_productivity(duration, focus, had_dist)
    xp_gain  = get_xp_reward(score)
    today    = date.today().isoformat()

    conn.execute("""
        INSERT INTO study_sessions
        (subject, duration_minutes, focus_level, had_distractions, sleep_hours,
         productivity_score, session_date, time_of_day)
        VALUES (?,?,?,?,?,?,?,?)
    """, (subject, duration, focus, had_dist, sleep, score, today, tod))

    # Goal check
    completed_goals = check_goal_completion(conn, subject)

    # RL update
    sessions = conn.execute("SELECT productivity_score FROM study_sessions ORDER BY id DESC LIMIT 5").fetchall()
    avg_prod = sum(s["productivity_score"] for s in sessions) / len(sessions)
    record_session_feedback(conn, subject, tod, sleep, avg_prod, score)

    # XP & level
    leveled_up, new_level = award_xp_and_level_up(conn, xp_gain)
    new_streak = update_streak(conn, today)
    new_badges = check_and_award_badges(conn)

    # Retrain every 5 sessions
    total = conn.execute("SELECT COUNT(*) as n FROM study_sessions").fetchone()["n"]
    if total % 5 == 0 and ML_AVAILABLE:
        _, acc = train_model(conn)
        if acc:
            info(f"ML model retrained — accuracy: {acc*100:.1f}%")

    conn.commit()

    print()
    print(f"  {BOLD}Productivity Score:{RESET}  {prod_bar(score)}")
    ok(f"XP earned: +{xp_gain}")
    ok(f"Streak: {new_streak} day(s) 🔥")
    if leveled_up:
        print(f"\n  {YELLOW}{'★'*40}{RESET}")
        print(f"  {YELLOW}🎉  LEVEL UP!  You are now Level {new_level}!  🎉{RESET}")
        print(f"  {YELLOW}{'★'*40}{RESET}")
    for badge_id in new_badges:
        name, desc = BADGES.get(badge_id, (badge_id, ""))
        print(f"\n  {MAGENTA}🏅 Badge Unlocked: {name}{RESET}")
        print(f"     {GRAY}{desc}{RESET}")
    for g in completed_goals:
        print(f"\n  {GREEN}🎯 Goal Completed: {g['subject']} — {g['target_hours']}h!{RESET}")


def menu_quests(conn):
    header("⚔️   DAILY QUESTS")
    sessions = conn.execute("SELECT * FROM study_sessions ORDER BY id DESC LIMIT 20").fetchall()
    if not sessions:
        warn("Log at least one session to generate quests.")
        return

    quests = generate_quests(conn)
    if not quests:
        warn("Couldn't generate quests. Add more subjects and sessions.")
        return

    print()
    for i, q in enumerate(quests, 1):
        status = f"{GREEN}✔ COMPLETE{RESET}" if q["is_completed"] else f"{YELLOW}◌ ACTIVE{RESET}"
        print(f"  {BOLD}[{i}]{RESET} {status}  {c(q['title'], WHITE)}")
        conf_pct2 = str(round(q["confidence"]*100)) + "%"
        xp_s = str(q["xp_reward"]) + " XP"
        tod_s = q["recommended_time"].capitalize()
        print(f"       {CYAN}{xp_s}{RESET}  |  Confidence: {c(conf_pct2, MAGENTA)}  |  Best time: {tod_s}")
    print()
    choice = ask("Mark quest as complete (1/2/3) or press Enter to skip: ")
    if choice in ("1","2","3"):
        idx = int(choice) - 1
        if idx < len(quests):
            q = quests[idx]
            if q["is_completed"]:
                warn("Quest already completed."); return
            conn.execute("UPDATE quests SET is_completed=1 WHERE id=?", (q["id"],))
            leveled_up, new_level = award_xp_and_level_up(conn, q["xp_reward"] + 50)
            conn.commit()
            ok(f"Quest completed! +{q['xp_reward']+50} XP")
            if leveled_up:
                print(f"\n  {YELLOW}🎉 LEVEL UP — You are now Level {new_level}!{RESET}")


def menu_goals(conn):
    while True:
        header("🎯  GOALS")
        goals = conn.execute("""
            SELECT g.*, 
                   (SELECT COALESCE(SUM(s.duration_minutes),0)/60.0
                    FROM study_sessions s WHERE s.subject=g.subject) as hours_done
            FROM study_goals g ORDER BY g.is_completed, g.id
        """).fetchall()

        if not goals:
            info("No goals yet.")
        else:
            print(f"\n  {'#':<4} {'Subject':<18} {'Progress':>20} {'Deadline':<12} {'Status'}")
            print(f"  {GRAY}{'─'*65}{RESET}")
            for i, g in enumerate(goals, 1):
                pct    = min(100, (g["hours_done"] / g["target_hours"]) * 100)
                status = f"{GREEN}✔ Done{RESET}" if g["is_completed"] else f"{YELLOW}Active{RESET}"
                dl     = g["deadline"] or "—"
                print(f"  {i:<4} {g['subject']:<18} "
                      f"{g['hours_done']:.1f}/{g['target_hours']:.0f}h ({pct:.0f}%){' ':>5}"
                      f" {dl:<12} {status}")

        print(f"\n  {GRAY}a{RESET}) Add goal   "
              f"{GRAY}p{RESET}) Pomodoro schedule   "
              f"{GRAY}b{RESET}) Back")
        ch = ask("Choice: ").lower()

        if ch == "b":
            break
        elif ch == "a":
            subjects = [r["subject"] for r in
                        conn.execute("SELECT DISTINCT subject FROM study_sessions").fetchall()]
            if subjects:
                print(f"  Known subjects: {c(', '.join(subjects), CYAN)}")
            subj = ask("Subject: ")
            if not subj: continue
            try:
                target = float(ask("Target hours: "))
            except ValueError:
                err("Invalid number."); continue
            dl = ask("Deadline (YYYY-MM-DD) or Enter to skip: ")
            if dl:
                try: date.fromisoformat(dl)
                except ValueError: err("Invalid date."); continue
            else:
                dl = None
            conn.execute(
                "INSERT INTO study_goals (subject, target_hours, deadline, created_at)"
                " VALUES (?,?,?,?)",
                (subj, target, dl, datetime.now().isoformat()))
            conn.commit()
            ok(f"Goal added: {target}h of {subj}")

        elif ch == "p":
            if not goals:
                warn("No goals yet."); continue
            try:
                idx = int(ask("Goal number for Pomodoro schedule: ")) - 1
            except ValueError:
                continue
            if 0 <= idx < len(goals):
                schedule, error = pomodoro_schedule(conn, goals[idx]["id"])
                if error:
                    warn(error)
                else:
                    sub(f"Pomodoro Schedule — {goals[idx]['subject']}")
                    for day, blocks in (schedule or [])[:7]:
                        print(f"\n  {BOLD}{day.strftime('%A, %d %b')}{RESET}")
                        for b in blocks:
                            print(c(b, CYAN))
                    input(f"\n  {GRAY}Press Enter to continue…{RESET}")


def menu_analytics(conn):
    header("📈  ANALYTICS")
    sessions = conn.execute("SELECT * FROM study_sessions ORDER BY id").fetchall()

    if not sessions:
        info("No sessions yet."); return

    total      = len(sessions)
    total_hrs  = sum(s["duration_minutes"] for s in sessions) / 60
    avg_prod   = sum(s["productivity_score"] for s in sessions) / total
    avg_focus  = sum(s["focus_level"] for s in sessions) / total

    sub("Overall Stats")
    print(f"  Sessions logged : {c(total, CYAN)}")
    print(f"  Total study time: {c(f'{total_hrs:.1f}h', CYAN)}")
    print(f"  Avg productivity: {prod_bar(avg_prod)}")
    print(f"  Avg focus level : {avg_focus:.1f}/5")

    # Time-of-day breakdown
    sub("Performance by Time of Day")
    tod_map = defaultdict(list)
    for s in sessions:
        tod_map[s["time_of_day"]].append(s["productivity_score"])
    for tod in TIMES:
        if tod in tod_map:
            avg = sum(tod_map[tod]) / len(tod_map[tod])
            count = len(tod_map[tod])
            print(f"  {tod.capitalize():<12} {prod_bar(avg, 15)} ({count} sessions)")

    # Subject breakdown
    sub("Performance by Subject")
    subj_map = defaultdict(list)
    for s in sessions:
        subj_map[s["subject"]].append(s["productivity_score"])
    for subj, scores in sorted(subj_map.items(), key=lambda x: -sum(x[1])/len(x[1])):
        avg = sum(scores)/len(scores)
        print(f"  {subj:<20} {prod_bar(avg, 15)} ({len(scores)} sessions)")

    # Last 14 days chart (ASCII)
    sub("Last 14 Days — Productivity")
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    recent = [s for s in sessions if s["session_date"] >= cutoff]
    day_map = defaultdict(list)
    for s in recent:
        day_map[s["session_date"]].append(s["productivity_score"])
    for i in range(14):
        d = (date.today() - timedelta(days=13-i)).isoformat()
        avg = sum(day_map[d])/len(day_map[d]) if d in day_map else None
        label = date.fromisoformat(d).strftime("%d %b")
        if avg is None:
            print(f"  {GRAY}{label}  ─{RESET}")
        else:
            filled = int(avg / 5)
            colour = GREEN if avg >= 60 else YELLOW
            bar = f"{colour}{'▓'*filled}{GRAY}{'·'*(20-filled)}{RESET}"
            print(f"  {label}  {bar} {avg:.0f}")

    # ML info
    if ML_AVAILABLE and os.path.exists(MODEL_PATH):
        sub("ML Model")
        _, acc = train_model(conn)
        if acc:
            print(f"  Random Forest accuracy: {c(f'{acc*100:.1f}%', GREEN)}")
            print(f"  Top features: avg_past_productivity, sleep_hours, time_of_day")

    input(f"\n  {GRAY}Press Enter to continue…{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

BANNER = f"""{CYAN}
  ╔═══════════════════════════════════════════╗
  ║  {BOLD}StudyQuest CLI{RESET}{CYAN} — AI Gamified Study Planner  ║
  ╚═══════════════════════════════════════════╝{RESET}
"""

def main():
    init_db()
    conn = get_db()

    print(BANNER)
    if not ML_AVAILABLE:
        warn("scikit-learn not installed — ML features disabled.")
        warn("Install with: pip install scikit-learn numpy")

    while True:
        print(f"""
  {BOLD}MAIN MENU{RESET}
  {CYAN}1{RESET}) Dashboard        {CYAN}2{RESET}) Log Session
  {CYAN}3{RESET}) Daily Quests     {CYAN}4{RESET}) Goals
  {CYAN}5{RESET}) Analytics        {CYAN}q{RESET}) Quit
""")
        ch = ask("Choice: ")
        if ch == "1":   menu_dashboard(conn)
        elif ch == "2": menu_log_session(conn)
        elif ch == "3": menu_quests(conn)
        elif ch == "4": menu_goals(conn)
        elif ch == "5": menu_analytics(conn)
        elif ch.lower() == "q":
            print(f"\n  {CYAN}Keep studying! 🎓  Goodbye.{RESET}\n")
            break
        else:
            warn("Invalid choice.")

    conn.close()

if __name__ == "__main__":
    main()
