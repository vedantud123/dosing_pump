<?php
header('Content-Type: application/json');

date_default_timezone_set('Asia/Kolkata');

$mysqli = new mysqli("localhost", "sunfra_farms", "sunfra_farms", "sunfra_farms");
if ($mysqli->connect_error) {
    die(json_encode([
        "status" => "error",
        "message" => "Database connection failed: " . $mysqli->connect_error
    ]));
}

$DB_HOST = 'localhost';
$DB_NAME = 'sunfra_farms';
$DB_USER = 'sunfra_farms';
$DB_PASS = 'sunfra_farms';

function resolveClientTable($pdo) {
    foreach (["dosing_clients", "doisng_clients"] as $tbl) {
        $stmt = $pdo->query("SHOW TABLES LIKE " . $pdo->quote($tbl));
        if ($stmt && $stmt->fetchColumn()) {
            return $tbl;
        }
    }
    return null;
}

function respond($statusCode, $data) {
    http_response_code($statusCode);
    echo json_encode($data);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'GET' && !isset($_GET['event_type'])) {
    respond(200, [
        'ok' => true,
        'message' => 'API is running',
        'how_to_test_get' => [
            'Use query params in URL for quick browser testing',
            'Required: mac_address, event_type, event_time, event_key',
            'Optional: payload_json as URL-encoded JSON string'
        ],
        'example_get_url' => 'dosing_pump_data_from_pi.php?mac_address=aa:bb:cc:dd:ee:ff&event_type=LIVE_SNAPSHOT&event_time=2026-04-28%2012:00:00&event_key=aa:bb:cc:dd:ee:ff|LIVE_SNAPSHOT|2026-04-28%2012:00:00&payload_json=%7B%22flow_rate_lpm%22%3A12.4%2C%22current_hour_water_liters%22%3A55.2%2C%22total_water_liters%22%3A1220.8%2C%22running_pulses%22%3A245%2C%22acid_status%22%3A%22automatic%22%2C%22chlorine_status%22%3A%22automatic%22%2C%22acid_trigger_liters%22%3A100%2C%22chlorine_trigger_liters%22%3A120%7D',
        'example_post_json' => [
            'mac_address' => 'aa:bb:cc:dd:ee:ff',
            'event_type' => 'WATER_HOURLY',
            'event_time' => '2026-04-28 12:00:00',
            'event_key' => 'aa:bb:cc:dd:ee:ff|WATER_HOURLY|2026-04-28 12:00:00',
            'payload' => [
                'period_start' => '2026-04-28 11:00:00',
                'period_end' => '2026-04-28 12:00:00',
                'water_liters' => 124.532,
                'pulses' => 1821
            ]
        ]
    ]);
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!is_array($data)) {
    $data = $_POST;
}
if (!is_array($data) || count($data) === 0) {
    $data = $_GET;
}
if (!is_array($data) || count($data) === 0) {
    $data = $_REQUEST;
}

if (isset($data['payload_json']) && !isset($data['payload'])) {
    $decodedPayload = json_decode($data['payload_json'], true);
    if (is_array($decodedPayload)) {
        $data['payload'] = $decodedPayload;
    }
}

$macAddress = isset($data['mac_address']) ? strtolower(trim($data['mac_address'])) : '';
$eventType = isset($data['event_type']) ? strtoupper(trim($data['event_type'])) : '';
$eventTime = isset($data['event_time']) ? trim($data['event_time']) : '';
$eventKey = isset($data['event_key']) ? trim($data['event_key']) : '';
$payload = isset($data['payload']) ? $data['payload'] : null;

if ($eventKey === '' && $eventType !== '' && $eventTime !== '') {
    $eventKey = $macAddress . '|' . $eventType . '|' . $eventTime;
}

if ($macAddress === '' || $eventType === '' || $eventTime === '') {
    respond(400, ['ok' => false, 'message' => 'Missing required fields']);
}

if ($macAddress !== '' && !preg_match('/^[0-9a-f:]{17}$/', $macAddress)) {
    respond(400, ['ok' => false, 'message' => 'Invalid mac_address format']);
}

if ($payload !== null && !is_array($payload)) {
    respond(400, ['ok' => false, 'message' => 'payload must be object/array']);
}

try {
    $pdo = new PDO(
        "mysql:host={$DB_HOST};dbname={$DB_NAME};charset=utf8mb4",
        $DB_USER,
        $DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]
    );

    $pdo->beginTransaction();

    $clientTable = resolveClientTable($pdo);
    if ($clientTable === null) {
        throw new Exception('Client table not found. Expected dosing_clients or doisng_clients');
    }

    $stmt = $pdo->prepare("SELECT id, client_id, mac_address FROM {$clientTable} WHERE mac_address = :mac LIMIT 1");
    $stmt->execute([':mac' => $macAddress]);
    $client = $stmt->fetch();
    if (!$client) {
        throw new Exception('Client mapping failed: mac_address not found in doisng_clients');
    }

    $payloadJson = $payload !== null ? json_encode($payload, JSON_UNESCAPED_UNICODE) : null;

    $insertEventSql = "
        INSERT INTO dosing_pump_pi_events
        (client_id, mac_address, event_type, event_time, event_key, payload_json, created_at)
        VALUES
        (:client_id, :mac, :event_type, :event_time, :event_key, :payload_json, NOW())
        ON DUPLICATE KEY UPDATE event_key = event_key
    ";

    $stmt = $pdo->prepare($insertEventSql);
    $stmt->execute([
        ':client_id' => $client['client_id'],
        ':mac' => $macAddress,
        ':event_type' => $eventType,
        ':event_time' => $eventTime,
        ':event_key' => $eventKey,
        ':payload_json' => $payloadJson,
    ]);

    $isDuplicate = ($stmt->rowCount() === 0);
    $latestStateUpdated = false;

    // Keep latest state in sync for every LIVE_SNAPSHOT request.
    // Even if the event row is duplicate (same event_key), latest state must still refresh.
    if ($eventType === 'LIVE_SNAPSHOT' && is_array($payload)) {
        $upsertLatestSql = "
            INSERT INTO dosing_pump_latest_state
            (client_id, mac_address, snapshot_time, flow_rate_lpm, current_hour_water_liters, total_water_liters, running_pulses,
             acid_status, chlorine_status, acid_trigger_liters, chlorine_trigger_liters, updated_at)
            VALUES
            (:client_id, :mac, :snapshot_time, :flow_rate_lpm, :current_hour_water_liters, :total_water_liters, :running_pulses,
             :acid_status, :chlorine_status, :acid_trigger_liters, :chlorine_trigger_liters, NOW())
            ON DUPLICATE KEY UPDATE
                snapshot_time = VALUES(snapshot_time),
                flow_rate_lpm = VALUES(flow_rate_lpm),
                current_hour_water_liters = VALUES(current_hour_water_liters),
                total_water_liters = VALUES(total_water_liters),
                running_pulses = VALUES(running_pulses),
                acid_status = VALUES(acid_status),
                chlorine_status = VALUES(chlorine_status),
                acid_trigger_liters = VALUES(acid_trigger_liters),
                chlorine_trigger_liters = VALUES(chlorine_trigger_liters),
                updated_at = NOW()
        ";

        $stmt = $pdo->prepare($upsertLatestSql);
        $stmt->execute([
            ':client_id' => $client['client_id'],
            ':mac' => $macAddress,
            ':snapshot_time' => $eventTime,
            ':flow_rate_lpm' => $payload['flow_rate_lpm'] ?? null,
            ':current_hour_water_liters' => $payload['current_hour_water_liters'] ?? null,
            ':total_water_liters' => $payload['total_water_liters'] ?? null,
            ':running_pulses' => $payload['running_pulses'] ?? null,
            ':acid_status' => $payload['acid_status'] ?? null,
            ':chlorine_status' => $payload['chlorine_status'] ?? null,
            ':acid_trigger_liters' => $payload['acid_trigger_liters'] ?? null,
            ':chlorine_trigger_liters' => $payload['chlorine_trigger_liters'] ?? null,
        ]);
        $latestStateUpdated = true;
    }

    $pdo->commit();

    respond(200, [
        'ok' => true,
        'duplicate' => $isDuplicate,
        'client_id' => $client['client_id'],
        'mac_address' => $macAddress,
        'event_type' => $eventType,
        'event_key' => $eventKey,
        'latest_state_updated' => $latestStateUpdated,
    ]);
} catch (Exception $e) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    respond(500, ['ok' => false, 'message' => $e->getMessage()]);
}
?>
