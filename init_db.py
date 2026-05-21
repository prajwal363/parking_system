"""
Run this ONCE before starting the Flask app:
    python init_db.py
It creates parking.db with all tables, triggers, views, and sample data.
"""
import sqlite3, os

DB = 'parking.db'

def init():
    if os.path.exists(DB):
        print(f"⚠  {DB} already exists. Delete it first to re-initialise.")
        return

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript("""
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────
--  TABLES
-- ─────────────────────────────────────────
CREATE TABLE vehicles (
    vehicle_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_name    TEXT NOT NULL,
    license_plate TEXT UNIQUE NOT NULL,
    vehicle_type  TEXT NOT NULL CHECK(vehicle_type IN ('car','bike','truck')),
    contact       TEXT
);

CREATE TABLE parking_slots (
    slot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_number  TEXT UNIQUE NOT NULL,
    slot_type    TEXT NOT NULL CHECK(slot_type IN ('car','bike','truck')),
    floor        INTEGER DEFAULT 1,
    is_available INTEGER DEFAULT 1
);

CREATE TABLE bookings (
    booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    slot_id    INTEGER NOT NULL,
    entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    exit_time  DATETIME,
    fee        REAL DEFAULT 0,
    status     TEXT DEFAULT 'active' CHECK(status IN ('active','completed')),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (slot_id)    REFERENCES parking_slots(slot_id)
);

CREATE TABLE audit_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    booking_id  INTEGER,
    slot_id     INTEGER,
    vehicle_id  INTEGER,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    details     TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
);

-- ─────────────────────────────────────────
--  TRIGGERS
-- ─────────────────────────────────────────
CREATE TRIGGER update_slot_on_booking
AFTER INSERT ON bookings
BEGIN
    UPDATE parking_slots SET is_available = 0 WHERE slot_id = NEW.slot_id;
END;

CREATE TRIGGER update_slot_on_release
AFTER UPDATE ON bookings
WHEN NEW.status = 'completed'
BEGIN
    UPDATE parking_slots SET is_available = 1 WHERE slot_id = NEW.slot_id;
END;

CREATE TRIGGER log_new_booking
AFTER INSERT ON bookings
BEGIN
    INSERT INTO audit_logs (action_type, booking_id, slot_id, vehicle_id, details)
    VALUES ('BOOKING_CREATED', NEW.booking_id, NEW.slot_id, NEW.vehicle_id,
            'New booking created at ' || NEW.entry_time);
END;

CREATE TRIGGER log_booking_release
AFTER UPDATE ON bookings
WHEN NEW.status = 'completed'
BEGIN
    INSERT INTO audit_logs (action_type, booking_id, slot_id, vehicle_id, details)
    VALUES ('SLOT_RELEASED', NEW.booking_id, NEW.slot_id, NEW.vehicle_id,
            'Booking completed. Fee: Rs.' || NEW.fee);
END;

-- ─────────────────────────────────────────
--  VIEWS (Stored Procedures equivalent)
-- ─────────────────────────────────────────
CREATE VIEW available_slots_view AS
SELECT slot_id, slot_number, slot_type, floor
FROM parking_slots
WHERE is_available = 1;

CREATE VIEW active_bookings_view AS
SELECT b.booking_id, v.owner_name, v.license_plate, v.vehicle_type,
       s.slot_number, s.floor, b.entry_time
FROM bookings b
JOIN vehicles v ON b.vehicle_id = v.vehicle_id
JOIN parking_slots s ON b.slot_id = s.slot_id
WHERE b.status = 'active';

CREATE VIEW daily_revenue_view AS
SELECT DATE(exit_time) AS date,
       COUNT(*)        AS total_bookings,
       SUM(fee)        AS total_revenue
FROM bookings
WHERE status = 'completed'
GROUP BY DATE(exit_time);

-- ─────────────────────────────────────────
--  SAMPLE DATA
-- ─────────────────────────────────────────
INSERT OR IGNORE INTO parking_slots (slot_number, slot_type, floor) VALUES
  ('A1','car',1),('A2','car',1),('A3','car',1),('A4','car',1),('A5','car',1),
  ('A6','car',2),('A7','car',2),('A8','car',3),('A9','car',3),('A10','car',3),
  ('B1','bike',1),('B2','bike',1),('B3','bike',1),('B4','bike',1),('B5','bike',1),
  ('B6','bike',2),('B7','bike',2),('B8','bike',2),('B9','bike',3),('B10','bike',3),
  ('C1','truck',2),('C2','truck',2),('C3','truck',2),('C4','truck',2),
  ('C5','truck',3),('C6','truck',3),('C7','truck',3),('C8','truck',3);


""")
    conn.commit()
    conn.close()
    print(f"✅  {DB} created with tables, triggers, views and sample data.")
    print("    You can now open it in DB Browser for SQLite to verify.")
    print("    Then run:  python app.py")

if __name__ == '__main__':
    init()