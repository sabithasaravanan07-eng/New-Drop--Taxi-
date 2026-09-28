import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "senthurmurugan.db")
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["DATABASE"] = os.environ.get("DATABASE_PATH", DATABASE)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)


class DatabaseConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        query = query.replace("?", "%s")
        query = query.replace("date('now', 'localtime')", "CURRENT_DATE")
        cursor = self.connection.cursor()
        cursor.execute(query, parameters)
        return cursor

    def executescript(self, script):
        script = script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        cursor = self.connection.cursor()
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)

    def executemany(self, query, parameter_list):
        query = query.replace("?", "%s")
        cursor = self.connection.cursor()
        cursor.executemany(query, parameter_list)
        return cursor

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def get_db():
    if "db" not in g:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            g.db = DatabaseConnection(psycopg2.connect(database_url, cursor_factory=DictCursor))
        elif os.environ.get("SUPABASE_DB_PASSWORD"):
            g.db = DatabaseConnection(psycopg2.connect(
                host=os.environ["SUPABASE_DB_HOST"],
                port=os.environ.get("SUPABASE_DB_PORT", "5432"),
                database=os.environ.get("SUPABASE_DB_NAME", "postgres"),
                user=os.environ["SUPABASE_DB_USER"],
                password=os.environ["SUPABASE_DB_PASSWORD"],
                cursor_factory=DictCursor,
            ))
        else:
            supabase_variables = ("SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD")
            if any(os.environ.get(key) for key in supabase_variables):
                missing = [key for key in supabase_variables if not os.environ.get(key)]
                raise RuntimeError(f"Missing Supabase database configuration: {', '.join(missing)}")
            if os.environ.get("VERCEL") == "1":
                raise RuntimeError("Configure DATABASE_URL or the SUPABASE_DB_* variables for persistent storage.")
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def settings_columns():
    db = get_db()
    if isinstance(db, DatabaseConnection):
        columns = {
            row[0]
            for row in db.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ?"
            , ("settings",)).fetchall()
        }
    else:
        columns = {row[1] for row in db.execute("PRAGMA table_info(settings)").fetchall()}
    if {"key", "value"}.issubset(columns):
        return "key", "value"
    if {"setting_key", "setting_value"}.issubset(columns):
        return "setting_key", "setting_value"
    raise RuntimeError("The settings table must contain key/value or setting_key/setting_value columns.")


def legacy_admins_exist(db):
    if isinstance(db, DatabaseConnection):
        return bool(db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?",
            ("admin_users",),
        ).fetchone())
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("admin_users",),
    ).fetchone())


def template_rows(rows):
    converted = []
    for row in rows:
        item = dict(row)
        for field in ("pickup_date", "created_at"):
            value = item.get(field)
            if isinstance(value, str):
                try:
                    item[field] = datetime.fromisoformat(value)
                except ValueError:
                    pass
        converted.append(item)
    return converted


def route_default_image(route_name="", pickup_city="", drop_city=""):
    text = f"{route_name} {pickup_city} {drop_city}".lower()
    if any(keyword in text for keyword in [
        "madurai", "thiruvannamalai", "trichy", "thanjavur", "kumbakonam",
        "rameswaram", "kanyakumari", "tiruchendur", "kanchipuram", "palani",
        "temple", "murugan"
    ]):
        return "/static/img/route-temple.jpg?v=3"
    if any(keyword in text for keyword in [
        "cuddalore", "chennai", "mahabalipuram", "puducherry", "beach", "coast",
        "sea", "harbor", "shore"
    ]):
        return "/static/img/route-coast.jpg?v=3"
    if any(keyword in text for keyword in [
        "ooty", "kodaikanal", "yercaud", "yelagiri", "nilgiris", "coimbatore",
        "hills", "hill", "mountain"
    ]):
        return "/static/img/route-hills.jpg?v=3"
    return "/static/img/route-city.jpg?v=3"


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT 'Administrator'
        );
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            car_type TEXT NOT NULL,
            seats INTEGER NOT NULL DEFAULT 4,
            price_per_km REAL NOT NULL DEFAULT 12,
            base_fare REAL NOT NULL DEFAULT 500,
            ac INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            pickup_location TEXT NOT NULL,
            drop_location TEXT NOT NULL,
            pickup_date TEXT NOT NULL,
            pickup_time TEXT NOT NULL,
            return_date TEXT,
            trip_type TEXT NOT NULL,
            car_id INTEGER,
            passengers INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            trip_route TEXT,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS route_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_name TEXT NOT NULL,
            pickup_city TEXT NOT NULL,
            drop_city TEXT NOT NULL,
            duration_text TEXT NOT NULL,
            distance_km INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            image_url TEXT NOT NULL DEFAULT ''
        );
        """
    )
    if legacy_admins_exist(db):
        db.execute(
            """INSERT INTO admins(username, password_hash, display_name)
            SELECT username, password_hash, COALESCE(full_name, 'Administrator')
            FROM admin_users
            WHERE password_hash NOT LIKE '%placeholder%'
            ON CONFLICT (username) DO NOTHING"""
        )
    if os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_PASSWORD"):
        db.execute("ALTER TABLE route_prices ADD COLUMN IF NOT EXISTS image_url TEXT NOT NULL DEFAULT ''")
    else:
        route_columns = {row[1] for row in db.execute("PRAGMA table_info(route_prices)").fetchall()}
        if "image_url" not in route_columns:
            db.execute("ALTER TABLE route_prices ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
    defaults = {
        "business_name": "New Drop Taxi",
        "owner_name": "T. Dhinesh",
        "mobile_number": "9600641848",
        "whatsapp_number": "9600641848",
        "service_area": "Tamil Nadu",
        "email": "",
        "address": "Tamil Nadu, India",
        "tagline": "Reliable outstation drop cab service",
    }
    key_column, value_column = settings_columns()
    db.executemany(
        f"INSERT INTO settings({key_column}, {value_column}) VALUES (?, ?) ON CONFLICT ({key_column}) DO NOTHING",
        defaults.items(),
    )
    db.execute(
        f"UPDATE settings SET {value_column} = ? WHERE {key_column} = ? AND {value_column} = ?",
        ("New Drop Taxi", "business_name", "SD Travels"),
    )
    initial_password = os.environ.get("ADMIN_INITIAL_PASSWORD", "admin123")
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO admins(username, password_hash, display_name) VALUES (?, ?, ?)",
            (admin_username, generate_password_hash(initial_password), os.environ.get("ADMIN_DISPLAY_NAME", "Administrator")),
        )
    if db.execute("SELECT COUNT(*) FROM cars").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO cars(name, car_type, seats, price_per_km, base_fare, ac) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Swift Dzire", "Sedan", 4, 12, 500, 1),
                ("Toyota Innova", "SUV", 7, 18, 800, 1),
                ("Tempo Traveller", "Van", 12, 25, 1200, 1),
            ],
        )
    if db.execute("SELECT COUNT(*) FROM route_prices").fetchone()[0] == 0:
        seeded_routes = [
            ("Chennai to Bangalore", "Chennai", "Bangalore", "6-7 hours", 350, 5590, 1),
            ("Chennai to Coimbatore", "Chennai", "Coimbatore", "8-9 hours", 500, 8020, 2),
            ("Chennai to Madurai", "Chennai", "Madurai", "7-8 hours", 460, 7337, 3),
            ("Chennai to Cuddalore", "Chennai", "Cuddalore", "3-4 hours", 170, 3332, 4),
            ("Chennai to Thiruvannamalai", "Chennai", "Thiruvannamalai", "3-4 hours", 190, 3600, 5),
            ("Chennai to Trichy", "Chennai", "Trichy", "4-5 hours", 220, 4150, 6),
            ("Coimbatore to Madurai", "Coimbatore", "Madurai", "5-6 hours", 245, 4625, 7),
            ("Bangalore to Chennai", "Bangalore", "Chennai", "6-7 hours", 350, 5850, 8),
            ("Madurai to Chennai", "Madurai", "Chennai", "7-8 hours", 460, 7480, 9),
        ]
        db.executemany(
            "INSERT INTO route_prices(route_name, pickup_city, drop_city, duration_text, distance_km, price, sort_order, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (*route, route_default_image(route[0], route[1], route[2]))
                for route in seeded_routes
            ],
        )
    if db.execute(
        "SELECT COUNT(*) FROM route_prices WHERE pickup_city = ? AND drop_city = ?",
        ("Chennai", "Thiruvannamalai"),
    ).fetchone()[0] == 0:
        next_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM route_prices").fetchone()[0]
        db.execute(
            "INSERT INTO route_prices(route_name, pickup_city, drop_city, duration_text, distance_km, price, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Chennai to Thiruvannamalai", "Chennai", "Thiruvannamalai", "3-4 hours", 190, 3600, next_order),
        )
    db.commit()


def setting(key):
    key_column, value_column = settings_columns()
    row = get_db().execute(
        f"SELECT {value_column} FROM settings WHERE {key_column} = ?", (key,)
    ).fetchone()
    return row[value_column] if row else ""


@app.context_processor
def inject_site_data():
    mobile = (setting("mobile_number") or "9600641848").strip() or "9600641848"
    whatsapp = (setting("whatsapp_number") or mobile).strip() or mobile
    return {
        "biz": {
            "name": setting("business_name"),
            "owner": setting("owner_name"),
            "mobile": mobile,
            "call_number": mobile,
            "whatsapp": whatsapp,
            "area": setting("service_area"),
            "email": setting("email"),
            "address": setting("address"),
            "tagline": setting("tagline"),
        },
        "current_year": datetime.now().year,
        "current_date": date.today().isoformat(),
    }


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in to access the admin panel.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def form_value(name, default=""):
    return request.form.get(name, default).strip()


def safe_next_url(value):
    if not value:
        return None
    parsed = urlparse(value or "")
    return value if not parsed.netloc and not parsed.scheme and value.startswith("/") else None

@app.route("/")
def index():
    db = get_db()
    stats = {
        "total_bookings": db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
        "active_cars": db.execute("SELECT COUNT(*) FROM cars WHERE status = 'active'").fetchone()[0],
    }
    reviews = template_rows(db.execute("SELECT * FROM reviews WHERE status = 'approved' ORDER BY created_at DESC LIMIT 3").fetchall())
    cars = db.execute("SELECT * FROM cars WHERE status = 'active' ORDER BY name").fetchall()
    routes = popular_routes()
    return render_template("index.html", stats=stats, reviews=reviews, cars=cars, routes=routes)


@app.route("/booking", methods=["GET", "POST"])
def booking():
    db = get_db()
    if request.method == "POST":
        required = ["customer_name", "phone", "pickup_location", "drop_location", "pickup_date", "pickup_time"]
        if any(not form_value(field) for field in required):
            flash("Please complete all required booking fields.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        try:
            pickup_date = date.fromisoformat(form_value("pickup_date"))
            passengers = max(1, min(20, int(form_value("passengers", "1"))))
            car_id = int(form_value("car_id")) if form_value("car_id") else None
        except (ValueError, TypeError):
            flash("Please provide a valid date, passenger count, and car.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        if pickup_date < date.today():
            flash("Pickup date cannot be in the past.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        if form_value("email") and "@" not in form_value("email"):
            flash("Please provide a valid email address.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        if not re.fullmatch(r"[0-9+() .-]{7,20}", form_value("phone")):
            flash("Please provide a valid phone number.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        if car_id is not None and not get_db().execute("SELECT 1 FROM cars WHERE id = ? AND status = 'active'", (car_id,)).fetchone():
            flash("Please select an available vehicle.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        try:
            db.execute(
                """INSERT INTO bookings
                (customer_name, phone, email, pickup_location, drop_location, pickup_date, pickup_time,
                 return_date, trip_type, car_id, passengers, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    form_value("customer_name"), form_value("phone"), form_value("email"),
                    form_value("pickup_location"), form_value("drop_location"), pickup_date.isoformat(),
                    form_value("pickup_time"), form_value("return_date") or None, form_value("trip_type", "one_way"),
                    car_id, passengers, form_value("notes"),
                ),
            )
            db.commit()
            booking_row = db.execute(
                "SELECT id FROM bookings WHERE customer_name = ? AND phone = ? ORDER BY id DESC LIMIT 1",
                (form_value("customer_name"), form_value("phone")),
            ).fetchone()
        except Exception:
            db.connection.rollback() if hasattr(db, "connection") else db.rollback()
            app.logger.exception("Booking persistence failed")
            flash("We could not save your booking right now. Please try again or call us.", "error")
            return render_template("booking.html", cars=active_cars(), form=request.form)
        booking_reference = f"SD-{booking_row[0]:06d}" if booking_row else "SD-PENDING"
        flash(f"Booking request received. Your reference is {booking_reference}.", "success")
        return redirect(url_for("booking"))
    return render_template("booking.html", cars=active_cars(), form={})


def active_cars():
    return get_db().execute("SELECT * FROM cars WHERE status = 'active' ORDER BY name").fetchall()


def popular_routes():
    return get_db().execute(
        "SELECT * FROM route_prices WHERE is_active = 1 ORDER BY sort_order, id"
    ).fetchall()


@app.route("/contact", methods=["POST"])
def contact():
    required = ("customer_name", "phone", "message")
    if any(not form_value(field) for field in required):
        flash("Please complete your name, phone number, and message.", "error")
        return redirect(url_for("index") + "#contact")
    if not re.fullmatch(r"[0-9+() .-]{7,20}", form_value("phone")):
        flash("Please provide a valid phone number.", "error")
        return redirect(url_for("index") + "#contact")
    db = get_db()
    db.execute(
        "INSERT INTO contact_messages(customer_name, phone, email, message) VALUES (?, ?, ?, ?)",
        (form_value("customer_name"), form_value("phone"), form_value("email"), form_value("message")),
    )
    db.commit()
    flash("Your message was sent. We will get back to you shortly.", "success")
    return redirect(url_for("index") + "#contact")


@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    db = get_db()
    if request.method == "POST":
        try:
            rating = int(form_value("rating", "5"))
        except ValueError:
            rating = 0
        if not form_value("customer_name") or not form_value("message") or rating not in range(1, 6):
            flash("Please provide your name, review, and a rating from 1 to 5.", "error")
        else:
            db.execute(
                "INSERT INTO reviews(customer_name, trip_route, rating, message) VALUES (?, ?, ?, ?)",
                (form_value("customer_name"), form_value("trip_route"), rating, form_value("message")),
            )
            db.commit()
            flash("Thank you. Your review will appear after approval.", "success")
            return redirect(url_for("reviews"))
    rows = template_rows(db.execute("SELECT * FROM reviews WHERE status = 'approved' ORDER BY created_at DESC").fetchall())
    total = len(rows)
    average = round(sum(row["rating"] for row in rows) / total, 1) if total else 0
    breakdown = {star: sum(row["rating"] == star for row in rows) for star in range(5, 0, -1)}
    return render_template("reviews.html", reviews=rows, total=total, avg_rating=average, breakdown=breakdown)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        admin = get_db().execute("SELECT * FROM admins WHERE username = ?", (form_value("username"),)).fetchone()
        if admin and check_password_hash(admin["password_hash"], request.form.get("password", "")):
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["display_name"]
            return redirect(safe_next_url(request.args.get("next")) or url_for("admin_dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def today_date_sql():
    if os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_PASSWORD"):
        return "CURRENT_DATE::text"
    return "date('now')"


def dashboard_stats():
    db = get_db()
    row = db.execute(
        f"""SELECT COUNT(*) AS total_bookings,
        SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed_bookings,
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_bookings,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_bookings,
        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_bookings,
        SUM(CASE WHEN pickup_date = {today_date_sql()} THEN 1 ELSE 0 END) AS today_bookings
        FROM bookings"""
    ).fetchone()
    stats = dict(row)
    stats["pending_reviews"] = db.execute("SELECT COUNT(*) FROM reviews WHERE status = 'pending'").fetchone()[0]
    return stats


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    recent_bookings = template_rows(db.execute("""SELECT b.*, c.name AS car_name FROM bookings b
        LEFT JOIN cars c ON c.id = b.car_id ORDER BY b.created_at DESC LIMIT 8""").fetchall())
    recent_reviews = template_rows(db.execute("SELECT * FROM reviews ORDER BY created_at DESC LIMIT 8").fetchall())
    return render_template("admin_dashboard.html", stats=dashboard_stats(), recent_bookings=recent_bookings, recent_reviews=recent_reviews)


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    status_filter = request.args.get("status", "")
    search = request.args.get("q", "").strip()
    query = "SELECT b.*, c.name AS car_name FROM bookings b LEFT JOIN cars c ON c.id = b.car_id"
    params = []
    conditions = []
    if status_filter in {"pending", "confirmed", "completed", "cancelled"}:
        conditions.append("b.status = ?")
        params.append(status_filter)
    if search:
        conditions.append("(b.customer_name LIKE ? OR b.phone LIKE ? OR b.pickup_location LIKE ? OR b.drop_location LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY b.pickup_date, b.pickup_time, b.created_at DESC"
    bookings = template_rows(get_db().execute(query, params).fetchall())
    return render_template("admin_bookings.html", bookings=bookings, status_filter=status_filter, search=search)


@app.route("/admin/bookings/<int:booking_id>/edit", methods=["POST"])
@admin_required
def edit_booking(booking_id):
    required = ["customer_name", "phone", "pickup_location", "drop_location", "pickup_date", "pickup_time"]
    if any(not form_value(field) for field in required):
        flash("Customer, route, date, and time are required.", "error")
        return redirect(url_for("admin_bookings"))
    try:
        passengers = max(1, min(20, int(form_value("passengers", "1"))))
        date.fromisoformat(form_value("pickup_date"))
    except ValueError:
        flash("Please provide a valid date and passenger count.", "error")
        return redirect(url_for("admin_bookings"))
    status = form_value("status", "pending")
    if status not in {"pending", "confirmed", "completed", "cancelled"}:
        flash("Please choose a valid booking status.", "error")
        return redirect(url_for("admin_bookings"))
    db = get_db()
    db.execute(
        """UPDATE bookings SET customer_name=?, phone=?, email=?, pickup_location=?, drop_location=?,
        pickup_date=?, pickup_time=?, passengers=?, notes=?, status=? WHERE id=?""",
        (form_value("customer_name"), form_value("phone"), form_value("email"), form_value("pickup_location"),
         form_value("drop_location"), form_value("pickup_date"), form_value("pickup_time"), passengers,
         form_value("notes"), status, booking_id),
    )
    db.commit()
    flash("Booking details updated.", "success")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/bookings/<int:booking_id>/status", methods=["POST"])
@admin_required
def update_booking_status(booking_id):
    status = form_value("status")
    if status not in {"pending", "confirmed", "completed", "cancelled"}:
        abort(400)
    db = get_db()
    db.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
    db.commit()
    flash("Booking status updated.", "success")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/bookings/<int:booking_id>/delete", methods=["POST"])
@admin_required
def delete_booking(booking_id):
    db = get_db()
    db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    db.commit()
    flash("Booking deleted.", "success")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/routes")
@admin_required
def admin_routes():
    return render_template("admin_routes.html", routes=get_db().execute("SELECT * FROM route_prices ORDER BY is_active DESC, sort_order, id").fetchall())


@app.route("/admin/routes/add", methods=["POST"])
@admin_required
def add_route():
    required = ["route_name", "pickup_city", "drop_city", "duration_text", "distance_km", "price"]
    if any(not form_value(field) for field in required):
        flash("Route name, cities, distance, duration, and price are required.", "error")
        return redirect(url_for("admin_routes"))
    try:
        image_url = save_route_image(request.files.get("route_image"))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_routes"))
    db = get_db()
    db.execute(
        "INSERT INTO route_prices(route_name, pickup_city, drop_city, duration_text, distance_km, price, sort_order, is_active, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            form_value("route_name"),
            form_value("pickup_city"),
            form_value("drop_city"),
            form_value("duration_text"),
            int(form_value("distance_km", "0")),
            float(form_value("price", "0")),
            int(form_value("sort_order", "0")) or 0,
            int("is_active" in request.form),
            image_url,
        ),
    )
    db.commit()
    flash("Popular route added.", "success")
    return redirect(url_for("admin_routes"))


def save_route_image(upload):
    if upload is None or not upload.filename:
        return ""

    filename = upload.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    mime_type = (upload.mimetype or "").lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    mime_to_extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    if extension not in allowed_extensions and mime_type not in mime_to_extension:
        raise ValueError("Choose a JPG, PNG, or WebP image.")

    if extension not in allowed_extensions:
        extension = mime_to_extension.get(mime_type, ".jpg")

    image_directory = os.path.join(BASE_DIR, "static", "uploads", "routes")
    os.makedirs(image_directory, exist_ok=True)
    saved_filename = f"{secrets.token_hex(16)}{extension}"
    upload.save(os.path.join(image_directory, saved_filename))
    return url_for("static", filename=f"uploads/routes/{saved_filename}")


@app.route("/admin/routes/<int:route_id>/edit", methods=["POST"])
@admin_required
def edit_route(route_id):
    required = ["route_name", "pickup_city", "drop_city", "duration_text", "distance_km", "price"]
    if any(not form_value(field) for field in required):
        flash("All route fields are required before saving.", "error")
        return redirect(url_for("admin_routes"))
    db = get_db()
    current_route = db.execute("SELECT image_url FROM route_prices WHERE id = ?", (route_id,)).fetchone()
    if current_route is None:
        abort(404)
    uploaded_image = request.files.get("route_image")
    try:
        image_url = save_route_image(uploaded_image) if uploaded_image and uploaded_image.filename else current_route["image_url"]
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin_routes"))
    db.execute(
        "UPDATE route_prices SET route_name = ?, pickup_city = ?, drop_city = ?, duration_text = ?, distance_km = ?, price = ?, sort_order = ?, is_active = ?, image_url = ? WHERE id = ?",
        (
            form_value("route_name"),
            form_value("pickup_city"),
            form_value("drop_city"),
            form_value("duration_text"),
            int(form_value("distance_km", "0")),
            float(form_value("price", "0")),
            int(form_value("sort_order", "0")) or 0,
            int("is_active" in request.form),
            image_url,
            route_id,
        ),
    )
    db.commit()
    flash("Route details updated.", "success")
    return redirect(url_for("admin_routes"))


@app.route("/admin/routes/<int:route_id>/delete", methods=["POST"])
@admin_required
def delete_route(route_id):
    db = get_db()
    db.execute("UPDATE route_prices SET is_active = 0 WHERE id = ?", (route_id,))
    db.commit()
    flash("Route removed from the popular list.", "success")
    return redirect(url_for("admin_routes"))


@app.route("/admin/cars")
@admin_required
def admin_cars():
    return render_template("admin_cars.html", cars=get_db().execute("SELECT * FROM cars ORDER BY name").fetchall())


@app.route("/admin/cars/add", methods=["POST"])
@admin_required
def add_car():
    if not form_value("name") or not form_value("car_type"):
        flash("Car name and type are required.", "error")
        return redirect(url_for("admin_cars"))
    db = get_db()
    db.execute(
        "INSERT INTO cars(name, car_type, seats, price_per_km, base_fare, ac, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (form_value("name"), form_value("car_type"), int(form_value("seats", "4")), float(form_value("price_per_km", "12")),
         float(form_value("base_fare", "500")), int("ac" in request.form), form_value("status", "active")),
    )
    db.commit()
    flash("Car added to the fleet.", "success")
    return redirect(url_for("admin_cars"))


@app.route("/admin/cars/<int:car_id>/edit", methods=["POST"])
@admin_required
def edit_car(car_id):
    db = get_db()
    db.execute(
        "UPDATE cars SET name=?, car_type=?, seats=?, price_per_km=?, base_fare=?, ac=?, status=? WHERE id=?",
        (form_value("name"), form_value("car_type"), int(form_value("seats", "4")), float(form_value("price_per_km", "12")),
         float(form_value("base_fare", "500")), int("ac" in request.form), form_value("status", "active"), car_id),
    )
    db.commit()
    flash("Car details updated.", "success")
    return redirect(url_for("admin_cars"))


@app.route("/admin/cars/<int:car_id>/delete", methods=["POST"])
@admin_required
def delete_car(car_id):
    db = get_db()
    db.execute("DELETE FROM cars WHERE id = ?", (car_id,))
    db.commit()
    flash("Car removed from the fleet.", "success")
    return redirect(url_for("admin_cars"))


@app.route("/admin/reviews")
@admin_required
def admin_reviews():
    status_filter = request.args.get("status", "")
    query = "SELECT * FROM reviews"
    params = []
    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)
    reviews = template_rows(get_db().execute(query + " ORDER BY created_at DESC", params).fetchall())
    return render_template("admin_reviews.html", reviews=reviews, status_filter=status_filter)


@app.route("/admin/reviews/<int:review_id>/approve", methods=["POST"])
@admin_required
def approve_review(review_id):
    db = get_db()
    db.execute("UPDATE reviews SET status = 'approved' WHERE id = ?", (review_id,))
    db.commit()
    flash("Review approved.", "success")
    return redirect(url_for("admin_reviews"))


@app.route("/admin/reviews/<int:review_id>/reject", methods=["POST"])
@admin_required
def reject_review(review_id):
    db = get_db()
    db.execute("UPDATE reviews SET status = 'rejected' WHERE id = ?", (review_id,))
    db.commit()
    flash("Review hidden from the website.", "success")
    return redirect(url_for("admin_reviews"))


@app.route("/admin/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def delete_review(review_id):
    db = get_db()
    db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    db.commit()
    flash("Review deleted.", "success")
    return redirect(url_for("admin_reviews"))


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    db = get_db()
    if request.method == "POST":
        if form_value("form_name") == "business_info":
            values = {
                "business_name": form_value("business_name"), "owner_name": form_value("owner_name"),
                "mobile_number": form_value("mobile_number"), "whatsapp_number": form_value("whatsapp_number"),
                "service_area": form_value("service_area"), "email": form_value("email"),
                "address": form_value("address"), "tagline": form_value("tagline"),
            }
            key_column, value_column = settings_columns()
            db.executemany(
                f"INSERT INTO settings({key_column}, {value_column}) VALUES (?, ?) "
                f"ON CONFLICT ({key_column}) DO UPDATE SET {value_column} = EXCLUDED.{value_column}",
                values.items(),
            )
            db.commit()
            flash("Business information saved.", "success")
        elif form_value("form_name") == "change_credentials":
            admin = db.execute("SELECT * FROM admins WHERE id = ?", (session["admin_id"],)).fetchone()
            new_username = form_value("new_username")
            new_password = form_value("new_password")
            if len(new_username) < 3:
                flash("Username must be at least 3 characters.", "error")
            elif not check_password_hash(admin["password_hash"], request.form.get("current_password", "")):
                flash("Current password is incorrect.", "error")
            elif new_password and new_password != form_value("confirm_password"):
                flash("New passwords do not match.", "error")
            else:
                try:
                    db.execute("UPDATE admins SET username = ?, password_hash = ? WHERE id = ?", (new_username, generate_password_hash(new_password) if new_password else admin["password_hash"], admin["id"]))
                    db.commit()
                    flash("Login details updated.", "success")
                except Exception:
                    db.connection.rollback() if hasattr(db, "connection") else db.rollback()
                    flash("That username is already in use.", "error")
    settings = {key: setting(key) for key in ("business_name", "owner_name", "mobile_number", "whatsapp_number", "service_area", "email", "address", "tagline")}
    settings["current_username"] = get_db().execute("SELECT username FROM admins WHERE id = ?", (session["admin_id"],)).fetchone()["username"]
    return render_template("admin_settings.html", settings=settings)


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


with app.app_context():
    init_db()

@app.route("/sitemap.xml")
def sitemap():
    pages = [
        url_for("index", _external=True),
        url_for("booking", _external=True),
        url_for("reviews", _external=True),
    ]

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'

    for page in pages:
        sitemap_xml += f"<url><loc>{page}</loc></url>"

    sitemap_xml += "</urlset>"

    return sitemap_xml, 200, {"Content-Type": "application/xml"}

@app.route("/robots.txt")
def robots():
    return """User-agent: *
Allow: /

Sitemap: https://new-drop-taxi-fd38.vercel.app/sitemap.xml
""", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
