from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any
import sqlite3, os, math
from contextlib import contextmanager

app = FastAPI(title="泰美国际养生预约系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])




UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(os.path.dirname(__file__), "massage.db")
try:
    open(DB_PATH, "a").close()
except Exception:
    DB_PATH = "/tmp/massage.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price_in_store REAL NOT NULL DEFAULT 0,
            price_outcall REAL NOT NULL DEFAULT 0,
            duration INTEGER NOT NULL,
            description TEXT,
            image_url TEXT,
            video_url TEXT,
            status INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cols = [r[1] for r in c.execute("PRAGMA table_info(services)").fetchall()]
        if "price" in cols and "price_in_store" not in cols:
            c.execute("ALTER TABLE services ADD COLUMN price_in_store REAL DEFAULT 0")
            c.execute("ALTER TABLE services ADD COLUMN price_outcall REAL DEFAULT 0")
            c.execute("UPDATE services SET price_in_store=price, price_outcall=price*1.3 WHERE price_in_store=0")
        for col, sql in [("price_in_store","ALTER TABLE services ADD COLUMN price_in_store REAL DEFAULT 0"),
                         ("price_outcall","ALTER TABLE services ADD COLUMN price_outcall REAL DEFAULT 0")]:
            if col not in cols:
                try: c.execute(sql)
                except: pass

        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            service_name TEXT,
            service_type TEXT DEFAULT 'in_store',
            price REAL,
            taxi_fee REAL DEFAULT 0,
            user_phone TEXT NOT NULL,
            address_name TEXT NOT NULL,
            address_detail TEXT,
            lat REAL, lng REAL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            remark TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        ocols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
        for col, sql in [("service_type","ALTER TABLE orders ADD COLUMN service_type TEXT DEFAULT 'in_store'"),
                         ("price","ALTER TABLE orders ADD COLUMN price REAL"),
                         ("taxi_fee","ALTER TABLE orders ADD COLUMN taxi_fee REAL DEFAULT 0")]:
            if col not in ocols:
                try: c.execute(sql)
                except: pass

        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        defaults = {
            "store_name": "泰美国际养生",
            "store_address": "马来西亚雪兰莪（点击导航）",
            "store_lat": "3.118743",
            "store_lng": "101.727844",
            "taxi_base_fee": "10",
            "taxi_per_km": "2",
            "payment_note": "见面收取费用，支持 USD / 支付宝 / 微信",
            "booking_open": "1",
            "whatsapp_notify": "",
            "google_maps_key": "",
            "callmebot_apikey": "",
            "telegram_bot_token": "",
            "telegram_chat_id": ""
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        c.execute("""CREATE TABLE IF NOT EXISTS service_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price_in_store REAL NOT NULL DEFAULT 0,
            price_outcall REAL NOT NULL DEFAULT 0,
            duration INTEGER NOT NULL DEFAULT 60,
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0
        )""")
        try:
            icols = [r[1] for r in c.execute("PRAGMA table_info(service_items)").fetchall()]
            if "description" not in icols:
                c.execute("ALTER TABLE service_items ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT NOT NULL,
            order_id INTEGER,
            service_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        try:
            cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
            if "service_id" not in cols:
                c.execute("ALTER TABLE messages ADD COLUMN service_id INTEGER")
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )""")
        if c.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
            c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", "admin123"))
        try:
            scols = [r[1] for r in c.execute("PRAGMA table_info(services)").fetchall()]
            if "country" not in scols:
                c.execute("ALTER TABLE services ADD COLUMN country TEXT DEFAULT ''")
            if "accepting" not in scols:
                c.execute("ALTER TABLE services ADD COLUMN accepting INTEGER DEFAULT 1")
        except Exception:
            pass
        if c.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
            c.execute("""INSERT INTO services (name, price_in_store, price_outcall, duration, description, image_url) VALUES
                ('泰式古法按摩', 299, 399, 60, '传统泰式按摩，疏通经络，缓解疲劳', 'https://picsum.photos/seed/thai1/600/400'),
                ('精油舒缓按摩', 399, 499, 90, '天然精油SPA，深度放松身心', 'https://picsum.photos/seed/thai2/600/400'),
                ('足部反射按摩', 199, 279, 45, '足底穴位按摩，促进血液循环', 'https://picsum.photos/seed/thai3/600/400'),
                ('全身SPA套餐', 599, 799, 120, '全身按摩+精油+热敷，尊享体验', 'https://picsum.photos/seed/thai4/600/400')""")

init_db()

class ServiceItemIn(BaseModel):
    name: str
    price_in_store: float = 0
    price_outcall: float = 0
    duration: int = 60

class ServiceCreate(BaseModel):
    name: str
    country: Optional[str] = ""
    price_in_store: float = 0
    price_outcall: float = 0
    duration: int = 60
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    video_url: Optional[str] = ""
    status: int = 1
    items: Optional[List[Any]] = None

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    price_in_store: Optional[float] = None
    price_outcall: Optional[float] = None
    duration: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    status: Optional[int] = None
    items: Optional[List[Any]] = None

class OrderCreate(BaseModel):
    service_id: int
    service_item_id: Optional[int] = None
    service_type: str = "in_store"
    user_phone: str
    address_name: str = ""
    address_detail: Optional[str] = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    appointment_date: str
    appointment_time: str
    remark: Optional[str] = ""

class OrderStatusUpdate(BaseModel):
    status: str

class AdminLogin(BaseModel):
    username: str
    password: str

class SettingsUpdate(BaseModel):
    store_name: Optional[str] = None
    store_address: Optional[str] = None
    store_lat: Optional[str] = None
    store_lng: Optional[str] = None
    taxi_base_fee: Optional[str] = None
    taxi_per_km: Optional[str] = None
    payment_note: Optional[str] = None
    booking_open: Optional[str] = None
    whatsapp_notify: Optional[str] = None
    google_maps_key: Optional[str] = None
    callmebot_apikey: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


def ensure_service_items_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS service_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price_in_store REAL NOT NULL DEFAULT 0,
        price_outcall REAL NOT NULL DEFAULT 0,
        duration INTEGER NOT NULL DEFAULT 60,
        description TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0
    )""")
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(service_items)").fetchall()]
        if "description" not in cols:
            conn.execute("ALTER TABLE service_items ADD COLUMN description TEXT DEFAULT ''")
    except Exception:
        pass

def attach_items(conn, services):
    if not services:
        return services
    try:
        ensure_service_items_table(conn)
    except Exception:
        pass
    if isinstance(services, dict):
        services = [services]
        single = True
    else:
        single = False
    for s in services:
        try:
            rows = conn.execute(
                "SELECT id, name, price_in_store, price_outcall, duration, description FROM service_items WHERE service_id=? ORDER BY sort_order, id",
                (s["id"],)
            ).fetchall()
            s["items"] = [dict(r) for r in rows]
        except Exception:
            try:
                rows = conn.execute(
                    "SELECT id, name, price_in_store, price_outcall, duration FROM service_items WHERE service_id=? ORDER BY sort_order, id",
                    (s["id"],)
                ).fetchall()
                s["items"] = [dict(r) for r in rows]
            except Exception:
                s["items"] = []
        if s.get("items"):
            s["price_in_store"] = s["items"][0].get("price_in_store", s.get("price_in_store") or 0)
            s["price_outcall"] = s["items"][0].get("price_outcall", s.get("price_outcall") or 0)
            s["duration"] = s["items"][0].get("duration", s.get("duration") or 60)
    return services[0] if single else services

def save_items(conn, service_id, items):
    ensure_service_items_table(conn)
    conn.execute("DELETE FROM service_items WHERE service_id=?", (service_id,))
    if not items:
        return
    for i, it in enumerate(items):
        if isinstance(it, dict):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            try:
                conn.execute(
                    "INSERT INTO service_items (service_id, name, price_in_store, price_outcall, duration, description, sort_order) VALUES (?,?,?,?,?,?,?)",
                    (service_id, name, float(it.get("price_in_store") or 0), float(it.get("price_outcall") or 0), int(it.get("duration") or 60), it.get("description") or "", i)
                )
            except Exception:
                conn.execute(
                    "INSERT INTO service_items (service_id, name, price_in_store, price_outcall, duration, sort_order) VALUES (?,?,?,?,?,?)",
                    (service_id, name, float(it.get("price_in_store") or 0), float(it.get("price_outcall") or 0), int(it.get("duration") or 60), i)
                )


@app.get("/api/store")
def get_store_info():
    with get_db() as conn:
        s = get_settings(conn)
    lat, lng = float(s.get("store_lat", 3.118743)), float(s.get("store_lng", 101.727844))
    return {
        "name": s.get("store_name", "泰美国际养生"),
        "address": s.get("store_address", ""),
        "lat": lat, "lng": lng,
        "map_url": f"https://www.google.com/maps?q={lat},{lng}",
        "taxi_base_fee": float(s.get("taxi_base_fee", 10)),
        "taxi_per_km": float(s.get("taxi_per_km", 2)),
        "payment_note": s.get("payment_note", "见面收取费用，支持 USD / 支付宝 / 微信"),
        "booking_open": s.get("booking_open", "1") == "1",
        "google_maps_key": s.get("google_maps_key", ""),
        "whatsapp_notify": s.get("whatsapp_notify", "")
    }

@app.get("/api/taxi-fee")
def calc_taxi_fee(lat: float, lng: float):
    with get_db() as conn:
        s = get_settings(conn)
    slat, slng = float(s.get("store_lat", 3.118743)), float(s.get("store_lng", 101.727844))
    km = haversine_km(slat, slng, lat, lng)
    base = float(s.get("taxi_base_fee", 10))
    per = float(s.get("taxi_per_km", 2))
    fee = round(base + km * per, 2)
    return {"distance_km": round(km, 2), "taxi_fee": fee, "base": base, "per_km": per}

@app.get("/api/services")
def list_services():
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM services WHERE status=1 ORDER BY id").fetchall()]
        return attach_items(conn, rows)

@app.get("/api/services/{service_id}")
def get_service(service_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
        if not row: raise HTTPException(404, "服务不存在")
        data = attach_items(conn, dict(row))
        s = get_settings(conn)
        lat, lng = float(s.get("store_lat", 3.118743)), float(s.get("store_lng", 101.727844))
        data["store"] = {
            "name": s.get("store_name"), "address": s.get("store_address"),
            "lat": lat, "lng": lng, "map_url": f"https://www.google.com/maps?q={lat},{lng}"
        }
        data["payment_note"] = s.get("payment_note", "见面收取费用，支持 USD / 支付宝 / 微信")
        return data



def notify_telegram(text: str):
    """Push text to configured Telegram bot chat. chat_id can be number or @username."""
    try:
        with get_db() as conn:
            s = get_settings(conn)
        token = (s.get("telegram_bot_token") or "").strip()
        chat_id = (s.get("telegram_chat_id") or "").strip()
        if not token or not chat_id:
            print("telegram: missing token or chat_id")
            return False
        import urllib.request, json
        # resolve @username if needed
        cid = chat_id
        def tg_api(method, payload):
            url = f"https://api.telegram.org/bot{token}/{method}"
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        # try send
        data = tg_api("sendMessage", {"chat_id": cid, "text": text, "parse_mode": "HTML"})
        if data.get("ok"):
            return True
        print("telegram send not ok:", data)
        return False
    except Exception as e:
        err = str(e)
        print("notify_telegram failed:", err)
        # try getUpdates hint in logs
        try:
            import urllib.request, json
            with get_db() as conn:
                s = get_settings(conn)
            token = (s.get("telegram_bot_token") or "").strip()
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            with urllib.request.urlopen(url, timeout=8) as resp:
                print("telegram getUpdates:", resp.read()[:500])
        except Exception as e2:
            print("getUpdates fail:", e2)
        return False

def notify_whatsapp(order_id, svc_name, service_type, phone, address, date, time, price, taxi_fee, remark=""):
    """Send order alert to configured WhatsApp via CallMeBot (free) or log fallback."""
    try:
        with get_db() as conn:
            s = get_settings(conn)
        wa = (s.get("whatsapp_notify") or "").strip().replace("+", "").replace(" ", "").replace("-", "")
        api_key = (s.get("callmebot_apikey") or "").strip()
        if not wa:
            return
        type_label = "上门" if service_type == "outcall" else "到店"
        text = (
            f"*新预约订单 #{order_id}*\n"
            f"服务: {svc_name} ({type_label})\n"
            f"电话: {phone}\n"
            f"时间: {date} {time}\n"
            f"地址: {address}\n"
            f"金额: ¥{price}" + (f" +打车¥{taxi_fee}" if taxi_fee else "") + "\n"
            f"备注: {remark or '无'}\n"
            f"请尽快确认"
        )
        import urllib.parse, urllib.request
        # CallMeBot: user must first message the bot to get apikey
        if api_key:
            url = (
                "https://api.callmebot.com/whatsapp.php?"
                + urllib.parse.urlencode({"phone": wa, "text": text, "apikey": api_key})
            )
            try:
                urllib.request.urlopen(url, timeout=8)
            except Exception as e:
                print("CallMeBot error:", e)
        # Always also print for server log
        print("WA_NOTIFY:", wa, text.replace("\n", " | "))
    except Exception as e:
        print("notify_whatsapp failed:", e)

@app.post("/api/orders")
def create_order(order: OrderCreate):
    with get_db() as conn:
        s = get_settings(conn)
        if s.get("booking_open", "1") != "1":
            raise HTTPException(400, "当前服务中，暂不可预约，请稍后再试")
        svc = conn.execute("SELECT * FROM services WHERE id=? AND status=1", (order.service_id,)).fetchone()
        if not svc: raise HTTPException(400, "服务不存在或已下架")
        try:
            if int(dict(svc).get("accepting", 1) or 1) != 1:
                raise HTTPException(400, "该服务商服务中，暂不可预约")
        except HTTPException:
            raise
        except Exception:
            pass
        s = get_settings(conn)
        price = svc["price_outcall"] if order.service_type == "outcall" else svc["price_in_store"]
        svc_display_name = svc["name"]
        if order.service_item_id:
            it = conn.execute("SELECT * FROM service_items WHERE id=? AND service_id=?", (order.service_item_id, order.service_id)).fetchone()
            if it:
                price = it["price_outcall"] if order.service_type == "outcall" else it["price_in_store"]
                svc_display_name = svc["name"] + " - " + it["name"]
        taxi_fee = 0.0
        address_name = order.address_name
        lat, lng = order.lat, order.lng
        if order.service_type == "in_store":
            address_name = address_name or s.get("store_address", "门店")
            lat = lat if lat is not None else float(s.get("store_lat", 3.118743))
            lng = lng if lng is not None else float(s.get("store_lng", 101.727844))
        elif order.service_type == "outcall" and lat is not None and lng is not None:
            slat, slng = float(s.get("store_lat", 3.118743)), float(s.get("store_lng", 101.727844))
            km = haversine_km(slat, slng, lat, lng)
            taxi_fee = round(float(s.get("taxi_base_fee", 10)) + km * float(s.get("taxi_per_km", 2)), 2)
        conn.execute("""INSERT INTO orders (service_id, service_name, service_type, price, taxi_fee, user_phone,
            address_name, address_detail, lat, lng, appointment_date, appointment_time, remark)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order.service_id, svc_display_name, order.service_type, price, taxi_fee, order.user_phone,
             address_name, order.address_detail, lat, lng, order.appointment_date, order.appointment_time, order.remark))
        oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # fire-and-forget WhatsApp notify
        try:
            notify_whatsapp(oid, svc["name"], order.service_type, order.user_phone,
                address_name + ((" · " + (order.address_detail or "")) if order.address_detail else ""),
                order.appointment_date, order.appointment_time, price, taxi_fee, order.remark or "")
        except Exception as e:
            print("notify skip:", e)
        try:
            type_label = "上门" if order.service_type == "outcall" else "到店"
            tg = (
                f"🆕 <b>新预约订单 #{oid}</b>\n"
                f"服务: {svc_display_name}（{type_label}）\n"
                f"电话: {order.user_phone}\n"
                f"时间: {order.appointment_date} {order.appointment_time}\n"
                f"地址: {address_name}\n"
                f"金额: ¥{price}" + (f" +打车¥{taxi_fee}" if taxi_fee else "") + "\n"
                f"备注: {order.remark or '无'}"
            )
            notify_telegram(tg)
        except Exception as e:
            print("tg order skip:", e)
        return {"id": oid, "message": "预约成功", "price": price, "taxi_fee": taxi_fee}

@app.get("/api/orders/by-phone/{phone}")
def get_orders_by_phone(phone: str):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM orders WHERE user_phone=? ORDER BY created_at DESC", (phone,)).fetchall()]

@app.post("/api/admin/login")
def admin_login(data: AdminLogin):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM admins WHERE username=? AND password=?", (data.username, data.password)).fetchone()
        if not row: raise HTTPException(401, "账号或密码错误")
        return {"token": "admin-token", "message": "登录成功"}

@app.get("/api/admin/services")
def admin_list_services():
    with get_db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM services ORDER BY id").fetchall()]
        return attach_items(conn, rows)

@app.post("/api/admin/services")
def admin_create_service(svc: ServiceCreate):
    try:
        with get_db() as conn:
            ensure_service_items_table(conn)
            items = list(svc.items or [])
            pin = float(svc.price_in_store or 0)
            pout = float(svc.price_outcall or 0)
            dur = int(svc.duration or 60)
            if items:
                first = items[0] if isinstance(items[0], dict) else {}
                pin = float(first.get("price_in_store") or pin or 0)
                pout = float(first.get("price_outcall") or pout or 0)
                dur = int(first.get("duration") or dur or 60)
            # 兼容旧表 price 字段
            cols = [r[1] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
            country = (svc.country or "").strip()
            if "country" not in cols:
                try:
                    conn.execute("ALTER TABLE services ADD COLUMN country TEXT DEFAULT ''")
                    cols.append("country")
                except Exception:
                    pass
            if "price" in cols:
                conn.execute(
                    """INSERT INTO services (name, price, price_in_store, price_outcall, duration, description, image_url, video_url, status, country)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (svc.name, pin, pin, pout, dur, svc.description or "", svc.image_url or "", svc.video_url or "", int(svc.status if svc.status is not None else 1), country),
                )
            else:
                conn.execute(
                    """INSERT INTO services (name, price_in_store, price_outcall, duration, description, image_url, video_url, status, country)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (svc.name, pin, pout, dur, svc.description or "", svc.image_url or "", svc.video_url or "", int(svc.status if svc.status is not None else 1), country),
                )
            sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            save_items(conn, sid, items)
            return {"id": sid, "message": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"保存失败: {type(e).__name__}: {e}")


@app.put("/api/admin/services/{service_id}")
def admin_update_service(service_id: int, svc: ServiceUpdate):
    try:
        with get_db() as conn:
            ensure_service_items_table(conn)
            existing = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
            if not existing:
                raise HTTPException(404, "服务不存在")
            data = dict(existing)
            update = svc.dict(exclude_unset=True)
            items = update.pop("items", None)
            data.update(update)
            if items is not None and isinstance(items, list) and items:
                data["price_in_store"] = float(items[0].get("price_in_store") or data.get("price_in_store") or 0)
                data["price_outcall"] = float(items[0].get("price_outcall") or data.get("price_outcall") or 0)
                data["duration"] = int(items[0].get("duration") or data.get("duration") or 60)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
            if "country" not in cols:
                try:
                    conn.execute("ALTER TABLE services ADD COLUMN country TEXT DEFAULT ''")
                    cols.append("country")
                except Exception:
                    pass
            country = data.get("country") or ""
            if "price" in cols:
                conn.execute(
                    """UPDATE services SET name=?, price=?, price_in_store=?, price_outcall=?, duration=?, description=?,
                    image_url=?, video_url=?, status=?, country=? WHERE id=?""",
                    (data["name"], data["price_in_store"], data["price_in_store"], data["price_outcall"], data["duration"],
                     data.get("description") or "", data.get("image_url") or "", data.get("video_url") or "", data["status"], country, service_id),
                )
            else:
                conn.execute(
                    """UPDATE services SET name=?, price_in_store=?, price_outcall=?, duration=?, description=?,
                    image_url=?, video_url=?, status=?, country=? WHERE id=?""",
                    (data["name"], data["price_in_store"], data["price_outcall"], data["duration"],
                     data.get("description") or "", data.get("image_url") or "", data.get("video_url") or "", data["status"], country, service_id),
                )
            if items is not None:
                save_items(conn, service_id, items)
            return {"message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"更新失败: {type(e).__name__}: {e}")


@app.delete("/api/admin/services/{service_id}")
def admin_delete_service(service_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM services WHERE id=?", (service_id,))
        return {"message": "删除成功"}

@app.get("/api/admin/orders")
def admin_list_orders(status: Optional[str] = None):
    with get_db() as conn:
        if status:
            return [dict(r) for r in conn.execute("SELECT * FROM orders WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()]
        return [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()]

@app.put("/api/admin/orders/{order_id}/status")
def admin_update_order_status(order_id: int, data: OrderStatusUpdate):
    with get_db() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (data.status, order_id))
        return {"message": "状态更新成功"}

@app.get("/api/admin/settings")
def admin_get_settings():
    with get_db() as conn:
        return get_settings(conn)

@app.put("/api/admin/settings")
def admin_update_settings(data: SettingsUpdate):
    with get_db() as conn:
        for k, v in data.dict(exclude_unset=True).items():
            if v is not None:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        return {"message": "设置已保存"}



class MessageCreate(BaseModel):
    user_phone: str
    content: str
    order_id: Optional[int] = None
    service_id: Optional[int] = None
    role: str = "user"


@app.get("/api/messages/{phone}/unread")
def messages_unread(phone: str, after_id: int = 0):
    """Return unread admin replies grouped by service_id (id > after_id)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, service_id, content, created_at FROM messages
               WHERE user_phone=? AND role='admin' AND id>?
               ORDER BY id ASC""",
            (phone.strip(), after_id)
        ).fetchall()
        by_svc = {}
        total = 0
        for r in rows:
            total += 1
            sid = r["service_id"] or 0
            key = str(sid)
            if key not in by_svc:
                by_svc[key] = {"service_id": sid, "count": 0, "last_content": "", "last_id": 0}
            by_svc[key]["count"] += 1
            by_svc[key]["last_content"] = r["content"]
            by_svc[key]["last_id"] = r["id"]
        return {"total": total, "by_service": list(by_svc.values()), "max_id": (rows[-1]["id"] if rows else after_id)}


@app.get("/api/messages/{phone}")
def list_messages(phone: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE user_phone=? ORDER BY id ASC", (phone,)
        ).fetchall()
        return [dict(r) for r in rows]

@app.post("/api/messages")
def post_message(data: MessageCreate):
    if not data.content.strip():
        raise HTTPException(400, "消息不能为空")
    role = data.role if data.role in ("user", "admin") else "user"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (user_phone, order_id, service_id, role, content) VALUES (?,?,?,?,?)",
            (data.user_phone.strip(), data.order_id, data.service_id, role, data.content.strip())
        )
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if role == "user":
            try:
                notify_telegram(
                    f"💬 <b>新用户咨询</b>\n"
                    f"手机: {data.user_phone.strip()}\n"
                    f"内容: {data.content.strip()[:500]}"
                )
            except Exception as e:
                print("tg msg skip:", e)
        return {"id": mid, "message": "已发送"}

@app.get("/api/admin/messages")
def admin_list_messages():
    with get_db() as conn:
        phones = conn.execute(
            "SELECT user_phone, MAX(id) as last_id, COUNT(*) as cnt FROM messages GROUP BY user_phone ORDER BY last_id DESC"
        ).fetchall()
        result = []
        for p in phones:
            last = conn.execute("SELECT * FROM messages WHERE id=?", (p["last_id"],)).fetchone()
            svc_name = ""
            if last and last["service_id"]:
                srow = conn.execute("SELECT name FROM services WHERE id=?", (last["service_id"],)).fetchone()
                svc_name = srow["name"] if srow else ""
            result.append({
                "user_phone": p["user_phone"],
                "count": p["cnt"],
                "last_content": last["content"] if last else "",
                "last_role": last["role"] if last else "",
                "last_at": last["created_at"] if last else "",
                "service_id": last["service_id"] if last else None,
                "service_name": svc_name
            })
        return result



@app.put("/api/admin/services/{service_id}/accepting")
def admin_set_accepting(service_id: int, body: dict):
    val = 1 if body.get("accepting") in (1, "1", True, "true") else 0
    with get_db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
        if "accepting" not in cols:
            conn.execute("ALTER TABLE services ADD COLUMN accepting INTEGER DEFAULT 1")
        row = conn.execute("SELECT id FROM services WHERE id=?", (service_id,)).fetchone()
        if not row:
            raise HTTPException(404, "服务商不存在")
        conn.execute("UPDATE services SET accepting=? WHERE id=?", (val, service_id))
        return {"id": service_id, "accepting": val}


@app.post("/api/admin/telegram-test")
def telegram_test():
    ok = notify_telegram("✅ 泰美预约系统测试消息\nTelegram 通知已绑定成功")
    if not ok:
        raise HTTPException(400, "发送失败。请确认：1)已点开机器人并点Start 2)Chat ID用数字(用@userinfobot查询) 3)Token正确")
    return {"message": "已发送测试消息"}

@app.get("/api/admin/stats")
def admin_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0]
        cancelled = conn.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled'").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now')").fetchone()[0]
        revenue = conn.execute("SELECT COALESCE(SUM(price),0)+COALESCE(SUM(taxi_fee),0) FROM orders WHERE status IN ('confirmed','completed')").fetchone()[0]
        services = conn.execute("SELECT COUNT(*) FROM services WHERE status=1").fetchone()[0]
        providers_total = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        try:
            providers_accepting = conn.execute("SELECT COUNT(*) FROM services WHERE status=1 AND COALESCE(accepting,1)=1").fetchone()[0]
        except Exception:
            providers_accepting = services
        recent = [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 8").fetchall()]
        return {
            "total_orders": total,
            "pending": pending,
            "confirmed": confirmed,
            "completed": completed,
            "cancelled": cancelled,
            "today_orders": today,
            "revenue": revenue,
            "active_services": services,
            "providers_total": providers_total,
            "providers_accepting": providers_accepting,
            "recent_orders": recent
        }


@app.post("/api/admin/upload")
async def admin_upload(file: UploadFile = File(...)):
    import uuid, re
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".mov"]:
        raise HTTPException(400, "仅支持图片 jpg/png/gif/webp 或视频 mp4/webm/mov")
    name = str(uuid.uuid4())[:12] + ext
    path = os.path.join(UPLOAD_DIR, name)
    data = await file.read()
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过 80MB，请压缩后再传")
    with open(path, "wb") as f:
        f.write(data)
    return {"url": f"/uploads/{name}", "filename": name}

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(os.path.join(STATIC_DIR, "uploads"), exist_ok=True)
try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
except Exception:
    pass
@app.get("/")
def index(): return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
@app.get("/detail.html")
def detail_page(): return FileResponse(os.path.join(FRONTEND_DIR, "detail.html"))
@app.get("/book.html")
def book_page(): return FileResponse(os.path.join(FRONTEND_DIR, "book.html"))
@app.get("/orders.html")
def orders_page(): return FileResponse(os.path.join(FRONTEND_DIR, "orders.html"))
@app.get("/admin.html")
def admin_page(): return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))
@app.get("/admin-login.html")
def admin_login_page(): return FileResponse(os.path.join(FRONTEND_DIR, "admin-login.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
