<?php
session_start();
header('Content-Type: application/json');
date_default_timezone_set('Asia/Kolkata');
mysqli_report(MYSQLI_REPORT_OFF);

$mysqli = new mysqli("localhost", "sunfra_farms", "sunfra_farms", "sunfra_farms");
if ($mysqli->connect_error) {
    http_response_code(500);
    echo json_encode(["ok" => false, "message" => "Database connection failed: " . $mysqli->connect_error]);
    exit;
}
$mysqli->set_charset("utf8mb4");

function resolveClientTable($mysqli) {
    foreach (["dosing_clients", "doisng_clients"] as $tbl) {
        $safe = $mysqli->real_escape_string($tbl);
        $res = $mysqli->query("SHOW TABLES LIKE '{$safe}'");
        if ($res && $res->num_rows > 0) return $tbl;
    }
    return null;
}

function fetchOneAssoc($mysqli, $sql, $types = "", $params = []) {
    $stmt = $mysqli->prepare($sql);
    if (!$stmt) return null;
    if ($types !== "" && !empty($params)) $stmt->bind_param($types, ...$params);
    $stmt->execute();
    $res = $stmt->get_result();
    $row = $res ? $res->fetch_assoc() : null;
    $stmt->close();
    return $row;
}

function fetchAllAssoc($mysqli, $sql, $types = "", $params = []) {
    $stmt = $mysqli->prepare($sql);
    if (!$stmt) return [];
    if ($types !== "" && !empty($params)) $stmt->bind_param($types, ...$params);
    $stmt->execute();
    $res = $stmt->get_result();
    $rows = [];
    if ($res) while ($r = $res->fetch_assoc()) $rows[] = $r;
    $stmt->close();
    return $rows;
}

function buildRangeWindow($mode, $fromDate, $toDate) {
    $now = new DateTime('now');
    $start = null;
    $end = null;
    $label = '';

    switch ($mode) {
        case 'today':
            $start = new DateTime($now->format('Y-m-d 00:00:00'));
            $end = $now;
            $label = 'Today';
            break;
        case 'yesterday':
            $y = (clone $now)->modify('-1 day');
            $start = new DateTime($y->format('Y-m-d 00:00:00'));
            $end = new DateTime($y->format('Y-m-d 23:59:59'));
            $label = 'Yesterday';
            break;
        case 'weekly':
            $start = (clone $now)->modify('-6 day');
            $start = new DateTime($start->format('Y-m-d 00:00:00'));
            $end = $now;
            $label = 'Last 7 Days';
            break;
        case 'monthly':
            $start = (clone $now)->modify('-29 day');
            $start = new DateTime($start->format('Y-m-d 00:00:00'));
            $end = $now;
            $label = 'Last 30 Days';
            break;
        case 'yearly':
            $start = (clone $now)->modify('-364 day');
            $start = new DateTime($start->format('Y-m-d 00:00:00'));
            $end = $now;
            $label = 'Last 365 Days';
            break;
        case 'custom':
            if (!$fromDate || !$toDate) return [null, null, 'Custom', 'For custom range, send from_date and to_date'];
            $start = DateTime::createFromFormat('Y-m-d H:i:s', $fromDate . ' 00:00:00');
            $end = DateTime::createFromFormat('Y-m-d H:i:s', $toDate . ' 23:59:59');
            if (!$start || !$end) return [null, null, 'Custom', 'Invalid custom date format. Use YYYY-MM-DD'];
            if ($start > $end) return [null, null, 'Custom', 'from_date must be before to_date'];
            $label = $fromDate . ' to ' . $toDate;
            break;
        default:
            $start = new DateTime($now->format('Y-m-d 00:00:00'));
            $end = $now;
            $label = 'Today';
            break;
    }

    return [$start, $end, $label, null];
}

$clientTable = resolveClientTable($mysqli);
if ($clientTable === null) {
    echo json_encode(["ok" => false, "message" => "Client table not found. Expected dosing_clients or doisng_clients."]);
    exit;
}

$sessionClientId = $_SESSION['client_id'] ?? '';
$clientId = isset($_GET['client_id']) ? trim($_GET['client_id']) : '';
if ($clientId === '' && !empty($sessionClientId)) $clientId = trim((string)$sessionClientId);
$macAddress = isset($_GET['mac_address']) ? strtolower(trim($_GET['mac_address'])) : '';

$rangeMode = strtolower(trim($_GET['range_mode'] ?? 'today'));
$fromDate = trim($_GET['from_date'] ?? '');
$toDate = trim($_GET['to_date'] ?? '');
$eventsLimit = isset($_GET['events_limit']) ? (int)$_GET['events_limit'] : 40;
$eventsLimit = max(5, min(200, $eventsLimit));

list($startDt, $endDt, $rangeLabel, $rangeError) = buildRangeWindow($rangeMode, $fromDate, $toDate);
if ($rangeError) {
    echo json_encode(["ok" => false, "message" => $rangeError]);
    exit;
}

$whereClause = '';
$types = '';
$params = [];
if ($clientId !== '') {
    $whereClause = 'client_id = ?';
    $types = 's';
    $params = [$clientId];
} elseif ($macAddress !== '') {
    $whereClause = 'mac_address = ?';
    $types = 's';
    $params = [$macAddress];
}

if ($whereClause === '') {
    $latestClient = fetchOneAssoc($mysqli, "SELECT client_id, mac_address FROM dosing_pump_latest_state ORDER BY updated_at DESC LIMIT 1");
    if (!$latestClient) {
        echo json_encode(["ok" => true, "message" => "No data yet", "range" => ["mode" => $rangeMode, "label" => $rangeLabel], "data" => null]);
        exit;
    }
    $clientId = $latestClient['client_id'];
    $whereClause = 'client_id = ?';
    $types = 's';
    $params = [$clientId];
}

$client = fetchOneAssoc($mysqli, "SELECT client_id, mac_address, created_at, last_seen_at FROM {$clientTable} WHERE {$whereClause} LIMIT 1", $types, $params);
if (!$client) {
    $client = fetchOneAssoc($mysqli, "SELECT client_id, mac_address, NULL as created_at, NULL as last_seen_at FROM dosing_pump_latest_state WHERE {$whereClause} ORDER BY updated_at DESC LIMIT 1", $types, $params);
}
if (!$client) {
    echo json_encode(["ok" => false, "message" => "Client not found"]);
    exit;
}

$latest = fetchOneAssoc(
    $mysqli,
    "SELECT snapshot_time, flow_rate_lpm, current_hour_water_liters, total_water_liters, running_pulses, acid_status, chlorine_status, acid_trigger_liters, chlorine_trigger_liters, updated_at
     FROM dosing_pump_latest_state
     WHERE client_id = ?
     ORDER BY updated_at DESC
     LIMIT 1",
    's',
    [$client['client_id']]
);

$startStr = $startDt->format('Y-m-d H:i:s');
$endStr = $endDt->format('Y-m-d H:i:s');

$rangeLatest = fetchOneAssoc(
    $mysqli,
    "SELECT
        event_time AS snapshot_time,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.flow_rate_lpm')) + 0 AS flow_rate_lpm,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.current_hour_water_liters')) + 0 AS current_hour_water_liters,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.total_water_liters')) + 0 AS total_water_liters,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.running_pulses')) + 0 AS running_pulses,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.acid_status')) AS acid_status,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.chlorine_status')) AS chlorine_status,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.acid_trigger_liters')) + 0 AS acid_trigger_liters,
        JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.chlorine_trigger_liters')) + 0 AS chlorine_trigger_liters
     FROM dosing_pump_pi_events
     WHERE client_id = ? AND event_type='LIVE_SNAPSHOT' AND event_time BETWEEN ? AND ?
     ORDER BY event_time DESC
     LIMIT 1",
    'sss',
    [$client['client_id'], $startStr, $endStr]
);

$summary = fetchOneAssoc(
    $mysqli,
    "SELECT
        COALESCE(SUM(CASE WHEN event_type='WATER_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.water_liters')) + 0 ELSE 0 END),0) AS water_liters,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.acid_ml_used')) + 0 ELSE 0 END),0) AS acid_ml,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.chlorine_ml_used')) + 0 ELSE 0 END),0) AS chlorine_ml,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN (JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.acid_starts')) + 0) ELSE 0 END),0) AS acid_starts,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN (JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.chlorine_starts')) + 0) ELSE 0 END),0) AS chlorine_starts,
        COUNT(*) AS total_events
     FROM dosing_pump_pi_events
     WHERE client_id = ? AND event_time BETWEEN ? AND ?",
    'sss',
    [$client['client_id'], $startStr, $endStr]
);
if (!is_array($summary)) $summary = [];

// Fallback from LIVE_SNAPSHOT when hourly aggregates are missing.
$snapshotUsage = fetchOneAssoc(
    $mysqli,
    "SELECT
        MIN(JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.total_water_liters')) + 0) AS min_total_water,
        MAX(JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.total_water_liters')) + 0) AS max_total_water,
        COUNT(*) AS snap_count
     FROM dosing_pump_pi_events
     WHERE client_id = ?
       AND event_type='LIVE_SNAPSHOT'
       AND event_time BETWEEN ? AND ?",
    'sss',
    [$client['client_id'], $startStr, $endStr]
);
if (!is_array($snapshotUsage)) $snapshotUsage = [];

$dailyRows = fetchAllAssoc(
    $mysqli,
    "SELECT
        DATE(event_time) AS usage_date,
        COALESCE(SUM(CASE WHEN event_type='WATER_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.water_liters')) + 0 ELSE 0 END),0) AS water_liters,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.acid_ml_used')) + 0 ELSE 0 END),0) AS acid_ml,
        COALESCE(SUM(CASE WHEN event_type='CHEMICAL_HOURLY' THEN JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.chlorine_ml_used')) + 0 ELSE 0 END),0) AS chlorine_ml
     FROM dosing_pump_pi_events
     WHERE client_id = ? AND event_time BETWEEN ? AND ?
     GROUP BY DATE(event_time)
     ORDER BY DATE(event_time) ASC",
    'sss',
    [$client['client_id'], $startStr, $endStr]
);
if (!is_array($dailyRows)) $dailyRows = [];

$recentEvents = fetchAllAssoc(
    $mysqli,
    "SELECT event_type, event_time, payload_json
     FROM dosing_pump_pi_events
     WHERE client_id = ?
     ORDER BY event_time DESC
     LIMIT {$eventsLimit}",
    's',
    [$client['client_id']]
);

$waterTotal = (float)($summary['water_liters'] ?? 0);
$acidTotal = (float)($summary['acid_ml'] ?? 0);
$chlorineTotal = (float)($summary['chlorine_ml'] ?? 0);
$waterSource = 'WATER_HOURLY';
$chemSource = 'CHEMICAL_HOURLY';

if ($waterTotal <= 0.0) {
    $minW = isset($snapshotUsage['min_total_water']) ? (float)$snapshotUsage['min_total_water'] : 0.0;
    $maxW = isset($snapshotUsage['max_total_water']) ? (float)$snapshotUsage['max_total_water'] : 0.0;
    if ($maxW > $minW) {
        $waterTotal = max(0.0, $maxW - $minW);
        $waterSource = 'LIVE_SNAPSHOT_DELTA';
    }
}

if ($acidTotal <= 0.0 && $chlorineTotal <= 0.0) {
    $chemSource = 'NO_CHEMICAL_HOURLY_DATA';
}

$chemTotal = $acidTotal + $chlorineTotal;
$dayCount = max(1, count($dailyRows));
$avgWaterPerDay = $waterTotal / $dayCount;
$avgChemPerDay = $chemTotal / $dayCount;
$peakDay = ['date' => null, 'water_liters' => 0, 'acid_ml' => 0, 'chlorine_ml' => 0];
foreach ($dailyRows as $row) {
    if ((float)$row['water_liters'] > (float)$peakDay['water_liters']) {
        $peakDay = $row;
    }
}

$mysqli->close();

echo json_encode([
    'ok' => true,
    'server_time' => date('Y-m-d H:i:s'),
    'range' => [
        'mode' => $rangeMode,
        'label' => $rangeLabel,
        'from' => $startStr,
        'to' => $endStr,
    ],
    'latest' => $latest,
    'range_latest' => $rangeLatest,
    'summary' => [
        'water_liters' => $waterTotal,
        'acid_ml' => $acidTotal,
        'chlorine_ml' => $chlorineTotal,
        'chemical_total_ml' => $chemTotal,
        'water_source' => $waterSource,
        'chemical_source' => $chemSource,
        'acid_starts' => (int)($summary['acid_starts'] ?? 0),
        'chlorine_starts' => (int)($summary['chlorine_starts'] ?? 0),
        'events_count' => (int)($summary['total_events'] ?? 0),
        'avg_water_per_day' => $avgWaterPerDay,
        'avg_chemical_per_day' => $avgChemPerDay,
        'peak_day' => $peakDay,
    ],
    'series' => $dailyRows,
    'recent_events' => $recentEvents,
], JSON_PRETTY_PRINT);
?>
