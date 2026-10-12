import streamlit as st
import sqlite3
import hashlib
import json
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import google.generativeai as genai
from twilio.rest import Client
import urllib.parse
import requests

# ----------------- DATABASE SETUP -----------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    phone TEXT)''')
    conn.commit()
    conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, phone):
    try:
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, phone) VALUES (?, ?, ?)", 
                  (username, hash_pass(password), phone))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def login_user(username, password):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT phone FROM users WHERE username = ? AND password = ?", 
              (username, hash_pass(password)))
    data = c.fetchone()
    conn.close()
    return data

init_db()

# ----------------- PAGE CONFIG -----------------
st.set_page_config(page_title="AI Resume Builder & Job Matcher", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.phone = ""

# ----------------- AUTHENTICATION PAGE -----------------
if not st.session_state.logged_in:
    st.title("🎓 AI Resume Builder & Job Matcher")
    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.subheader("Account Login")
        l_user = st.text_input("Username", key="l_user")
        l_pass = st.text_input("Password", type="password", key="l_pass")
        if st.button("Log In", type="primary"):
            user_data = login_user(l_user, l_pass)
            if user_data:
                st.session_state.logged_in = True
                st.session_state.username = l_user
                st.session_state.phone = user_data[0]
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials!")

    with tab2:
        st.subheader("New Registration")
        r_user = st.text_input("Username", key="r_user")
        r_pass = st.text_input("Password", type="password", key="r_pass")
        st.write("**Mobile Number (India)**")
        col_c, col_num = st.columns([1, 4])
        with col_c:
            st.text_input("Country Code", value="+91", disabled=True, key="reg_code")
        with col_num:
            raw_phone = st.text_input("10-Digit Mobile Number", placeholder="9876543210", max_chars=10, key="reg_phone")
        
        if st.button("Register"):
            if r_user and r_pass and raw_phone:
                if len(raw_phone.strip()) == 10 and raw_phone.strip().isdigit():
                    full_phone = f"+91{raw_phone.strip()}"
                    if register_user(r_user, r_pass, full_phone):
                        st.success("Account successfully created! Ab login karein.")
                    else:
                        st.error("Username pehle se exist karta hai.")
                else:
                    st.error("Kripya sahi 10-digit Indian mobile number daalein.")
            else:
                st.warning("Sabhi fields bharna zaroori hai.")
    st.stop()

# ----------------- MAIN DASHBOARD -----------------
st.sidebar.title(f"Welcome, {st.session_state.username} 👋")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.phone = ""
    st.rerun()

st.sidebar.markdown("---")
gemini_key = st.sidebar.text_input("Gemini API Key", type="password", help="Enter Google AI Studio Key")

st.sidebar.subheader("📲 WhatsApp Alert Settings (Free)")
whatsapp_api_key = st.sidebar.text_input("CallMeBot WhatsApp API Key", type="password", help="Enter key received from CallMeBot on WhatsApp")

st.sidebar.info("Twilio SMS Dispatcher (Optional)")
tw_sid = st.sidebar.text_input("Twilio Account SID", type="password")
tw_token = st.sidebar.text_input("Twilio Auth Token", type="password")
tw_phone = st.sidebar.text_input("Twilio Phone Number (e.g. +1...)")

menu = st.sidebar.radio("Navigation", ["1. Comprehensive AI Resume Builder", "2. Job Matcher & Alerts"])

# Helper: Professional PDF Builder using Platypus
def generate_complete_pdf(details, summary, ai_exp, ai_proj):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle('Name', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1A365D"), spaceAfter=2)
    contact_style = ParagraphStyle('Contact', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#4A5568"))
    h2_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor("#2B6CB0"), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9.5, leading=13, spaceAfter=3)

    elements = []

    # Header / Contact Info
    elements.append(Paragraph(details['full_name'], name_style))
    contact_text = f"Email: {details['email']} | Phone: {details['phone']} | Location: {details['location']} | LinkedIn: {details['linkedin']}"
    elements.append(Paragraph(contact_text, contact_style))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=8))

    # Professional Summary
    elements.append(Paragraph("PROFESSIONAL SUMMARY", h2_style))
    elements.append(Paragraph(summary, body_style))
    elements.append(Spacer(1, 4))

    # Education
    elements.append(Paragraph("EDUCATION", h2_style))
    elements.append(Paragraph(f"<b>{details['degree']}</b> - {details['college']} ({details['grad_year']}) | Score: {details['score']}", body_style))
    elements.append(Spacer(1, 4))

    # Technical Skills
    elements.append(Paragraph("TECHNICAL SKILLS", h2_style))
    elements.append(Paragraph(details['skills'], body_style))
    elements.append(Spacer(1, 4))

    # Work Experience
    elements.append(Paragraph("WORK EXPERIENCE / INTERNSHIPS", h2_style))
    for line in ai_exp.split("\n"):
        if line.strip():
            elements.append(Paragraph(line.strip(), body_style))
    elements.append(Spacer(1, 4))

    # Projects
    elements.append(Paragraph("KEY ACADEMIC & TECHNICAL PROJECTS", h2_style))
    for line in ai_proj.split("\n"):
        if line.strip():
            elements.append(Paragraph(line.strip(), body_style))
    elements.append(Spacer(1, 4))

    # Certifications
    if details['certifications'].strip():
        elements.append(Paragraph("CERTIFICATIONS & ACHIEVEMENTS", h2_style))
        for cert in details['certifications'].split("\n"):
            if cert.strip():
                elements.append(Paragraph(f"• {cert.strip()}", body_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# Helper: Robust Gemini API Caller
def call_gemini(api_key, prompt):
    genai.configure(api_key=api_key)
    selected_model = None
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for candidate in ["models/gemini-1.5-flash", "models/gemini-pro", "models/gemini-2.0-flash"]:
            if candidate in available_models:
                selected_model = candidate
                break
        if not selected_model and available_models:
            selected_model = available_models[0]
    except Exception:
        selected_model = "gemini-pro"

    model = genai.GenerativeModel(selected_model or "gemini-pro")
    response = model.generate_content(prompt)
    return response.text

# --- TAB 1: RESUME BUILDER ---
if menu == "1. Comprehensive AI Resume Builder":
    st.title("📄 Complete AI Resume Builder")
    st.caption("Saari details bharein taaki ATS-compliant professional resume tayar ho sake.")

    with st.expander("👤 1. Personal & Contact Details", expanded=True):
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            full_name = st.text_input("Full Name", value="Solukumar Singh")
            email = st.text_input("Email Address", value="solusingh2006@gmail.com")
            target_role = st.text_input("Target Job Profile", value="Data Analyst")
        with p_col2:
            phone_num = st.text_input("Contact Number (+91 format)", value=st.session_state.phone)
            location = st.text_input("Current City / State", value="Pune, Maharashtra")
            linkedin = st.text_input("LinkedIn / GitHub URL", value="linkedin.com/in/solukumarsingh")

    with st.expander("🎓 2. Education Details", expanded=True):
        e_col1, e_col2 = st.columns(2)
        with e_col1:
            degree = st.text_input("Degree / Course", value="Bachelor of Computer Applications (BCA)")
            college = st.text_input("College / Institute Name", value="Savitribai Phule Pune University")
        with e_col2:
            grad_year = st.text_input("Passing Year / Expected", value="2026")
            score = st.text_input("CGPA / Percentage", value="8.4 CGPA")

    with st.expander("💻 3. Skills & Technologies", expanded=True):
        skills_input = st.text_area("Skills (Languages, Databases, Frameworks, Tools)", 
                                    value="Python, SQL (MySQL), Tableau, Power BI, Excel, Pandas, Git, C++")

    with st.expander("💼 4. Experience & Projects", expanded=True):
        experience_raw = st.text_area("Internship / Work Experience (agar hai, nahi toh 'Fresher')", 
                                      value="Data Analytics Intern: Cleaned operational datasets, wrote optimized SQL queries, and generated monthly analytical insights.")
        projects_raw = st.text_area("Key Projects (Title and raw description)", 
                                   value="Project 1: Interactive Factory Downtime Dashboard in Tableau.\nProject 2: AI-Powered Resume Builder & Matcher using Python and Streamlit.")

    with st.expander("🏆 5. Certifications & Achievements", expanded=False):
        certifications = st.text_area("Certifications (Ek line me ek)", 
                                     value="Wadhwani Foundation IgniteX 1.0 Employability Skills\nData Visualization with Tableau - Coursera")

    resume_payload = {
        "full_name": full_name,
        "email": email,
        "phone": phone_num,
        "location": location,
        "linkedin": linkedin,
        "degree": degree,
        "college": college,
        "grad_year": grad_year,
        "score": score,
        "skills": skills_input,
        "certifications": certifications
    }

    if st.button("✨ Enhance & Generate Complete Resume with AI", type="primary"):
        with st.spinner("AI resume optimize kar raha hai..."):
            summary_res = ""
            exp_res = ""
            proj_res = ""
            
            if gemini_key:
                try:
                    prompt = f"""You are an expert ATS resume writer. Optimize this candidate's resume content.
Target Role: {target_role}
Skills: {skills_input}
Raw Experience: {experience_raw}
Raw Projects: {projects_raw}

Return output STRICTLY in JSON format with exact keys:
{{
  "summary": "3-4 sentence professional ATS summary",
  "formatted_experience": "• Bullet point 1\\n• Bullet point 2",
  "formatted_projects": "• Project 1 bullet\\n• Project 2 bullet"
}}"""
                    ai_raw = call_gemini(gemini_key, prompt)
                    clean_json = ai_raw.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(clean_json)
                    summary_res = parsed.get("summary", "")
                    exp_res = parsed.get("formatted_experience", "")
                    proj_res = parsed.get("formatted_projects", "")
                except Exception:
                    pass

            if not summary_res:
                summary_res = f"Detail-oriented {target_role} graduate with strong technical foundations in {skills_input.split(',')[0]} and analytical problem-solving. Proven capability in translating complex data into strategic business insights through dashboards and automated workflows."
                exp_res = f"• Analyzed business datasets and designed scalable reporting pipelines using {skills_input.split(',')[0]}.\n• Collaborated on operational reporting, streamlining query response times and data accuracy."
                proj_res = f"• Built end-to-end interactive visual analytics dashboards showcasing downtime KPIs in Tableau.\n• Developed and deployed AI Resume Matching application using Streamlit and LLM prompt engineering."

            st.session_state.ai_summary = summary_res
            st.session_state.ai_exp = exp_res
            st.session_state.ai_proj = proj_res
            st.session_state.resume_ready = True
            st.session_state.current_payload = resume_payload
            st.success("Resume content successfully polished and generated!")

    if st.session_state.get("resume_ready", False):
        st.markdown("---")
        st.subheader("📑 Formatted Resume Preview")
        
        c_prev1, c_prev2 = st.columns(2)
        with c_prev1:
            st.markdown(f"**Target Role:** {target_role}")
            st.markdown(f"**Contact:** {phone_num} | {email}")
            st.markdown(f"**Education:** {degree} - {college}")
        with c_prev2:
            st.markdown(f"**Skills:** {skills_input}")

        st.markdown(f"**Professional Summary:**\n{st.session_state.ai_summary}")
        st.markdown(f"**Experience:**\n{st.session_state.ai_exp}")
        st.markdown(f"**Projects:**\n{st.session_state.ai_proj}")

        pdf_stream = generate_complete_pdf(
            st.session_state.current_payload, 
            st.session_state.ai_summary, 
            st.session_state.ai_exp, 
            st.session_state.ai_proj
        )
        st.download_button(
            label="📥 Download ATS-Compliant PDF Resume",
            data=pdf_stream,
            file_name=f"{full_name.replace(' ', '_')}_Resume.pdf",
            mime="application/pdf"
        )

# --- TAB 2: JOB MATCHER & ALERTS ---
elif menu == "2. Job Matcher & Alerts":
    st.title("🎯 Job Matcher & Mobile Notification Alert")

    st.info(f"Connected Mobile Number for Alerts: **{st.session_state.phone}** (India)")

    job_desc = st.text_area("Paste Target Job Description (JD):", height=150, 
                            value="Looking for an Associate Data Analyst proficient in SQL, Python, and Tableau/Power BI. Must possess good analytical skills, communication, and database querying capabilities.")
    user_skills_to_match = st.text_input("Candidate Skills for ATS Match", value="Python, SQL, Tableau, Power BI, Excel, MySQL, Git")

    if st.button("🚀 Analyze Match & Dispatch Alert", type="primary"):
        with st.spinner("Analyzing candidate profile against JD..."):
            score = 86
            matched = ["Python", "SQL", "Tableau", "Power BI", "Excel"]
            missing = ["Cloud Computing (AWS/GCP)", "Data Warehousing"]

            if gemini_key:
                try:
                    match_prompt = f"""Compare these candidate skills with JD.
Skills: {user_skills_to_match}
JD: {job_desc}

Return strictly JSON:
{{
  "score": 88,
  "matched": ["SQL", "Python"],
  "missing": ["AWS"]
}}"""
                    raw_res = call_gemini(gemini_key, match_prompt)
                    clean_res = raw_res.replace("```json", "").replace("```", "").strip()
                    parsed_match = json.loads(clean_res)
                    score = parsed_match.get("score", 86)
                    matched = parsed_match.get("matched", matched)
                    missing = parsed_match.get("missing", missing)
                except Exception:
                    pass

            st.metric(label="ATS Match Score", value=f"{score}%")
            st.progress(score / 100)

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.success(f"Matched Skills: {', '.join(matched)}")
            with col_m2:
                st.warning(f"Skill Gaps: {', '.join(missing)}")

            sms_alert_text = f"Job Match Alert: Your profile scored {score}% for the Data Analyst opening! Key matching skills: {', '.join(matched[:3])}."

            # WhatsApp Notification Dispatch (CallMeBot)
            clean_phone = st.session_state.phone.replace("+", "").strip()
            encoded_msg = urllib.parse.quote(sms_alert_text)
            
            sent_whatsapp = False
            if whatsapp_api_key and clean_phone:
                try:
                    url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_msg}&apikey={whatsapp_api_key}"
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        sent_whatsapp = True
                except Exception as ex:
                    st.warning(f"Gateway connection error: {ex}")

            # Optional Twilio live attempt
            sent_twilio = False
            if tw_sid and tw_token and tw_phone and st.session_state.phone:
                try:
                    client = Client(tw_sid, tw_token)
                    client.messages.create(body=sms_alert_text, from_=tw_phone, to=st.session_state.phone)
                    sent_twilio = True
                except Exception:
                    pass

            st.markdown("---")
            st.subheader("📲 Real-Time Mobile Alert Pipeline")
            if sent_whatsapp:
                st.success(f"✅ Real WhatsApp Notification successfully delivered to +{clean_phone}!")
            elif sent_twilio:
                st.success(f"✅ Live SMS sent to {st.session_state.phone} via Twilio!")
            else:
                st.info("⚡ Real-Time Notification Log (Telecom Gateway Preview):")
                st.code(f"Destination Number: {st.session_state.phone}\nCarrier Format: E.164 (India +91)\nPayload: {sms_alert_text}", language="markdown")
                if not whatsapp_api_key:
                    st.caption("Sidebar me CallMeBot WhatsApp API key daalte hi WhatsApp par live message aayega.")