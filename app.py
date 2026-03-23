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

# In-memory state (resets on server restart)
state = {
    "current_round": None,  # "round1" or "round2"
    "round1_scores": {},    # {participant_id: {guest_id: score}}
    "round2_scores": {},    # {couple_id: {guest_id: score}}
    "guests": {},           # {guest_id: guest_name}
    "participants": {
        "boys": [{"id": f"b{i}", "name": f"Boy {i}", "number": i} for i in range(1, 11)],
        "girls": [{"id": f"g{i}", "name": f"Girl {i}", "number": i} for i in range(1, 11)]
    },
    "couples": [
        {"id": f"c{i}", "boy_id": f"b{i}", "girl_id": f"g{i}", "theme": f"Couple {i}"} 
        for i in range(1, 11)
    ],
    "setup_done": False,
    "winners": []
}

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
    # Setup guests
    state["guests"] = {}
    for g in data.get("guests", []):
        state["guests"][g["id"]] = g["name"]
    # Setup participants
    boys = data.get("boys", [])
    girls = data.get("girls", [])
    state["participants"]["boys"] = [{"id": f"b{i+1}", "name": boys[i], "number": i+1} for i in range(len(boys))]
    state["participants"]["girls"] = [{"id": f"g{i+1}", "name": girls[i], "number": i+1} for i in range(len(girls))]
    # Setup couples with themes
    couples = data.get("couples", [])
    state["couples"] = []
    for i, c in enumerate(couples):
        state["couples"].append({
            "id": f"c{i+1}",
            "boy_id": f"b{i+1}",
            "girl_id": f"g{i+1}",
            "theme": c.get("theme", f"Couple {i+1}"),
            "boy_name": boys[i] if i < len(boys) else f"Boy {i+1}",
            "girl_name": girls[i] if i < len(girls) else f"Girl {i+1}"
        })
    state["round1_scores"] = {}
    state["round2_scores"] = {}
    state["current_round"] = None
    state["setup_done"] = True
    state["winners"] = []
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
        socketio.emit('round_started', {"round": round_name})
        socketio.emit('state_update', get_public_state())
        return jsonify({"success": True, "round": round_name})
    return jsonify({"error": "Invalid round"}), 400

@app.route('/api/submit_score', methods=['POST'])
def submit_score():
    data = request.json
    guest_id = data.get("guest_id")
    target_id = data.get("target_id")  # participant or couple id
    score = data.get("score")
    round_name = data.get("round")

    if guest_id not in state["guests"]:
        return jsonify({"error": "Invalid guest"}), 400
    if not (1 <= int(score) <= 10):
        return jsonify({"error": "Score must be 1-10"}), 400

    score_dict = state["round1_scores"] if round_name == "round1" else state["round2_scores"]
    if target_id not in score_dict:
        score_dict[target_id] = {}
    score_dict[target_id][guest_id] = int(score)

    # Broadcast live score update to anchor
    socketio.emit('score_update', {
        "round": round_name,
        "target_id": target_id,
        "guest_id": guest_id,
        "guest_name": state["guests"][guest_id],
        "score": int(score),
        "scores": score_dict
    })
    return jsonify({"success": True})

@app.route('/api/finalize_round2', methods=['POST'])
def finalize_round2():
    if not session.get('admin'):
        return jsonify({"error": "Unauthorized"}), 401
    results = compute_results()
    state["winners"] = results
    socketio.emit('winners_announced', {"winners": results})
    return jsonify({"success": True, "winners": results})

@app.route('/api/state')
def get_state():
    return jsonify(get_public_state())

@app.route('/api/scores')
def get_scores():
    r1 = compute_round1_totals()
    r2 = compute_round2_totals()
    return jsonify({"round1": r1, "round2": r2})

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
        totals[pid] = sum(gscores.values())
    return totals

def compute_round2_totals():
    totals = {}
    for cid, gscores in state["round2_scores"].items():
        totals[cid] = {"total": sum(gscores.values()), "scores": gscores}
    return totals

def compute_results():
    totals = compute_round2_totals()
    sorted_couples = sorted(totals.items(), key=lambda x: x[1]["total"], reverse=True)
    results = []
    for rank, (cid, data) in enumerate(sorted_couples[:2], 1):
        couple = next((c for c in state["couples"] if c["id"] == cid), None)
        if couple:
            results.append({
                "rank": rank,
                "couple_id": cid,
                "boy_name": couple.get("boy_name", ""),
                "girl_name": couple.get("girl_name", ""),
                "theme": couple.get("theme", ""),
                "total_score": data["total"]
            })
    return results

# ─── SocketIO Events ─────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    emit('state_update', get_public_state())

@socketio.on('join_anchor')
def on_join_anchor():
    join_room('anchor')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
