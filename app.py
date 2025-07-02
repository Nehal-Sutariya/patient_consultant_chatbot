import streamlit as st

# MUST be the first Streamlit command
st.set_page_config(layout="wide")

import google.generativeai as genai
from fpdf import FPDF
from dotenv import load_dotenv
import os
from datetime import datetime
import base64
import speech_recognition as sr
import re
import threading
import time
import tempfile
import sqlite3
from pydub import AudioSegment  # ✅ Added

# Load environment
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

# SQLite setup
conn = sqlite3.connect("consultations.db", check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT CHECK(role IN ('admin', 'user')) DEFAULT 'user'
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT,
        data BLOB,
        timestamp TEXT
    )
""")
conn.commit()

# Insert default admin user if not exists
cursor.execute("SELECT * FROM users WHERE username = ?", ("admin",))
if cursor.fetchone() is None:
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "admin123", "admin"))
    conn.commit()

# Initialize session state
for key, default in {
    'logged_in': False,
    'user_id': None,
    'role': None,
    'username': "",
    'recording': False,
    'audio_file_path': None,
    'user_input': "",
    'pdf_bytes': None,
    'pdf_filename': None,
    'generated': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Authentication
st.sidebar.title("🔐 Authentication")
auth_option = st.sidebar.radio("Choose:", ["Login", "Register"])

if not st.session_state.logged_in:
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")

    if auth_option == "Login":
        if st.sidebar.button("🔓 Login"):
            cursor.execute("SELECT id, role FROM users WHERE username=? AND password=?", (username, password))
            result = cursor.fetchone()
            if result:
                st.session_state.logged_in = True
                st.session_state.user_id = result[0]
                st.session_state.role = result[1]
                st.session_state.username = username
                st.success("✅ Login successful! Redirecting...")
                st.rerun()
                st.stop()
            else:
                st.sidebar.error("❌ Invalid credentials")

    elif auth_option == "Register" and st.sidebar.button("📝 Register"):
        role = st.sidebar.selectbox("Role", ["user", "admin"])
        try:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
            conn.commit()
            st.sidebar.success("✅ Registered successfully. Please login.")
        except sqlite3.IntegrityError:
            st.sidebar.error("❌ Username already exists.")
    st.stop()

if st.sidebar.button("🔒 Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
    st.stop()

# Admin Dashboard
if st.session_state.logged_in and st.session_state.role == "admin":
    st.title("👨‍⚕️ Admin Dashboard")
    st.subheader(f"Welcome Admin, {st.session_state.username}!")

    st.markdown("### 📋 All Uploaded Summaries")
    cursor.execute("SELECT id, filename, timestamp, user_id FROM summaries ORDER BY id DESC")
    rows = cursor.fetchall()
    for row in rows:
        with st.expander(f"{row[1]} - {row[2]} (User ID: {row[3]})"):
            cursor.execute("SELECT data FROM summaries WHERE id = ?", (row[0],))
            pdf_record = cursor.fetchone()
            if pdf_record and pdf_record[0]:
                pdf_data = pdf_record[0]
                st.download_button("📥 Download", data=pdf_data, file_name=row[1], mime="application/pdf", key=f"download_{row[0]}")
            else:
                st.sidebar.warning(f"No PDF found for {row[1]}")
    st.stop()

# User Chatbot UI
st.title("🩺 Patient Consultation Chatbot")

language = st.sidebar.selectbox("🌐 Select Language", ["English", "Hindi", "Gujarati", "Spanish", "German"])
if st.sidebar.button("🚨 Emergency"):
    st.sidebar.error("📞 Call 108 for Ambulance or Visit Nearest Hospital")
st.sidebar.markdown("⏰ **Consultation Timings**")
st.sidebar.info("🕒 Mon-Sat: 9 AM - 5 PM\n\n🚫 Sunday: Closed")

# View history
st.sidebar.markdown("📜 **View History**")
rows = []
if st.session_state.logged_in and st.session_state.role == "user":
    cursor.execute("SELECT id, filename, timestamp FROM summaries WHERE user_id=? ORDER BY id DESC LIMIT 5", (st.session_state.user_id,))
    rows = cursor.fetchall()
for row in rows:
    with st.sidebar.expander(f"{row[1]} - {row[2]}"):
        cursor.execute("SELECT data FROM summaries WHERE id = ?", (row[0],))
        pdf_data = cursor.fetchone()[0]
        st.download_button("📥 Download", data=pdf_data, file_name=row[1], mime="application/pdf", key=f"download_{row[0]}")

# Input choice
input_mode = st.radio("Choose Input Method:", ["🎤 Voice", "✍️ Text"], horizontal=True)

def remove_emojis(text):
    return re.sub(r'[^\x00-\x7F]+', '', text)

def record_audio(stop_event, filepath):
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source, timeout=300, phrase_time_limit=300)
        with open(filepath, "wb") as f:
            f.write(audio.get_wav_data())

# ✅ Converts only if needed
def convert_to_wav(input_path, output_path="converted.wav"):
    if input_path.endswith(".wav"):
        return input_path
    audio = AudioSegment.from_file(input_path)
    audio.export(output_path, format="wav")
    return output_path

# ✅ Uses converted file only if needed
def transcribe_audio(filepath):
    recognizer = sr.Recognizer()
    converted_path = convert_to_wav(filepath)
    with sr.AudioFile(converted_path) as source:
        audio = recognizer.record(source)
    return recognizer.recognize_google(audio)

# Voice input
if input_mode == "🎤 Voice":
    st.subheader("Voice Recording")
    if not st.session_state.recording:
        if st.button("🔴 Start Recording"):
            st.session_state.recording = True
            stop_event = threading.Event()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            st.session_state.audio_file_path = temp_file.name
            thread = threading.Thread(target=record_audio, args=(stop_event, st.session_state.audio_file_path))
            thread.start()
            timer_placeholder = st.empty()
            start_time = time.time()
            while thread.is_alive():
                elapsed = int(time.time() - start_time)
                timer_placeholder.info(f"⏱️ Recording... {elapsed} seconds")
                time.sleep(1)
                if elapsed >= 300:
                    stop_event.set()
                    break
            st.session_state.recording = False
            timer_placeholder.success("✅ Recording complete.")
            try:
                st.session_state.user_input = transcribe_audio(st.session_state.audio_file_path)
                st.success("📝 Voice Transcription Successful!")
            except sr.UnknownValueError:
                st.error("❌ Could not understand your speech.")
            except sr.RequestError:
                st.error("❌ Google API error.")
            except Exception as e:
                st.error(f"❌ Audio Error: {str(e)}")
    else:
        st.warning("⏺️ Recording already in progress...")

# Text input
elif input_mode == "✍️ Text":
    st.subheader("Enter Your Symptoms")
    user_text = st.text_area("Describe your symptoms here:")
    st.session_state.user_input = user_text

# Generate
if st.button("📄 Generate Summary"):
    if not st.session_state.user_input.strip():
        st.warning("Please provide input via voice or text.")
    else:
        st.session_state.generated = True

# Output
if st.session_state.generated:
    with st.spinner("Analyzing your input with Gemini AI..."):
        try:
            prompt = f"""
You're a medical assistant. From this description, extract a consultation summary in this format:

📄 Patient Consultation Summary
🗓️ Date: {datetime.today().strftime('%Y-%m-%d')}
👤 Patient Name: [Optional / Anonymous]
🆔 Patient ID: [Optional]

🧰 Reported Symptoms: ...
⏳ Duration of Symptoms: ...
⚖️ Severity: ...
📋 Medical History: ...
💊 Current Medications: ...
🧠 Additional Notes: ...
🦠 Suggested Next Steps: ...
📍 Location (Optional):
🗣 Language Detected: {language}

Here is the patient input:
\"\"\"{st.session_state.user_input}\"\"\"
"""
            response = model.generate_content(prompt)
            summary = response.text

            if not st.session_state.pdf_bytes or not st.session_state.pdf_filename:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                for line in remove_emojis(summary).split("\n"):
                    pdf.multi_cell(0, 10, line)
                now = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{st.session_state.username}_{now}.pdf"
              
                st.session_state.pdf_bytes = pdf.output(dest="S").encode("latin1")
                st.session_state.pdf_filename = filename

            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown("#### 📄 Generated Summary")
            with col2:
                st.download_button(
                    label="📥 Download",
                    data=st.session_state.pdf_bytes,
                    file_name=st.session_state.pdf_filename,
                    mime="application/pdf",
                    key="download_button_top"
                )
            with col3:
                if st.button("📤 Share to Consultant", key="share_button_top"):
                    try:
                        cursor.execute(
                            "INSERT INTO summaries (user_id, filename, data, timestamp) VALUES (?, ?, ?, ?)",
                            (
                                st.session_state.user_id,
                                st.session_state.pdf_filename,
                                st.session_state.pdf_bytes,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            )
                        )
                        conn.commit()
                        st.success("✅ Shared")
                    except Exception as e:
                        st.error(f"❌ Failed to save summary: {e}")

            st.text_area(label="", value=summary, height=300)

        except Exception as e:
            st.error(f"❌ Gemini Error: {str(e)}")
