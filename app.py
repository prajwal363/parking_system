from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3, os, io, base64
from datetime import datetime
import qrcode

app = Flask(__name__)
app.secret_key = 'parkease_secret_2024'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, 'parking.db')

ADMIN_USER = 'admin'
ADMIN_PASS = 'parkease123'

def get_db():
    if not os.path.exists(DB):
        raise RuntimeError(f"parking.db not found — run: python init_db.py")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def make_qr(data):
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode()

# ── PUBLIC ROUTES ─────────────────────────────────────────

@app.route('/')
def index():
    try:
        db = get_db()
        total_slots = db.execute("SELECT COUNT(*) FROM parking_slots").fetchone()[0]
        available   = db.execute("SELECT COUNT(*) FROM parking_slots WHERE is_available=1").fetchone()[0]
        active_book = db.execute("SELECT COUNT(*) FROM bookings WHERE status='active'").fetchone()[0]
        db.close()
        return render_template('public_index.html', total_slots=total_slots, available=available, active_book=active_book)
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/slots')
def slots():
    try:
        db = get_db()
        all_slots = db.execute(
            "SELECT * FROM parking_slots ORDER BY slot_type, SUBSTR(slot_number,1,1), CAST(SUBSTR(slot_number,2) AS INTEGER)"
        ).fetchall()
        db.close()
        return render_template('slots.html', slots=all_slots)
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/book', methods=['GET', 'POST'])
def book():
    try:
        db = get_db()
        if request.method == 'POST':
            license_plate = request.form.get('license_plate','').strip().upper()
            slot_id       = request.form.get('slot_id','')
            owner_name    = request.form.get('owner_name','').strip()
            vehicle_type  = request.form.get('vehicle_type','')
            contact       = request.form.get('contact','').strip()

            if not all([license_plate, slot_id, owner_name, vehicle_type]):
                flash('All fields are required.', 'error')
                db.close()
                return redirect(url_for('book'))

            slot = db.execute(
                "SELECT * FROM parking_slots WHERE slot_id=? AND is_available=1", (slot_id,)).fetchone()
            if not slot:
                flash('That slot is no longer available.', 'error')
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
            booking = db.execute(
                "SELECT booking_id FROM bookings WHERE vehicle_id=? AND status='active'",
                (vehicle['vehicle_id'],)).fetchone()
            booking_id = booking['booking_id']
            db.close()

            # Generate QR code with booking_id
            qr_data = f"PARKEASE|{booking_id}"
            qr_b64  = make_qr(qr_data)

            return render_template('booking_success.html',
                booking_id=booking_id,
                owner_name=owner_name,
                license_plate=license_plate,
                slot_number=slot['slot_number'],
                qr_b64=qr_b64)

        avail_slots = db.execute(
            "SELECT * FROM available_slots_view ORDER BY slot_type, SUBSTR(slot_number,1,1), CAST(SUBSTR(slot_number,2) AS INTEGER)"
        ).fetchall()
        db.close()
        return render_template('book.html', slots=avail_slots)
    except Exception as e:
        return f"<h2>Booking Error</h2><pre>{e}</pre>", 500

# ── ADMIN ROUTES ──────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USER and request.form.get('password') == ADMIN_PASS:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Wrong username or password.', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        db = get_db()
        total_slots = db.execute("SELECT COUNT(*) FROM parking_slots").fetchone()[0]
        available   = db.execute("SELECT COUNT(*) FROM parking_slots WHERE is_available=1").fetchone()[0]
        active_book = db.execute("SELECT COUNT(*) FROM bookings WHERE status='active'").fetchone()[0]
        revenue     = db.execute("SELECT COALESCE(SUM(fee),0) FROM bookings WHERE status='completed'").fetchone()[0]
        db.close()
        return render_template('index.html',
            total_slots=total_slots, available=available,
            active_book=active_book, revenue=round(revenue,2))
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/admin/active')
@admin_required
def active_bookings():
    try:
        db = get_db()
        bookings = db.execute("SELECT * FROM active_bookings_view ORDER BY entry_time DESC").fetchall()
        db.close()
        return render_template('active.html', bookings=bookings)
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/admin/logs')
@admin_required
def logs():
    try:
        db = get_db()
        all_logs = db.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100").fetchall()
        db.close()
        return render_template('logs.html', logs=all_logs)
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/admin/release/<int:booking_id>', methods=['POST'])
@admin_required
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
                entry_dt = datetime.strptime(entry_str, fmt); break
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
        flash(f'Slot released. Fee charged: Rs.{fee}', 'success')
        return redirect(url_for('active_bookings'))
    except Exception as e:
        return f"<h2>Error</h2><pre>{e}</pre>", 500

@app.route('/admin/scanner')
@admin_required
def scanner():
    return render_template('scanner.html')

@app.route('/admin/scan_release', methods=['POST'])
@admin_required
def scan_release():
    try:
        data = request.form.get('qr_data','').strip()
        # QR format: PARKEASE|booking_id
        if not data.startswith('PARKEASE|'):
            return {'success': False, 'message': 'Invalid QR code'}, 400

        booking_id = int(data.split('|')[1])
        db = get_db()
        row = db.execute(
            """SELECT b.booking_id, b.entry_time, v.owner_name, v.license_plate,
                      s.slot_number, v.vehicle_type
               FROM bookings b
               JOIN vehicles v      ON b.vehicle_id = v.vehicle_id
               JOIN parking_slots s ON b.slot_id    = s.slot_id
               WHERE b.booking_id=? AND b.status='active'""",
            (booking_id,)).fetchone()

        if not row:
            db.close()
            return {'success': False, 'message': 'Booking not found or already released'}, 404

        entry_str = row['entry_time']
        entry_dt  = None
        for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S.%f'):
            try:
                entry_dt = datetime.strptime(entry_str, fmt); break
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

        return {
            'success': True,
            'booking_id': booking_id,
            'owner_name': row['owner_name'],
            'license_plate': row['license_plate'],
            'slot_number': row['slot_number'],
            'vehicle_type': row['vehicle_type'],
            'hours': round(hours, 2),
            'fee': fee
        }
    except Exception as e:
        return {'success': False, 'message': str(e)}, 500

if __name__ == '__main__':
    if not os.path.exists(DB):
        print("ERROR: parking.db not found! Run: python init_db.py")
    else:
        print("="*55)
        print("  ParkEase running at http://127.0.0.1:5000")
        print("  Public booking : http://127.0.0.1:5000/")
        print("  Admin login    : http://127.0.0.1:5000/admin/login")
        print("  Admin user     : admin")
        print("  Admin password : parkease123")
        print("="*55)
    app.run(debug=True)