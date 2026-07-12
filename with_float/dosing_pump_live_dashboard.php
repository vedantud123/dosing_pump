<?php
session_start();
date_default_timezone_set('Asia/Kolkata');

$current_feature = "Egg Godown";

if (!isset($_SESSION['loggedin']) || $_SESSION['loggedin'] !== true) {
    header("Location: ../login/login.php");
    exit;
}
$username  = $_SESSION['username'] ?? '';
$client_id = $_SESSION['client_id'] ?? 0;

if (empty($username) || !$client_id) {
    header("Location: ../login/login.php");
    exit;
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dosing Pump Insight Board</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/js/all.min.js" defer></script>
  <style>
    :root{
      --bg1:#081426;
      --bg2:#0d2342;
      --panel:#122846;
      --panel2:#17345d;
      --line:#2c5d96;
      --text:#eef4ff;
      --muted:#9eb7dd;
      --aqua:#49dbff;
      --lime:#77ff9b;
      --amber:#ffd27a;
      --rose:#ff9ea4;
    }
    *{box-sizing:border-box}
    html,body{max-width:100%;overflow-x:hidden}
    body{margin:0;font-family:"Segoe UI",Tahoma,sans-serif;color:var(--text);background:radial-gradient(1200px 500px at 10% -10%,#244d86 0%,transparent 55%),linear-gradient(135deg,var(--bg2),var(--bg1));min-height:100vh}
    .sidebar{position:fixed;top:0;left:0;width:70px;height:100vh;background-color:#016795;display:flex;flex-direction:column;align-items:flex-start;padding-top:10px;overflow-y:auto;transition:width .3s ease;z-index:1000;box-shadow:2px 0 5px rgba(0,0,0,.1)}
    .sidebar.expanded{width:250px}
    .sidebar a{color:white;text-decoration:none;width:100%;padding:14px 20px;display:flex;align-items:center;font-size:15px;transition:background-color .2s ease-in-out;white-space:nowrap}
    .sidebar a:hover{background-color:#0194c7}
    .sidebar i{font-size:16px;min-width:30px;text-align:center}
    .sidebar .label{margin-left:10px;white-space:nowrap;display:none}
    .sidebar.expanded .label{display:inline}
    .toggle-btn{width:100%;cursor:pointer;padding:10px 20px;background:none;border:none;color:white;font-size:18px;text-align:left;outline:none;user-select:none;display:flex;align-items:center}
    .toggle-btn i{margin-right:10px}
    .attendance-submenu{display:none;flex-direction:column;background:#1e293b;width:100%;padding-left:40px}
    .attendance-submenu button{background:none;border:none;color:white;text-align:left;padding:10px 20px;font-size:14px;cursor:pointer;transition:background-color .2s ease}
    .attendance-submenu button:hover{background-color:#2563EB}
    .content{margin-left:70px;width:calc(100vw - 70px);transition:margin-left .3s ease,width .3s ease;overflow-x:hidden}
    .content.expanded{margin-left:250px;width:calc(100vw - 250px)}
    .wrap{width:100%;max-width:100%;margin:0 auto;padding:12px}
    .hero{background:linear-gradient(150deg,rgba(20,47,83,.95),rgba(14,34,64,.95));border:1px solid var(--line);border-radius:18px;padding:20px 22px;box-shadow:0 15px 35px rgba(0,0,0,.35)}
    .hero-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}
    .hero-top > div{min-width:0}
    .title{margin:0;font-size:40px;font-weight:800;letter-spacing:.4px}
    .sub{margin-top:6px;color:var(--muted);font-size:15px}
    .meta{display:none}
    .filter-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;align-items:center}
    .chip{border:1px solid var(--line);background:rgba(17,39,70,.9);color:var(--text);padding:9px 14px;border-radius:999px;cursor:pointer;font-weight:700}
    .chip.active{background:linear-gradient(130deg,#2f74cc,#4c9cff);border-color:#6ab7ff}
    .date-box{display:none;gap:10px;align-items:center;flex-wrap:wrap}
    input[type="date"]{background:#0f2748;border:1px solid var(--line);color:var(--text);padding:8px 10px;border-radius:10px}
    .btn{border:1px solid var(--line);background:#10315c;color:var(--text);padding:10px 14px;border-radius:10px;cursor:pointer;font-weight:700}
    .btn:hover{background:#14407a}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:12px;margin-top:14px}
    .card{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:16px;padding:14px;position:relative;overflow:hidden}
    .card::after{content:"";position:absolute;right:-30px;top:-30px;width:90px;height:90px;border-radius:50%;background:rgba(255,255,255,.06)}
    .k{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:8px}
    .dot{width:10px;height:10px;border-radius:50%}
    .v{font-size:40px;font-weight:800;line-height:1.1;margin-top:8px}
    .v.small{font-size:26px}
    .aqua{color:var(--aqua)} .lime{color:var(--lime)} .amber{color:var(--amber)} .rose{color:var(--rose)}
    .status{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;font-weight:700;font-size:13px}
    .st-auto{background:#1d426a;color:#8ad2ff}.st-run{background:#275f38;color:#8effa4}.st-man{background:#64472a;color:#ffd39b}
    .section{margin-top:14px}
    .panel{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:16px;padding:14px}
    .panel h3{margin:0 0 10px 0}
    .bar-wrap{display:grid;gap:8px}
    .bar-row{display:grid;grid-template-columns:160px 1fr 90px;gap:10px;align-items:center}
    .bar{height:12px;border-radius:999px;background:#0f2442;border:1px solid #244a77;overflow:hidden}
    .bar > span{display:block;height:100%;background:linear-gradient(90deg,#3fb3ff,#6cff95)}
    table{width:100%;border-collapse:collapse}
    th,td{padding:9px 8px;border-bottom:1px solid #2a4d79;text-align:left;font-size:14px}
    th{color:var(--muted)}
    .err{color:#ffb7bc;font-size:14px;margin-top:6px}
    .float-alert{display:none;margin-top:12px;padding:10px 12px;border-radius:10px;border:1px solid #8a2d35;background:rgba(130,30,40,.35);color:#ffd4d8;font-weight:700}
    .float-alert.ok{display:block;border-color:#2b6d48;background:rgba(25,95,55,.35);color:#b9ffd3}
    @media (max-width:1150px){.wrap{width:calc(100vw - 18px);padding:9px}.grid{grid-template-columns:repeat(2,minmax(220px,1fr))}.title{font-size:34px}}
    @media (max-width:920px){
      .hero{padding:14px}
      .hero-top{gap:10px}
      .title{font-size:28px}
      .sub{font-size:13px}
      .filter-row{gap:8px}
      .chip{padding:8px 12px;font-size:13px}
      .grid{grid-template-columns:repeat(2,minmax(140px,1fr));gap:10px}
      .card{padding:12px}
      .v{font-size:32px}
      .v.small{font-size:22px}
      .bar-row{grid-template-columns:100px 1fr 56px;gap:8px}
      th,td{padding:8px 6px;font-size:12px}
    }
    @media (max-width:640px){
      .sidebar{width:58px}
      .sidebar.expanded{width:220px}
      .content{margin-left:58px;width:calc(100vw - 58px)}
      .content.expanded{margin-left:220px;width:calc(100vw - 220px)}
      .wrap{width:calc(100vw - 8px);padding:4px}
      .hero{border-radius:12px}
      .hero-top{flex-direction:column;align-items:stretch}
      .hero-top > div:last-child{width:100%;display:grid;grid-template-columns:1fr 1fr;gap:8px}
      .btn{width:100%;padding:9px 8px;font-size:13px}
      .date-box{width:100%;display:grid;grid-template-columns:1fr 1fr;gap:8px}
      .date-box label{display:flex;flex-direction:column;font-size:12px}
      .date-box .btn{grid-column:1 / -1}
      .grid{grid-template-columns:1fr}
      .k{font-size:12px}
      .v{font-size:30px}
      .v.small{font-size:21px}
      .panel{padding:10px}
      .panel h3{font-size:18px}
      .bar-row{grid-template-columns:88px 1fr 52px}
      .bar{height:10px}
      table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
      th,td{min-width:92px;white-space:nowrap}
      .float-alert{font-size:13px;padding:8px 10px}
    }
  </style>
</head>
<body>
<div class="sidebar" id="sidebar">
  <button class="toggle-btn" id="sidebarToggleBtn" aria-label="Toggle menu" title="Toggle menu">
    <i class="fas fa-bars"></i>
    <span class="label">Menu</span>
  </button>
  <a href="https://sunfra.com/farm/sunfra/index.php"><i class="fas fa-home"></i><span class="label">My Dashboard</span></a>
  <a href="https://sunfra.com/farm/sunfra/batch/batch_json_to_web.php"><i class="fas fa-globe"></i><span class="label">Batch</span></a>
  <a href="https://sunfra.com/farm/sunfra/sensor/iot_web_page.php"><i class="fas fa-microchip"></i><span class="label">IOT</span></a>
  <a href="https://sunfra.com/farm/sunfra/weighbridge/weighbridge_json_to_web.php"><i class="fas fa-truck"></i><span class="label">WeighBridge</span></a>
  <a href="https://sunfra.com/farm/sunfra/tractor_production_mortality/tractor_production_mortality_json_to_web.php"><i class="fas fa-tractor"></i><span class="label">Tractor Production</span></a>
  <div class="attendance-dropdown">
    <a onclick="toggleAttendance()" href="javascript:void(0)"><i class="fas fa-user-check"></i><span class="label">Attendance <i class="fas fa-caret-down" style="margin-left:5px;"></i></span></a>
    <div class="attendance-submenu" id="attendanceSubmenu">
      <button onclick="location.href='https://sunfra.com/farm/sunfra/attendance/labour_master_json_to_web.php'">Labour Details</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/attendance/labour_attendance_json_to_web.php'">Labour Attendance</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/attendance/assigned_master_json_to_web.php'">Assigned Master</button>
    </div>
  </div>
  <div class="attendance-dropdown">
    <a onclick="toggleShed()" href="javascript:void(0)"><i class="fas fa-users-cog"></i><span class="label">Shead Supervisor <i class="fas fa-caret-down" style="margin-left:5px;"></i></span></a>
    <div class="attendance-submenu" id="shedSubmenu">
      <button onclick="location.href='https://sunfra.com/farm/sunfra/supervisor/supervisor_feed_feeding_shead_json_to_web.php'">Feed Feeding Shead</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/supervisor/supervisor_shead_mortality_json_to_web.php'">Shead Mortality</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/supervisor/supervisor_shead_production_json_to_web.php'">Production Shead</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/supervisor/supervisor_birds_weight_json_to_web.php'">Birds Weight</button>
    </div>
  </div>
  <div class="attendance-dropdown">
    <a onclick="toggleFeedPlant()" href="javascript:void(0)"><i class="fas fa-industry"></i><span class="label">Feed Plant Supervisor <i class="fas fa-caret-down" style="margin-left:5px;"></i></span></a>
    <div class="attendance-submenu" id="feedPlantSubmenu">
      <button onclick="location.href='https://sunfra.com/farm/sunfra/feed_formula/feed_formula_json_to_web.php'">Feed Formula</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/feedrawmaterial/feed_raw_material_json_to_web.php'">Feed Raw Material</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/feedrawmaterial/feed_to_shead_json_to_web.php'">Feed Material To Shead</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/feedrawmaterial/water_medicine_json_to_web.php'">Water Medicine</button>
    </div>
  </div>
  <div class="attendance-dropdown">
    <a onclick="toggleEggGodown()" href="javascript:void(0)"><i class="fas fa-warehouse"></i><span class="label">Egg Godown <i class="fas fa-caret-down" style="margin-left:5px;"></i></span></a>
    <div class="attendance-submenu" id="eggGodownSubmenu">
      <button onclick="location.href='https://sunfra.com/farm/sunfra/egg_godown/egg_godown_stock_json_to_web.php'">Egg Production From Shead</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/egg_godown/egg_godown_sale_json_to_web.php'">Eggs for Sale</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/egg_godown/egg_weight_json_to_web.php'">Egg Weight</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/egg_godown/egg_damaged_json_to_web.php'">Weekly Egg Damages</button>
    </div>
  </div>
  <div class="attendance-dropdown">
    <a onclick="toggleProfitLoss()" href="javascript:void(0)"><i class="fas fa-chart-line"></i><span class="label">Profit & Loss <i class="fas fa-caret-down" style="margin-left:5px;"></i></span></a>
    <div class="attendance-submenu" id="profitLossSubmenu">
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/material_cost_json_to_web.php'">Feed Material Price</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/egg_cutting_json_to_web.php'">Egg Price Per Piece</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/profit_loss_json_to_web.php'">Profit & Loss Summary</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/summary_report_json_to_web.php'">Summary Report</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/vaccination_json_to_web.php'">Vaccination</button>
      <button onclick="location.href='https://sunfra.com/farm/sunfra/profit_and_loss_details/labour_salary_json_to_web.php'">Labour Salary</button>
    </div>
  </div>
  <a href="https://sunfra.com/farm/sunfra/task/task_status.php"><i class="fas fa-tasks"></i><span class="label">Task Status</span></a>
  <a href="https://sunfra.com/farm/sunfra/login/client_user_json_to_web.php"><i class="fas fa-user-plus"></i><span class="label">Registration</span></a>
  <a href="https://sunfra.com/farm/sunfra/configuration/configuration.php"><i class="fas fa-cogs"></i><span class="label">Configuration</span></a>
  <a href="https://sunfra.com"><i class="fas fa-life-ring"></i><span class="label">Support</span></a>
  <a href="https://sunfra.com/farm/sunfra/login/logout.php"><i class="fas fa-sign-out-alt"></i><span class="label">Logout</span></a>
</div>
<main class="content" id="mainContent">
<div class="wrap">
  <div class="hero">
    <div class="hero-top">
      <div>
        <h1 class="title">Dosing Pump Insight Board</h1>
        <div class="sub">Single-page live + historical visibility for water, acid, and chlorine usage.</div>
        <div id="meta" class="meta">Loading...</div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button id="refreshBtn" class="btn">Refresh</button>
        <button id="autoBtn" class="btn">Auto Refresh: ON</button>
      </div>
    </div>

    <div class="filter-row" id="rangeChips">
      <button class="chip active" data-mode="today">Today</button>
      <button class="chip" data-mode="yesterday">Yesterday</button>
      <button class="chip" data-mode="weekly">Weekly</button>
      <button class="chip" data-mode="monthly">Monthly</button>
      <button class="chip" data-mode="yearly">Yearly</button>
      <button class="chip" data-mode="custom">Custom</button>
      <div class="date-box" id="customBox">
        <label>From <input type="date" id="fromDate"></label>
        <label>To <input type="date" id="toDate"></label>
        <button class="btn" id="applyCustomBtn">Apply</button>
      </div>
    </div>
    <div id="errorText" class="err"></div>
    <div id="floatAlert" class="float-alert">Low chemical level detected.</div>
  </div>

  <div class="grid">
    <div class="card"><div class="k"><span class="dot" style="background:var(--aqua)"></span>Flow Rate (LPM)</div><div class="v aqua" id="flowRate">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--amber)"></span>Current Hour Water (L)</div><div class="v amber" id="curHourWater">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--lime)"></span>Total Water (L)</div><div class="v lime" id="totalWater">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--rose)"></span>Running Pulses</div><div class="v rose" id="pulses">-</div></div>

    <div class="card"><div class="k"><span class="dot" style="background:var(--aqua)"></span>Water Used (Range)</div><div class="v aqua" id="waterUsed">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--amber)"></span>Acid Used (Range)</div><div class="v amber" id="acidUsed">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--lime)"></span>Chlorine Used (Range)</div><div class="v lime" id="chlorineUsed">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:var(--rose)"></span>Total Chemical (Range)</div><div class="v rose" id="chemTotal">-</div></div>

    <div class="card"><div class="k"><span class="dot" style="background:#8cbaff"></span>Avg Water / Day</div><div class="v small" id="avgWater">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:#ffd5a0"></span>Avg Chemical / Day</div><div class="v small" id="avgChem">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:#a5ffba"></span>Dose Starts</div><div class="v small" id="doseStarts">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:#ffb5bd"></span>Acid / Chlorine Status</div><div class="v small" id="statusBox">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:#58f6ff"></span>Acid Float Switch</div><div class="v small" id="acidFloat">-</div></div>
    <div class="card"><div class="k"><span class="dot" style="background:#7cff9b"></span>Chlorine Float Switch</div><div class="v small" id="chlorineFloat">-</div></div>
  </div>

  <div class="section panel">
    <h3>Daily Visibility</h3>
    <div class="bar-wrap" id="bars"></div>
  </div>

  <div class="section panel">
    <h3>Daily Breakdown Table</h3>
    <table>
      <thead>
        <tr><th>Date</th><th>Water (L)</th><th>Acid (ml)</th><th>Chlorine (ml)</th></tr>
      </thead>
      <tbody id="dailyTable"></tbody>
    </table>
  </div>
</div>
</main>

<script>
const API_FILE = 'dosing_pump_live_data_json.php';
let autoRefresh = true;
let timer = null;
let isLoading = false;
let currentMode = 'today';

function fmt(n, d=3){ return (n===null || n===undefined || isNaN(Number(n))) ? '-' : Number(n).toFixed(d); }
function floatBadge(v){
  const x = (v || '').toString().toUpperCase();
  if(x === 'ON') return '<span class="status st-run">ON</span>';
  if(x === 'OFF') return '<span class="status st-man">OFF</span>';
  return '<span class="status st-auto">-</span>';
}
function statusClass(v){
  v=(v||'').toLowerCase();
  if(v.includes('manual')) return 'st-man';
  if(v.includes('run')) return 'st-run';
  return 'st-auto';
}
function updateFloatAlert(acidFloat, chlorineFloat){
  const el = document.getElementById('floatAlert');
  const a = (acidFloat || '').toString().toUpperCase();
  const c = (chlorineFloat || '').toString().toUpperCase();
  if(a === 'OFF' || c === 'OFF'){
    el.classList.remove('ok');
    el.style.display = 'block';
    const parts = [];
    if(a === 'OFF') parts.push('Acid Float OFF');
    if(c === 'OFF') parts.push('Chlorine Float OFF');
    el.textContent = '⚠ Low Chemical Level Detected: ' + parts.join(' | ');
  }else if(a === 'ON' && c === 'ON'){
    el.style.display = 'block';
    el.classList.add('ok');
    el.textContent = '✓ Float Switch Status Normal: Acid ON | Chlorine ON';
  }else{
    el.style.display = 'none';
    el.classList.remove('ok');
  }
}

function setMode(mode){
  currentMode = mode;
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c.dataset.mode===mode));
  document.getElementById('customBox').style.display = mode === 'custom' ? 'flex' : 'none';
  if(mode !== 'custom') loadData();
}

async function loadData(){
  if(isLoading) return;
  isLoading = true;
  const errEl = document.getElementById('errorText');
  errEl.textContent = '';
  const params = new URLSearchParams();
  params.set('range_mode', currentMode);
  params.set('events_limit', '20');
  if(currentMode === 'custom'){
    const from = document.getElementById('fromDate').value;
    const to = document.getElementById('toDate').value;
    if(!from || !to){ errEl.textContent = 'Select From and To date for custom range.'; return; }
    params.set('from_date', from);
    params.set('to_date', to);
  }

  try{
    const res = await fetch(API_FILE + '?' + params.toString(), {cache:'no-store'});
    const text = await res.text();
    if(!text){ errEl.textContent='Empty API response'; return; }
    let json;
    try{ json = JSON.parse(text); }catch(_e){ errEl.textContent='Invalid JSON response'; return; }
    if(!json.ok){ errEl.textContent = json.message || 'No data'; return; }

    const latest = json.latest || {};
    const latestSnapshot = json.latest_snapshot || {};
    const rangeLatest = json.range_latest || null;
    const todaySnap = Object.assign({}, latest, latestSnapshot);
    const snap = (currentMode === 'today') ? todaySnap : (rangeLatest || {});
    const s = json.summary || {};
    const series = json.series || [];
    const rangeLabel = (json.range && json.range.label) ? json.range.label : currentMode;

    document.getElementById('meta').textContent = '';
    document.getElementById('flowRate').textContent = fmt(snap.flow_rate_lpm,2);
    document.getElementById('curHourWater').textContent = fmt(snap.current_hour_water_liters,3);
    document.getElementById('totalWater').textContent = fmt(snap.total_water_liters,3);
    document.getElementById('pulses').textContent = (snap.running_pulses ?? '-');

    document.getElementById('waterUsed').textContent = fmt(s.water_liters,3);
    document.getElementById('acidUsed').textContent = fmt(s.acid_ml,3);
    document.getElementById('chlorineUsed').textContent = fmt(s.chlorine_ml,3);
    document.getElementById('chemTotal').textContent = fmt(s.chemical_total_ml,3);
    document.getElementById('avgWater').textContent = fmt(s.avg_water_per_day,3) + ' L';
    document.getElementById('avgChem').textContent = fmt(s.avg_chemical_per_day,3) + ' ml';
    document.getElementById('doseStarts').textContent = `${s.acid_starts ?? 0} / ${s.chlorine_starts ?? 0}`;

    const acidSt = snap.acid_status || 'automatic';
    const chlSt = snap.chlorine_status || 'automatic';
    document.getElementById('statusBox').innerHTML =
      `<span class="status ${statusClass(acidSt)}">Acid: ${acidSt}</span> <span class="status ${statusClass(chlSt)}">Chlorine: ${chlSt}</span>`;
    document.getElementById('acidFloat').innerHTML = floatBadge(snap.acid_float_switch);
    document.getElementById('chlorineFloat').innerHTML = floatBadge(snap.chlorine_float_switch);
    updateFloatAlert(snap.acid_float_switch, snap.chlorine_float_switch);

    const maxWater = Math.max(1, ...series.map(r => Number(r.water_liters || 0)));
    const bars = document.getElementById('bars');
    bars.innerHTML = '';
    series.forEach(r => {
      const w = Number(r.water_liters || 0);
      const pct = Math.min(100, (w / maxWater) * 100);
      const row = document.createElement('div');
      row.className = 'bar-row';
      row.innerHTML = `
        <div>${r.usage_date}</div>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <div>${fmt(w,3)}</div>
      `;
      bars.appendChild(row);
    });
    if(series.length === 0) bars.innerHTML = '<div class="muted">No data in selected range</div>';

    const table = document.getElementById('dailyTable');
    table.innerHTML = '';
    series.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${r.usage_date}</td><td>${fmt(r.water_liters,3)}</td><td>${fmt(r.acid_ml,3)}</td><td>${fmt(r.chlorine_ml,3)}</td>`;
      table.appendChild(tr);
    });
    if(series.length === 0) table.innerHTML = '<tr><td colspan="4">No records</td></tr>';
  }catch(e){
    errEl.textContent = 'Error: ' + e.message;
  } finally {
    isLoading = false;
  }
}

document.querySelectorAll('.chip').forEach(btn => btn.addEventListener('click', () => setMode(btn.dataset.mode)));
document.getElementById('applyCustomBtn').addEventListener('click', loadData);
document.getElementById('refreshBtn').addEventListener('click', loadData);
document.getElementById('autoBtn').addEventListener('click', () => {
  autoRefresh = !autoRefresh;
  document.getElementById('autoBtn').textContent = 'Auto Refresh: ' + (autoRefresh ? 'ON' : 'OFF');
});

function startLoop(){
  if(timer) clearInterval(timer);
  timer = setInterval(() => { if(autoRefresh) loadData(); }, 12000);
}

function toggleSubmenu(id){
  const submenu = document.getElementById(id);
  if(!submenu) return;
  submenu.style.display = submenu.style.display === 'flex' ? 'none' : 'flex';
}
function toggleAttendance(){ toggleSubmenu('attendanceSubmenu'); }
function toggleFeedPlant(){ toggleSubmenu('feedPlantSubmenu'); }
function toggleEggGodown(){ toggleSubmenu('eggGodownSubmenu'); }
function toggleProfitLoss(){ toggleSubmenu('profitLossSubmenu'); }
function toggleShed(){ toggleSubmenu('shedSubmenu'); }

const sidebar = document.getElementById('sidebar');
const mainContent = document.getElementById('mainContent');
const toggleBtn = document.getElementById('sidebarToggleBtn');
toggleBtn.addEventListener('click', () => {
  sidebar.classList.toggle('expanded');
  mainContent.classList.toggle('expanded');
  const icon = toggleBtn.querySelector('i');
  if (sidebar.classList.contains('expanded')) {
    icon.classList.remove('fa-bars');
    icon.classList.add('fa-times');
  } else {
    icon.classList.add('fa-bars');
    icon.classList.remove('fa-times');
  }
});

loadData();
startLoop();
</script>
</body>
</html>

