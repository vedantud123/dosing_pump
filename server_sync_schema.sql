CREATE DATABASE IF NOT EXISTS dosing_pump;
USE dosing_pump;

CREATE TABLE IF NOT EXISTS dosing_clients (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id VARCHAR(64) NOT NULL,
  mac_address VARCHAR(17) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_clients_mac (mac_address),
  UNIQUE KEY uq_clients_client_id (client_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- generate a client_id for old rows if missing
UPDATE dosing_clients
SET client_id = CONCAT('CL-', LPAD(id, 6, '0'))
WHERE client_id IS NULL OR client_id = '';

-- for new inserts without client_id, trigger format CL-000001 style
DROP TRIGGER IF EXISTS trg_dosing_clients_client_id;
DELIMITER $$
CREATE TRIGGER trg_dosing_clients_client_id
BEFORE INSERT ON dosing_clients
FOR EACH ROW
BEGIN
  IF NEW.client_id IS NULL OR NEW.client_id = '' THEN
    SET NEW.client_id = CONCAT('CL-', DATE_FORMAT(NOW(), '%y%m%d'), '-', SUBSTRING(REPLACE(UUID(), '-', ''), 1, 6));
  END IF;
END$$
DELIMITER ;

CREATE TABLE IF NOT EXISTS dosing_pump_pi_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id VARCHAR(64) NOT NULL,
  mac_address VARCHAR(17) NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  event_time DATETIME NOT NULL,
  event_key VARCHAR(191) NOT NULL,
  payload_json JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pi_events_event_key (event_key),
  KEY idx_pi_events_client_time (client_id, event_time),
  KEY idx_pi_events_type_time (event_type, event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS dosing_pump_latest_state (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id VARCHAR(64) NOT NULL,
  mac_address VARCHAR(17) NOT NULL,
  snapshot_time DATETIME NOT NULL,
  flow_rate_lpm DECIMAL(12,3) DEFAULT NULL,
  current_hour_water_liters DECIMAL(12,3) DEFAULT NULL,
  total_water_liters DECIMAL(14,3) DEFAULT NULL,
  running_pulses INT DEFAULT NULL,
  acid_status VARCHAR(30) DEFAULT NULL,
  chlorine_status VARCHAR(30) DEFAULT NULL,
  acid_trigger_liters DECIMAL(12,3) DEFAULT NULL,
  chlorine_trigger_liters DECIMAL(12,3) DEFAULT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_latest_state_client (client_id),
  KEY idx_latest_state_mac (mac_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
