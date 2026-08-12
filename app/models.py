from datetime import datetime
from .database import db

class User(db.Model):
    __tablename__ = 'users'
    telegram_id = db.Column(db.String(50), primary_key=True)
    first_name = db.Column(db.String(100))
    role = db.Column(db.Enum('Admin', 'User'), default='User')
    status = db.Column(db.Enum('Active', 'Inactive'), default='Active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuthToken(db.Model):
    __tablename__ = 'auth_tokens'
    token = db.Column(db.String(100), primary_key=True)
    telegram_id = db.Column(db.String(50), nullable=True)
    status = db.Column(db.Enum('Pending', 'WaitingForAdmin', 'Approved', 'Denied'), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Patient(db.Model):
    __tablename__ = 'patients'
    uhid = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.Enum('M', 'F', 'Other'), nullable=False)
    telegram_chat_id = db.Column(db.String(50), nullable=True)
    consent_status = db.Column(db.Enum('Pending', 'Accepted', 'Denied'), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PatientComplaint(db.Model):
    __tablename__ = 'patient_complaints'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uhid = db.Column(db.String(50), db.ForeignKey('patients.uhid', ondelete='CASCADE'), nullable=False)
    hpo_id = db.Column(db.String(50), nullable=False)
    hpo_term = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.String(50), nullable=False)

class PatientDiagnosis(db.Model):
    __tablename__ = 'patient_diagnoses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uhid = db.Column(db.String(50), db.ForeignKey('patients.uhid', ondelete='CASCADE'), nullable=False)
    icd10_code = db.Column(db.String(20), nullable=False)
    icd10_term = db.Column(db.String(255), nullable=False)

class PatientMedication(db.Model):
    __tablename__ = 'patient_medications'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uhid = db.Column(db.String(50), db.ForeignKey('patients.uhid', ondelete='CASCADE'), nullable=False)
    rxcui = db.Column(db.String(50), nullable=False)
    drug_name = db.Column(db.String(255), nullable=False)
    dose = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

class MedicationTiming(db.Model):
    __tablename__ = 'medication_timings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    medication_id = db.Column(db.Integer, db.ForeignKey('patient_medications.id', ondelete='CASCADE'), nullable=False)
    dosage_time = db.Column(db.Time, nullable=False)
