-- Phase 1 schema for Dosing Pump panel board
-- Safe to run multiple times (uses IF NOT EXISTS where possible).

CREATE DATABASE IF NOT EXISTS dosing_pump;
USE dosing_pump;

-- 1) Live/periodic water readings (used by current script)
CREATE TABLE IF NOT EXISTS dosing_pump_water (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  water_value DECIMAL(10,3) NOT NULL,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_dosing_pump_water_timestamp (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 2) pH readings (panel chart/history)
CREATE TABLE IF NOT EXISTS dosing_pump_ph (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  ph_value DECIMAL(4,2) NOT NULL,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_dosing_pump_ph_timestamp (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 3) pH target range configuration (single active row expected)
CREATE TABLE IF NOT EXISTS dosing_pump_ph_range (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  first_range DECIMAL(4,2) NOT NULL,
  second_range DECIMAL(4,2) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 4) Chemical dosing configuration for panel + runtime logic
CREATE TABLE IF NOT EXISTS dosing_pump_chemical_config (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  chemical_name ENUM('acid', 'chlorine') NOT NULL,
  interval_liters DECIMAL(10,3) NOT NULL,
  pump_on_seconds DECIMAL(6,3) NOT NULL DEFAULT 0.250,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_dosing_pump_chemical_name (chemical_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 5) Pump activity log (important for audits and panel history)
CREATE TABLE IF NOT EXISTS dosing_pump_pump_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chemical_name ENUM('acid', 'chlorine') NOT NULL,
  started_at DATETIME NOT NULL,
  stopped_at DATETIME DEFAULT NULL,
  run_seconds DECIMAL(8,3) DEFAULT NULL,
  trigger_water_total_liters DECIMAL(12,3) DEFAULT NULL,
  notes VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (id),
  KEY idx_pump_events_started_at (started_at),
  KEY idx_pump_events_chemical_started (chemical_name, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 6) Daily summary cache table for quick dashboard loading
CREATE TABLE IF NOT EXISTS dosing_pump_water_daily (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usage_date DATE NOT NULL,
  total_water_liters DECIMAL(12,3) NOT NULL DEFAULT 0.000,
  avg_ph DECIMAL(4,2) DEFAULT NULL,
  acid_runs INT UNSIGNED NOT NULL DEFAULT 0,
  chlorine_runs INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_dosing_pump_water_daily_date (usage_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Default seed rows (won't duplicate because of unique key)
INSERT IGNORE INTO dosing_pump_chemical_config (chemical_name, interval_liters, pump_on_seconds, is_enabled)
VALUES
('acid', 100.000, 0.250, 1),
('chlorine', 100.000, 0.250, 1);

-- Optional: create one default pH range if no row exists
INSERT INTO dosing_pump_ph_range (first_range, second_range)
SELECT 7.00, 7.10
WHERE NOT EXISTS (SELECT 1 FROM dosing_pump_ph_range);
