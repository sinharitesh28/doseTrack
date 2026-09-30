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
        # Load translations

        try:

            import json

            with open('app/translations.json', 'r', encoding='utf-8') as tf:

                trans_dict = json.load(tf)

            t = trans_dict.get(pref_lang, trans_dict['English'])

        except Exception as e:

            t = {"reminder_header": "🔔 *Medication Reminder*", "time_to_take": "Time to take your medication:", "dose": "🩸 Dose:", "record_prompt": "Please record your response below:", "btn_taken": "✅ Taken", "btn_missed": "❌ Missed"}

        

        kb = {"inline_keyboard": [[{"text": t["btn_taken"], "callback_data": f"{new_log.id}:Taken"}, {"text": t["btn_missed"], "callback_data": f"{new_log.id}:Missed"}]]}

        msg_text = f"{t['reminder_header']}\n\n{t['time_to_take']}\n💊 *{drug_name}*\n{t['dose']} {dose}\n\n{t['record_prompt']}"

        send_tg_message(chat_id, msg_text, reply_markup=kb)

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

        # Handle Patient Consent: /start <uhid>
        if text.startswith('/start'):
            parts = text.split(' ')
            if len(parts) > 1:
                uhid = parts[1].strip()
                patient = Patient.query.filter_by(uhid=uhid).first()

                if patient:
                    patient.telegram_chat_id = str(chat_id)
                    patient.consent_status = 'Accepted'
                    db.session.commit()

                    success_msg = f"✅ Registration successful! Welcome to DoseTrack, {patient.name}. You will now receive your localized medication reminders here."
                    send_tg_message(chat_id, success_msg)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Webhook Error: {e}")
        return jsonify({"status": "error"}), 500
