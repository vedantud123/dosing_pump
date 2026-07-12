<?php
session_start();
date_default_timezone_set('Asia/Kolkata');

if (!isset($_SESSION['loggedin']) || $_SESSION['loggedin'] !== true) {
    header("Location: ../login/login.php");
    exit;
}

$username = $_SESSION['username'] ?? '';
$client_id = (string)($_SESSION['client_id'] ?? '');
if ($username === '' || $client_id === '') {
    header("Location: ../login/login.php");
    exit;
}

$db = new mysqli("localhost", "sunfra_farms", "sunfra_farms", "sunfra_farms");
if ($db->connect_error) die("Database connection failed");
$db->set_charset("utf8mb4");

function resolveClientTable($db) {
    foreach (["dosing_clients", "doisng_clients"] as $tbl) {
        $safe = $db->real_escape_string($tbl);
        $res = $db->query("SHOW TABLES LIKE '{$safe}'");
        if ($res && $res->num_rows > 0) return $tbl;
    }
    return null;
}

$clientTable = resolveClientTable($db);
$hasDeviceMapping = false;
$mappedMac = '';
if ($clientTable !== null) {
    $stmt = $db->prepare("SELECT mac_address FROM {$clientTable} WHERE client_id = ? AND mac_address IS NOT NULL AND mac_address <> '' LIMIT 1");
    if ($stmt) {
        $stmt->bind_param("s", $client_id);
        $stmt->execute();
        $res = $stmt->get_result();
        if ($row = $res->fetch_assoc()) {
            $hasDeviceMapping = true;
            $mappedMac = $row['mac_address'];
        }
        $stmt->close();
    }
}
$db->close();

// Absolute URLs avoid broken relative path issues on live server.
$mainDashboardUrl = "https://sunfra.com/farm/sunfra/index.php";
$dosingDashboardUrl = "https://sunfra.com/farm/sunfra/feedrawmaterial/dosing_pump_live_dashboard.php";
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Merged Dashboard (With Float)</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <style>
    :root{--card:#15355d;--line:#2e639e;--txt:#eaf2ff}
    html,body{margin:0;padding:0;max-width:100%;overflow-x:hidden;background:linear-gradient(135deg,#081a33,#0b2340);font-family:Segoe UI,Tahoma,sans-serif;color:var(--txt)}
    .sidebar{position:fixed;top:0;left:0;width:70px;height:100vh;background:#016795;display:flex;flex-direction:column;align-items:flex-start;padding-top:10px;overflow-y:auto;transition:width .3s ease;z-index:1000}
    .sidebar.expanded{width:250px}
    .sidebar a{color:#fff;text-decoration:none;width:100%;padding:14px 20px;display:flex;align-items:center;white-space:nowrap}
    .sidebar a:hover{background:#0194c7}
    .sidebar i{min-width:30px;text-align:center}
    .label{display:none;margin-left:10px}
    .sidebar.expanded .label{display:inline}
    .toggle-btn{width:100%;cursor:pointer;padding:10px 20px;background:none;border:none;color:#fff;font-size:18px;text-align:left;display:flex;align-items:center}
    .content{margin-left:70px;width:calc(100vw - 70px);transition:margin-left .3s ease,width .3s ease;padding:14px;box-sizing:border-box}
    .content.expanded{margin-left:250px;width:calc(100vw - 250px)}
    .panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:14px}
    .head{font-size:30px;font-weight:800;margin:0 0 8px 0}
    .sub{margin:0 0 8px 0}
    .ok{color:#7dff9f}.warn{color:#ffd27a}
    .seg{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
    .pill{background:#102d52;border:1px solid #28558a;border-radius:999px;padding:8px 12px;font-weight:700}
    .btn{display:inline-block;background:#1f6aa5;color:#fff;text-decoration:none;padding:10px 14px;border-radius:10px;font-weight:700;border:1px solid #4d8ccc}
    iframe{width:100%;border:0;border-radius:12px;background:#06142a}
    .main-iframe{height:58vh}
    .dosing-iframe{height:82vh}
    @media (max-width:640px){.content{margin-left:58px;width:calc(100vw - 58px)}.content.expanded{margin-left:220px;width:calc(100vw - 220px)}.head{font-size:24px}.main-iframe{height:52vh}.dosing-iframe{height:72vh}}
  </style>
</head>
<body>
<div class="sidebar" id="sidebar">
  <button class="toggle-btn" id="sidebarToggleBtn"><i class="fas fa-bars"></i><span class="label">Menu</span></button>
  <a href="https://sunfra.com/farm/sunfra/index.php"><i class="fas fa-home"></i><span class="label">My Dashboard</span></a>
  <a href="https://sunfra.com/farm/sunfra/sensor/iot_web_page.php"><i class="fas fa-microchip"></i><span class="label">IOT</span></a>
  <a href="<?= htmlspecialchars($dosingDashboardUrl) ?>"><i class="fas fa-flask"></i><span class="label">Dosing Pump</span></a>
  <a href="https://sunfra.com/farm/sunfra/login/logout.php"><i class="fas fa-sign-out-alt"></i><span class="label">Logout</span></a>
</div>

<main class="content" id="mainContent">
  <div class="panel">
    <h1 class="head">Merged Dashboard (With Float)</h1>
    <p class="sub">Client ID: <strong><?= htmlspecialchars($client_id) ?></strong></p>
    <div class="seg">
      <span class="pill">Farm Main Dashboard</span>
      <span class="pill">Dosing Pump Dashboard (With Float)</span>
    </div>
  </div>

  <div class="panel">
    <h3 style="margin-top:0;">Main Dashboard (Filter + Graphs)</h3>
    <p>Use this section for filter data and main analytics.</p>
    <a class="btn" href="<?= htmlspecialchars($mainDashboardUrl) ?>" target="_blank" rel="noopener">Open Full Main Dashboard</a>
    <iframe class="main-iframe" src="<?= htmlspecialchars($mainDashboardUrl) ?>" title="Main Dashboard"></iframe>
  </div>

  <div class="panel">
    <h3 style="margin-top:0;">Dosing Pump Live Data</h3>
    <?php if ($hasDeviceMapping): ?>
      <p class="ok">Device mapped. MAC: <strong><?= htmlspecialchars($mappedMac) ?></strong></p>
    <?php else: ?>
      <p class="warn">No MAC mapping for this client. Live data may be empty until mapping is added.</p>
    <?php endif; ?>
    <a class="btn" href="<?= htmlspecialchars($dosingDashboardUrl) ?>" target="_blank" rel="noopener">Open Full Dosing Dashboard</a>
    <iframe class="dosing-iframe" src="<?= htmlspecialchars($dosingDashboardUrl) ?>" title="Dosing Pump Live Dashboard"></iframe>
  </div>
</main>

<script>
const sidebar = document.getElementById('sidebar');
const mainContent = document.getElementById('mainContent');
const toggleBtn = document.getElementById('sidebarToggleBtn');
toggleBtn.addEventListener('click', () => {
  sidebar.classList.toggle('expanded');
  mainContent.classList.toggle('expanded');
  const icon = toggleBtn.querySelector('i');
  if (sidebar.classList.contains('expanded')) { icon.classList.remove('fa-bars'); icon.classList.add('fa-times'); }
  else { icon.classList.add('fa-bars'); icon.classList.remove('fa-times'); }
});
</script>
</body>
</html>
