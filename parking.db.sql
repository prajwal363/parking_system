-- Table 1: Vehicles
CREATE TABLE vehicles (
    vehicle_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_name   TEXT NOT NULL,
    license_plate TEXT UNIQUE NOT NULL,
    vehicle_type TEXT CHECK(vehicle_type IN ('car','bike','truck')) NOT NULL,
    contact      TEXT
);

-- Table 2: Parking Slots
CREATE TABLE parking_slots (
    slot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_number  TEXT UNIQUE NOT NULL,
    slot_type    TEXT CHECK(slot_type IN ('car','bike','truck')) NOT NULL,
    floor        INTEGER DEFAULT 1,
    is_available INTEGER DEFAULT 1  -- 1=available, 0=occupied
);

-- Table 3: Bookings
CREATE TABLE bookings (
    booking_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id   INTEGER NOT NULL,
    slot_id      INTEGER NOT NULL,
    entry_time   DATETIME DEFAULT CURRENT_TIMESTAMP,
    exit_time    DATETIME,
    fee          REAL DEFAULT 0,
    status       TEXT DEFAULT 'active' CHECK(status IN ('active','completed')),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (slot_id) REFERENCES parking_slots(slot_id)
);

-- Table 4: Audit Logs
CREATE TABLE audit_logs (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type  TEXT NOT NULL,
    booking_id   INTEGER,
    slot_id      INTEGER,
    vehicle_id   INTEGER,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
    details      TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
);
-- Trigger 1: Mark slot OCCUPIED when booking is created
CREATE TRIGGER update_slot_on_booking
AFTER INSERT ON bookings
BEGIN
    UPDATE parking_slots
    SET is_available = 0
    WHERE slot_id = NEW.slot_id;
END;

-- Trigger 2: Mark slot AVAILABLE when booking is completed
CREATE TRIGGER update_slot_on_release
AFTER UPDATE ON bookings
WHEN NEW.status = 'completed'
BEGIN
    UPDATE parking_slots
    SET is_available = 1
    WHERE slot_id = NEW.slot_id;
END;

-- Trigger 3: Auto-log every new booking into audit_logs
CREATE TRIGGER log_new_booking
AFTER INSERT ON bookings
BEGIN
    INSERT INTO audit_logs (action_type, booking_id, slot_id, vehicle_id, details)
    VALUES ('BOOKING_CREATED', NEW.booking_id, NEW.slot_id, NEW.vehicle_id,
            'New booking created at ' || NEW.entry_time);
END;

-- Trigger 4: Auto-log every booking completion
CREATE TRIGGER log_booking_release
AFTER UPDATE ON bookings
WHEN NEW.status = 'completed'
BEGIN
    INSERT INTO audit_logs (action_type, booking_id, slot_id, vehicle_id, details)
    VALUES ('SLOT_RELEASED', NEW.booking_id, NEW.slot_id, NEW.vehicle_id,
            'Booking completed. Fee: ' || NEW.fee);
END;
-- View 1: Available slots with details
CREATE VIEW available_slots_view AS
SELECT s.slot_id, s.slot_number, s.slot_type, s.floor
FROM parking_slots s
WHERE s.is_available = 1;

-- View 2: Active bookings with vehicle and slot info
CREATE VIEW active_bookings_view AS
SELECT b.booking_id, v.owner_name, v.license_plate, v.vehicle_type,
       s.slot_number, s.floor, b.entry_time
FROM bookings b
JOIN vehicles v ON b.vehicle_id = v.vehicle_id
JOIN parking_slots s ON b.slot_id = s.slot_id
WHERE b.status = 'active';

-- View 3: Revenue summary per day
CREATE VIEW daily_revenue_view AS
SELECT DATE(exit_time) as date,
       COUNT(*) as total_bookings,
       SUM(fee) as total_revenue
FROM bookings
WHERE status = 'completed'
GROUP BY DATE(exit_time);