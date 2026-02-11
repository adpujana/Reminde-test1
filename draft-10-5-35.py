# ============================================================
#   REMIND-E v2.0 (Beta) 30 Menit
# ============================================================

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from gtts import gTTS
import io
import base64
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# AUTO REFRESH setiap 10 detik
st_autorefresh(interval=10 * 1000, key="refresh")

# SESSION STATE DEFAULTS
defaults = {
    "audio_permission": False,
    "app_running": False,
    "pending_alarm": False,
    "acknowledged": True,
    "last_alarm_timestamp": None,
    "combined_alert_text": "",
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# PAGE CONFIG
st.set_page_config(page_title="REMIND-E v2.0 (Beta)", layout="wide")
st.title("⚡REMIND-E🚨")
st.caption("Reliable Energy Monitoring and Indicator for Dispatcher v2.0 (Beta)")

# ============================================================
# TTS FUNCTIONS
# ============================================================

def normalize_for_tts(text: str) -> str:
    if not text:
        return text

    # Hanya eja singkatan pembangkit (nama lokasi tetap utuh)
    repl = {
        "PLTA": "p l t a",
        "PLTM": "p l t m",
        "PLTP": "p l t p",
        "PLTD": "p l t d",
        "PLTU": "p l t u",
        "PLTG": "p l t g",
        "PLTS": "p l t s",
        "MW": "mega watt",
    }

    out = text

    # ganti token utuh saja (hindari merusak kata lain)
    for k, v in repl.items():
        out = out.replace(f"{k} ", f"{v} ")
        out = out.replace(f" {k}", f" {v}")

    return out


def tts_base64(text):
    if not text or text.strip() == "":
        return None
    buf = io.BytesIO()
    gTTS(text, lang="id").write_to_fp(buf)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def play_feedback(text):
    if not st.session_state.audio_permission:
        return
    b64 = tts_base64(text)
    if b64:
        st.markdown(f"""
        <audio autoplay>
            <source src="data:audio/mp3;base64,{b64}" type="audio/mpeg">
        </audio>""", unsafe_allow_html=True)

def play_audio_if_allowed(text):
    if not st.session_state.audio_permission or not st.session_state.app_running:
        return

    tts_text = normalize_for_tts(text)   # ⬅️ NORMALISASI DI SINI

    b64 = tts_base64(tts_text)
    if b64:
        st.markdown(f"""
        <audio autoplay>
            <source src="data:audio/mp3;base64,{b64}" type="audio/mpeg">
        </audio>""", unsafe_allow_html=True)


# ============================================================
# BUTTON PANEL
# ============================================================
col1, col2, col3 = st.columns([1,1,1])

with col1:
    if not st.session_state.audio_permission:
        if st.button("Ijinkan Audio"):
            st.session_state.audio_permission = True
            st.success("Notifikasi audio telah diijinkan")
            play_feedback("Notifikasi audio telah diijinkan")
            st.stop()
    else:
        st.info("Notifikasi audio aktif")

with col2:
    if st.button("START"):
        st.session_state.app_running = True
        st.session_state.acknowledged = False
        st.success("Aplikasi berhasil dijalankan")
        play_feedback("Aplikasi berhasil dijalankan")
        st.stop()

with col3:
    if st.button("STOP/PAUSED"):
        st.session_state.app_running = False
        st.session_state.pending_alarm = False
        st.session_state.acknowledged = True
        st.session_state.last_alarm_timestamp = None
        st.session_state.combined_alert_text = ""
        st.success("Aplikasi berhasil dihentikan")
        play_feedback("Aplikasi berhasil dihentikan")
        st.stop()

# ============================================================
# STATUS BAR
# ============================================================
if st.session_state.app_running:
    st.success("Aplikasi: RUNNING. Pilih STOP/PAUSED untuk menghentikan.")
else:
    st.warning("Aplikasi: STOP/PAUSED. Pilih START untuk menjalankan.")
    st.stop()

# ============================================================
# LOAD CSV
# ============================================================
url = "https://drive.google.com/uc?export=download&id=1V8ZRZGwj__bBl8bFP8AqwKZvQCPaG5af"

# ============================================================
# LOAD CSV
# ============================================================

@st.cache_data(ttl=10)
def load_data():

    df_raw = pd.read_excel(url, engine="openpyxl")

    ts_col = next(
        (c for c in df_raw.columns if c.lower() in ["timestamp","waktu","jam","time"]),
        df_raw.columns[0]
    )

    df_raw["timestamp"] = (
        pd.to_datetime(df_raw[ts_col], errors="coerce")
        .dt.tz_localize(None)
        .dt.floor("min")
    )

    df_raw = df_raw.dropna(subset=["timestamp"])

    if ts_col.lower() != "timestamp":
        df_raw = df_raw.drop(columns=[ts_col], errors="ignore")

    df = df_raw.loc[:, ~df_raw.columns.duplicated()]
    unit_cols = [c for c in df.columns if c != "timestamp"]

    return df.sort_values("timestamp"), unit_cols


# WAJIB langsung panggil setelah fungsi selesai
df, unit_cols = load_data()


# ============================================================
# DETECT JENIS
# ============================================================

def detect_jenis(unit_name: str):
    for t in ["PLTA", "PLTM", "PLTP", "PLTD", "PLTU", "PLTS", "PLTG"]:
        if unit_name.upper().startswith(t):
            return t
    return "LAINNYA"


# ============================================================
# MAPPING JENIS
# ============================================================

jenis_map = {}
for u in unit_cols:
    j = detect_jenis(u)
    jenis_map.setdefault(j, []).append(u)

# ============================================================
# DEBUG DATA CHECK (WAJIB SAAT DEPLOY)
# ============================================================
if df.empty:
    st.error("❌ DATA KOSONG — semua timestamp gagal diparse")
    st.stop()

st.caption(
    f"🕒 Data tersedia: {df['timestamp'].min()} s/d {df['timestamp'].max()} "
    f"({len(df)} baris)"
)

# ============================================================
# SIDEBAR SETTINGS
# ============================================================

st.sidebar.header("Pengaturan Monitoring")

threshold = st.sidebar.slider("Delta P (MW)", 0.1, 20.0, 0.5, 0.1)

#if "saved_monitored_cols" not in st.session_state:
 #   st.session_state.saved_monitored_cols = unit_cols
 
if "saved_monitored_cols" not in st.session_state:
    st.session_state.saved_monitored_cols = []


if "show_only_monitored" not in st.session_state:
    st.session_state.show_only_monitored = False

# buang default pilihan lama yang sudah tidak ada di CSV terbaru
st.session_state.saved_monitored_cols = [
    c for c in st.session_state.saved_monitored_cols
    if c in unit_cols
]

pass

monitor_all = st.sidebar.checkbox("Monitor semua pembangkit", value=False)

st.sidebar.subheader("Filter Jenis Pembangkit")

jenis_opsi = list(jenis_map.keys())

jenis_dipilih = st.sidebar.multiselect(
    "Pilih jenis pembangkit",
    options=jenis_opsi,
    default=jenis_opsi   # default: semua jenis tampil
)

# filter unit berdasarkan jenis terpilih
filtered_units = []
for j in jenis_dipilih:
    filtered_units.extend(jenis_map.get(j, []))

with st.sidebar.form("monitor_form"):

    monitored_cols = st.multiselect(
        "Pilih pembangkit yang akan dimonitor",
        options=filtered_units,  # ⬅️ pakai hasil filter jenis
        default=[c for c in st.session_state.saved_monitored_cols if c in filtered_units],
        disabled=monitor_all
    )

    show_only_monitored = st.checkbox(
        "Tampilkan hanya pembangkit yang dipilih",
        value=st.session_state.show_only_monitored
    )

    submitted = st.form_submit_button("Terapkan")

if submitted:
    if monitor_all:
        st.session_state.saved_monitored_cols = unit_cols.copy()
    else:
        st.session_state.saved_monitored_cols = monitored_cols

    st.session_state.show_only_monitored = show_only_monitored


# gunakan nilai yang tersimpan

monitored_cols = st.session_state.saved_monitored_cols
show_only_monitored = st.session_state.show_only_monitored

if not monitored_cols:
    st.warning("⚠️ Tidak ada pembangkit yang dimonitor.")
    st.info("Silakan pilih pembangkit di sidebar lalu klik Terapkan.")
    st.stop()
 
# ============================================================
# RESET ALARM JIKA PILIHAN PEMBANGKIT BERUBAH
# ============================================================
if "prev_monitored_cols" not in st.session_state:
    st.session_state.prev_monitored_cols = set(monitored_cols)

if set(monitored_cols) != st.session_state.prev_monitored_cols:
    # reset alarm state
    st.session_state.pending_alarm = False
    st.session_state.acknowledged = True
    st.session_state.last_alarm_timestamp = None
    st.session_state.combined_alert_text = ""

    st.session_state.prev_monitored_cols = set(monitored_cols)

# ============================================================
# TIME TARGETS
# ============================================================
# SET timezone sesuai lokasi (PILIH SALAH SATU)
# WIB  : Asia/Jakarta
# WITA : Asia/Makassar
# WIT  : Asia/Jayapura

now = (
    pd.Timestamp.now(tz="Asia/Makassar")   # ⬅️ SESUAIKAN
    .tz_localize(None)                     # buang tz agar match CSV
)

INTERVAL_MIN = 30  # ⬅️ data 30 menit

# boundary berikutnya (11:50, 11:55, dst)
next_block = (
    now.floor(f"{INTERVAL_MIN}min")
    + pd.Timedelta(minutes=INTERVAL_MIN)
)

# highlight pindah 10 detik sebelum boundary
highlight_switch_time = next_block - pd.Timedelta(seconds=10)

if now >= highlight_switch_time:
    highlight_target = next_block
else:
    highlight_target = next_block - pd.Timedelta(minutes=INTERVAL_MIN)

# safety clamp ke data
if highlight_target < df["timestamp"].min():
    highlight_target = df["timestamp"].min()
elif highlight_target > df["timestamp"].max():
    highlight_target = df["timestamp"].max()

event_target = (
    now.floor(f"{INTERVAL_MIN}min")
    + pd.Timedelta(minutes=INTERVAL_MIN)
)

# clamp ke data
if event_target < df["timestamp"].min():
    event_target = df["timestamp"].min()
elif event_target > df["timestamp"].max():
    event_target = df["timestamp"].max()

alarm_target = event_target

# alarm muncul 29 menit sebelum event
alarm_trigger_time = event_target - pd.Timedelta(minutes=29)

st.write(
    f"Delta P: **{threshold} MW** — Monitoring **{len(monitored_cols)}/{len(unit_cols)} pembangkit**"
)
if highlight_target == df["timestamp"].max() and now > highlight_target + pd.Timedelta(minutes=1):
    st.warning("⏳ Menunggu data terbaru...")

# ============================================================
# DETECTION LOGIC — NILAI AKTUAL
# ============================================================

event_row = df[df["timestamp"] == event_target]
alerts = []

if not event_row.empty:
    idx = df.index[df["timestamp"] == event_target][0]

    if idx > 0:
        prev = df.iloc[idx - 1]
        curr = df.iloc[idx]

        for col in monitored_cols:
            if col not in curr.index:
                continue

            try:
                delta = float(curr[col]) - float(prev[col])
                nilai_baru = float(curr[col])
            except:
                continue

            if abs(delta) >= threshold:
                arah = "naik ke" if delta > 0 else "turun ke"
                alerts.append(f"{col} {arah} {nilai_baru:.1f} MW")

        if alerts and now >= alarm_trigger_time:
            st.session_state.combined_alert_text = ", ".join(alerts)

            if st.session_state.last_alarm_timestamp != event_target:
                st.session_state.pending_alarm = True
                st.session_state.acknowledged = False
                st.session_state.last_alarm_timestamp = event_target



# ============================================================
# HTML TABLE + FONT STREAMLIT + AUTOSCROLL INSIDE IFRAME
# ============================================================
display_cols = monitored_cols if show_only_monitored else unit_cols

rows_html = ""
for _, row in df.iterrows():

    css = ""
    rid = ""

    # Highlight SELALU untuk baris aktif
    if row["timestamp"] == highlight_target:
        css = "shift"
        rid = "shift_row"

    # Jika alarm aktif, tambahkan efek blink
    if (
        row["timestamp"] == alarm_target
        and st.session_state.pending_alarm
        and not st.session_state.acknowledged
    ):
        css = "blink"
        rid = "alarm_row"

    cells = "".join([
        f"<td><b>{row[col]}</b></td>" if col in monitored_cols else f"<td>{row[col]}</td>"
        for col in display_cols
    ])

    rows_html += (
        f"<tr id='{rid}' class='{css}'>"
        #f"<td>{row['timestamp'].strftime('%H:%M:%S')}</td>"
        f"<td>{row['timestamp'].strftime('%H:%M') if pd.notna(row['timestamp']) else '-'}</td>"
        f"{cells}</tr>"
    )
    
render_nonce = pd.Timestamp.now().strftime("%Y%m%d%H%M%S")
html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<!-- render_nonce: {render_nonce} -->

<style>

:root {{
    --font: system-ui, Roboto, Inter, Arial, sans-serif;
}}

.table-wrap {{
    height: 430px;
    overflow-y: auto;
    border: 1px solid #999;
    font-family: var(--font);
}}

.tbl {{
    width: 100%;
    border-collapse: collapse;
    font-family: var(--font);
}}

.tbl th, .tbl td {{
    padding: 6px;
    text-align: center;
    border: 1px solid #ccc;
    font-family: var(--font);
    font-size: 0.9rem;
}}

.tbl th {{
    background: #222;
    color: white;
    position: sticky;
    top: 0;
}}

.shift {{
    background: yellow;
    font-weight: bold;
}}

@keyframes blink {{
    50% {{ background: red; color: white; }}
}}

.blink {{
    animation: blink 1s infinite;
    font-weight: bold;
}} 

</style>
</head>

<body>

<div id="wrap" class="table-wrap">
<table class="tbl">
<thead>
<tr>
<th>Waktu</th>
{''.join(f'<th>{c}</th>' for c in display_cols)}
</tr>
</thead>

<tbody>
{rows_html}
</tbody>
</table>
</div>

<script>
setTimeout(function() {{
    var alarm = document.getElementById("alarm_row");
    var shift = document.getElementById("shift_row");
    var wrap  = document.getElementById("wrap");

    if (alarm) {{
        alarm.scrollIntoView({{ behavior: "smooth", block: "center" }});
    }} 
    else if (shift) {{
        shift.scrollIntoView({{ behavior: "smooth", block: "center" }});
    }}
    else {{
        wrap.scrollTop = wrap.scrollHeight / 3;
    }}

}}, 300);
</script>

</body>
</html>
"""

components.html(html, height=470, scrolling=True)

st.caption(f"🎯 Highlight aktif: {highlight_target} | render {render_nonce}")

# ============================================================
# STATUS ALARM
# ============================================================
st.subheader("Status Alarm")

if st.session_state.pending_alarm and not st.session_state.acknowledged:
    st.error("🚨 " + st.session_state.combined_alert_text)
    play_audio_if_allowed(st.session_state.combined_alert_text)

    if st.button("Acknowledge"):
        st.session_state.pending_alarm = False
        st.session_state.acknowledged = True
        st.success("Alarm di-Acknowledge")

else:
    st.info("Tidak ada alarm aktif.")
