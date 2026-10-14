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
            db.session.add(Patient(uhid=data['uhid'], name=data['name'], age=data['age'], gender=data['gender'], preferred_language=data.get('preferred_language', 'English')))
            db.session.commit()
        import base64
        safe_uhid = base64.urlsafe_b64encode(data['uhid'].encode('utf-8')).decode('utf-8').rstrip('=')
        return jsonify({"status": "success", "telegram_link": f"https://{TELEGRAM_BOT_URL}?start={safe_uhid}"}), 200
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

        msg_text = (
            f"Hello {patient.name}, please click the link below and press 'Start' to re-verify your consent:\n"
            f"https://{TELEGRAM_BOT_URL}?start={patient.uhid}"
        )
        send_tg_message(patient.telegram_chat_id, msg_text)
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "Patient not found or no Telegram chat ID"}), 404

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

@main_bp.route('/cron_reminders', methods=['GET', 'POST'])
def cron_reminders():
    secret = request.args.get('secret')
    if secret != "dose_cron_secure_123":
        return jsonify({"error": "Unauthorized"}), 403

    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime('%H:%M')
    current_date_str = now_ist.strftime('%Y-%m-%d')
    current_datetime_minute = now_ist.strftime('%Y-%m-%d %H:%M:00')

    try:
        import json
        with open('app/translations.json', 'r', encoding='utf-8') as tf:
            trans_dict = json.load(tf)
    except Exception:
        trans_dict = {}

    sql = text("""
        SELECT t.id as timing_id, p.telegram_chat_id, m.drug_name, m.dose, p.preferred_language
        FROM medication_timings t
        JOIN patient_medications m ON t.medication_id = m.id
        JOIN patients p ON m.uhid = p.uhid
        WHERE m.start_date <= :d 
          AND m.end_date >= :d
          AND LEFT(CAST(t.dosage_time AS CHAR), 5) = :t
          AND p.telegram_chat_id IS NOT NULL
          AND p.consent_status = 'Accepted'
    """)

    results = db.session.execute(sql, {'d': current_date_str, 't': current_time_str}).fetchall()

    for timing_id, chat_id, drug_name, dose, pref_lang in results:
        log = DosageLog.query.filter_by(timing_id=timing_id, scheduled_datetime=current_datetime_minute).first()
        if not log:
            new_log = DosageLog(timing_id=timing_id, scheduled_datetime=current_datetime_minute, status='Pending')
            db.session.add(new_log)
            db.session.flush()

            lang = pref_lang if pref_lang in trans_dict else 'English'
            t = trans_dict.get(lang, trans_dict.get('English', {}))

            btn_taken = t.get("btn_taken", "✅ Taken")
            btn_missed = t.get("btn_missed", "❌ Missed")

            kb = {"inline_keyboard": [[{"text": btn_taken, "callback_data": f"{new_log.id}:Taken"}, {"text": btn_missed, "callback_data": f"{new_log.id}:Missed"}]]}

            msg_lines = [
                t.get('reminder_header', '🔔 *Medication Reminder*'),
                "",
                t.get('time_to_take', 'Time to take your medication:'),
                f"💊 *{drug_name}*",
                f"{t.get('dose', '🩸 Dose:')} {dose}",
                "",
                t.get('record_prompt', 'Please record your response below:')
            ]
            msg = chr(10).join(msg_lines)

            send_tg_message(chat_id, msg, reply_markup=kb)

    db.session.commit()
    return jsonify({"status": "success", "processed": len(results), "server_time": current_time_str, "db_query_date": current_date_str}), 200

@main_bp.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.json
        if not data or 'message' not in data:
            return jsonify({"status": "ignored"}), 200

        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')

        if text.startswith('/start'):
            parts = text.split(' ')
            if len(parts) > 1:
                arg = parts[1].strip()

                if arg.startswith('auth_'):
                    auth = AuthToken.query.get(arg)
                    if auth and auth.status == 'Pending':
                        auth.telegram_id = str(chat_id)
                        user = User.query.get(str(chat_id))
                        if user and user.status == 'Active':
                            auth.status = 'Approved'
                            send_tg_message(chat_id, "✅ Login successful! You may return to your web browser.")
                        else:
                            auth.status = 'Denied'
                            send_tg_message(chat_id, "❌ Unauthorized. Your Telegram account is not registered.")
                        db.session.commit()
                        return jsonify({"status": "success"}), 200
                else:
                    import base64
                    try:
                        padding = '=' * (4 - len(arg) % 4)
                        uhid = base64.urlsafe_b64decode(arg + padding).decode('utf-8')
                    except Exception:
                        uhid = arg

                    patient = Patient.query.filter_by(uhid=uhid).first()
                    if patient:
                        patient.telegram_chat_id = str(chat_id)
                        patient.consent_status = 'Accepted'
                        db.session.commit()

                        try:
                            import json
                            with open('app/translations.json', 'r', encoding='utf-8') as tf:
                                trans_dict = json.load(tf)
                            lang = patient.preferred_language if patient.preferred_language in trans_dict else 'English'
                            welcome = trans_dict.get(lang, trans_dict.get('English', {})).get('reminder_header', '🔔')
                            success_msg = f"{welcome}" + chr(10) + f"✅ Registration successful! Welcome {patient.name}."
                        except Exception:
                            success_msg = f"✅ Registration successful! Welcome {patient.name}."

                        send_tg_message(chat_id, success_msg)
                        return jsonify({"status": "success"}), 200

        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error"}), 500
