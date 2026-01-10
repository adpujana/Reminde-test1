# ============================================================
#   REMIND-E v3.6 (FINAL)
#   - Scroll 100% Working
#   - Nilai Aktual
#   - Font Menggunakan Font Streamlit (var(--font))
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
st.set_page_config(page_title="REMIND-E v3.6", layout="wide")
st.title("⚡ REMIND-E v3.6 — START / STOP + Voice Feedback")

# ============================================================
# TTS FUNCTIONS
# ============================================================
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
    b64 = tts_base64(text)
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
url = "https://drive.google.com/uc?export=download&id=1ycCOIWaw0JPdPsuvxrA-cLhhJJaNYEz4"

@st.cache_data(ttl=10)
def load_data():
    df_raw = pd.read_csv(url)
    ts_col = next((c for c in df_raw.columns if c.lower() in ["timestamp","waktu","jam","time"]), df_raw.columns[0])

#    df_raw["timestamp"] = (
#        pd.to_datetime(df_raw[ts_col], errors="coerce").dt.tz_localize(None).dt.floor("s")
#    )
    df_raw["timestamp"] = (
        pd.to_datetime(
            df_raw[ts_col],
            format="%m/%d/%Y %I:%M:%S %p",   # <-- AM/PM FIX
            errors="coerce"
        )
        .dt.tz_localize(None)
        .dt.floor("min")
    )
    df_raw = df_raw.dropna(subset=["timestamp"])
    if ts_col.lower() != "timestamp":
        df_raw = df_raw.drop(columns=[ts_col], errors="ignore")

    df = df_raw.loc[:, ~df_raw.columns.duplicated()]
    unit_cols = [c for c in df.columns if c != "timestamp"]

    return df.sort_values("timestamp"), unit_cols

df, unit_cols = load_data()

# ============================================================
# SIDEBAR SETTINGS
# ============================================================
st.sidebar.header("Pengaturan Monitoring")

threshold = st.sidebar.slider("Sensitifitas (MW)", 0.1, 20.0, 2.0, 0.1)

if "saved_monitored_cols" not in st.session_state:
    st.session_state.saved_monitored_cols = unit_cols

monitored_cols = st.sidebar.multiselect(
    "Pilih pembangkit yang akan dimonitor",
    options=unit_cols,
    default=st.session_state.saved_monitored_cols
)

st.session_state.saved_monitored_cols = monitored_cols

show_only_monitored = st.sidebar.checkbox("Tampilkan hanya pembangkit yang dipilih", False)

if not monitored_cols:
    st.warning("Pilih minimal satu pembangkit!")
    st.stop()

# ============================================================
# TIME TARGETS
# ============================================================
#now = datetime.now().replace(microsecond=0)
#highlight_target = (now + timedelta(seconds=15)).replace(second=0)
#alert_target = (now + timedelta(seconds=30)).replace(second=0)
now = pd.Timestamp.now().floor("min")

future_df = df[df["timestamp"] >= now]

highlight_target = None
alert_target = None

if not future_df.empty:
    highlight_target = future_df.iloc[0]["timestamp"]
    alert_target = highlight_target

st.write(
    f"Sensitifitas: **{threshold} MW** — Monitoring **{len(monitored_cols)}/{len(unit_cols)} pembangkit**"
)

# ============================================================
# DETECTION LOGIC — NILAI AKTUAL
# ============================================================
#future_row = df[df["timestamp"] == alert_target]
future_row = df[df["timestamp"] == alert_target] if alert_target is not None else pd.DataFrame()
alerts = []

if not future_row.empty:
    idx = df.index[df["timestamp"] == alert_target][0]

    if idx > 0:
        prev = df.iloc[idx - 1]
        curr = df.iloc[idx]

        for col in monitored_cols:
            try:
                delta = float(curr[col]) - float(prev[col])
                nilai_baru = float(curr[col])
            except:
                continue

            if abs(delta) >= threshold:
                arah = "naik ke" if delta > 0 else "turun ke"
                alerts.append(f"{col} {arah} {nilai_baru:.1f} MW")

        if alerts:
            st.session_state.combined_alert_text = ", ".join(alerts)

            if st.session_state.last_alarm_timestamp != alert_target:
                st.session_state.pending_alarm = True
                st.session_state.acknowledged = False
                st.session_state.last_alarm_timestamp = alert_target

# ============================================================
# HTML TABLE + FONT STREAMLIT + AUTOSCROLL INSIDE IFRAME
# ============================================================
display_cols = monitored_cols if show_only_monitored else unit_cols

rows_html = ""
for _, row in df.iterrows():

    css = ""
    rid = ""

    #if row["timestamp"] == alert_target and st.session_state.pending_alarm and not st.session_state.acknowledged:
    if alert_target is not None and row["timestamp"] == alert_target and st.session_state.pending_alarm and not st.session_state.acknowledged:
        css = "blink"
        rid = "alarm_row"

    #elif row["timestamp"] == highlight_target:
    elif highlight_target is not None and row["timestamp"] == highlight_target:
        css = "shift"
        rid = "shift_row"

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

html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">

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
