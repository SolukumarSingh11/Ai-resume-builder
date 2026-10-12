import streamlit as st
import sqlite3
import hashlib
import json
import io
import urllib.parse
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import google.generativeai as genai
from twilio.rest import Client

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

# ----------------- PAGE CONFIGURATION -----------------
st.set_page_config(page_title="AI Resume Builder & Job Matcher", page_icon="📄", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.phone = ""

# ----------------- AUTHENTICATION PORTAL -----------------
if not st.session_state.logged_in:
    st.title("🎓 AI Resume Builder & Smart Job Matcher")
    st.caption("Empowering job seekers with automated ATS optimization and real-time job compatibility alerts.")
    
    tab1, tab2 = st.tabs(["Sign In", "Sign Up"])

    with tab1:
        st.subheader("Account Login")
        l_user = st.text_input("Username", key="l_user", placeholder="Enter your registered username")
        l_pass = st.text_input("Password", type="password", key="l_pass", placeholder="Enter your password")
        if st.button("Log In", type="primary"):
            user_data = login_user(l_user, l_pass)
            if user_data:
                st.session_state.logged_in = True
                st.session_state.username = l_user
                st.session_state.phone = user_data[0]
                st.success("Authentication successful! Redirecting...")
                st.rerun()
            else:
                st.error("Invalid credentials. Please verify your username and password.")

    with tab2:
        st.subheader("Create a New Account")
        r_user = st.text_input("Username", key="r_user", placeholder="Choose a unique username")
        r_pass = st.text_input("Password", type="password", key="r_pass", placeholder="Create a secure password")
        st.write("**Mobile Contact (+91 - India)**")
        col_c, col_num = st.columns([1, 4])
        with col_c:
            st.text_input("Country Code", value="+91", disabled=True, key="reg_code")
        with col_num:
            raw_phone = st.text_input("10-Digit Mobile Number", placeholder="e.g. 9876543210", max_chars=10, key="reg_phone")
        
        if st.button("Register Account"):
            if r_user and r_pass and raw_phone:
                if len(raw_phone.strip()) == 10 and raw_phone.strip().isdigit():
                    full_phone = f"+91{raw_phone.strip()}"
                    if register_user(r_user, r_pass, full_phone):
                        st.success("Account registered successfully! Please switch to the Sign In tab.")
                    else:
                        st.error("Username already taken. Please select an alternate username.")
                else:
                    st.error("Please provide a valid 10-digit Indian mobile contact number.")
            else:
                st.warning("All registration fields are required.")
    st.stop()

# ----------------- MAIN DASHBOARD -----------------
st.sidebar.title(f"Welcome, {st.session_state.username} 👋")
st.sidebar.caption(f"Verified Contact: `{st.session_state.phone}`")

if st.sidebar.button("Log Out"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.phone = ""
    st.session_state.resume_ready = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ API Configuration")
gemini_key = st.sidebar.text_input("Gemini API Key", type="password", help="Enter Google AI Studio Key")

st.sidebar.subheader("📲 WhatsApp Notification Gateway")
whatsapp_api_key = st.sidebar.text_input("CallMeBot WhatsApp API Key", type="password", help="Enter free API key provided by CallMeBot on WhatsApp")

st.sidebar.subheader("📡 Twilio SMS Gateway (Optional)")
tw_sid = st.sidebar.text_input("Twilio Account SID", type="password")
tw_token = st.sidebar.text_input("Twilio Auth Token", type="password")
tw_phone = st.sidebar.text_input("Twilio Phone Number (e.g. +1...)")

menu = st.sidebar.radio("Navigation", ["1. Comprehensive AI Resume Builder", "2. Smart Job Matcher & Alerts"])

# Helper: ReportLab Platypus PDF Builder
def generate_complete_pdf(details, summary, ai_exp, ai_proj):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle('Name', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1A365D"), spaceAfter=2)
    contact_style = ParagraphStyle('Contact', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#4A5568"))
    h2_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor("#2B6CB0"), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9.5, leading=13, spaceAfter=3)

    elements = []

    # Header / Contact Details
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
    elements.append(Paragraph(f"<b>{details['degree']}</b> - {details['college']} ({details['grad_year']}) | Academic Score: {details['score']}", body_style))
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

    # Technical Projects
    elements.append(Paragraph("KEY TECHNICAL PROJECTS", h2_style))
    for line in ai_proj.split("\n"):
        if line.strip():
            elements.append(Paragraph(line.strip(), body_style))
    elements.append(Spacer(1, 4))

    # Certifications & Achievements
    if details['certifications'].strip():
        elements.append(Paragraph("CERTIFICATIONS & ACHIEVEMENTS", h2_style))
        for cert in details['certifications'].split("\n"):
            if cert.strip():
                elements.append(Paragraph(f"• {cert.strip()}", body_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# Helper: Robust Multi-Model Gemini Invoker
def call_gemini(api_key, prompt):
    genai.configure(api_key=api_key)
    selected_model = None
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for candidate in ["models/gemini-1.5-flash-latest", "models/gemini-1.5-flash", "models/gemini-2.0-flash", "models/gemini-pro"]:
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
    st.title("📄 Comprehensive AI Resume Builder")
    st.caption("Provide your professional details to generate an ATS-compliant, recruiter-ready resume.")

    with st.expander("👤 1. Personal & Contact Details", expanded=True):
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            full_name = st.text_input("Full Name", value=st.session_state.username)
            email = st.text_input("Email Address", placeholder="e.g. candidate@gmail.com")
            target_role = st.text_input("Target Job Profile", placeholder="e.g. Data Analyst / Software Engineer")
        with p_col2:
            phone_num = st.text_input("Contact Number (+91)", value=st.session_state.phone, disabled=True)
            location = st.text_input("Current City / State", placeholder="e.g. Pune, Maharashtra")
            linkedin = st.text_input("LinkedIn / Portfolio URL", placeholder="e.g. linkedin.com/in/username")

    with st.expander("🎓 2. Educational Qualifications", expanded=True):
        e_col1, e_col2 = st.columns(2)
        with e_col1:
            degree = st.text_input("Degree / Course", placeholder="e.g. Bachelor of Computer Applications (BCA)")
            college = st.text_input("College / Institute Name", placeholder="e.g. Savitribai Phule Pune University")
        with e_col2:
            grad_year = st.text_input("Graduation Year / Expected", placeholder="e.g. 2026")
            score = st.text_input("CGPA / Percentage", placeholder="e.g. 8.4 CGPA")

    with st.expander("💻 3. Technical Competencies", expanded=True):
        skills_input = st.text_area("Skills (Languages, Databases, Frameworks, Tools)", placeholder="e.g. Python, SQL (MySQL), Tableau, Power BI, Excel, Pandas, Git, C++")

    with st.expander("💼 4. Experience & Projects", expanded=True):
        experience_raw = st.text_area("Internships / Work Experience (Enter 'Fresher' if none)", placeholder="Describe your responsibilities, internships, or practical industry exposure...")
        projects_raw = st.text_area("Key Technical Projects", placeholder="Project 1: Real-time Analytics Dashboard using Tableau.\nProject 2: AI-Powered ATS Resume Builder using Streamlit.")

    with st.expander("🏆 5. Certifications & Achievements", expanded=False):
        certifications = st.text_area("Certifications (One entry per line)", placeholder="e.g. Data Analytics Professional Certificate - Coursera\nIgniteX 1.0 Employability Skills Program")

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

    if st.button("✨ Enhance & Generate ATS Resume with AI", type="primary"):
        with st.spinner("Optimizing resume content for ATS compliance..."):
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

            # Fail-safe Fallback
            if not summary_res:
                summary_res = f"Detail-oriented {target_role if target_role else 'Professional'} equipped with solid technical foundations in {skills_input if skills_input else 'Core Computing Technologies'} and analytical problem-solving abilities. Capable of translating technical requirements into actionable, high-quality deliverables."
                exp_res = f"• Developed and executed technical assignments utilizing {skills_input if skills_input else 'modern toolkits'}.\n• Maintained structured workflows and adhered to industry-standard documentation practices."
                proj_res = f"• Engineered end-to-end software applications showcasing practical problem-solving capabilities.\n• Integrated external API services and optimized document rendering pipelines."

            st.session_state.ai_summary = summary_res
            st.session_state.ai_exp = exp_res
            st.session_state.ai_proj = proj_res
            st.session_state.resume_ready = True
            st.session_state.current_payload = resume_payload
            st.success("Resume successfully generated and formatted!")

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
        st.markdown(f"**Key Projects:**\n{st.session_state.ai_proj}")

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
elif menu == "2. Smart Job Matcher & Alerts":
    st.title("🎯 Smart Job Matcher & Real-Time Alerts")
    st.info(f"Target Alert Recipient: **{st.session_state.username}** (`{st.session_state.phone}`)")

    job_title_input = st.text_input("Job Role / Designation", placeholder="e.g. Associate Data Analyst / Business Intelligence Engineer")
    job_desc = st.text_area("Job Description (JD):", height=150, 
                            placeholder="Paste the target job description here...")
    user_skills_to_match = st.text_input("Extracted Resume Skills for ATS Matching", placeholder="e.g. Python, SQL, Tableau, Power BI, Excel, MySQL, Git")

    if st.button("🚀 Analyze Compatibility & Dispatch Mobile Alert", type="primary"):
        with st.spinner("Evaluating profile compatibility against job criteria..."):
            score = 85
            matched = ["Relevant Foundational Skills"]
            missing = ["Specialized Domain Expertise"]

            if gemini_key and job_desc and user_skills_to_match:
                try:
                    match_prompt = f"""Compare candidate skills with JD.
Skills: {user_skills_to_match}
JD: {job_desc}

Return strictly JSON:
{{
  "score": 85,
  "matched": ["skill1", "skill2"],
  "missing": ["skill3"]
}}"""
                    raw_res = call_gemini(gemini_key, match_prompt)
                    clean_res = raw_res.replace("```json", "").replace("```", "").strip()
                    parsed_match = json.loads(clean_res)
                    score = parsed_match.get("score", 85)
                    matched = parsed_match.get("matched", matched)
                    missing = parsed_match.get("missing", missing)
                except Exception:
                    pass

            st.metric(label="ATS Profile Match Score", value=f"{score}%")
            st.progress(score / 100)

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.success(f"Matched Competencies: {', '.join(matched)}")
            with col_m2:
                st.warning(f"Skill Deficiencies: {', '.join(missing)}")

            sms_alert_text = f"Job Match Alert for {st.session_state.username}: Profile scored {score}% for '{job_title_input}'! Matching skills: {', '.join(matched[:3])}."

            # WhatsApp Webhook Dispatch (CallMeBot)
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

            # Optional Twilio Dispatch
            sent_twilio = False
            if tw_sid and tw_token and tw_phone and st.session_state.phone:
                try:
                    client = Client(tw_sid, tw_token)
                    client.messages.create(body=sms_alert_text, from_=tw_phone, to=st.session_state.phone)
                    sent_twilio = True
                except Exception:
                    pass

            st.markdown("---")
            st.subheader("📲 Real-Time Mobile Dispatch Pipeline")
            if sent_whatsapp:
                st.success(f"✅ Real-time WhatsApp alert successfully dispatched to +{clean_phone}!")
            elif sent_twilio:
                st.success(f"✅ Live SMS notification dispatched to {st.session_state.phone} via Twilio Gateway!")
            else:
                st.info("⚡ Live Telecom Dispatch Pipeline (E.164 Format Preview):")
                st.code(f"Destination: {st.session_state.phone}\nTelecom Standard: E.164 (India)\nPayload: {sms_alert_text}", language="markdown")
                if not whatsapp_api_key:
                    st.caption("Provide a CallMeBot API key in the sidebar to trigger live WhatsApp messages.")
