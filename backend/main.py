from datetime import datetime, timedelta, timezone
from calendar import monthrange
from os import getenv
from pathlib import Path
from sqlite3 import Row, connect as sqlite_connect
from typing import Annotated
import asyncio
import time

import bcrypt
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Keeps local SQLite development working before PostgreSQL deps are installed.
    psycopg = None
    dict_row = None


load_dotenv()

DATABASE_PATH = Path(__file__).with_name("jiujitsu.db")
DATABASE_URL = getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
APP_ENV = getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV in ("production", "prod") or USE_POSTGRES
ENFORCE_HTTPS = getenv("ENFORCE_HTTPS", "true" if IS_PRODUCTION else "false").lower() == "true"
JWT_SECRET = getenv("JWT_SECRET", "troque-esta-chave-em-producao-com-mais-de-32-caracteres")
JWT_ALGORITHM = "HS256"
PIX_KEY = getenv("PIX_KEY", "jiujitsu.academy@email.com")
ACADEMY_WHATSAPP = getenv("ACADEMY_WHATSAPP", "55889993632214")
ACADEMY_WHATSAPP_DISPLAY = getenv("ACADEMY_WHATSAPP_DISPLAY", "(88) 9993632214")
MERCADO_PAGO_ACCESS_TOKEN = getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
REMINDER_CHECK_INTERVAL_SECONDS = int(getenv("REMINDER_CHECK_INTERVAL_SECONDS", "3600"))
WHATSAPP_ACCESS_TOKEN = getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION = getenv("WHATSAPP_API_VERSION", "v25.0")
CORS_ORIGINS = [
    origin.strip()
    for origin in getenv(
        "CORS_ORIGINS",
        "http://localhost:4200,http://127.0.0.1:4200",
    ).split(",")
    if origin.strip()
]

DEFAULT_JWT_SECRET = "troque-esta-chave-em-producao-com-mais-de-32-caracteres"
DEFAULT_ADMIN_PASSWORD = "admin123"
RATE_LIMIT_WINDOW_SECONDS = int(getenv("RATE_LIMIT_WINDOW_SECONDS", "300"))
LOGIN_RATE_LIMIT = int(getenv("LOGIN_RATE_LIMIT", "8"))
REGISTER_RATE_LIMIT = int(getenv("REGISTER_RATE_LIMIT", "5"))
RATE_LIMITS: dict[str, list[float]] = {}

if IS_PRODUCTION and (JWT_SECRET == DEFAULT_JWT_SECRET or len(JWT_SECRET) < 32):
    raise RuntimeError("Defina um JWT_SECRET forte antes de rodar em produção.")

if IS_PRODUCTION and "*" in CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS não pode conter '*' em produção.")

if IS_PRODUCTION:
    insecure_origins = [
        origin
        for origin in CORS_ORIGINS
        if origin.startswith("http://") and "localhost" not in origin and "127.0.0.1" not in origin
    ]
    if insecure_origins:
        raise RuntimeError("Use apenas origens HTTPS em CORS_ORIGINS quando estiver em produção.")

app = FastAPI(title="CTC - Centro de Treinamento Canoa API")


@app.middleware("http")
async def enforce_https_and_security_headers(request: Request, call_next):
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", "")
    is_local_host = host.startswith("localhost") or host.startswith("127.0.0.1")
    if ENFORCE_HTTPS and forwarded_proto == "http" and not is_local_host:
        https_url = request.url.replace(scheme="https")
        from fastapi.responses import RedirectResponse

        return RedirectResponse(str(https_url), status_code=308)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if ENFORCE_HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TrainingDay(BaseModel):
    day: str
    start_time: str
    end_time: str


class StudentCreate(BaseModel):
    username: str = Field(min_length=3)
    phone: str = Field(min_length=10)
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=3)
    age: int = Field(ge=4, le=100)
    birth_date: str = ""
    cpf: str = ""
    address: str = ""
    neighborhood: str = ""
    city: str = ""
    modality: str = Field(pattern="^(kid|kid \\+|juvenil)$")
    jiu_jitsu_start_date: str = ""
    monthly_fee: float = Field(gt=0)
    payment_day: int = Field(ge=1, le=31)
    guardian_name: str = ""
    guardian_relationship: str = ""
    guardian_cpf: str = ""
    guardian_phone: str = ""
    guardian_secondary_phone: str = ""
    medical_restriction: str = "nao"
    medical_restriction_description: str = ""
    training_days: list[TrainingDay]


class LoginRequest(BaseModel):
    username: str
    password: str


class PaymentCreate(BaseModel):
    amount: float = Field(gt=0)


class PaymentStatusUpdate(BaseModel):
    payment_status: str = Field(pattern="^(pendente|pago)$")


class CashFlowCreate(BaseModel):
    entry_type: str = Field(pattern="^(entrada|saida)$")
    description: str = Field(min_length=3)
    category: str = "geral"
    payment_method: str = Field(default="pix", pattern="^(pix|dinheiro|cartao|transferencia|outro)$")
    amount: float = Field(gt=0)
    entry_date: str = ""
    notes: str = ""


class StudentAdminUpdate(BaseModel):
    authorization_signed: str = Field(pattern="^(sim|nao)$")
    scholarship_type: str = Field(pattern="^(nao|sim|bolsa parcial|com 2 filhos)$")


class TeacherCreate(BaseModel):
    name: str = Field(min_length=3)
    cpf: str = ""
    phone: str = Field(min_length=10)
    class_group: str = Field(pattern="^(jiu-jitsu|jiu-jitsu feminino|boxe)$")
    schedule: list[TrainingDay]


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(key: str, limit: int) -> None:
    now = time.time()
    recent = [
        timestamp
        for timestamp in RATE_LIMITS.get(key, [])
        if now - timestamp < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(recent) >= limit:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos.")
    recent.append(now)
    RATE_LIMITS[key] = recent


def mask_phone(phone: str) -> str:
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) <= 4:
        return "****"
    return f"{'*' * max(len(digits) - 4, 0)}{digits[-4:]}"


class DatabaseConnection:
    def __init__(self):
        if USE_POSTGRES:
            if psycopg is None or dict_row is None:
                raise RuntimeError("Instale psycopg[binary] para usar PostgreSQL.")
            self.connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.connection = sqlite_connect(DATABASE_PATH)
            self.connection.row_factory = Row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def _sql(self, sql: str) -> str:
        if not USE_POSTGRES:
            return sql
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        return self.connection.execute(self._sql(sql), params)

    def executemany(self, sql: str, params):
        return self.connection.executemany(self._sql(sql), params)

    def executescript(self, sql: str) -> None:
        if USE_POSTGRES:
            for statement in sql.split(";"):
                if statement.strip():
                    self.execute(statement)
            return
        self.connection.executescript(sql)


def get_connection():
    return DatabaseConnection()


def row_to_dict(row) -> dict:
    return dict(row) if row else {}


def table_columns(connection: DatabaseConnection, table_name: str) -> set[str]:
    if USE_POSTGRES:
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
        return {row["column_name"] for row in rows}

    return {
        column["name"]
        for column in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def insert_returning_id(connection: DatabaseConnection, sql: str, params: tuple) -> int:
    if USE_POSTGRES:
        cursor = connection.execute(f"{sql} RETURNING id", params)
        return cursor.fetchone()["id"]
    cursor = connection.execute(sql, params)
    return cursor.lastrowid


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login necessario.")
    token = authorization.replace("Bearer ", "")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado.") from exc


def require_student(payload: Annotated[dict, Depends(decode_token)]) -> dict:
    if payload.get("role") != "student":
        raise HTTPException(status_code=403, detail="Acesso permitido apenas para alunos.")
    return payload


def require_admin(payload: Annotated[dict, Depends(decode_token)]) -> dict:
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso permitido apenas para professores.")
    return payload


def init_database() -> None:
    with get_connection() as connection:
        if USE_POSTGRES:
            schema_sql = """
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                birth_date TEXT,
                cpf TEXT,
                address TEXT,
                neighborhood TEXT,
                city TEXT,
                modality TEXT NOT NULL DEFAULT 'kid',
                jiu_jitsu_start_date TEXT,
                monthly_fee DOUBLE PRECISION NOT NULL,
                payment_day INTEGER NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'pendente',
                authorization_signed TEXT NOT NULL DEFAULT 'nao',
                scholarship_type TEXT NOT NULL DEFAULT 'nao',
                student_status TEXT NOT NULL DEFAULT 'ativo',
                dropout_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_days (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                amount DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL,
                method TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_payment_id TEXT,
                pix_code TEXT,
                paid_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_reminders (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                reminder_date TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(student_id, reminder_date)
            );

            CREATE TABLE IF NOT EXISTS guardians (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
                name TEXT,
                relationship TEXT,
                cpf TEXT,
                phone TEXT,
                secondary_phone TEXT
            );

            CREATE TABLE IF NOT EXISTS medical_infos (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
                has_restriction TEXT NOT NULL DEFAULT 'nao',
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS teachers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                cpf TEXT,
                phone TEXT NOT NULL,
                class_group TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teacher_schedules (
                id SERIAL PRIMARY KEY,
                teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cash_flow_entries (
                id SERIAL PRIMARY KEY,
                entry_type TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'pix',
                amount DOUBLE PRECISION NOT NULL,
                entry_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        else:
            schema_sql = """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                birth_date TEXT,
                cpf TEXT,
                address TEXT,
                neighborhood TEXT,
                city TEXT,
                modality TEXT NOT NULL DEFAULT 'kid',
                jiu_jitsu_start_date TEXT,
                monthly_fee REAL NOT NULL,
                payment_day INTEGER NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'pendente',
                authorization_signed TEXT NOT NULL DEFAULT 'nao',
                scholarship_type TEXT NOT NULL DEFAULT 'nao',
                student_status TEXT NOT NULL DEFAULT 'ativo',
                dropout_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                method TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_payment_id TEXT,
                pix_code TEXT,
                paid_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                reminder_date TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id),
                UNIQUE(student_id, reminder_date)
            );

            CREATE TABLE IF NOT EXISTS guardians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL UNIQUE,
                name TEXT,
                relationship TEXT,
                cpf TEXT,
                phone TEXT,
                secondary_phone TEXT,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS medical_infos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL UNIQUE,
                has_restriction TEXT NOT NULL DEFAULT 'nao',
                description TEXT,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cpf TEXT,
                phone TEXT NOT NULL,
                class_group TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teacher_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            );

            CREATE TABLE IF NOT EXISTS cash_flow_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'pix',
                amount REAL NOT NULL,
                entry_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            """
        connection.executescript(schema_sql)

        columns = table_columns(connection, "students")
        if "phone" not in columns:
            connection.execute("ALTER TABLE students ADD COLUMN phone TEXT")
            connection.execute("UPDATE students SET phone = email WHERE phone IS NULL")
        if "jiu_jitsu_start_date" not in columns:
            connection.execute("ALTER TABLE students ADD COLUMN jiu_jitsu_start_date TEXT")
        for column_name, column_type, default_value in [
            ("birth_date", "TEXT", None),
            ("cpf", "TEXT", None),
            ("address", "TEXT", None),
            ("neighborhood", "TEXT", None),
            ("city", "TEXT", None),
            ("modality", "TEXT", "'kid'"),
            ("authorization_signed", "TEXT", "'nao'"),
            ("scholarship_type", "TEXT", "'nao'"),
            ("student_status", "TEXT", "'ativo'"),
            ("dropout_date", "TEXT", None),
        ]:
            if column_name not in columns:
                default_sql = f" DEFAULT {default_value}" if default_value else ""
                connection.execute(
                    f"ALTER TABLE students ADD COLUMN {column_name} {column_type}{default_sql}"
                )
        guardian_columns = table_columns(connection, "guardians")
        if "secondary_phone" not in guardian_columns:
            connection.execute("ALTER TABLE guardians ADD COLUMN secondary_phone TEXT")
        teacher_columns = table_columns(connection, "teachers")
        if "cpf" not in teacher_columns:
            connection.execute("ALTER TABLE teachers ADD COLUMN cpf TEXT")
        cash_flow_columns = table_columns(connection, "cash_flow_entries")
        if "payment_method" not in cash_flow_columns:
            connection.execute(
                "ALTER TABLE cash_flow_entries ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'pix'"
            )
        if "notes" not in cash_flow_columns:
            connection.execute("ALTER TABLE cash_flow_entries ADD COLUMN notes TEXT")

        admin_username = getenv("ADMIN_USERNAME", "admin")
        admin_password = getenv("ADMIN_PASSWORD", "admin123")
        if IS_PRODUCTION and admin_password == DEFAULT_ADMIN_PASSWORD:
            raise RuntimeError("Defina ADMIN_PASSWORD forte antes de rodar em produção.")
        admin = connection.execute(
            "SELECT id FROM admins WHERE username = ?",
            (admin_username,),
        ).fetchone()
        if not admin:
            connection.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (admin_username, hash_password(admin_password)),
            )


@app.on_event("startup")
async def startup() -> None:
    init_database()
    app.state.reminder_task = asyncio.create_task(payment_reminder_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    reminder_task = getattr(app.state, "reminder_task", None)
    if reminder_task:
        reminder_task.cancel()


def fetch_student(username: str) -> Row:
    with get_connection() as connection:
        student = connection.execute(
            "SELECT * FROM students WHERE username = ?",
            (username,),
        ).fetchone()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return student


def public_student(student: Row) -> dict:
    with get_connection() as connection:
        training_days = connection.execute(
            """
            SELECT day, start_time, end_time
            FROM training_days
            WHERE student_id = ?
            ORDER BY id
            """,
            (student["id"],),
        ).fetchall()
        guardian = connection.execute(
            """
            SELECT name, relationship, cpf, phone, secondary_phone
            FROM guardians
            WHERE student_id = ?
            """,
            (student["id"],),
        ).fetchone()
        medical_info = connection.execute(
            """
            SELECT has_restriction, description
            FROM medical_infos
            WHERE student_id = ?
            """,
            (student["id"],),
        ).fetchone()
    return {
        "student_number": f"{student['id']:03d}",
        "username": student["username"],
        "phone": phone_for_display(student["phone"]),
        "full_name": student["full_name"],
        "age": student["age"],
        "birth_date": student["birth_date"] or "",
        "cpf": student["cpf"] or "",
        "address": student["address"] or "",
        "neighborhood": student["neighborhood"] or "",
        "city": student["city"] or "",
        "modality": student["modality"],
        "jiu_jitsu_start_date": student["jiu_jitsu_start_date"] or "",
        "monthly_fee": student["monthly_fee"],
        "payment_day": student["payment_day"],
        "pix_key": PIX_KEY,
        "academy_whatsapp": ACADEMY_WHATSAPP_DISPLAY,
        "academy_whatsapp_url": academy_whatsapp_link(),
        "payment_status": student["payment_status"],
        "authorization_signed": student["authorization_signed"],
        "scholarship_type": student["scholarship_type"],
        "student_status": student["student_status"],
        "dropout_date": student["dropout_date"] or "",
        "guardian": {
            **dict(guardian),
            "phone": phone_for_display(guardian["phone"]),
            "secondary_phone": phone_for_display(guardian["secondary_phone"]),
        } if guardian else {},
        "medical_info": dict(medical_info) if medical_info else {},
        "training_days": [dict(item) for item in training_days],
    }


def normalize_whatsapp_phone(phone: str) -> str:
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) in (10, 11):
        return f"55{digits}"
    return digits


def phone_for_display(phone: str | None) -> str:
    if not phone or "@" in phone:
        return ""
    return phone


def whatsapp_link(phone: str, body: str) -> str:
    from urllib.parse import quote

    normalized_phone = normalize_whatsapp_phone(phone)
    return f"https://wa.me/{normalized_phone}?text={quote(body)}"


def academy_whatsapp_link() -> str:
    return f"https://wa.me/{normalize_whatsapp_phone(ACADEMY_WHATSAPP)}"


def send_whatsapp(to_phone: str, body: str) -> bool:
    normalized_phone = normalize_whatsapp_phone(to_phone)
    if len(normalized_phone) < 12:
        print("\n--- WHATSAPP COM CELULAR INVALIDO ---")
        print(f"Celular cadastrado: {mask_phone(to_phone)}")
        print("-------------------------------------\n")
        return False

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        print("\n--- WHATSAPP SEM API CONFIGURADA ---")
        print(f"Para: {mask_phone(normalized_phone)}")
        print("Mensagem pronta para envio pelo painel administrativo.")
        print("------------------------------------\n")
        return False

    response = httpx.post(
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
        headers={
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        },
        timeout=20,
    )

    if response.status_code >= 400:
        print("\n--- ERRO AO ENVIAR WHATSAPP ---")
        print(response.status_code)
        print("Falha retornada pelo provedor de WhatsApp.")
        print("-------------------------------\n")
        return False
    return True


def build_payment_reminder_message(student: Row, reminder_type: str = "due") -> str:
    if reminder_type == "before":
        intro = "Passando para lembrar que amanhã é o dia de pagamento da mensalidade de Jiu-Jitsu."
    else:
        intro = "Hoje é o dia de pagamento da mensalidade de Jiu-Jitsu."

    return (
        f"Olá, {student['full_name']}.\n\n"
        f"{intro}\n"
        f"Valor: R$ {student['monthly_fee']:.2f}\n"
        f"Chave Pix: {PIX_KEY}\n\n"
        "Depois de pagar, envie o comprovante para a equipe da academia."
    )


def reminder_contact(student: Row, guardian: Row | None) -> tuple[str, str]:
    if student["age"] < 18 and guardian:
        guardian_phone = phone_for_display(guardian["phone"])
        secondary_phone = phone_for_display(guardian["secondary_phone"])
        if guardian_phone:
            return guardian_phone, guardian["name"] or "Responsável"
        if secondary_phone:
            return secondary_phone, guardian["name"] or "Responsável"
    return phone_for_display(student["phone"]), student["full_name"]


def send_due_payment_reminders() -> dict:
    today = datetime.now().date()
    today_text = today.isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    last_month_day = monthrange(today.year, today.month)[1]
    sent_count = 0
    failed_count = 0

    with get_connection() as connection:
        students = connection.execute(
            """
            SELECT students.*
            FROM students
            LEFT JOIN email_reminders
                ON email_reminders.student_id = students.id
                AND email_reminders.reminder_date = ?
            WHERE students.payment_status = 'pendente'
                AND students.student_status = 'ativo'
                AND email_reminders.id IS NULL
            """,
            (today_text,),
        ).fetchall()

        for student in students:
            due_day = min(student["payment_day"], last_month_day)
            if due_day != today.day:
                continue

            guardian = connection.execute(
                "SELECT name, phone, secondary_phone FROM guardians WHERE student_id = ?",
                (student["id"],),
            ).fetchone()
            contact_phone, _ = reminder_contact(student, guardian)
            body = build_payment_reminder_message(student)
            if not contact_phone or not send_whatsapp(contact_phone, body):
                failed_count += 1
                continue

            connection.execute(
                """
                INSERT INTO email_reminders (student_id, reminder_date, sent_at)
                VALUES (?, ?, ?)
                """,
                (student["id"], today_text, now),
            )
            sent_count += 1

    return {"sent": sent_count, "failed": failed_count, "date": today_text}


def build_admin_payment_reminder_links(reminder_type: str) -> dict:
    today = datetime.now().date()
    target_date = today + timedelta(days=1) if reminder_type == "before" else today
    last_month_day = monthrange(target_date.year, target_date.month)[1]
    target_day = min(target_date.day, last_month_day)
    links = []
    skipped = 0

    with get_connection() as connection:
        students = connection.execute(
            """
            SELECT *
            FROM students
            WHERE payment_status = 'pendente'
                AND student_status = 'ativo'
            ORDER BY full_name
            """
        ).fetchall()

        for student in students:
            due_day = min(student["payment_day"], last_month_day)
            if due_day != target_day:
                continue

            guardian = connection.execute(
                "SELECT name, phone, secondary_phone FROM guardians WHERE student_id = ?",
                (student["id"],),
            ).fetchone()
            contact_phone, contact_name = reminder_contact(student, guardian)
            if not contact_phone:
                skipped += 1
                continue

            body = build_payment_reminder_message(student, reminder_type)
            links.append({
                "student_number": f"{student['id']:03d}",
                "student_name": student["full_name"],
                "contact_name": contact_name,
                "phone": contact_phone,
                "due_day": student["payment_day"],
                "url": whatsapp_link(contact_phone, body),
            })

    return {
        "date": target_date.isoformat(),
        "reminder_type": reminder_type,
        "links": links,
        "skipped": skipped,
    }


async def payment_reminder_loop() -> None:
    while True:
        try:
            send_due_payment_reminders()
        except Exception as exc:
            print(f"Erro ao enviar lembretes automaticos: {exc}")
        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


async def create_provider_pix_payment(student: Row, amount: float) -> dict:
    if not MERCADO_PAGO_ACCESS_TOKEN:
        return {
            "provider": "manual",
            "provider_payment_id": None,
            "pix_code": PIX_KEY,
            "status": "pendente",
        }

    payload = {
        "transaction_amount": amount,
        "description": f"Mensalidade Jiu-Jitsu - {student['full_name']}",
        "payment_method_id": "pix",
        "payer": {"email": student["email"] or "pagamento@jiujitsu.local"},
    }
    headers = {
        "Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}",
        "X-Idempotency-Key": f"{student['username']}-{datetime.now(timezone.utc).timestamp()}",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.mercadopago.com/v1/payments",
            json=payload,
            headers=headers,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail="Nao foi possivel criar cobranca Pix no provedor.",
        )

    data = response.json()
    transaction_data = data.get("point_of_interaction", {}).get("transaction_data", {})
    return {
        "provider": "mercado_pago",
        "provider_payment_id": str(data.get("id")),
        "pix_code": transaction_data.get("qr_code") or PIX_KEY,
        "status": data.get("status", "pending"),
    }


@app.get("/")
def health_check() -> dict:
    return {
        "message": "API do sistema de Jiu-Jitsu funcionando",
        "academy_whatsapp": ACADEMY_WHATSAPP_DISPLAY,
        "academy_whatsapp_url": academy_whatsapp_link(),
    }


@app.post("/students", status_code=201)
def create_student(student: StudentCreate, request: Request) -> dict:
    enforce_rate_limit(f"register:{client_ip(request)}", REGISTER_RATE_LIMIT)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as connection:
        username_exists = connection.execute(
            "SELECT id FROM students WHERE lower(username) = lower(?)",
            (student.username,),
        ).fetchone()
        normalized_phone = normalize_whatsapp_phone(student.phone)
        phone_exists = connection.execute(
            "SELECT id FROM students WHERE phone = ?",
            (normalized_phone,),
        ).fetchone()

        if username_exists:
            raise HTTPException(status_code=400, detail="Dados de cadastro já estão em uso.")
        if phone_exists:
            raise HTTPException(status_code=400, detail="Dados de cadastro já estão em uso.")

        student_id = insert_returning_id(
            connection,
            """
            INSERT INTO students (
                username, phone, email, password_hash, full_name, age,
                birth_date, cpf, address, neighborhood, city, modality,
                jiu_jitsu_start_date, monthly_fee,
                payment_day, payment_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                student.username,
                normalized_phone,
                f"{normalized_phone}@phone.local",
                hash_password(student.password),
                student.full_name,
                student.age,
                student.birth_date,
                student.cpf,
                student.address,
                student.neighborhood,
                student.city,
                student.modality,
                student.jiu_jitsu_start_date,
                student.monthly_fee,
                student.payment_day,
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO training_days (student_id, day, start_time, end_time)
            VALUES (?, ?, ?, ?)
            """,
            [
                (student_id, item.day, item.start_time, item.end_time)
                for item in student.training_days
            ],
        )
        connection.execute(
            """
            INSERT INTO guardians (student_id, name, relationship, cpf, phone, secondary_phone)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                student_id,
                student.guardian_name,
                student.guardian_relationship,
                student.guardian_cpf,
                normalize_whatsapp_phone(student.guardian_phone),
                normalize_whatsapp_phone(student.guardian_secondary_phone),
            ),
        )
        connection.execute(
            """
            INSERT INTO medical_infos (student_id, has_restriction, description)
            VALUES (?, ?, ?)
            """,
            (
                student_id,
                student.medical_restriction,
                student.medical_restriction_description,
            ),
        )
    return {"message": "Aluno cadastrado com sucesso."}


@app.post("/login")
def login(login_data: LoginRequest, request: Request) -> dict:
    enforce_rate_limit(f"login:{client_ip(request)}", LOGIN_RATE_LIMIT)
    with get_connection() as connection:
        student = connection.execute(
            "SELECT username, password_hash FROM students WHERE lower(username) = lower(?)",
            (login_data.username,),
        ).fetchone()
        admin = connection.execute(
            "SELECT username, password_hash FROM admins WHERE lower(username) = lower(?)",
            (login_data.username,),
        ).fetchone()

    if student and verify_password(login_data.password, student["password_hash"]):
        return {
            "access_token": create_token(student["username"], "student"),
            "token_type": "bearer",
            "role": "student",
        }

    if admin and verify_password(login_data.password, admin["password_hash"]):
        return {
            "access_token": create_token(admin["username"], "admin"),
            "token_type": "bearer",
            "role": "admin",
        }

    raise HTTPException(status_code=401, detail="Usuario ou senha invalidos.")


@app.get("/me")
def get_profile(payload: Annotated[dict, Depends(require_student)]) -> dict:
    return public_student(fetch_student(payload["sub"]))


@app.post("/payments/pix")
async def create_pix_payment(
    payment: PaymentCreate,
    payload: Annotated[dict, Depends(require_student)],
) -> dict:
    student = fetch_student(payload["sub"])
    provider_result = await create_provider_pix_payment(student, payment.amount)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO payments (
                student_id, amount, status, method, provider,
                provider_payment_id, pix_code, created_at
            )
            VALUES (?, ?, ?, 'pix', ?, ?, ?, ?)
            """,
            (
                student["id"],
                payment.amount,
                provider_result["status"],
                provider_result["provider"],
                provider_result["provider_payment_id"],
                provider_result["pix_code"],
                now,
            ),
        )

    return {
        "message": "Cobranca Pix criada.",
        "pix_code": provider_result["pix_code"],
        "status": provider_result["status"],
        "provider": provider_result["provider"],
    }


@app.post("/payments")
def create_manual_payment(
    payment: PaymentCreate,
    payload: Annotated[dict, Depends(require_student)],
) -> dict:
    student = fetch_student(payload["sub"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute(
            "UPDATE students SET payment_status = 'pago' WHERE id = ?",
            (student["id"],),
        )
        connection.execute(
            """
            INSERT INTO payments (
                student_id, amount, status, method, provider, pix_code, paid_at, created_at
            )
            VALUES (?, ?, 'pago', 'pix', 'manual', ?, ?, ?)
            """,
            (student["id"], payment.amount, PIX_KEY, now, now),
        )

    return {"message": "Pagamento registrado."}


@app.get("/admin/students")
def list_students(_: Annotated[dict, Depends(require_admin)]) -> list[dict]:
    with get_connection() as connection:
        students = connection.execute(
            """
            SELECT
                id,
                username,
                phone,
                full_name,
                age,
                modality,
                monthly_fee,
                payment_day,
                payment_status,
                authorization_signed,
                scholarship_type,
                student_status
            FROM students
            WHERE student_status = 'ativo'
            ORDER BY full_name
            """
        ).fetchall()
    return [
        {
            **dict(student),
            "student_number": f"{student['id']:03d}",
            "phone": phone_for_display(student["phone"]),
        }
        for student in students
    ]


@app.get("/admin/students/{username}")
def get_student_details(
    username: str,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    return public_student(fetch_student(username))


@app.get("/admin/payments")
def list_payments(_: Annotated[dict, Depends(require_admin)]) -> list[dict]:
    with get_connection() as connection:
        payments = connection.execute(
            """
            SELECT
                payments.id,
                students.full_name,
                students.username,
                payments.amount,
                payments.status,
                payments.method,
                payments.provider,
                payments.created_at,
                payments.paid_at
            FROM payments
            JOIN students ON students.id = payments.student_id
            ORDER BY payments.id DESC
            """
        ).fetchall()
    return [dict(payment) for payment in payments]


@app.get("/admin/cash-flow")
def list_cash_flow(
    _: Annotated[dict, Depends(require_admin)],
    month: str = Query(default=""),
) -> dict:
    selected_month = month or datetime.now().date().isoformat()[:7]
    with get_connection() as connection:
        entries = connection.execute(
            """
            SELECT
                id,
                entry_type,
                description,
                category,
                payment_method,
                amount,
                entry_date,
                notes,
                created_at
            FROM cash_flow_entries
            WHERE substr(entry_date, 1, 7) = ?
            ORDER BY entry_date DESC, id DESC
            """,
            (selected_month,),
        ).fetchall()
        totals = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN entry_type = 'entrada' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN entry_type = 'saida' THEN amount ELSE 0 END), 0) AS expense
            FROM cash_flow_entries
            WHERE substr(entry_date, 1, 7) = ?
            """,
            (selected_month,),
        ).fetchone()

    income = totals["income"]
    expense = totals["expense"]
    return {
        "summary": {
            "income": income,
            "expense": expense,
            "balance": income - expense,
        },
        "month": selected_month,
        "entries": [dict(entry) for entry in entries],
    }


@app.post("/admin/cash-flow", status_code=201)
def create_cash_flow_entry(
    entry: CashFlowCreate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    today = datetime.now().date().isoformat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry_date = entry.entry_date or today

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO cash_flow_entries (
                entry_type,
                description,
                category,
                payment_method,
                amount,
                entry_date,
                notes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.entry_type,
                entry.description,
                entry.category or "geral",
                entry.payment_method,
                entry.amount,
                entry_date,
                entry.notes,
                now,
            ),
        )
    return {"message": "Lançamento registrado."}


@app.delete("/admin/cash-flow/{entry_id}")
def delete_cash_flow_entry(
    entry_id: int,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM cash_flow_entries WHERE id = ?", (entry_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
    return {"message": "Lançamento excluído."}


@app.get("/admin/dropouts")
def list_dropout_students(_: Annotated[dict, Depends(require_admin)]) -> list[dict]:
    with get_connection() as connection:
        students = connection.execute(
            """
            SELECT id, username, full_name, phone, modality, dropout_date
            FROM students
            WHERE student_status = 'desistente'
            ORDER BY dropout_date DESC, full_name
            """
        ).fetchall()
    return [
        {
            **dict(student),
            "student_number": f"{student['id']:03d}",
            "phone": phone_for_display(student["phone"]),
        }
        for student in students
    ]


@app.patch("/admin/students/{username}/admin-info")
def update_student_admin_info(
    username: str,
    update: StudentAdminUpdate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE students
            SET authorization_signed = ?, scholarship_type = ?
            WHERE username = ?
            """,
            (update.authorization_signed, update.scholarship_type, username),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return {"message": "Dados administrativos atualizados."}


@app.patch("/admin/students/{username}/dropout")
def mark_student_dropout(
    username: str,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    today = datetime.now().date().isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE students
            SET student_status = 'desistente', dropout_date = ?
            WHERE username = ?
            """,
            (today, username),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return {"message": "Aluno marcado como desistente."}


@app.patch("/admin/students/{username}/reactivate")
def reactivate_student(
    username: str,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE students
            SET student_status = 'ativo', dropout_date = NULL
            WHERE username = ?
            """,
            (username,),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return {"message": "Aluno reativado."}


@app.get("/admin/teachers")
def list_teachers(_: Annotated[dict, Depends(require_admin)]) -> list[dict]:
    with get_connection() as connection:
        teachers = connection.execute(
            """
            SELECT id, name, cpf, phone, class_group, created_at
            FROM teachers
            ORDER BY name
            """
        ).fetchall()
        schedules = connection.execute(
            """
            SELECT teacher_id, day, start_time, end_time
            FROM teacher_schedules
            ORDER BY id
            """
        ).fetchall()

    schedules_by_teacher: dict[int, list[dict]] = {}
    for schedule in schedules:
        schedules_by_teacher.setdefault(schedule["teacher_id"], []).append({
            "day": schedule["day"],
            "start_time": schedule["start_time"],
            "end_time": schedule["end_time"],
        })

    return [
        {
            **dict(teacher),
            "phone": phone_for_display(teacher["phone"]),
            "schedule": schedules_by_teacher.get(teacher["id"], []),
        }
        for teacher in teachers
    ]


@app.post("/admin/teachers", status_code=201)
def create_teacher(
    teacher: TeacherCreate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as connection:
        teacher_id = insert_returning_id(
            connection,
            """
            INSERT INTO teachers (name, cpf, phone, class_group, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                teacher.name,
                teacher.cpf,
                normalize_whatsapp_phone(teacher.phone),
                teacher.class_group,
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO teacher_schedules (teacher_id, day, start_time, end_time)
            VALUES (?, ?, ?, ?)
            """,
            [
                (teacher_id, item.day, item.start_time, item.end_time)
                for item in teacher.schedule
            ],
        )
    return {"message": "Professor cadastrado."}


@app.delete("/admin/teachers/{teacher_id}")
def delete_teacher(
    teacher_id: int,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        connection.execute("DELETE FROM teacher_schedules WHERE teacher_id = ?", (teacher_id,))
        cursor = connection.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Professor nao encontrado.")
    return {"message": "Professor excluido."}


@app.post("/admin/payment-reminders/run")
def run_payment_reminders(_: Annotated[dict, Depends(require_admin)]) -> dict:
    result = send_due_payment_reminders()
    return {
        "message": "Verificacao de lembretes concluida.",
        **result,
    }


@app.get("/admin/payment-reminders/whatsapp-links")
def get_payment_reminder_links(
    _: Annotated[dict, Depends(require_admin)],
    reminder_type: str = "due",
) -> dict:
    if reminder_type not in ("before", "due"):
        raise HTTPException(status_code=400, detail="Tipo de lembrete invalido.")
    return build_admin_payment_reminder_links(reminder_type)


@app.patch("/admin/students/{username}/payment-status")
def update_payment_status(
    username: str,
    status_update: PaymentStatusUpdate,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE students SET payment_status = ? WHERE username = ?",
            (status_update.payment_status, username),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return {"message": "Status atualizado."}


@app.delete("/admin/students/{username}")
def delete_student(
    username: str,
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    with get_connection() as connection:
        student = connection.execute(
            "SELECT id FROM students WHERE username = ?",
            (username,),
        ).fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="Aluno nao encontrado.")

        student_id = student["id"]
        connection.execute("DELETE FROM email_reminders WHERE student_id = ?", (student_id,))
        connection.execute("DELETE FROM payments WHERE student_id = ?", (student_id,))
        connection.execute("DELETE FROM training_days WHERE student_id = ?", (student_id,))
        connection.execute("DELETE FROM guardians WHERE student_id = ?", (student_id,))
        connection.execute("DELETE FROM medical_infos WHERE student_id = ?", (student_id,))
        connection.execute("DELETE FROM students WHERE id = ?", (student_id,))

    return {"message": "Aluno excluido com sucesso."}


@app.post("/payments/webhook")
async def payment_webhook(request: Request) -> dict:
    data = await request.json()
    payment_id = str(data.get("data", {}).get("id") or data.get("id") or "")
    if not payment_id:
        return {"message": "Webhook recebido sem pagamento."}

    if MERCADO_PAGO_ACCESS_TOKEN:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}"},
            )
        if response.status_code < 400:
            provider_payment = response.json()
            status = provider_payment.get("status", "pending")
            if status == "approved":
                with get_connection() as connection:
                    payment = connection.execute(
                        "SELECT student_id FROM payments WHERE provider_payment_id = ?",
                        (payment_id,),
                    ).fetchone()
                    if payment:
                        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                        connection.execute(
                            "UPDATE payments SET status = 'pago', paid_at = ? WHERE provider_payment_id = ?",
                            (now, payment_id),
                        )
                        connection.execute(
                            "UPDATE students SET payment_status = 'pago' WHERE id = ?",
                            (payment["student_id"],),
                        )

    return {"message": "Webhook processado."}
