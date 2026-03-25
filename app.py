from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import os
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rampwalk-annual-function-2024')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# In-memory state (will be loaded from file)
state = {
    "current_round": None,  # "round1" or "round2"
    "round1_scores": {},    # {participant_id: {guest_id: score}}
    "round2_scores": {},    # {participant_id: {guest_id: score}}
    "guests": {},           # {guest_id: guest_name}
    "participants": {
        "boys": [
            {"id": "b3", "name": "PRIYANSH", "number": 3},
            {"id": "b4", "name": "SANGAM", "number": 4},
            {"id": "b5", "name": "ABHISHEK", "number": 5},
            {"id": "b6", "name": "DIPANSHU", "number": 6},
            {"id": "b7", "name": "KULDEEP", "number": 7},
            {"id": "b8", "name": "HARSHAL", "number": 8},
            {"id": "b9", "name": "PRANAY", "number": 9}
        ],
        "girls": [
            {"id": "g1", "name": "NIKITA", "number": 1},
            {"id": "g2", "name": "DIVYA", "number": 2},
            {"id": "g3", "name": "SUMATI", "number": 3},
            {"id": "g4", "name": "AARYA", "number": 4},
            {"id": "g5", "name": "SEJAL", "number": 5},
            {"id": "g6", "name": "SHIVANI", "number": 6},
            {"id": "g7", "name": "ANJALI", "number": 7},
            {"id": "g8", "name": "DEEPIKA", "number": 8},
            {"id": "g9", "name": "PRIYANKA", "number": 9},
            {"id": "g10", "name": "POOJA", "number": 10},
            {"id": "g11", "name": "RIYA", "number": 11}
        ]
    },
    "couples": [
        {"id": "c1", "p1_id": "g1", "p2_id": "g2", "theme": "Couple 1"},
        {"id": "c3", "p1_id": "b3", "p2_id": "g3", "theme": "Couple 3"},
        {"id": "c4", "p1_id": "b4", "p2_id": "g4", "theme": "Couple 4"},
        {"id": "c5", "p1_id": "b5", "p2_id": "g5", "theme": "Couple 5"},
        {"id": "c6", "p1_id": "b6", "p2_id": "g6", "theme": "Couple 6"},
        {"id": "c7", "p1_id": "b7", "p2_id": "g7", "theme": "Couple 7"},
        {"id": "c8", "p1_id": "b8", "p2_id": "g8", "theme": "Couple 8"},
        {"id": "c9", "p1_id": "b9", "p2_id": "g9", "theme": "Couple 9"},
        {"id": "c10", "p1_id": "g10", "p2_id": "g11", "theme": "Couple 10"},
    ],
    "setup_done": False,
    "winners": {}
}

import threading
state_lock = threading.Lock()

def load_state():
    global state
    if os.path.exists('data.json'):
        try:
            with open('data.json', 'r') as f:
                loaded = json.load(f)
                state.update(loaded)
        except Exception as e:
            pass

def save_state():
    with state_lock:
        try:
            with open('data.json', 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            pass

load_state()

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))
        return render_template('login.html', error="Invalid password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/join')
def join_page():
    return render_template('join.html')

@app.route('/guest/<guest_id>')
def guest_panel(guest_id):
    if guest_id not in state["guests"]:
        return render_template('join.html')
    return render_template('guest.html', guest_id=guest_id, guest_name=state["guests"][guest_id])

@app.route('/anchor')
def anchor():
    return render_template('anchor.html')

# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/setup', methods=['POST'])
def setup():
    if not session.get('admin'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    # Setup guests only if explicitly provided (prevents wiping live guests on later saves)
    if "guests" in data:
        state["guests"] = {}
        for g in data.get("guests", []):
            state["guests"][g["id"]] = g["name"]
    elif "guests" not in state:
        state["guests"] = {}
    
    # Setup participants based on specific id, name, and number
    state["participants"]["boys"] = data.get("boys", state["participants"]["boys"])
    state["participants"]["girls"] = data.get("girls", state["participants"]["girls"])
    
    # Setup couples
    state["couples"] = data.get("couples", state["couples"])
    
    # Only reset scores if explicitly asked (to prevent accidental wipe mid-event)
    if data.get("reset_scores"):
        state["round1_scores"] = {}
        state["round2_scores"] = {}
        state["current_round"] = None
        state["winners"] = {}
        
    state["setup_done"] = True
    save_state()
    socketio.emit('state_update', get_public_state())
    return jsonify({"success": True, "guests": state["guests"]})

@app.route('/api/guest_register', methods=['POST'])
def guest_register():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not state["setup_done"]:
        return jsonify({"error": "Event is not setup yet. Please wait."}), 400
    # If the same name already exists, return the same ID
    for gid, gname in state["guests"].items():
        if gname.lower() == name.lower():
            return jsonify({"success": True, "guest_id": gid, "guest_name": gname})
    guest_id = "g_" + uuid.uuid4().hex[:8]
    state["guests"][guest_id] = name
    save_state()
    socketio.emit('guest_joined', {"guest_id": guest_id, "guest_name": name})
    socketio.emit('state_update', get_public_state())
    return jsonify({"success": True, "guest_id": guest_id, "guest_name": name})

@app.route('/api/start_round', methods=['POST'])
def start_round():
    if not session.get('admin'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    round_name = data.get("round")
    if round_name in ["round1", "round2"]:
        state["current_round"] = round_name
        save_state()
        socketio.emit('round_started', {"round": round_name})
        socketio.emit('state_update', get_public_state())
        return jsonify({"success": True, "round": round_name})
    return jsonify({"error": "Invalid round"}), 400

@app.route('/api/submit_score', methods=['POST'])
def submit_score():
    data = request.json
    guest_id = data.get("guest_id")
    target_id = data.get("target_id")  # participant or couple id
    scores = data.get("scores", {})    # {look: 10, walk: 10, dress: 10, extra: 10}
    round_name = data.get("round")

    if guest_id not in state["guests"]:
        return jsonify({"error": "Invalid guest"}), 400
    
    # Calculate total and validate individual scores
    total_score = 0
    categories = ["look", "walk", "dress", "extra"]
    for cat in categories:
        val = int(scores.get(cat, 0))
        if not (1 <= val <= 10):
            return jsonify({"error": f"{cat.capitalize()} score must be 1-10"}), 400
        total_score += val

    score_dict = state["round1_scores"] if round_name == "round1" else state["round2_scores"]
    if target_id not in score_dict:
        score_dict[target_id] = {}
    
    # Store the breakdown as well as the total for the UI
    score_dict[target_id][guest_id] = {
        "total": total_score,
        "breakdown": scores
    }
    save_state()

    # Broadcast live score update to anchor
    socketio.emit('score_update', {
        "round": round_name,
        "target_id": target_id,
        "guest_id": guest_id,
        "guest_name": state["guests"][guest_id],
        "score": total_score, # Keep 'score' for backward compatibility in anchor's total
        "scores": score_dict
    })
    return jsonify({"success": True, "total": total_score})

@app.route('/api/finalize_round2', methods=['POST'])
def finalize_round2():
    if not session.get('admin'):
        return jsonify({"error": "Unauthorized"}), 401
    results = compute_results()
    state["winners"] = results
    save_state()
    socketio.emit('winners_announced', {"winners": results})
    return jsonify({"success": True, "winners": results})

@app.route('/api/state')
def get_state():
    return jsonify(get_public_state())

@app.route('/api/scores')
def get_scores():
    return jsonify({"round1": state["round1_scores"], "round2": state["round2_scores"]})

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_public_state():
    return {
        "current_round": state["current_round"],
        "guests": state["guests"],
        "participants": state["participants"],
        "couples": state["couples"],
        "setup_done": state["setup_done"],
        "winners": state["winners"]
    }

def compute_round1_totals():
    totals = {}
    for pid, gscores in state["round1_scores"].items():
        total = 0
        for g_data in gscores.values():
            if isinstance(g_data, dict):
                total += g_data.get("total", 0)
            else:
                total += g_data # Fallback for legacy data
        totals[pid] = total
    return totals

def compute_round2_totals():
    totals = {}
    for pid, gscores in state["round2_scores"].items():
        total = 0
        for g_data in gscores.values():
            if isinstance(g_data, dict):
                total += g_data.get("total", 0)
            else:
                total += g_data # Fallback for legacy data
        totals[pid] = total
    return totals

def compute_results():
    participant_totals = {}
    for boy in state["participants"]["boys"]:
        participant_totals[boy["id"]] = 0
    for girl in state["participants"]["girls"]:
        participant_totals[girl["id"]] = 0
        
    for pid, gscores in state["round1_scores"].items():
        if pid in participant_totals:
            for g_data in gscores.values():
                if isinstance(g_data, dict):
                    participant_totals[pid] += g_data.get("total", 0)
                else:
                    participant_totals[pid] += g_data
            
    for pid, gscores in state["round2_scores"].items():
        if pid in participant_totals:
            for g_data in gscores.values():
                if isinstance(g_data, dict):
                    participant_totals[pid] += g_data.get("total", 0)
                else:
                    participant_totals[pid] += g_data
            
    boys = sorted([p for p in state["participants"]["boys"]], key=lambda x: participant_totals.get(x["id"], 0), reverse=True)
    girls = sorted([p for p in state["participants"]["girls"]], key=lambda x: participant_totals.get(x["id"], 0), reverse=True)
    
    top_boys = []
    for rank, boy in enumerate(boys[:3], 1):
        theme = next((c["theme"] for c in state["couples"] if c.get("p1_id") == boy["id"] or c.get("p2_id") == boy["id"]), "")
        top_boys.append({
            "rank": rank,
            "id": boy["id"],
            "name": boy["name"],
            "theme": theme,
            "total_score": participant_totals.get(boy["id"], 0)
        })
        
    top_girls = []
    for rank, girl in enumerate(girls[:3], 1):
        theme = next((c["theme"] for c in state["couples"] if c.get("p1_id") == girl["id"] or c.get("p2_id") == girl["id"]), "")
        top_girls.append({
            "rank": rank,
            "id": girl["id"],
            "name": girl["name"],
            "theme": theme,
            "total_score": participant_totals.get(girl["id"], 0)
        })
        
    return {"boys": top_boys, "girls": top_girls}

# ─── SocketIO Events ─────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    emit('state_update', get_public_state())

@socketio.on('join_anchor')
def on_join_anchor():
    join_room('anchor')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
