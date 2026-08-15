from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from datetime import datetime, timedelta, timezone
import uuid
import requests
from sqlalchemy import text
from .database import db
from .models import Patient, PatientComplaint, PatientDiagnosis, PatientMedication, MedicationTiming, User, AuthToken, DosageLog

main_bp = Blueprint('main', __name__)
TELEGRAM_TOKEN = "8615887860:AAHixEeOgVoEZzijqgpgF7-6LvYB_GWxN14"
TELEGRAM_BOT_URL = "t.me/Dosetrack_bot"
ADMIN_CHAT_ID = "863968849"
IST = timezone(timedelta(hours=5, minutes=30))

# --- Helper Telegram Functions ---
def send_tg_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

def edit_tg_message(chat_id, message_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    requests.post(url, json={"chat_id": chat_id, "message_id": message_id, "text": text})

# --- Middleware ---
@main_bp.before_request
def require_auth():
    allowed = ['main.login', 'main.api_auth_token', 'main.api_auth_status', 'main.logout', 'static', 'main.telegram_webhook', 'main.cron_reminders']
    if request.endpoint not in allowed and not request.endpoint.startswith('static'):
        if 'telegram_id' not in session:
            return redirect(url_for('main.login'))
        user = User.query.get(session['telegram_id'])
        if not user or user.status != 'Active':
            session.clear()
            return redirect(url_for('main.login'))

# --- Auth & Admin Routes ---
@main_bp.route('/login')
def login():
    if 'telegram_id' in session: return redirect(url_for('main.index'))
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))

@main_bp.route('/api/auth/token', methods=['GET'])
def api_auth_token():
    token_str = f"auth_{uuid.uuid4().hex}"
    db.session.add(AuthToken(token=token_str))
    db.session.commit()
    return jsonify({"token": token_str, "link": f"https://{TELEGRAM_BOT_URL}?start={token_str}"})

@main_bp.route('/api/auth/status/<token>', methods=['GET'])
def api_auth_status(token):
    db.session.commit() 
    auth = AuthToken.query.get(token)
    if not auth: return jsonify({"status": "Invalid"}), 404
    if auth.status == 'Approved':
        session['telegram_id'] = auth.telegram_id
        user = User.query.get(auth.telegram_id)
        session['role'] = user.role if user else 'User'
        session['first_name'] = user.first_name if user else 'Staff'
    return jsonify({"status": auth.status})

@main_bp.route('/admin')
def admin():
    if session.get('role') != 'Admin': return render_template('unauthorized.html'), 403
    return render_template('admin.html', users=User.query.all())

@main_bp.route('/api/admin/remove/<telegram_id>', methods=['POST'])
def remove_user(telegram_id):
    if session.get('role') != 'Admin': return jsonify({"error": "Unauthorized"}), 403
    user = User.query.get(telegram_id)
    if user:
        user.status = 'Inactive'
        db.session.commit()
        send_tg_message(telegram_id, "❌ Your access to the web app has been revoked by an administrator.")
        return jsonify({"status": "success"})
    return jsonify({"error": "User not found"}), 404

# --- Clinical Routes ---
@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/api/register', methods=['POST'])
def register_patient():
    data = request.json
    try:
        if not Patient.query.get(data['uhid']):
            db.session.add(Patient(uhid=data['uhid'], name=data['name'], age=data['age'], gender=data['gender']))
            db.session.commit()
        return jsonify({"status": "success", "telegram_link": f"https://{TELEGRAM_BOT_URL}?start={data['uhid']}"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400

@main_bp.route('/api/consent_status/<uhid>', methods=['GET'])
def check_consent(uhid):
    db.session.commit()
    res = db.session.execute(text("SELECT consent_status FROM patients WHERE uhid = :u"), {'u': uhid}).fetchone()
    return jsonify({"status": res[0] if res else "Not Found"}), 200 if res else 404

@main_bp.route('/api/resend_consent/<uhid>', methods=['POST'])
def resend_consent(uhid):
    patient = Patient.query.get(uhid)
    if patient and patient.telegram_chat_id:
        patient.consent_status = 'Pending'
        db.session.commit()
        kb = {"inline_keyboard": [[{"text": "✅ I Accept", "callback_data": f"consent:{uhid}:Accepted"}], [{"text": "❌ I Deny", "callback_data": f"consent:{uhid}:Denied"}]]}
        send_tg_message(patient.telegram_chat_id, f"Hello {patient.name}! \n\n*Informed Consent:*\nDo you consent to enroll...", reply_markup=kb)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@main_bp.route('/api/clinical', methods=['POST'])
def save_clinical_data():
    data = request.json
    uhid = data['uhid']
    for comp in data.get('complaints', []): db.session.add(PatientComplaint(uhid=uhid, hpo_id=comp['hpo_id'], hpo_term=comp['hpo_term'], duration=comp['duration']))
    for diag in data.get('diagnoses', []): db.session.add(PatientDiagnosis(uhid=uhid, icd10_code=diag['icd10_code'], icd10_term=diag['icd10_term']))
    for med in data.get('medications', []):
        m = PatientMedication(uhid=uhid, rxcui=med['rxcui'], drug_name=med['drug_name'], dose=med['dose'], start_date=datetime.strptime(med['start_date'], '%Y-%m-%d').date(), end_date=datetime.strptime(med['end_date'], '%Y-%m-%d').date())
        db.session.add(m)
        db.session.flush() 
        for time_str in med.get('timings', []): db.session.add(MedicationTiming(medication_id=m.id, dosage_time=datetime.strptime(time_str, '%H:%M').time()))
    db.session.commit()
    return jsonify({"status": "success"}), 201

# ==========================================
# SERVERLESS TELEGRAM WEBHOOK (Replaces bot.py)
# ==========================================
@main_bp.route('/webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    if not data: return "ok", 200

    try:
        if 'message' in data and 'text' in data['message']:
            msg_text = data['message']['text']
            chat_id = str(data['message']['chat']['id'])
            first_name = data['message']['from'].get('first_name', 'User')

            if msg_text.startswith('/start '):
                payload = msg_text.split(' ')[1]

                # Auth Flow
                if payload.startswith("auth_"):
                    token = payload
                    user = User.query.get(chat_id)
                    auth_token = AuthToken.query.get(token)

                    if user and user.status == 'Active':
                        if auth_token:
                            auth_token.telegram_id = chat_id
                            auth_token.status = 'Approved'
                            db.session.commit()
                        send_tg_message(chat_id, "✅ Login approved! Your web dashboard is loading.")
                    else:
                        if auth_token:
                            auth_token.telegram_id = chat_id
                            auth_token.status = 'WaitingForAdmin'
                            db.session.commit()
                        send_tg_message(chat_id, "⏳ Your login request is pending Admin approval. Please wait...")
                        kb = {"inline_keyboard": [
                            [{"text": "✅ Approve", "callback_data": f"adm_ok:{token}:{chat_id}"}],
                            [{"text": "❌ Reject", "callback_data": f"adm_no:{token}:{chat_id}"}]
                        ]}
                        send_tg_message(ADMIN_CHAT_ID, f"🔔 *New Web Access Request*\nName: {first_name}\nTelegram ID: {chat_id}\nAction required:", reply_markup=kb)

                # Patient Consent Flow
                else:
                    uhid = payload
                    patient = Patient.query.get(uhid)
                    if patient:
                        patient.telegram_chat_id = chat_id
                        patient.consent_status = 'Pending'
                        db.session.commit()
                        kb = {"inline_keyboard": [[{"text": "✅ I Accept", "callback_data": f"consent:{uhid}:Accepted"}], [{"text": "❌ I Deny", "callback_data": f"consent:{uhid}:Denied"}]]}
                        send_tg_message(chat_id, f"Hello {patient.name}! Welcome to DoseTrack.\n\n*Informed Consent:*\nDo you consent to enroll in this study, receive automated dosage reminders, and record responses?", reply_markup=kb)
                    else:
                        send_tg_message(chat_id, "Patient ID not found.")

        elif 'callback_query' in data:
            cb = data['callback_query']
            cb_id = cb['id']
            chat_id = str(cb['message']['chat']['id'])
            msg_id = cb['message']['message_id']
            cb_data = cb['data']
            first_name = cb['from'].get('first_name', 'User')

            # Instantly acknowledge callback
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb_id})

            if cb_data.startswith("adm_ok:"):
                _, token, t_id = cb_data.split(":")
                user = User.query.get(t_id)
                if not user:
                    db.session.add(User(telegram_id=t_id, first_name=first_name, role='User', status='Active'))
                else:
                    user.status = 'Active'
                    user.first_name = first_name
                auth = AuthToken.query.get(token)
                if auth: auth.status = 'Approved'
                db.session.commit()
                send_tg_message(t_id, "🎉 Your access request has been APPROVED by the Admin. Your web page is logging you in.")
                edit_tg_message(chat_id, msg_id, "User approved and granted access.")

            elif cb_data.startswith("adm_no:"):
                _, token, t_id = cb_data.split(":")
                auth = AuthToken.query.get(token)
                if auth: auth.status = 'Denied'
                db.session.commit()
                send_tg_message(t_id, "❌ Your access request was DENIED by the Admin.")
                edit_tg_message(chat_id, msg_id, "User rejected.")

            elif cb_data.startswith("consent:"):
                _, uhid, status = cb_data.split(":")
                patient = Patient.query.get(uhid)
                if patient:
                    patient.consent_status = status
                    db.session.commit()
                    edit_tg_message(chat_id, msg_id, "Thank you! You have accepted the consent." if status == "Accepted" else "You have denied consent.")

            elif ":" in cb_data:
                log_id, status = cb_data.split(":")
                log = DosageLog.query.get(log_id)
                if log:
                    log.status = status
                    log.response_time = datetime.now(IST)
                    db.session.commit()
                    edit_tg_message(chat_id, msg_id, f"Response recorded: {status} ✅. Thank you!")

    except Exception as e:
        print(f"Webhook processing error: {e}")
        db.session.rollback()

    return "ok", 200

# ==========================================
# SERVERLESS SCHEDULER CRON (Replaces scheduler.py)
# ==========================================
@main_bp.route('/api/cron/reminders', methods=['GET', 'POST'])
def cron_reminders():
    # Simple security check to prevent random people from triggering it
    secret = request.args.get('secret')
    if secret != "dose_cron_secure_123":
        return jsonify({"error": "Unauthorized"}), 403

    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime('%H:%M')
    current_date_str = now_ist.strftime('%Y-%m-%d')
    current_datetime_minute = now_ist.strftime('%Y-%m-%d %H:%M:00')

    sql = text("""
        SELECT t.id as timing_id, p.telegram_chat_id, m.drug_name, m.dose
        FROM medication_timings t
        JOIN patient_medications m ON t.medication_id = m.id
        JOIN patients p ON m.uhid = p.uhid
        WHERE m.start_date <= :d 
          AND m.end_date >= :d
          AND TIME_FORMAT(t.dosage_time, '%H:%i') = :t
          AND p.telegram_chat_id IS NOT NULL
          AND p.consent_status = 'Accepted'
    """)

    results = db.session.execute(sql, {'d': current_date_str, 't': current_time_str}).fetchall()

    for timing_id, chat_id, drug_name, dose in results:
        log = DosageLog.query.filter_by(timing_id=timing_id, scheduled_datetime=current_datetime_minute).first()
        if not log:
            new_log = DosageLog(timing_id=timing_id, scheduled_datetime=current_datetime_minute, status='Pending')
            db.session.add(new_log)
            db.session.flush()

            kb = {"inline_keyboard": [[{"text": "✅ Taken", "callback_data": f"{new_log.id}:Taken"}, {"text": "❌ Missed", "callback_data": f"{new_log.id}:Missed"}]]}
            send_tg_message(
                chat_id, 
                f"🔔 *Medication Reminder*\n\nTime to take your medication:\n💊 *{drug_name}*\n🩸 Dose: {dose}\n\nPlease record your response below:",
                reply_markup=kb
            )

    db.session.commit()
    return jsonify({"status": "success", "processed": len(results)}), 200
