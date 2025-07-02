import streamlit as st
import sqlite3

# Page setup
st.set_page_config(page_title="🛠 Admin Dashboard", layout="wide")

# Connect to DB
conn = sqlite3.connect("consultations.db", check_same_thread=False)
cursor = conn.cursor()

# Ensure 'summaries' table has 'status' column
cursor.execute("""
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT,
        data BLOB,
        timestamp TEXT,
        status TEXT DEFAULT 'pending'
    )
""")
conn.commit()

# --- Debug / Confirm admin session ---
if 'logged_in' not in st.session_state or not st.session_state.logged_in or st.session_state.role != 'admin':
    st.error("⛔ Access Denied: Only Admin can access this dashboard.")
    st.stop()

st.sidebar.success(f"Logged in as: {st.session_state.username} (ID: {st.session_state.user_id}, Role: {st.session_state.role})")

# Sidebar Admin Panel
st.sidebar.title("⚙️ Admin Panel")
st.sidebar.markdown("🌐 **Language Select (UI Only)**")
st.sidebar.selectbox("Choose Language", ["English", "Hindi", "Gujarati"])
st.sidebar.text_input("🔍 Doctor Search")
if st.sidebar.button("🚨 Emergency"):
    st.sidebar.error("📞 Call 108 or visit nearest hospital")

st.sidebar.markdown("⏰ **Consultation Timings**")
st.sidebar.info("🕒 Mon–Sat: 9 AM – 5 PM\n🚫 Sunday Closed")

# View Users
st.header("👥 All Registered Users")
cursor.execute("SELECT id, username, role FROM users ORDER BY id ASC")
users = cursor.fetchall()
for u in users:
    st.markdown(f"- ID: `{u[0]}`, Username: `{u[1]}`, Role: `{u[2]}`")

st.divider()

# Manage Patient Summaries
st.header("📄 Manage Patient Summaries")
filter_status = st.selectbox("📂 Filter by Status", ["all", "pending", "accepted", "rejected"])

if filter_status == "all":
    cursor.execute("SELECT id, user_id, filename, timestamp, status FROM summaries ORDER BY id DESC")
else:
    cursor.execute("SELECT id, user_id, filename, timestamp, status FROM summaries WHERE status=? ORDER BY id DESC", (filter_status,))
summaries = cursor.fetchall()

if not summaries:
    st.info("No summaries found for the selected filter.")
else:
    for sid, uid, fname, ts, status in summaries:
        with st.expander(f"📁 {fname or 'Unnamed'} | 🗓 {ts} | 🧾 Status: {status.upper()}"):
            st.markdown(f"👤 User ID: `{uid}`")

            # Editable Fields
            new_fname = st.text_input("Edit Filename", value=fname or "", key=f"fname_{sid}")
            new_ts = st.text_input("Edit Timestamp", value=ts or "", key=f"time_{sid}")

            # PDF Download Section
            cursor.execute("SELECT data FROM summaries WHERE id = ?", (sid,))
            result = cursor.fetchone()
            if result and result[0]:
                pdf_data = result[0]
                if isinstance(pdf_data, str):
                    pdf_data = pdf_data.encode("latin1")
                st.download_button("📥 Download PDF", data=pdf_data, file_name=new_fname, mime="application/pdf", key=f"pdf_{sid}")
            else:
                st.warning("⚠️ No PDF data available.")

            # Action Buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("✅ Accept", key=f"accept_{sid}"):
                    cursor.execute("UPDATE summaries SET status='accepted' WHERE id=?", (sid,))
                    conn.commit()
                    st.success("Summary marked as accepted.")
                    st.rerun()
            with col2:
                if st.button("❌ Reject", key=f"reject_{sid}"):
                    cursor.execute("UPDATE summaries SET status='rejected' WHERE id=?", (sid,))
                    conn.commit()
                    st.warning("Summary marked as rejected.")
                    st.rerun()
            with col3:
                if st.button("💾 Save Changes", key=f"save_{sid}"):
                    cursor.execute("UPDATE summaries SET filename=?, timestamp=? WHERE id=?", (new_fname, new_ts, sid))
                    conn.commit()
                    st.success("Changes saved.")
                    st.rerun()

st.divider()

# Delete Summary
st.header("🗑️ Delete Summary by ID")
delete_id = st.text_input("Enter Summary ID to Delete:")
if st.button("Delete"):
    try:
        cursor.execute("DELETE FROM summaries WHERE id=?", (delete_id,))
        conn.commit()
        st.success(f"✅ Summary ID {delete_id} deleted.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error: {e}")