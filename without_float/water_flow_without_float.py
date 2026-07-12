import time
import threading
import RPi.GPIO as GPIO
import mysql.connector
import customtkinter as ctk
import csv
import os
import calendar
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from collections import OrderedDict

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

FLOW_PIN = 17
RELAY1 = 23  
RELAY2 = 24  `r`nRELAY3 = 5  `r`nBUTTON_PIN = 25`r`nRELAY3_ON_SECONDS = 600`r`ncalibrationFactor = 0.218

pulse_count = 0
totalLiters = 0.0
sessionLiters = 0.0
totalPulses = 0
next_acid_liter = 0.0
flow_lock = threading.Lock()
DB_INSERT_INTERVAL_SECONDS = 3600

DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = "sunfra"
DB_NAME = "dosing_pump"

WATER_TABLE = "dosing_pump_water"
CHEMICAL_HOURLY_TABLE = "dosing_pump_chemical_hourly_usage"

CHEMICAL_CSV = "/home/sunfra/Documents/new_dosing_pump/chemical_data.csv"
APP_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "panel_config.json"
)
PENDING_SYNC_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "pending_server_sync.jsonl"
)
SERVER_API_URL = "http://sunfra.com/farm/sunfra/sensor/dosing_pump_data_from_pi.php"
SERVER_SYNC_ENABLED = True
SERVER_SYNC_TIMEOUT_SECONDS = 8
SERVER_SYNC_RETRY_INTERVAL_SECONDS = 30

ACID_ML_PER_START = 0.41
CHLORINE_ML_PER_START = 0.50
ACID_DEFAULT_TRIGGER_LITERS = 100.0
CHLORINE_DEFAULT_TRIGGER_LITERS = 100.0

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(FLOW_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RELAY1, GPIO.OUT)
GPIO.setup(RELAY2, GPIO.OUT)`r`nGPIO.setup(RELAY3, GPIO.OUT)`r`nGPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)`r`n
RELAY_ON = GPIO.LOW
RELAY_OFF = GPIO.HIGH

GPIO.output(RELAY1, RELAY_OFF)
GPIO.output(RELAY2, RELAY_OFF)`r`nGPIO.output(RELAY3, RELAY_OFF)`r`n
relay1_manual = False
relay2_manual = False
relay3_running = False
relay3_off_time = 0.0
button_prev_state = GPIO.HIGH


def start_relay3_cycle():
    global relay3_running, relay3_off_time
    GPIO.output(RELAY3, RELAY_ON)
    relay3_running = True
    relay3_off_time = time.time() + RELAY3_ON_SECONDS

db = mysql.connector.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASS,
    database=DB_NAME
)
cursor = db.cursor()

DEFAULT_APP_CONFIG = {
    "calibration_factor": 0.218,
    "acid_ml_per_start": 0.41,
    "chlorine_ml_per_start": 0.50,
    "acid_pump_duration_sec": 0.25,
    "chlorine_pump_duration_sec": 0.25,
    "db_insert_interval_seconds": 3600,
    "acid_trigger_liters": ACID_DEFAULT_TRIGGER_LITERS,
    "chlorine_trigger_liters": CHLORINE_DEFAULT_TRIGGER_LITERS,
}

def load_app_config():
    config = dict(DEFAULT_APP_CONFIG)
    if not os.path.exists(APP_CONFIG_FILE):
        return config
    try:
        with open(APP_CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            for key in config:
                if key in loaded:
                    config[key] = loaded[key]
    except Exception:
        pass
    return config

def save_app_config(config):
    with open(APP_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def save_chemical_values_to_csv(acid_value, chlorine_value):
    rows = []
    fieldnames = ["name", "value", "dose"]
    if os.path.exists(CHEMICAL_CSV):
        with open(CHEMICAL_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
            if "name" not in fieldnames:
                fieldnames.insert(0, "name")
            if "value" not in fieldnames:
                fieldnames.append("value")
            if "dose" not in fieldnames:
                fieldnames.append("dose")
            for row in reader:
                rows.append(dict(row))

    def upsert_row(target_name, new_value):
        for row in rows:
            if str(row.get("name", "")).strip().lower() == target_name:
                row["value"] = f"{new_value:.3f}"
                row.setdefault("dose", row.get("dose", "0"))
                return
        rows.append({"name": target_name, "value": f"{new_value:.3f}", "dose": "0"})

    upsert_row("acid", acid_value)
    upsert_row("chlorine", chlorine_value)

    with open(CHEMICAL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})

def read_chemical_values():
    acid = None
    chlorine = None
    if not os.path.exists(CHEMICAL_CSV):
        return acid, chlorine

    try:
        with open(CHEMICAL_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = str(row.get("name", "")).strip().lower()
                raw_value = str(row.get("value", "")).strip()
                if not raw_value:
                    continue
                try:
                    parsed_value = float(raw_value)
                except ValueError:
                    continue
                if name == "acid":
                    acid = parsed_value
                elif name == "chlorine":
                    chlorine = parsed_value
    except Exception:
        return None, None
    return acid, chlorine

def get_mac_address():
    net_candidates = ("eth0", "wlan0")
    for iface in net_candidates:
        path = f"/sys/class/net/{iface}/address"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    mac = f.read().strip().lower()
                if mac and mac != "00:00:00:00:00:00":
                    return mac
            except Exception:
                pass
    mac_hex = f"{uuid.getnode():012x}"
    return ":".join(mac_hex[i:i + 2] for i in range(0, 12, 2))

MAC_ADDRESS = get_mac_address()
last_server_sync_retry = 0.0
last_live_snapshot_bucket = None

def _post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Sunfra-DosingPump/1.0"
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=SERVER_SYNC_TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8", errors="replace")
        if 200 <= response.status < 300:
            return True, body
        return False, body

def enqueue_sync_event(event_payload):
    try:
        with open(PENDING_SYNC_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_payload) + "\n")
    except Exception:
        pass

def flush_pending_sync_events(max_items=20):
    if not os.path.exists(PENDING_SYNC_FILE):
        return

    try:
        with open(PENDING_SYNC_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception:
        return

    if not lines:
        try:
            os.remove(PENDING_SYNC_FILE)
        except Exception:
            pass
        return

    remaining = []
    sent_count = 0
    for line in lines:
        if sent_count >= max_items:
            remaining.append(line)
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue

        try:
            ok, _resp = _post_json(SERVER_API_URL, payload)
            if ok:
                sent_count += 1
            else:
                remaining.append(line)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            remaining.append(line)
        except Exception:
            remaining.append(line)

    if remaining:
        try:
            with open(PENDING_SYNC_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(remaining) + "\n")
        except Exception:
            pass
    else:
        try:
            os.remove(PENDING_SYNC_FILE)
        except Exception:
            pass

def send_server_event(event_type, event_time, payload, queue_on_fail=True):
    if not SERVER_SYNC_ENABLED:
        return

    if isinstance(event_time, datetime):
        event_time_str = event_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        event_time_str = str(event_time)

    event_key = f"{MAC_ADDRESS}|{event_type}|{event_time_str}"
    event_payload = {
        "mac_address": MAC_ADDRESS,
        "event_type": event_type,
        "event_time": event_time_str,
        "event_key": event_key,
        "payload": payload,
    }

    try:
        ok, _resp = _post_json(SERVER_API_URL, event_payload)
        if not ok and queue_on_fail:
            enqueue_sync_event(event_payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        if queue_on_fail:
            enqueue_sync_event(event_payload)
    except Exception:
        if queue_on_fail:
            enqueue_sync_event(event_payload)

app_config = load_app_config()
calibrationFactor = float(app_config["calibration_factor"])
ACID_ML_PER_START = float(app_config["acid_ml_per_start"])
CHLORINE_ML_PER_START = float(app_config["chlorine_ml_per_start"])
ACID_PUMP_DURATION = float(app_config["acid_pump_duration_sec"])
CHLORINE_PUMP_DURATION = float(app_config["chlorine_pump_duration_sec"])
DB_INSERT_INTERVAL_SECONDS = int(app_config["db_insert_interval_seconds"])
acid_trigger_liters = float(app_config["acid_trigger_liters"])
chlorine_trigger_liters = float(app_config["chlorine_trigger_liters"])

csv_acid_value, csv_chlorine_value = read_chemical_values()
if csv_acid_value is not None and csv_acid_value > 0:
    acid_trigger_liters = csv_acid_value
if csv_chlorine_value is not None and csv_chlorine_value > 0:
    chlorine_trigger_liters = csv_chlorine_value

def insert_water_value(value):
    cursor.execute(
        f"INSERT INTO {WATER_TABLE} (water_value, timestamp) VALUES (%s, NOW())",
        (round(value, 3),)
    )
    db.commit()

def insert_chemical_hourly_usage(
    period_start,
    period_end,
    acid_starts,
    chlorine_starts,
    acid_runtime_seconds,
    chlorine_runtime_seconds
):
    acid_ml_used = round(acid_starts * ACID_ML_PER_START, 3)
    chlorine_ml_used = round(chlorine_starts * CHLORINE_ML_PER_START, 3)
    cursor.execute(
        f"""
        INSERT INTO {CHEMICAL_HOURLY_TABLE}
        (period_start, period_end, acid_starts, chlorine_starts, acid_ml_used, chlorine_ml_used, acid_runtime_seconds, chlorine_runtime_seconds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            period_start,
            period_end,
            acid_starts,
            chlorine_starts,
            acid_ml_used,
            chlorine_ml_used,
            round(acid_runtime_seconds, 3),
            round(chlorine_runtime_seconds, 3),
        )
    )
    db.commit()

def flow_thread():
    global pulse_count
    last_state = GPIO.input(FLOW_PIN)

    while True:
        state = GPIO.input(FLOW_PIN)
        if state == GPIO.HIGH and last_state == GPIO.LOW:
            with flow_lock:
                pulse_count += 1
        last_state = state
        time.sleep(0.002)

acid_pump_running = False
chlorine_pump_running = False
acid_off_time = 0
chlorine_off_time = 0
acid_starts_hour = 0
chlorine_starts_hour = 0
acid_runtime_seconds_hour = 0.0
chlorine_runtime_seconds_hour = 0.0

def start_acid_pump():
    global acid_pump_running, acid_off_time, acid_starts_hour
    GPIO.output(RELAY1, GPIO.LOW)
    acid_pump_running = True
    acid_off_time = time.time() + ACID_PUMP_DURATION
    acid_starts_hour += 1


def start_chlorine_pump():
    global chlorine_pump_running, chlorine_off_time, chlorine_starts_hour
    GPIO.output(RELAY2, GPIO.LOW)
    chlorine_pump_running = True
    chlorine_off_time = time.time() + CHLORINE_PUMP_DURATION
    chlorine_starts_hour += 1

def refresh_manual_button_styles():
    relay1_button.configure(
        text="Acid MANUAL ON" if relay1_manual else "Acid AUTO",
        fg_color="#16a34a" if relay1_manual else "#334155",
        hover_color="#15803d" if relay1_manual else "#475569"
    )
    relay2_button.configure(
        text="Chlorine MANUAL ON" if relay2_manual else "Chlorine AUTO",
        fg_color="#16a34a" if relay2_manual else "#334155",
        hover_color="#15803d" if relay2_manual else "#475569"
    )

def toggle_relay1():
    global relay1_manual, acid_pump_running, acid_off_time, acid_starts_hour
    relay1_manual = not relay1_manual
    acid_pump_running = False
    acid_off_time = 0
    if relay1_manual:
        acid_starts_hour += 1
    GPIO.output(RELAY1, RELAY_ON if relay1_manual else RELAY_OFF)
    refresh_manual_button_styles()

def toggle_relay2():
    global relay2_manual, chlorine_pump_running, chlorine_off_time, chlorine_starts_hour
    relay2_manual = not relay2_manual
    chlorine_pump_running = False
    chlorine_off_time = 0
    if relay2_manual:
        chlorine_starts_hour += 1
    GPIO.output(RELAY2, RELAY_ON if relay2_manual else RELAY_OFF)
    refresh_manual_button_styles()

def relay_on(relay_pin, duration=0.25):
    GPIO.output(relay_pin, RELAY_ON)
    time.sleep(duration)
    GPIO.output(relay_pin, RELAY_OFF)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("WATER MONITORING SYSTEM")
app.bind("<Escape>", lambda e: app.iconify())

def apply_display_scaling():
    sw = app.winfo_screenwidth()
    sh = app.winfo_screenheight()
    if sw <= 1024 or sh <= 600:
        ctk.set_widget_scaling(0.78)
        ctk.set_window_scaling(0.86)
    elif sw <= 1280 or sh <= 720:
        ctk.set_widget_scaling(0.88)
        ctk.set_window_scaling(0.93)
    else:
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

def configure_startup_window():
    sw = app.winfo_screenwidth()
    sh = app.winfo_screenheight()

    # Apply scaling first, then final geometry for stable 7-inch rendering.
    apply_display_scaling()

    try:
        app.state("zoomed")
    except Exception:
        try:
            app.attributes("-zoomed", True)
        except Exception:
            pass

    app.geometry(f"{sw}x{sh}+0+0")
    app.minsize(max(800, int(sw * 0.75)), max(480, int(sh * 0.75)))

app.after(120, configure_startup_window)

app.grid_columnconfigure(1, weight=1)
app.grid_rowconfigure(0, weight=1)

sidebar = ctk.CTkFrame(app, width=250, corner_radius=20)
sidebar.grid(row=0, column=0, sticky="ns", padx=(15, 10), pady=15)
sidebar.grid_propagate(False)

ctk.CTkLabel(sidebar, text="DASHBOARD", font=("Poppins", 24, "bold")).pack(pady=(25, 10))
ctk.CTkLabel(
    sidebar,
    text="Select a feature",
    font=("Poppins", 14),
    text_color="#aab3c5"
).pack(pady=(0, 20))

content_container = ctk.CTkFrame(app, corner_radius=20)
content_container.grid(row=0, column=1, sticky="nsew", padx=(10, 15), pady=15)
content_container.grid_rowconfigure(0, weight=1)
content_container.grid_columnconfigure(0, weight=1)

dosing_view = ctk.CTkScrollableFrame(content_container, fg_color="transparent")
water_view = ctk.CTkScrollableFrame(content_container, fg_color="transparent")
chemical_view = ctk.CTkScrollableFrame(content_container, fg_color="transparent")
config_view = ctk.CTkScrollableFrame(content_container, fg_color="transparent")

def set_scrollbar_width(scrollable_frame, width=22):
    try:
        scrollable_frame._scrollbar.configure(width=width)
    except Exception:
        pass

for view in (dosing_view, water_view, chemical_view, config_view):
    set_scrollbar_width(view, 22)
    view.grid(row=0, column=0, sticky="nsew")

current_active_view = dosing_view


dosing_btn = ctk.CTkButton(sidebar, text="Dosing Pump System", font=("Poppins", 16, "bold"))
water_btn = ctk.CTkButton(sidebar, text="Water Data", font=("Poppins", 16, "bold"))
chemical_btn = ctk.CTkButton(sidebar, text="Chemical Data", font=("Poppins", 16, "bold"))
config_btn = ctk.CTkButton(sidebar, text="Configuration", font=("Poppins", 16, "bold"))

dosing_btn.pack(fill="x", padx=20, pady=(10, 8))
water_btn.pack(fill="x", padx=20, pady=(0, 8))
chemical_btn.pack(fill="x", padx=20, pady=(0, 8))
config_btn.pack(fill="x", padx=20, pady=(0, 8))

def set_active_button(active_button):
    for btn in (dosing_btn, water_btn, chemical_btn, config_btn):
        if btn == active_button:
            btn.configure(fg_color="#1f6aa5", hover_color="#1a5a8c")
        else:
            btn.configure(fg_color="#2b2b2b", hover_color="#3a3a3a")


def on_mousewheel(event):
    target = current_active_view if current_active_view is not None else dosing_view
    try:
        if event.delta != 0:
            step = int(-1 * (event.delta / 120))
            target._parent_canvas.yview_scroll(step, "units")
    except Exception:
        pass


def on_mousewheel_linux_up(_event):
    target = current_active_view if current_active_view is not None else dosing_view
    try:
        target._parent_canvas.yview_scroll(-1, "units")
    except Exception:
        pass


def on_mousewheel_linux_down(_event):
    target = current_active_view if current_active_view is not None else dosing_view
    try:
        target._parent_canvas.yview_scroll(1, "units")
    except Exception:
        pass


app.bind_all("<MouseWheel>", on_mousewheel)
app.bind_all("<Button-4>", on_mousewheel_linux_up)
app.bind_all("<Button-5>", on_mousewheel_linux_down)
def switch_view(target_view):
    global current_active_view
    for view in (dosing_view, water_view, chemical_view, config_view):
        view.grid_remove()
    target_view.grid(row=0, column=0, sticky="nsew")
    target_view.lift()
    current_active_view = target_view

def show_dosing_view():
    global water_tab_active, water_refresh_job, chemical_tab_active, chemical_refresh_job
    switch_view(dosing_view)
    water_tab_active = False
    chemical_tab_active = False
    if water_refresh_job is not None:
        app.after_cancel(water_refresh_job)
        water_refresh_job = None
    if chemical_refresh_job is not None:
        app.after_cancel(chemical_refresh_job)
        chemical_refresh_job = None
    set_active_button(dosing_btn)

def show_water_view():
    global water_tab_active, chemical_tab_active, chemical_refresh_job
    switch_view(water_view)
    water_tab_active = True
    chemical_tab_active = False
    if chemical_refresh_job is not None:
        app.after_cancel(chemical_refresh_job)
        chemical_refresh_job = None
    set_active_button(water_btn)
    app.after(50, update_water_dashboard)

def show_chemical_view():
    global water_tab_active, water_refresh_job, chemical_tab_active
    switch_view(chemical_view)
    water_tab_active = False
    chemical_tab_active = True
    if water_refresh_job is not None:
        app.after_cancel(water_refresh_job)
        water_refresh_job = None
    set_active_button(chemical_btn)
    app.after(50, update_chemical_dashboard)

def show_config_view():
    global water_tab_active, water_refresh_job, chemical_tab_active, chemical_refresh_job
    switch_view(config_view)
    water_tab_active = False
    chemical_tab_active = False
    if water_refresh_job is not None:
        app.after_cancel(water_refresh_job)
        water_refresh_job = None
    if chemical_refresh_job is not None:
        app.after_cancel(chemical_refresh_job)
        chemical_refresh_job = None
    set_active_button(config_btn)

dosing_btn.configure(command=show_dosing_view)
water_btn.configure(command=show_water_view)
chemical_btn.configure(command=show_chemical_view)
config_btn.configure(command=show_config_view)

dosing_header = ctk.CTkFrame(dosing_view, corner_radius=24, fg_color="#111a2a")
dosing_header.pack(fill="x", padx=30, pady=(20, 12))

ctk.CTkLabel(
    dosing_header,
    text="DOSING PUMP COMMAND CENTER",
    font=("Poppins", 34, "bold")
).pack(anchor="w", padx=24, pady=(18, 4))

ctk.CTkLabel(
    dosing_header,
    text="Live flow monitoring, hourly usage, and automated chemical dosing status.",
    font=("Poppins", 15),
    text_color="#9caece"
).pack(anchor="w", padx=24, pady=(0, 14))

top_status_row = ctk.CTkFrame(dosing_view, corner_radius=18, fg_color="#101722")
top_status_row.pack(fill="x", padx=30, pady=(0, 12))
top_status_row.grid_columnconfigure((0, 1, 2), weight=1)

pulse_card = ctk.CTkFrame(top_status_row, corner_radius=16, fg_color="#182233")
pulse_card.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
ctk.CTkLabel(
    pulse_card,
    text="RUNNING PULSES",
    font=("Poppins", 13, "bold"),
    text_color="#9fb0c9"
).pack(anchor="w", padx=16, pady=(12, 2))
pulse_value_label = ctk.CTkLabel(
    pulse_card, text="0", font=("Poppins", 34, "bold"), text_color="#ff7b7b"
)
pulse_value_label.pack(anchor="w", padx=16, pady=(0, 10))

acid_status_card = ctk.CTkFrame(top_status_row, corner_radius=16, fg_color="#182233")
acid_status_card.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
ctk.CTkLabel(
    acid_status_card,
    text="ACID PUMP",
    font=("Poppins", 13, "bold"),
    text_color="#9fb0c9"
).pack(anchor="w", padx=16, pady=(12, 2))
acid_status_value = ctk.CTkLabel(
    acid_status_card, text="Standby", font=("Poppins", 28, "bold"), text_color="#7ad6ff"
)
acid_status_value.pack(anchor="w", padx=16, pady=(0, 10))

chlorine_status_card = ctk.CTkFrame(top_status_row, corner_radius=16, fg_color="#182233")
chlorine_status_card.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
ctk.CTkLabel(
    chlorine_status_card,
    text="CHLORINE PUMP",
    font=("Poppins", 13, "bold"),
    text_color="#9fb0c9"
).pack(anchor="w", padx=16, pady=(12, 2))
chlorine_status_value = ctk.CTkLabel(
    chlorine_status_card, text="Standby", font=("Poppins", 28, "bold"), text_color="#7ad6ff"
)
chlorine_status_value.pack(anchor="w", padx=16, pady=(0, 10))

manual_control_row = ctk.CTkFrame(dosing_view, corner_radius=16, fg_color="#101722")
manual_control_row.pack(fill="x", padx=30, pady=(0, 12))
manual_control_row.grid_columnconfigure((0, 1), weight=1)

relay1_button = ctk.CTkButton(
    manual_control_row,
    text="Acid AUTO",
    font=("Poppins", 14, "bold"),
    corner_radius=12,
    height=44,
    command=toggle_relay1
)
relay1_button.grid(row=0, column=0, padx=12, pady=12, sticky="ew")

relay2_button = ctk.CTkButton(
    manual_control_row,
    text="Chlorine AUTO",
    font=("Poppins", 14, "bold"),
    corner_radius=12,
    height=44,
    command=toggle_relay2
)
relay2_button.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

refresh_manual_button_styles()

display_frame = ctk.CTkFrame(dosing_view, corner_radius=24, fg_color="#111a2a")
display_frame.pack(fill="x", padx=30, pady=(0, 12))
display_frame.grid_columnconfigure((0, 1), weight=1)

flow_card = ctk.CTkFrame(display_frame, corner_radius=18, fg_color="#182233")
flow_card.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
ctk.CTkLabel(
    flow_card,
    text="FLOW / MINUTE (L)",
    font=("Poppins", 16, "bold"),
    text_color="#9fb0c9"
).pack(anchor="w", padx=18, pady=(16, 2))
flow_value = ctk.CTkLabel(
    flow_card, text="0.00", font=("Poppins", 64, "bold"), text_color="#40f7c7"
)
flow_value.pack(anchor="w", padx=18, pady=(0, 18))

total_card = ctk.CTkFrame(display_frame, corner_radius=18, fg_color="#182233")
total_card.grid(row=0, column=1, padx=14, pady=14, sticky="nsew")
ctk.CTkLabel(
    total_card,
    text="WATER DATA (CURRENT HOUR) (L)",
    font=("Poppins", 16, "bold"),
    text_color="#9fb0c9"
).pack(anchor="w", padx=18, pady=(16, 2))
total_value = ctk.CTkLabel(
    total_card, text="0.000", font=("Poppins", 64, "bold"), text_color="#ffd166"
)
total_value.pack(anchor="w", padx=18, pady=(0, 18))

chemical_frame = ctk.CTkFrame(dosing_view, corner_radius=24, fg_color="#111a2a")
chemical_frame.pack(fill="x", padx=30, pady=(0, 14))

ctk.CTkLabel(
    chemical_frame,
    text="CHEMICAL STATUS",
    font=("Poppins", 26, "bold")
).pack(anchor="w", padx=20, pady=(14, 2))

ctk.CTkLabel(
    chemical_frame,
    text="Live values and dose settings from your chemical configuration source.",
    font=("Poppins", 13),
    text_color="#9fb0c9"
).pack(anchor="w", padx=20, pady=(0, 8))

chemical_cards_container = ctk.CTkFrame(chemical_frame, fg_color="transparent")
chemical_cards_container.pack(fill="x", padx=6, pady=(0, 10))

water_tab_active = False
water_range_mode = "Today"
water_refresh_job = None
water_canvas = None
water_table_box = None
water_chart_notice_label = None
water_filter_error_label = None
water_from_selector = None
water_to_selector = None
water_custom_from = None
water_custom_to = None
water_value_labels = {}

chemical_tab_active = False
chemical_range_mode = "Yesterday"
chemical_refresh_job = None
chemical_canvas = None
chemical_table_box = None
chemical_chart_notice_label = None
chemical_filter_error_label = None
chemical_from_selector = None
chemical_to_selector = None
chemical_custom_from = None
chemical_custom_to = None
chemical_value_labels = {}

water_header = ctk.CTkFrame(water_view, corner_radius=20)
water_header.pack(fill="x", padx=30, pady=(20, 10))

ctk.CTkLabel(
    water_header,
    text="WATER DATA ANALYTICS",
    font=("Poppins", 34, "bold")
).pack(anchor="w", padx=25, pady=(18, 2))

ctk.CTkLabel(
    water_header,
    text="Track water data trends, compare periods, and monitor hourly behavior in one view.",
    font=("Poppins", 15),
    text_color="#99a8bf"
).pack(anchor="w", padx=25, pady=(0, 18))

water_control_row = ctk.CTkFrame(water_view, corner_radius=16)
water_control_row.pack(fill="x", padx=30, pady=(0, 10))

ctk.CTkLabel(
    water_control_row,
    text="View Range",
    font=("Poppins", 15, "bold")
).pack(side="left", padx=(20, 10), pady=14)

water_range_selector = ctk.CTkSegmentedButton(
    water_control_row,
    values=["Today", "Yesterday", "30 Days", "Custom"],
    font=("Poppins", 14, "bold")
)
water_range_selector.pack(side="left", padx=(0, 12), pady=10)

water_refresh_btn = ctk.CTkButton(
    water_control_row,
    text="Refresh",
    font=("Poppins", 14, "bold"),
    width=120
)
water_refresh_btn.pack(side="right", padx=20, pady=10)

water_custom_row = ctk.CTkFrame(water_view, corner_radius=14)

ctk.CTkLabel(
    water_custom_row,
    text="Custom Range",
    font=("Poppins", 14, "bold"),
    text_color="#9fb0c9"
).pack(side="left", padx=(20, 10), pady=10)

def build_date_selector(parent, label_text):
    selector_frame = ctk.CTkFrame(parent, corner_radius=10)
    selector_frame.pack(side="left", padx=(0, 8), pady=8)

    ctk.CTkLabel(
        selector_frame,
        text=label_text,
        font=("Poppins", 12),
        text_color="#9fb0c9"
    ).pack(side="left", padx=(10, 6))

    today = datetime.now()
    year_values = [str(y) for y in range(today.year - 5, today.year + 2)]
    month_values = [f"{m:02d}" for m in range(1, 13)]
    day_values = [f"{d:02d}" for d in range(1, 32)]

    day_box = ctk.CTkComboBox(selector_frame, values=day_values, width=62)
    month_box = ctk.CTkComboBox(selector_frame, values=month_values, width=62)
    year_box = ctk.CTkComboBox(selector_frame, values=year_values, width=78)

    day_box.set(f"{today.day:02d}")
    month_box.set(f"{today.month:02d}")
    year_box.set(str(today.year))

    day_box.pack(side="left", padx=(0, 4), pady=8)
    month_box.pack(side="left", padx=(0, 4), pady=8)
    year_box.pack(side="left", padx=(0, 10), pady=8)

    return {
        "frame": selector_frame,
        "day": day_box,
        "month": month_box,
        "year": year_box,
    }

def update_selector_day_limit(selector):
    try:
        year = int(selector["year"].get())
        month = int(selector["month"].get())
        current_day = int(selector["day"].get())
    except ValueError:
        return

    max_day = calendar.monthrange(year, month)[1]
    day_values = [f"{d:02d}" for d in range(1, max_day + 1)]
    selector["day"].configure(values=day_values)
    selector["day"].set(f"{min(current_day, max_day):02d}")

water_from_selector = build_date_selector(water_custom_row, "From")
water_to_selector = build_date_selector(water_custom_row, "To")

water_from_selector["month"].configure(command=lambda _v: update_selector_day_limit(water_from_selector))
water_from_selector["year"].configure(command=lambda _v: update_selector_day_limit(water_from_selector))
water_to_selector["month"].configure(command=lambda _v: update_selector_day_limit(water_to_selector))
water_to_selector["year"].configure(command=lambda _v: update_selector_day_limit(water_to_selector))

update_selector_day_limit(water_from_selector)
update_selector_day_limit(water_to_selector)

water_apply_custom_btn = ctk.CTkButton(
    water_custom_row,
    text="Apply Custom",
    font=("Poppins", 13, "bold"),
    width=120
)
water_apply_custom_btn.pack(side="left", padx=(0, 10), pady=10)

water_filter_error_label = ctk.CTkLabel(
    water_custom_row,
    text="",
    font=("Poppins", 12),
    text_color="#ff9f9f"
)
water_filter_error_label.pack(side="left", padx=(0, 10), pady=10)

water_stats_frame = ctk.CTkFrame(water_view, corner_radius=20)
water_stats_frame.pack(fill="x", padx=30, pady=(0, 10))

stats_grid = ctk.CTkFrame(water_stats_frame, fg_color="transparent")
stats_grid.pack(fill="x", padx=15, pady=15)
for col in range(4):
    stats_grid.grid_columnconfigure(col, weight=1)

for i, (title, key, color) in enumerate([
    ("Total Water Data", "total", "#4dd0ff"),
    ("Average Usage", "avg", "#9eff7c"),
    ("Peak Usage", "peak", "#ffcd70"),
    ("Latest Usage", "latest", "#ff8e8e"),
]):
    card = ctk.CTkFrame(stats_grid, corner_radius=16)
    card.grid(row=0, column=i, padx=8, pady=5, sticky="nsew")
    ctk.CTkLabel(
        card,
        text=title,
        font=("Poppins", 14),
        text_color="#9fb0c9"
    ).pack(anchor="w", padx=16, pady=(14, 4))
    value_label = ctk.CTkLabel(
        card,
        text="-",
        font=("Poppins", 28, "bold"),
        text_color=color
    )
    value_label.pack(anchor="w", padx=16, pady=(0, 14))
    water_value_labels[key] = value_label

water_chart_frame = ctk.CTkFrame(water_view, corner_radius=20)
water_chart_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))

ctk.CTkLabel(
    water_chart_frame,
    text="Water Data Trend",
    font=("Poppins", 20, "bold")
).pack(anchor="w", padx=20, pady=(16, 0))

ctk.CTkLabel(
    water_chart_frame,
    text="Graph shows stored DB values for selected range",
    font=("Poppins", 13),
    text_color="#9fb0c9"
).pack(anchor="w", padx=20, pady=(0, 8))

water_chart_body = ctk.CTkFrame(water_chart_frame, corner_radius=16)
water_chart_body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

if MATPLOTLIB_AVAILABLE:
    water_fig = Figure(figsize=(7.5, 3.2), dpi=100)
    water_ax = water_fig.add_subplot(111)
    water_fig.patch.set_facecolor("#161b26")
    water_ax.set_facecolor("#161b26")
    water_canvas = FigureCanvasTkAgg(water_fig, master=water_chart_body)
    water_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
else:
    water_chart_notice_label = ctk.CTkLabel(
        water_chart_body,
        text="Matplotlib not installed. Install it to show chart: pip install matplotlib",
        font=("Poppins", 15),
        text_color="#ff9f9f"
    )
    water_chart_notice_label.pack(expand=True, pady=20)

water_table_frame = ctk.CTkFrame(water_view, corner_radius=20)
water_table_frame.pack(fill="x", padx=30, pady=(0, 20))

ctk.CTkLabel(
    water_table_frame,
    text="Recent Timeline",
    font=("Poppins", 18, "bold")
).pack(anchor="w", padx=20, pady=(14, 8))

water_table_box = ctk.CTkTextbox(water_table_frame, height=150, font=("Consolas", 13))
water_table_box.pack(fill="x", padx=20, pady=(0, 16))
water_table_box.configure(state="disabled")

chemical_header = ctk.CTkFrame(chemical_view, corner_radius=20)
chemical_header.pack(fill="x", padx=30, pady=(20, 10))

ctk.CTkLabel(
    chemical_header,
    text="CHEMICAL USAGE ANALYTICS",
    font=("Poppins", 34, "bold")
).pack(anchor="w", padx=25, pady=(18, 2))

ctk.CTkLabel(
    chemical_header,
    text="See acid and chlorine usage by day, week, month, or custom date range.",
    font=("Poppins", 15),
    text_color="#99a8bf"
).pack(anchor="w", padx=25, pady=(0, 18))

chemical_control_row = ctk.CTkFrame(chemical_view, corner_radius=16)
chemical_control_row.pack(fill="x", padx=30, pady=(0, 10))

ctk.CTkLabel(
    chemical_control_row,
    text="View Range",
    font=("Poppins", 15, "bold")
).pack(side="left", padx=(20, 10), pady=14)

chemical_range_selector = ctk.CTkSegmentedButton(
    chemical_control_row,
    values=["Today", "Yesterday", "7 Days", "30 Days", "Custom"],
    font=("Poppins", 14, "bold")
)
chemical_range_selector.pack(side="left", padx=(0, 12), pady=10)

chemical_refresh_btn = ctk.CTkButton(
    chemical_control_row,
    text="Refresh",
    font=("Poppins", 14, "bold"),
    width=120
)
chemical_refresh_btn.pack(side="right", padx=20, pady=10)

chemical_custom_row = ctk.CTkFrame(chemical_view, corner_radius=14)
ctk.CTkLabel(
    chemical_custom_row,
    text="Custom Range",
    font=("Poppins", 14, "bold"),
    text_color="#9fb0c9"
).pack(side="left", padx=(20, 10), pady=10)

chemical_from_selector = build_date_selector(chemical_custom_row, "From")
chemical_to_selector = build_date_selector(chemical_custom_row, "To")

chemical_from_selector["month"].configure(command=lambda _v: update_selector_day_limit(chemical_from_selector))
chemical_from_selector["year"].configure(command=lambda _v: update_selector_day_limit(chemical_from_selector))
chemical_to_selector["month"].configure(command=lambda _v: update_selector_day_limit(chemical_to_selector))
chemical_to_selector["year"].configure(command=lambda _v: update_selector_day_limit(chemical_to_selector))

update_selector_day_limit(chemical_from_selector)
update_selector_day_limit(chemical_to_selector)

chemical_apply_custom_btn = ctk.CTkButton(
    chemical_custom_row,
    text="Apply Custom",
    font=("Poppins", 13, "bold"),
    width=120
)
chemical_apply_custom_btn.pack(side="left", padx=(0, 10), pady=10)

chemical_filter_error_label = ctk.CTkLabel(
    chemical_custom_row,
    text="",
    font=("Poppins", 12),
    text_color="#ff9f9f"
)
chemical_filter_error_label.pack(side="left", padx=(0, 10), pady=10)

chemical_stats_frame = ctk.CTkFrame(chemical_view, corner_radius=20)
chemical_stats_frame.pack(fill="x", padx=30, pady=(0, 10))

chemical_stats_grid = ctk.CTkFrame(chemical_stats_frame, fg_color="transparent")
chemical_stats_grid.pack(fill="x", padx=15, pady=15)
for col in range(4):
    chemical_stats_grid.grid_columnconfigure(col, weight=1)

for i, (title, key, color) in enumerate([
    ("Acid Used", "acid_total", "#53e1ff"),
    ("Chlorine Used", "chlorine_total", "#6dff85"),
    ("Total Chemical", "total", "#ffc66b"),
    ("Dose Events", "events", "#ff8d8d"),
]):
    card = ctk.CTkFrame(chemical_stats_grid, corner_radius=16)
    card.grid(row=0, column=i, padx=8, pady=5, sticky="nsew")
    ctk.CTkLabel(
        card,
        text=title,
        font=("Poppins", 14),
        text_color="#9fb0c9"
    ).pack(anchor="w", padx=16, pady=(14, 4))
    value_label = ctk.CTkLabel(
        card,
        text="-",
        font=("Poppins", 28, "bold"),
        text_color=color
    )
    value_label.pack(anchor="w", padx=16, pady=(0, 14))
    chemical_value_labels[key] = value_label

chemical_chart_frame = ctk.CTkFrame(chemical_view, corner_radius=20)
chemical_chart_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))

ctk.CTkLabel(
    chemical_chart_frame,
    text="Acid vs Chlorine Trend",
    font=("Poppins", 20, "bold")
).pack(anchor="w", padx=20, pady=(16, 0))

ctk.CTkLabel(
    chemical_chart_frame,
    text="Based on hourly usage log saved by the dosing system.",
    font=("Poppins", 13),
    text_color="#9fb0c9"
).pack(anchor="w", padx=20, pady=(0, 8))

chemical_chart_body = ctk.CTkFrame(chemical_chart_frame, corner_radius=16)
chemical_chart_body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

if MATPLOTLIB_AVAILABLE:
    chemical_fig = Figure(figsize=(7.5, 3.2), dpi=100)
    chemical_ax = chemical_fig.add_subplot(111)
    chemical_fig.patch.set_facecolor("#161b26")
    chemical_ax.set_facecolor("#161b26")
    chemical_canvas = FigureCanvasTkAgg(chemical_fig, master=chemical_chart_body)
    chemical_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
else:
    chemical_chart_notice_label = ctk.CTkLabel(
        chemical_chart_body,
        text="Matplotlib not installed. Install it to show chart: pip install matplotlib",
        font=("Poppins", 15),
        text_color="#ff9f9f"
    )
    chemical_chart_notice_label.pack(expand=True, pady=20)

chemical_table_frame = ctk.CTkFrame(chemical_view, corner_radius=20)
chemical_table_frame.pack(fill="x", padx=30, pady=(0, 20))

ctk.CTkLabel(
    chemical_table_frame,
    text="Chemical Timeline",
    font=("Poppins", 18, "bold")
).pack(anchor="w", padx=20, pady=(14, 8))

chemical_table_box = ctk.CTkTextbox(chemical_table_frame, height=160, font=("Consolas", 13))
chemical_table_box.pack(fill="x", padx=20, pady=(0, 16))
chemical_table_box.configure(state="disabled")

config_header = ctk.CTkFrame(config_view, corner_radius=20)
config_header.pack(fill="x", padx=30, pady=(20, 10))

ctk.CTkLabel(
    config_header,
    text="SYSTEM CONFIGURATION",
    font=("Poppins", 34, "bold")
).pack(anchor="w", padx=25, pady=(18, 2))

ctk.CTkLabel(
    config_header,
    text="Configure calibration, dosing amounts, trigger liters, and hourly storage behavior.",
    font=("Poppins", 15),
    text_color="#99a8bf"
).pack(anchor="w", padx=25, pady=(0, 18))

config_form = ctk.CTkFrame(config_view, corner_radius=20)
config_form.pack(fill="x", padx=30, pady=(0, 12))
config_form.grid_columnconfigure((0, 1), weight=1)

config_fields = [
    ("Calibration Factor", "calibration_factor"),
    ("Acid ml per Start", "acid_ml_per_start"),
    ("Chlorine ml per Start", "chlorine_ml_per_start"),
    ("Acid Pump Duration (sec)", "acid_pump_duration_sec"),
    ("Chlorine Pump Duration (sec)", "chlorine_pump_duration_sec"),
    ("Hourly Save Interval (minutes)", "db_interval_minutes"),
    ("Acid Value (CSV Liters)", "acid_trigger_liters"),
    ("Chlorine Value (CSV Liters)", "chlorine_trigger_liters"),
]

config_entries = {}
for idx, (label_text, key) in enumerate(config_fields):
    row = idx // 2
    col = idx % 2
    field_card = ctk.CTkFrame(config_form, corner_radius=14, fg_color="#182233")
    field_card.grid(row=row, column=col, padx=10, pady=10, sticky="ew")
    ctk.CTkLabel(
        field_card,
        text=label_text,
        font=("Poppins", 13, "bold"),
        text_color="#9fb0c9"
    ).pack(anchor="w", padx=14, pady=(12, 4))
    entry = ctk.CTkEntry(field_card, height=38, font=("Poppins", 14))
    entry.pack(fill="x", padx=14, pady=(0, 12))
    config_entries[key] = entry

config_action_row = ctk.CTkFrame(config_view, corner_radius=16, fg_color="#101722")
config_action_row.pack(fill="x", padx=30, pady=(0, 14))

config_status_label = ctk.CTkLabel(
    config_action_row,
    text="",
    font=("Poppins", 13),
    text_color="#9fb0c9"
)
config_status_label.pack(side="left", padx=16, pady=12)

config_csv_values_label = ctk.CTkLabel(
    config_view,
    text="CSV: Acid - | Chlorine -",
    font=("Poppins", 13),
    text_color="#8ec5ff"
)
config_csv_values_label.pack(anchor="w", padx=34, pady=(0, 8))

def refresh_csv_values_label():
    acid_csv, chlorine_csv = read_chemical_values()
    acid_text = f"{acid_csv:.3f}" if acid_csv is not None else "-"
    chlorine_text = f"{chlorine_csv:.3f}" if chlorine_csv is not None else "-"
    config_csv_values_label.configure(
        text=f"CSV Trigger Values -> Acid: {acid_text} L | Chlorine: {chlorine_text} L"
    )

def fill_config_form():
    refresh_csv_values_label()
    acid_csv, chlorine_csv = read_chemical_values()
    acid_display = acid_csv if acid_csv is not None and acid_csv > 0 else acid_trigger_liters
    chlorine_display = chlorine_csv if chlorine_csv is not None and chlorine_csv > 0 else chlorine_trigger_liters

    config_entries["calibration_factor"].delete(0, "end")
    config_entries["calibration_factor"].insert(0, f"{calibrationFactor:.6f}")
    config_entries["acid_ml_per_start"].delete(0, "end")
    config_entries["acid_ml_per_start"].insert(0, f"{ACID_ML_PER_START:.3f}")
    config_entries["chlorine_ml_per_start"].delete(0, "end")
    config_entries["chlorine_ml_per_start"].insert(0, f"{CHLORINE_ML_PER_START:.3f}")
    config_entries["acid_pump_duration_sec"].delete(0, "end")
    config_entries["acid_pump_duration_sec"].insert(0, f"{ACID_PUMP_DURATION:.3f}")
    config_entries["chlorine_pump_duration_sec"].delete(0, "end")
    config_entries["chlorine_pump_duration_sec"].insert(0, f"{CHLORINE_PUMP_DURATION:.3f}")
    config_entries["db_interval_minutes"].delete(0, "end")
    config_entries["db_interval_minutes"].insert(0, f"{DB_INSERT_INTERVAL_SECONDS / 60:.1f}")
    config_entries["acid_trigger_liters"].delete(0, "end")
    config_entries["acid_trigger_liters"].insert(0, f"{acid_display:.3f}")
    config_entries["chlorine_trigger_liters"].delete(0, "end")
    config_entries["chlorine_trigger_liters"].insert(0, f"{chlorine_display:.3f}")

def parse_positive_float(entry_key, label):
    raw = config_entries[entry_key].get().strip()
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{label} must be a number")
    if value <= 0:
        raise ValueError(f"{label} must be greater than 0")
    return value

def save_configuration():
    global calibrationFactor, ACID_ML_PER_START, CHLORINE_ML_PER_START
    global ACID_PUMP_DURATION, CHLORINE_PUMP_DURATION, DB_INSERT_INTERVAL_SECONDS
    global acid_trigger_liters, chlorine_trigger_liters
    try:
        new_calibration_factor = parse_positive_float("calibration_factor", "Calibration Factor")
        new_acid_ml_per_start = parse_positive_float("acid_ml_per_start", "Acid ml per Start")
        new_chlorine_ml_per_start = parse_positive_float("chlorine_ml_per_start", "Chlorine ml per Start")
        new_acid_pump_duration = parse_positive_float("acid_pump_duration_sec", "Acid Pump Duration")
        new_chlorine_pump_duration = parse_positive_float("chlorine_pump_duration_sec", "Chlorine Pump Duration")
        new_interval_minutes = parse_positive_float("db_interval_minutes", "Hourly Save Interval")
        new_acid_trigger_liters = parse_positive_float("acid_trigger_liters", "Acid Value")
        new_chlorine_trigger_liters = parse_positive_float("chlorine_trigger_liters", "Chlorine Value")
    except ValueError as exc:
        config_status_label.configure(text=str(exc), text_color="#ff9f9f")
        return

    new_interval_seconds = max(60, int(round(new_interval_minutes * 60)))

    calibrationFactor = new_calibration_factor
    ACID_ML_PER_START = new_acid_ml_per_start
    CHLORINE_ML_PER_START = new_chlorine_ml_per_start
    ACID_PUMP_DURATION = new_acid_pump_duration
    CHLORINE_PUMP_DURATION = new_chlorine_pump_duration
    DB_INSERT_INTERVAL_SECONDS = new_interval_seconds
    acid_trigger_liters = new_acid_trigger_liters
    chlorine_trigger_liters = new_chlorine_trigger_liters

    app_config["calibration_factor"] = calibrationFactor
    app_config["acid_ml_per_start"] = ACID_ML_PER_START
    app_config["chlorine_ml_per_start"] = CHLORINE_ML_PER_START
    app_config["acid_pump_duration_sec"] = ACID_PUMP_DURATION
    app_config["chlorine_pump_duration_sec"] = CHLORINE_PUMP_DURATION
    app_config["db_insert_interval_seconds"] = DB_INSERT_INTERVAL_SECONDS
    app_config["acid_trigger_liters"] = acid_trigger_liters
    app_config["chlorine_trigger_liters"] = chlorine_trigger_liters

    try:
        save_app_config(app_config)
    except Exception as exc:
        config_status_label.configure(text=f"Save failed: {exc}", text_color="#ff9f9f")
        return

    csv_warning = ""
    try:
        save_chemical_values_to_csv(acid_trigger_liters, chlorine_trigger_liters)
    except Exception as exc:
        csv_warning = f" (CSV not updated: {exc})"

    config_status_label.configure(
        text=f"Configuration saved (Acid/Chlorine updated in CSV){csv_warning}",
        text_color="#7dff9a" if not csv_warning else "#ffd37d"
    )
    send_server_event(
        event_type="CONFIG_UPDATE",
        event_time=datetime.now(),
        payload={
            "calibration_factor": calibrationFactor,
            "acid_ml_per_start": ACID_ML_PER_START,
            "chlorine_ml_per_start": CHLORINE_ML_PER_START,
            "acid_pump_duration_sec": ACID_PUMP_DURATION,
            "chlorine_pump_duration_sec": CHLORINE_PUMP_DURATION,
            "db_insert_interval_seconds": DB_INSERT_INTERVAL_SECONDS,
            "acid_trigger_liters": acid_trigger_liters,
            "chlorine_trigger_liters": chlorine_trigger_liters,
        },
    )
    fill_config_form()

config_save_btn = ctk.CTkButton(
    config_action_row,
    text="Save Configuration",
    font=("Poppins", 14, "bold"),
    width=220,
    command=save_configuration
)
config_save_btn.pack(side="right", padx=16, pady=12)

fill_config_form()

chemical_cards = OrderedDict()
show_dosing_view()

def set_custom_controls_enabled(enabled):
    state = "normal" if enabled else "disabled"
    for selector in (water_from_selector, water_to_selector):
        selector["day"].configure(state=state)
        selector["month"].configure(state=state)
        selector["year"].configure(state=state)
    water_apply_custom_btn.configure(state=state)
    if enabled:
        water_custom_row.pack(fill="x", padx=30, pady=(0, 10), before=water_stats_frame)
    else:
        water_custom_row.pack_forget()

def get_filter_text():
    if water_range_mode == "Custom" and water_custom_from and water_custom_to:
        return f"{water_custom_from:%Y-%m-%d} to {water_custom_to:%Y-%m-%d}"
    return water_range_mode

def fetch_water_data():
    now = datetime.now()

    if water_range_mode == "Today":
        start_time = datetime.combine(now.date(), datetime.min.time())
        end_time = now
        params = (start_time, end_time)
        query = f"SELECT water_value, timestamp FROM {WATER_TABLE} WHERE timestamp BETWEEN %s AND %s ORDER BY timestamp ASC"
    elif water_range_mode == "Yesterday":
        yesterday = now.date() - timedelta(days=1)
        start_time = datetime.combine(yesterday, datetime.min.time())
        end_time = datetime.combine(yesterday, datetime.max.time())
        params = (start_time, end_time)
        query = f"SELECT water_value, timestamp FROM {WATER_TABLE} WHERE timestamp BETWEEN %s AND %s ORDER BY timestamp ASC"
    elif water_range_mode == "30 Days":
        start_time = now - timedelta(days=30)
        params = (start_time,)
        query = f"SELECT water_value, timestamp FROM {WATER_TABLE} WHERE timestamp >= %s ORDER BY timestamp ASC"
    elif water_range_mode == "Custom":
        if not water_custom_from or not water_custom_to:
            return None
        params = (water_custom_from, water_custom_to)
        query = f"SELECT water_value, timestamp FROM {WATER_TABLE} WHERE timestamp BETWEEN %s AND %s ORDER BY timestamp ASC"
    else:
        return []

    cursor.execute(query, params)
    return cursor.fetchall()

def update_water_table(rows):
    water_table_box.configure(state="normal")
    water_table_box.delete("1.0", "end")
    water_table_box.insert("end", "Timestamp              | Water Data (L)\n")
    water_table_box.insert("end", "-" * 38 + "\n")

    if rows is None:
        water_table_box.insert("end", "Please select From/To and click Apply Custom.\n")
    elif not rows:
        water_table_box.insert("end", "No data available for selected range.\n")
    else:
        for value, ts in rows[-12:]:
            water_table_box.insert("end", f"{ts:%Y-%m-%d %H:%M:%S} | {float(value):8.3f}\n")

    water_table_box.configure(state="disabled")

def update_water_chart(rows):
    if not MATPLOTLIB_AVAILABLE:
        return

    water_ax.clear()
    water_ax.set_facecolor("#161b26")

    if rows is None:
        water_ax.text(0.5, 0.5, "Select From/To and click Apply Custom", color="#9fb0c9",
                      ha="center", va="center", transform=water_ax.transAxes, fontsize=13)
        water_ax.grid(False)
    elif rows:
        x_vals = [ts for _, ts in rows]
        y_vals = [float(v) for v, _ in rows]
        water_ax.plot(x_vals, y_vals, color="#42e8e0", linewidth=2.3)
        water_ax.fill_between(x_vals, y_vals, color="#1fb2aa", alpha=0.25)
        water_ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.25)
    else:
        water_ax.text(0.5, 0.5, "No data in selected range", color="#9fb0c9",
                      ha="center", va="center", transform=water_ax.transAxes, fontsize=13)
        water_ax.grid(False)

    water_ax.tick_params(colors="#9fb0c9", labelsize=9)
    for spine in water_ax.spines.values():
        spine.set_color("#2b354a")
    water_ax.set_title(f"Water Data Trend ({get_filter_text()})", color="#d8e1f2", fontsize=12, pad=10)
    water_fig.tight_layout()
    water_canvas.draw_idle()

def update_water_summary(rows):
    if rows is None:
        water_value_labels["total"].configure(text="-")
        water_value_labels["avg"].configure(text="-")
        water_value_labels["peak"].configure(text="-")
        water_value_labels["latest"].configure(text="-")
        return

    values = [float(v) for v, _ in rows]
    total = sum(values) if values else 0.0
    avg = (total / len(values)) if values else 0.0
    peak = max(values) if values else 0.0
    latest = values[-1] if values else 0.0

    water_value_labels["total"].configure(text=f"{total:.2f} L")
    water_value_labels["avg"].configure(text=f"{avg:.2f} L")
    water_value_labels["peak"].configure(text=f"{peak:.2f} L")
    water_value_labels["latest"].configure(text=f"{latest:.2f} L")

def schedule_water_refresh(delay_ms=15000):
    global water_refresh_job
    if water_refresh_job is not None:
        app.after_cancel(water_refresh_job)
    water_refresh_job = app.after(delay_ms, update_water_dashboard)

def update_water_dashboard():
    global water_refresh_job
    if not water_tab_active:
        water_refresh_job = None
        return

    try:
        rows = fetch_water_data()
        update_water_summary(rows)
        update_water_chart(rows)
        update_water_table(rows)
    except Exception as exc:
        update_water_table([])
        water_value_labels["total"].configure(text="DB Error")
        water_value_labels["avg"].configure(text="-")
        water_value_labels["peak"].configure(text="-")
        water_value_labels["latest"].configure(text="-")
        if water_chart_notice_label is not None:
            water_chart_notice_label.configure(text=f"Chart unavailable: {exc}")
    schedule_water_refresh(15000)

def on_water_range_change(value):
    global water_range_mode, water_custom_from, water_custom_to
    water_range_mode = value
    water_filter_error_label.configure(text="")
    set_custom_controls_enabled(value == "Custom")
    if value == "Custom":
        water_custom_from = None
        water_custom_to = None
        if water_tab_active:
            update_water_dashboard()
        return
    if water_tab_active:
        update_water_dashboard()

def refresh_water_dashboard():
    if water_tab_active:
        update_water_dashboard()

def apply_custom_range():
    global water_custom_from, water_custom_to

    try:
        from_date = datetime(
            int(water_from_selector["year"].get()),
            int(water_from_selector["month"].get()),
            int(water_from_selector["day"].get())
        ).date()
        to_date = datetime(
            int(water_to_selector["year"].get()),
            int(water_to_selector["month"].get()),
            int(water_to_selector["day"].get())
        ).date()
        custom_from = datetime.combine(from_date, datetime.min.time())
        custom_to = datetime.combine(to_date, datetime.max.time())
    except ValueError:
        water_filter_error_label.configure(text="Please select valid dates")
        return

    if custom_from > custom_to:
        water_filter_error_label.configure(text="From date must be before To date")
        return

    water_custom_from = custom_from
    water_custom_to = custom_to
    water_filter_error_label.configure(text="Custom range applied")
    if water_tab_active and water_range_mode == "Custom":
        update_water_dashboard()

water_range_selector.set("Today")
water_range_selector.configure(command=on_water_range_change)
water_refresh_btn.configure(command=refresh_water_dashboard)
water_apply_custom_btn.configure(command=apply_custom_range)
set_custom_controls_enabled(False)

def set_chemical_custom_controls_enabled(enabled):
    state = "normal" if enabled else "disabled"
    for selector in (chemical_from_selector, chemical_to_selector):
        selector["day"].configure(state=state)
        selector["month"].configure(state=state)
        selector["year"].configure(state=state)
    chemical_apply_custom_btn.configure(state=state)
    if enabled:
        chemical_custom_row.pack(fill="x", padx=30, pady=(0, 10), before=chemical_stats_frame)
    else:
        chemical_custom_row.pack_forget()

def get_chemical_filter_text():
    if chemical_range_mode == "Custom" and chemical_custom_from and chemical_custom_to:
        return f"{chemical_custom_from:%Y-%m-%d} to {chemical_custom_to:%Y-%m-%d}"
    return chemical_range_mode

def fetch_chemical_data():
    now = datetime.now()

    if chemical_range_mode == "Today":
        start_time = datetime.combine(now.date(), datetime.min.time())
        params = (start_time, now)
        query = (
            f"SELECT period_end, acid_ml_used, chlorine_ml_used, acid_starts, chlorine_starts "
            f"FROM {CHEMICAL_HOURLY_TABLE} WHERE period_end BETWEEN %s AND %s ORDER BY period_end ASC"
        )
    elif chemical_range_mode == "Yesterday":
        yesterday = now.date() - timedelta(days=1)
        start_time = datetime.combine(yesterday, datetime.min.time())
        end_time = datetime.combine(yesterday, datetime.max.time())
        params = (start_time, end_time)
        query = (
            f"SELECT period_end, acid_ml_used, chlorine_ml_used, acid_starts, chlorine_starts "
            f"FROM {CHEMICAL_HOURLY_TABLE} WHERE period_end BETWEEN %s AND %s ORDER BY period_end ASC"
        )
    elif chemical_range_mode == "7 Days":
        start_time = now - timedelta(days=7)
        params = (start_time,)
        query = (
            f"SELECT period_end, acid_ml_used, chlorine_ml_used, acid_starts, chlorine_starts "
            f"FROM {CHEMICAL_HOURLY_TABLE} WHERE period_end >= %s ORDER BY period_end ASC"
        )
    elif chemical_range_mode == "30 Days":
        start_time = now - timedelta(days=30)
        params = (start_time,)
        query = (
            f"SELECT period_end, acid_ml_used, chlorine_ml_used, acid_starts, chlorine_starts "
            f"FROM {CHEMICAL_HOURLY_TABLE} WHERE period_end >= %s ORDER BY period_end ASC"
        )
    elif chemical_range_mode == "Custom":
        if not chemical_custom_from or not chemical_custom_to:
            return None
        params = (chemical_custom_from, chemical_custom_to)
        query = (
            f"SELECT period_end, acid_ml_used, chlorine_ml_used, acid_starts, chlorine_starts "
            f"FROM {CHEMICAL_HOURLY_TABLE} WHERE period_end BETWEEN %s AND %s ORDER BY period_end ASC"
        )
    else:
        return []

    cursor.execute(query, params)
    return cursor.fetchall()

def update_chemical_table(rows):
    chemical_table_box.configure(state="normal")
    chemical_table_box.delete("1.0", "end")
    chemical_table_box.insert("end", "Timestamp              | Acid(ml) | Chlorine(ml) | Events\n")
    chemical_table_box.insert("end", "-" * 66 + "\n")

    if rows is None:
        chemical_table_box.insert("end", "Please select From/To and click Apply Custom.\n")
    elif not rows:
        chemical_table_box.insert("end", "No chemical usage data in selected range.\n")
    else:
        for ts, acid_ml, chlorine_ml, acid_starts, chlorine_starts in rows[-12:]:
            events = int(acid_starts) + int(chlorine_starts)
            chemical_table_box.insert(
                "end",
                f"{ts:%Y-%m-%d %H:%M:%S} | {float(acid_ml):8.3f} | {float(chlorine_ml):12.3f} | {events:6d}\n"
            )
    chemical_table_box.configure(state="disabled")

def update_chemical_summary(rows):
    if rows is None:
        for key in ("acid_total", "chlorine_total", "total", "events"):
            chemical_value_labels[key].configure(text="-")
        return

    acid_total = sum(float(r[1]) for r in rows) if rows else 0.0
    chlorine_total = sum(float(r[2]) for r in rows) if rows else 0.0
    total = acid_total + chlorine_total
    events = sum(int(r[3]) + int(r[4]) for r in rows) if rows else 0

    chemical_value_labels["acid_total"].configure(text=f"{acid_total:.2f} ml")
    chemical_value_labels["chlorine_total"].configure(text=f"{chlorine_total:.2f} ml")
    chemical_value_labels["total"].configure(text=f"{total:.2f} ml")
    chemical_value_labels["events"].configure(text=f"{events}")

def build_chemical_chart_series(rows):
    if not rows:
        return [], [], []
    if chemical_range_mode in ("7 Days", "30 Days"):
        grouped = OrderedDict()
        for ts, acid_ml, chlorine_ml, _acid_starts, _chlorine_starts in rows:
            key = ts.strftime("%m-%d")
            if key not in grouped:
                grouped[key] = [0.0, 0.0]
            grouped[key][0] += float(acid_ml)
            grouped[key][1] += float(chlorine_ml)
        labels = list(grouped.keys())
        acid_vals = [v[0] for v in grouped.values()]
        chlorine_vals = [v[1] for v in grouped.values()]
        return labels, acid_vals, chlorine_vals

    labels = [ts.strftime("%m-%d %H:%M") for ts, *_rest in rows]
    acid_vals = [float(r[1]) for r in rows]
    chlorine_vals = [float(r[2]) for r in rows]
    return labels, acid_vals, chlorine_vals

def update_chemical_chart(rows):
    if not MATPLOTLIB_AVAILABLE:
        return

    chemical_ax.clear()
    chemical_ax.set_facecolor("#161b26")

    if rows is None:
        chemical_ax.text(
            0.5, 0.5, "Select From/To and click Apply Custom",
            color="#9fb0c9", ha="center", va="center", transform=chemical_ax.transAxes, fontsize=13
        )
        chemical_ax.grid(False)
    elif rows:
        labels, acid_vals, chlorine_vals = build_chemical_chart_series(rows)
        x_idx = list(range(len(labels)))
        chemical_ax.plot(x_idx, acid_vals, color="#4dd7ff", linewidth=2.2, label="Acid")
        chemical_ax.plot(x_idx, chlorine_vals, color="#7dff87", linewidth=2.2, label="Chlorine")
        chemical_ax.fill_between(x_idx, acid_vals, color="#2fa4c7", alpha=0.18)
        chemical_ax.fill_between(x_idx, chlorine_vals, color="#4ec05d", alpha=0.16)
        step = max(1, len(labels) // 8)
        tick_positions = x_idx[::step]
        tick_labels = labels[::step]
        chemical_ax.set_xticks(tick_positions)
        chemical_ax.set_xticklabels(tick_labels, rotation=20, ha="right")
        chemical_ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.25)
        legend = chemical_ax.legend(loc="upper left", facecolor="#161b26", edgecolor="#2b354a")
        if legend is not None:
            for text in legend.get_texts():
                text.set_color("#dbe6fb")
    else:
        chemical_ax.text(
            0.5, 0.5, "No chemical data in selected range",
            color="#9fb0c9", ha="center", va="center", transform=chemical_ax.transAxes, fontsize=13
        )
        chemical_ax.grid(False)

    chemical_ax.tick_params(colors="#9fb0c9", labelsize=9)
    for spine in chemical_ax.spines.values():
        spine.set_color("#2b354a")
    chemical_ax.set_title(f"Chemical Usage Trend ({get_chemical_filter_text()})", color="#d8e1f2", fontsize=12, pad=10)
    chemical_fig.tight_layout()
    chemical_canvas.draw_idle()

def schedule_chemical_refresh(delay_ms=15000):
    global chemical_refresh_job
    if chemical_refresh_job is not None:
        app.after_cancel(chemical_refresh_job)
    chemical_refresh_job = app.after(delay_ms, update_chemical_dashboard)

def update_chemical_dashboard():
    global chemical_refresh_job
    if not chemical_tab_active:
        chemical_refresh_job = None
        return

    try:
        rows = fetch_chemical_data()
        update_chemical_summary(rows)
        update_chemical_chart(rows)
        update_chemical_table(rows)
    except Exception as exc:
        update_chemical_table([])
        chemical_value_labels["acid_total"].configure(text="DB Error")
        chemical_value_labels["chlorine_total"].configure(text="-")
        chemical_value_labels["total"].configure(text="-")
        chemical_value_labels["events"].configure(text="-")
        if chemical_chart_notice_label is not None:
            chemical_chart_notice_label.configure(text=f"Chart unavailable: {exc}")
    schedule_chemical_refresh(15000)

def on_chemical_range_change(value):
    global chemical_range_mode, chemical_custom_from, chemical_custom_to
    chemical_range_mode = value
    chemical_filter_error_label.configure(text="")
    set_chemical_custom_controls_enabled(value == "Custom")
    if value == "Custom":
        chemical_custom_from = None
        chemical_custom_to = None
        if chemical_tab_active:
            update_chemical_dashboard()
        return
    if chemical_tab_active:
        update_chemical_dashboard()

def refresh_chemical_dashboard():
    if chemical_tab_active:
        update_chemical_dashboard()

def apply_chemical_custom_range():
    global chemical_custom_from, chemical_custom_to
    try:
        from_date = datetime(
            int(chemical_from_selector["year"].get()),
            int(chemical_from_selector["month"].get()),
            int(chemical_from_selector["day"].get())
        ).date()
        to_date = datetime(
            int(chemical_to_selector["year"].get()),
            int(chemical_to_selector["month"].get()),
            int(chemical_to_selector["day"].get())
        ).date()
        custom_from = datetime.combine(from_date, datetime.min.time())
        custom_to = datetime.combine(to_date, datetime.max.time())
    except ValueError:
        chemical_filter_error_label.configure(text="Please select valid dates")
        return

    if custom_from > custom_to:
        chemical_filter_error_label.configure(text="From date must be before To date")
        return

    chemical_custom_from = custom_from
    chemical_custom_to = custom_to
    chemical_filter_error_label.configure(text="Custom range applied")
    if chemical_tab_active and chemical_range_mode == "Custom":
        update_chemical_dashboard()

chemical_range_selector.set("Yesterday")
chemical_range_selector.configure(command=on_chemical_range_change)
chemical_refresh_btn.configure(command=refresh_chemical_dashboard)
chemical_apply_custom_btn.configure(command=apply_chemical_custom_range)
set_chemical_custom_controls_enabled(False)

def update_chemical_display():
    if not os.path.exists(CHEMICAL_CSV):
        app.after(3000, update_chemical_display)
        return

    with open(CHEMICAL_CSV) as f:
        for row in csv.DictReader(f):
            name = row["name"]
            value = row["value"]
            dose = row["dose"]

            if name not in chemical_cards:
                card = ctk.CTkFrame(chemical_cards_container, corner_radius=18, fg_color="#182233")
                card.pack(side="left", expand=True, fill="both", padx=10, pady=8)

                ctk.CTkLabel(card, text=name,
                             font=("Poppins", 22, "bold")).pack(pady=(14, 4))

                val_lbl = ctk.CTkLabel(card, text=value,
                                       font=("Poppins", 46, "bold"),
                                       text_color="#00ccff")
                val_lbl.pack()

                dose_lbl = ctk.CTkLabel(card, text=f"Dose : {dose}",
                                        font=("Poppins", 17),
                                        text_color="#ffaa00")
                dose_lbl.pack(pady=(4, 14))

                chemical_cards[name] = (val_lbl, dose_lbl)
            else:
                chemical_cards[name][0].configure(text=value)
                chemical_cards[name][1].configure(text=f"Dose : {dose}")

    try:
        refresh_csv_values_label()
    except Exception:
        pass

    app.after(3000, update_chemical_display)

last_time = time.time()
last_db_insert = time.time()

next_acid_liter = 0.0
next_chlorine_liter = 0.0

def update_loop():
    global pulse_count, totalLiters, sessionLiters, totalPulses
    global last_time, last_db_insert
    global next_acid_liter, next_chlorine_liter
    global acid_pump_running, chlorine_pump_running
    global acid_off_time, chlorine_off_time
    global acid_starts_hour, chlorine_starts_hour
    global acid_runtime_seconds_hour, chlorine_runtime_seconds_hour
    global last_server_sync_retry, last_live_snapshot_bucket

    acid_csv, chlorine_csv = read_chemical_values()
    effective_acid_trigger = acid_csv if acid_csv is not None and acid_csv > 0 else acid_trigger_liters
    effective_chlorine_trigger = chlorine_csv if chlorine_csv is not None and chlorine_csv > 0 else chlorine_trigger_liters

    now = time.time()

    if now - last_time >= 1:
        elapsed_seconds = now - last_time

        with flow_lock:
            pulses = pulse_count
            pulse_count = 0
            totalPulses += pulses

        flowRate = pulses / calibrationFactor
        liters = flowRate / 60.0

        totalLiters += liters
        sessionLiters += liters

        flow_value.configure(text=f"{flowRate:.2f}")
        total_value.configure(text=f"{sessionLiters:.3f}")
        pulse_value_label.configure(text=str(totalPulses))

        if effective_acid_trigger > 0 and pulses > 0:

            dose_index = int(totalLiters / effective_acid_trigger)

            if dose_index > next_acid_liter and not acid_pump_running and not relay1_manual:
                start_acid_pump()
                next_acid_liter = dose_index

        if effective_chlorine_trigger > 0 and pulses > 0:

            dose_index = int(totalLiters / effective_chlorine_trigger)

            if dose_index > next_chlorine_liter and not chlorine_pump_running and not relay2_manual:
                start_chlorine_pump()
                next_chlorine_liter = dose_index

        if acid_pump_running or relay1_manual:
            acid_runtime_seconds_hour += elapsed_seconds
        if chlorine_pump_running or relay2_manual:
            chlorine_runtime_seconds_hour += elapsed_seconds

        if now - last_db_insert >= DB_INSERT_INTERVAL_SECONDS:
            period_start = datetime.fromtimestamp(last_db_insert)
            period_end = datetime.fromtimestamp(now)
            insert_water_value(sessionLiters)
            insert_chemical_hourly_usage(
                period_start=period_start,
                period_end=period_end,
                acid_starts=acid_starts_hour,
                chlorine_starts=chlorine_starts_hour,
                acid_runtime_seconds=acid_runtime_seconds_hour,
                chlorine_runtime_seconds=chlorine_runtime_seconds_hour,
            )
            send_server_event(
                event_type="WATER_HOURLY",
                event_time=period_end,
                payload={
                    "period_start": period_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "period_end": period_end.strftime("%Y-%m-%d %H:%M:%S"),
                    "water_liters": round(sessionLiters, 3),
                    "pulses": int(totalPulses),
                },
            )
            send_server_event(
                event_type="CHEMICAL_HOURLY",
                event_time=period_end,
                payload={
                    "period_start": period_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "period_end": period_end.strftime("%Y-%m-%d %H:%M:%S"),
                    "acid_starts": int(acid_starts_hour),
                    "chlorine_starts": int(chlorine_starts_hour),
                    "acid_ml_used": round(acid_starts_hour * ACID_ML_PER_START, 3),
                    "chlorine_ml_used": round(chlorine_starts_hour * CHLORINE_ML_PER_START, 3),
                    "acid_runtime_seconds": round(acid_runtime_seconds_hour, 3),
                    "chlorine_runtime_seconds": round(chlorine_runtime_seconds_hour, 3),
                },
            )
            sessionLiters = 0.0
            totalPulses = 0
            acid_starts_hour = 0
            chlorine_starts_hour = 0
            acid_runtime_seconds_hour = 0.0
            chlorine_runtime_seconds_hour = 0.0
            pulse_value_label.configure(text="0")
            total_value.configure(text="0.000")
            last_db_insert = now

        live_bucket = int(now // 60)
        if last_live_snapshot_bucket != live_bucket:
            last_live_snapshot_bucket = live_bucket
            send_server_event(
                event_type="LIVE_SNAPSHOT",
                event_time=datetime.fromtimestamp(live_bucket * 60),
                payload={
                    "flow_rate_lpm": round(flowRate, 3),
                    "current_hour_water_liters": round(sessionLiters, 3),
                    "total_water_liters": round(totalLiters, 3),
                    "running_pulses": int(totalPulses),
                    "acid_status": "manual" if relay1_manual else ("running" if acid_pump_running else "automatic"),
                    "chlorine_status": "manual" if relay2_manual else ("running" if chlorine_pump_running else "automatic"),
                    "acid_trigger_liters": round(effective_acid_trigger, 3),
                    "chlorine_trigger_liters": round(effective_chlorine_trigger, 3),
                },
            )

        last_time = now

    if now - last_server_sync_retry >= SERVER_SYNC_RETRY_INTERVAL_SECONDS:
        last_server_sync_retry = now
        flush_pending_sync_events()

    if acid_pump_running and now >= acid_off_time:
        GPIO.output(RELAY1, RELAY_OFF)
        acid_pump_running = False

    if chlorine_pump_running and now >= chlorine_off_time:
        GPIO.output(RELAY2, RELAY_OFF)`r`nGPIO.output(RELAY3, RELAY_OFF)`r`n        chlorine_pump_running = False

    if relay1_manual:
        acid_status_value.configure(text="Manual ON", text_color="#52ffa8")
    else:
        acid_status_value.configure(
            text="Auto Running" if acid_pump_running else "Automatic",
            text_color="#66ff9f" if acid_pump_running else "#7ad6ff"
        )

    if relay2_manual:
        chlorine_status_value.configure(text="Manual ON", text_color="#52ffa8")
    else:
        chlorine_status_value.configure(
            text="Auto Running" if chlorine_pump_running else "Automatic",
            text_color="#66ff9f" if chlorine_pump_running else "#7ad6ff"
        )

    app.after(100, update_loop)

threading.Thread(target=flow_thread, daemon=True).start()

print(f"[INFO] Device MAC Address: {MAC_ADDRESS}")

update_chemical_display()
update_loop()
app.after(300, show_dosing_view)
app.mainloop()

GPIO.output(RELAY3, RELAY_OFF)`r`nGPIO.cleanup()`r`ncursor.close()
db.close()
















