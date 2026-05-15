from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'parkease_secret'

# Always find parking.db relative to THIS file, not cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, 'parking.db')

def get_db():
    if not os.path.exists(DB):
        raise RuntimeError(
            f"parking.db not found at {DB} — run: python init_db.py"
        )
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@app.route('/')
def index():
    try:
        db = get_db()
        total_slots = db.execute("SELECT COUNT(*) FROM parking_slots").fetchone()[0]
        available   = db.execute("SELECT COUNT(*) FROM parking_slots WHERE is_available=1").fetchone()[0]
        active_book = db.execute("SELECT COUNT(*) FROM bookings WHERE status='active'").fetchone()[0]
        revenue     = db.execute("SELECT COALESCE(SUM(fee),0) FROM bookings WHERE status='completed'").fetchone()[0]
        db.close()
        return render_template('index.html',
            total_slots=total_slots, available=available,
            active_book=active_book, revenue=round(revenue, 2))
    except Exception as e:
        return f"<h2>Dashboard Error</h2><pre>{e}</pre><p>Run <b>python init_db.py</b> first.</p>", 500

@app.route('/slots')
def slots():
    try:
        db = get_db()
        all_slots = db.execute("SELECT * FROM parking_slots ORDER BY slot_type, slot_number").fetchall()
        db.close()
        return render_template('slots.html', slots=all_slots)
    except Exception as e:
        return f"<h2>Slots Error</h2><pre>{e}</pre>", 500

@app.route('/book', methods=['GET', 'POST'])
def book():
    try:
        db = get_db()
        if request.method == 'POST':
            license_plate = request.form.get('license_plate', '').strip().upper()
            slot_id       = request.form.get('slot_id', '')
            owner_name    = request.form.get('owner_name', '').strip()
            vehicle_type  = request.form.get('vehicle_type', '')
            contact       = request.form.get('contact', '').strip()

            if not all([license_plate, slot_id, owner_name, vehicle_type]):
                flash('All fields are required.', 'error')
                db.close()
                return redirect(url_for('book'))

            slot = db.execute(
                "SELECT * FROM parking_slots WHERE slot_id=? AND is_available=1",
                (slot_id,)).fetchone()
            if not slot:
                flash('That slot is no longer available. Pick another.', 'error')
                db.close()
                return redirect(url_for('book'))

            if slot['slot_type'] != vehicle_type:
                flash(f'Slot {slot["slot_number"]} is for {slot["slot_type"]}s only.', 'error')
                db.close()
                return redirect(url_for('book'))

            vehicle = db.execute(
                "SELECT * FROM vehicles WHERE license_plate=?", (license_plate,)).fetchone()
            if not vehicle:
                db.execute(
                    "INSERT INTO vehicles (owner_name, license_plate, vehicle_type, contact) VALUES (?,?,?,?)",
                    (owner_name, license_plate, vehicle_type, contact))
                db.commit()
                vehicle = db.execute(
                    "SELECT * FROM vehicles WHERE license_plate=?", (license_plate,)).fetchone()

            existing = db.execute(
                "SELECT booking_id FROM bookings WHERE vehicle_id=? AND status='active'",
                (vehicle['vehicle_id'],)).fetchone()
            if existing:
                flash('This vehicle already has an active booking.', 'error')
                db.close()
                return redirect(url_for('book'))

            db.execute("INSERT INTO bookings (vehicle_id, slot_id) VALUES (?,?)",
                       (vehicle['vehicle_id'], slot_id))
            db.commit()
            db.close()
            flash('Slot booked successfully!', 'success')
            return redirect(url_for('active_bookings'))

        avail_slots = db.execute(
            "SELECT * FROM available_slots_view ORDER BY slot_type, slot_number").fetchall()
        db.close()
        return render_template('book.html', slots=avail_slots)
    except Exception as e:
        return f"<h2>Booking Error</h2><pre>{e}</pre>", 500

@app.route('/active')
def active_bookings():
    try:
        db = get_db()
        bookings = db.execute(
            "SELECT * FROM active_bookings_view ORDER BY entry_time DESC").fetchall()
        db.close()
        return render_template('active.html', bookings=bookings)
    except Exception as e:
        return f"<h2>Active Bookings Error</h2><pre>{e}</pre>", 500

@app.route('/release/<int:booking_id>', methods=['POST'])
def release(booking_id):
    try:
        db = get_db()
        row = db.execute(
            "SELECT entry_time FROM bookings WHERE booking_id=? AND status='active'",
            (booking_id,)).fetchone()
        if not row:
            flash('Booking not found or already completed.', 'error')
            db.close()
            return redirect(url_for('active_bookings'))

        entry_str = row['entry_time']
        entry_dt  = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                entry_dt = datetime.strptime(entry_str, fmt)
                break
            except ValueError:
                continue
        if entry_dt is None:
            entry_dt = datetime.now()

        hours = max((datetime.now() - entry_dt).total_seconds() / 3600, 0.5)
        fee   = round(hours * 50, 2)

        db.execute(
            "UPDATE bookings SET status='completed', exit_time=CURRENT_TIMESTAMP, fee=? WHERE booking_id=?",
            (fee, booking_id))
        db.commit()
        db.close()
        flash(f'Slot released successfully. Fee charged: Rs.{fee}', 'success')
        return redirect(url_for('active_bookings'))
    except Exception as e:
        return f"<h2>Release Error</h2><pre>{e}</pre>", 500

@app.route('/logs')
def logs():
    try:
        db = get_db()
        all_logs = db.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100").fetchall()
        db.close()
        return render_template('logs.html', logs=all_logs)
    except Exception as e:
        return f"<h2>Logs Error</h2><pre>{e}</pre>", 500

if __name__ == '__main__':
    if not os.path.exists(DB):
        print("="*55)
        print("  ERROR: parking.db not found!")
        print("  Run this first:  python init_db.py")
        print("="*55)
    else:
        print("="*55)
        print("  parking.db found — OK")
        print("  Open: http://127.0.0.1:5000")
        print("="*55)
    app.run(debug=True)