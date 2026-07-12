USE dosing_pump;

CREATE TABLE IF NOT EXISTS dosing_pump_chemical_hourly_usage (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  period_start DATETIME NOT NULL,
  period_end DATETIME NOT NULL,
  acid_starts INT UNSIGNED NOT NULL DEFAULT 0,
  chlorine_starts INT UNSIGNED NOT NULL DEFAULT 0,
  acid_ml_used DECIMAL(10,3) NOT NULL DEFAULT 0.000,
  chlorine_ml_used DECIMAL(10,3) NOT NULL DEFAULT 0.000,
  acid_runtime_seconds DECIMAL(10,3) NOT NULL DEFAULT 0.000,
  chlorine_runtime_seconds DECIMAL(10,3) NOT NULL DEFAULT 0.000,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_chemical_hourly_period_start (period_start),
  KEY idx_chemical_hourly_period_end (period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
