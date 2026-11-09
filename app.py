"""Zubair Hall Mess Manager (Streamlit edition).

Mess register and reports for the East Wing and West Wing messes of
Zubair Hall, UET Lahore. Data is stored in PostgreSQL (Neon) when
DATABASE_URL is provided, otherwise in a local SQLite file.
"""
import datetime as dt
import hashlib
import html
import hmac
import io
import json
import os
import random
import re
import secrets
import time
import uuid

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, column, create_engine, insert, table, text

st.set_page_config(page_title="Zubair Hall Mess Manager", page_icon="🍽️", layout="wide")

GREEN, AMBER, RED, BLUE, PINK = "#19e6a1", "#ffb020", "#ff4d6d", "#38bdf8", "#f472b6"
MESS_KEYS = ["EAST", "WEST"]
DEFAULT_PASSWORD = "Hadi2750"
ITEM_CATEGORIES = ["Grains & Flour", "Meat & Chicken", "Vegetables", "Dairy & Eggs", "Oil & Spices", "Fuel / Gas", "Other"]
EXPENSE_CATEGORIES = ["Gas", "Salaries", "Repairs", "Transport", "Utilities", "Other"]
UNITS = ["kg", "g", "litre", "ml", "dozen", "piece", "packet", "bag"]

NEON_CSS = """
<style>
:root { --neon:#22e6c3; --neon2:#7c5cff; --edge:#0a1233; }
.stApp {
  background:
    radial-gradient(1100px 520px at 8% -8%, rgba(34,230,195,.10) 0%, transparent 60%),
    radial-gradient(900px 480px at 100% 0%, rgba(124,92,255,.14) 0%, transparent 58%),
    #070b18;
}
.block-container {padding-top: 1.4rem; max-width: 1400px;}
header[data-testid="stHeader"] {background: transparent;}
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0c1233 0%, #070b18 100%);
  border-right: 1px solid rgba(34,230,195,.28);
  box-shadow: 0 0 34px rgba(34,230,195,.10);
}
.hero {padding: .4rem 0 .9rem 0; margin-bottom: .6rem; border-bottom: 1px solid rgba(34,230,195,.22);}
.hero h2 {margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: .3px;
  background: linear-gradient(90deg, #22e6c3, #7cc4ff 55%, #a78bfa); -webkit-background-clip: text;
  background-clip: text; color: transparent; filter: drop-shadow(0 0 10px rgba(34,230,195,.35));}
.hero p {margin: .15rem 0 0 0; color: #93a4c8; font-size: .92rem;}
.brand {font-weight: 800; font-size: 1.15rem; letter-spacing: .4px; color: #e8f1ff;
  text-shadow: 0 0 14px rgba(34,230,195,.55);}
.brand-sub {color: #7f93bd; font-size: .78rem; margin-bottom: .4rem;}

/* ---------- 3D neon buttons ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 12px; font-weight: 600; letter-spacing: .2px; color: #eaf6ff;
  border: 1px solid rgba(34,230,195,.55);
  background: linear-gradient(180deg, #2c3d86 0%, #17245a 100%);
  box-shadow: 0 5px 0 var(--edge), 0 9px 16px rgba(0,0,0,.45), 0 0 12px rgba(34,230,195,.22),
              inset 0 1px 0 rgba(255,255,255,.28);
  transform: translateY(0); transition: transform .08s ease, box-shadow .08s ease, filter .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  filter: brightness(1.12); transform: translateY(-1px); color: #ffffff; border-color: var(--neon);
  box-shadow: 0 6px 0 var(--edge), 0 11px 18px rgba(0,0,0,.5), 0 0 20px rgba(34,230,195,.5),
              inset 0 1px 0 rgba(255,255,255,.32);
}
.stButton > button:active, .stDownloadButton > button:active, [data-testid="stFormSubmitButton"] > button:active {
  transform: translateY(5px);
  box-shadow: 0 0 0 var(--edge), 0 2px 6px rgba(0,0,0,.5), 0 0 22px rgba(34,230,195,.6),
              inset 0 2px 6px rgba(0,0,0,.35);
}
button[data-testid^="stBaseButton-primary"] {
  background: linear-gradient(180deg, #2df0cc 0%, #0fae95 100%) !important; color: #042a24 !important;
  border: 1px solid #7dfbe4 !important;
  box-shadow: 0 5px 0 #08665a, 0 9px 16px rgba(0,0,0,.45), 0 0 18px rgba(34,230,195,.55),
              inset 0 1px 0 rgba(255,255,255,.55) !important;
}
button[data-testid^="stBaseButton-primary"]:active {
  box-shadow: 0 0 0 #08665a, 0 2px 6px rgba(0,0,0,.5), 0 0 26px rgba(34,230,195,.75), inset 0 2px 6px rgba(0,0,0,.3) !important;
}
button[data-testid^="stBaseButton-primary"] p, button[data-testid^="stBaseButton-primary"] span {color: #042a24 !important; font-weight: 700;}
section[data-testid="stSidebar"] .stButton > button {justify-content: flex-start; padding-left: 1rem; margin-bottom: .35rem;}

/* ---------- cards, tabs, inputs ---------- */
div[data-testid="stMetric"] {
  background: linear-gradient(160deg, rgba(34,230,195,.09), rgba(124,92,255,.08));
  border: 1px solid rgba(34,230,195,.30); border-radius: 14px; padding: .75rem .95rem;
  box-shadow: 0 8px 18px rgba(0,0,0,.35), 0 0 14px rgba(34,230,195,.10), inset 0 1px 0 rgba(255,255,255,.08);
}
div[data-testid="stMetricLabel"] p {color: #9fb2d9;}
div[data-testid="stMetricValue"] {text-shadow: 0 0 12px rgba(34,230,195,.35); font-size: 1.7rem;}
div[data-testid="stMetricValue"] > div {overflow: visible; text-overflow: clip; white-space: nowrap;}
button[data-baseweb="tab"] {font-weight: 600;}
div[data-baseweb="tab-highlight"] {background: var(--neon) !important; box-shadow: 0 0 12px var(--neon);}
div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within, div[data-baseweb="textarea"]:focus-within {
  box-shadow: 0 0 0 1px var(--neon), 0 0 14px rgba(34,230,195,.35);
}
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
  border: 1px solid rgba(34,230,195,.20); border-radius: 12px; box-shadow: 0 6px 16px rgba(0,0,0,.35);
}
div[data-testid="stExpander"] {border: 1px solid rgba(34,230,195,.25); border-radius: 12px;}
hr {border-color: rgba(34,230,195,.18) !important;}

.final {margin: 1.4rem 0 .8rem 0; padding: 1.3rem 1.5rem; border-radius: 18px;}
.final.good {border: 1px solid #19e6a1; background: linear-gradient(160deg, rgba(25,230,161,.15), rgba(25,230,161,.04));
  box-shadow: 0 0 28px rgba(25,230,161,.28), 0 10px 22px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.10);}
.final.bad {border: 1px solid #ff4d6d; background: linear-gradient(160deg, rgba(255,77,109,.16), rgba(255,77,109,.04));
  box-shadow: 0 0 28px rgba(255,77,109,.30), 0 10px 22px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.10);}
.final-title {letter-spacing: 3px; font-weight: 800; font-size: .85rem; color: #9fb2d9;}
.final-main {font-size: 1.5rem; font-weight: 700; line-height: 1.55; margin: .45rem 0 1rem 0; color: #f2f7ff;}
.final-meals {display: grid; grid-template-columns: 1fr 1fr; gap: .9rem;}
.mini {padding: .85rem 1.05rem; border-radius: 14px; font-size: 1.12rem; font-weight: 600; line-height: 1.5;}
.mini.good {border: 1px solid rgba(25,230,161,.55); background: rgba(25,230,161,.09); color: #c9ffec;}
.mini.bad {border: 1px solid rgba(255,77,109,.6); background: rgba(255,77,109,.10); color: #ffd3da;}
@media (max-width: 760px) {.final-meals {grid-template-columns: 1fr;} .final-main {font-size: 1.2rem;}}
</style>
"""
st.markdown(NEON_CSS, unsafe_allow_html=True)


def header(title: str, sub: str = "") -> None:
    st.markdown(f"<div class='hero'><h2>{html.escape(title)}</h2><p>{html.escape(sub)}</p></div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------
def _database_url() -> str:
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        url = None
    url = url or os.environ.get("DATABASE_URL") or "sqlite:///mess.db"
    url = url.strip().strip('"').strip("'")
    url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


@st.cache_resource
def engine():
    eng = create_engine(_database_url(), pool_pre_ping=True, pool_recycle=300)
    ddl = [
        "CREATE TABLE IF NOT EXISTS mm_settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
        """CREATE TABLE IF NOT EXISTS mm_meals (
            id TEXT PRIMARY KEY, mess TEXT NOT NULL, mdate TEXT NOT NULL, mtype TEXT NOT NULL,
            menu TEXT, students INTEGER, rate DOUBLE PRECISION, UNIQUE (mess, mdate, mtype))""",
        """CREATE TABLE IF NOT EXISTS mm_ingredients (
            id TEXT PRIMARY KEY, meal_id TEXT NOT NULL, category TEXT, name TEXT,
            quantity DOUBLE PRECISION, unit TEXT, unit_price DOUBLE PRECISION, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS mm_extras (
            id TEXT PRIMARY KEY, mess TEXT NOT NULL, mdate TEXT NOT NULL, mtype TEXT, category TEXT,
            description TEXT, amount DOUBLE PRECISION)""",
    ]
    with eng.begin() as c:
        for stmt in ddl:
            c.execute(text(stmt))
    # Upgrade older databases: extras now belong to a meal (LUNCH or DINNER).
    from sqlalchemy import inspect

    if "mtype" not in [col["name"] for col in inspect(eng).get_columns("mm_extras")]:
        with eng.begin() as c:
            c.execute(text("ALTER TABLE mm_extras ADD COLUMN mtype TEXT"))
    with eng.begin() as c:
        c.execute(text("UPDATE mm_extras SET mtype='LUNCH' WHERE mtype IS NULL"))
    return eng


@st.cache_data(ttl=600, show_spinner=False)
def qdf(sql: str, **params) -> pd.DataFrame:
    """Read query. Results are cached (cleared automatically after every write)."""
    with engine().connect() as c:
        return pd.read_sql(text(sql), c, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def load_all() -> dict:
    """Load every table in ONE connection. All pages filter this cached data in pandas,
    so clicking around never waits for the database (cache is cleared after each write)."""
    with engine().connect() as c:
        settings = pd.read_sql(text("SELECT k, v FROM mm_settings"), c)
        meals = pd.read_sql(text("SELECT * FROM mm_meals"), c)
        ingr_raw = pd.read_sql(text("SELECT * FROM mm_ingredients"), c)
        extras = pd.read_sql(text("SELECT * FROM mm_extras"), c)
    extras["mtype"] = extras["mtype"].fillna("LUNCH")
    link = meals[["id", "mess", "mdate", "mtype"]].rename(columns={"id": "meal_id"})
    ingr = ingr_raw.merge(link, on="meal_id", how="inner")
    return {"settings": settings, "meals": meals, "ingr_raw": ingr_raw, "ingr": ingr, "extras": extras}


def run(sql: str, **params) -> None:
    with engine().begin() as c:
        c.execute(text(sql), params)
    st.cache_data.clear()


T_MEAL = table("mm_meals", column("id"), column("mess"), column("mdate"), column("mtype"), column("menu"),
               column("students"), column("rate"))
T_ING = table("mm_ingredients", column("id"), column("meal_id"), column("category"), column("name"),
              column("quantity"), column("unit"), column("unit_price"), column("note"))
T_EXT = table("mm_extras", column("id"), column("mess"), column("mdate"), column("mtype"), column("category"),
              column("description"), column("amount"))
T_SET = table("mm_settings", column("k"), column("v"))


def uid() -> str:
    return uuid.uuid4().hex


# ----------------------------------------------------------------------
# Settings and authentication
# ----------------------------------------------------------------------
def all_settings() -> dict:
    df = load_all()["settings"]
    return dict(zip(df["k"], df["v"]))


def set_settings(values: dict) -> None:
    """Save several settings in ONE transaction (fast)."""
    if not values:
        return
    stmt = text("DELETE FROM mm_settings WHERE k IN :ks").bindparams(bindparam("ks", expanding=True))
    with engine().begin() as c:
        c.execute(stmt, {"ks": list(values.keys())})
        c.execute(insert(T_SET), [{"k": k, "v": str(v)} for k, v in values.items()])
    st.cache_data.clear()


def set_setting(key: str, value: str) -> None:
    set_settings({key: value})


def get_list(s: dict, key: str, default: list) -> list:
    try:
        arr = json.loads(s.get(key, ""))
        arr = [x.strip() for x in arr if isinstance(x, str) and x.strip()]
        return list(dict.fromkeys(arr)) or default
    except Exception:
        return default


def mess_cfg(s: dict, mess: str) -> dict:
    def num(k, d=0.0):
        try:
            return float(s.get(f"{mess}.{k}", d))
        except ValueError:
            return d

    default_name = "East Wing Mess" if mess == "EAST" else "West Wing Mess"
    return {
        "name": s.get(f"{mess}.displayName", "").strip() or default_name,
        "incharge": s.get(f"{mess}.messIncharge", ""),
        "munshi": s.get(f"{mess}.munshi", ""),
        "strength": int(num("totalStudents", 0)),
        "default_rate": num("defaultRate", 0.0),
        "budget": num("monthlyBudget", 0.0),
        "last_lunch": num("lastRateLunch", 0.0),
        "last_dinner": num("lastRateDinner", 0.0),
    }


def hash_password(pw: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def check_login(pw: str) -> bool:
    stored = all_settings().get("pw_hash")
    if stored:
        return verify_password(pw, stored)
    initial = DEFAULT_PASSWORD
    try:
        initial = st.secrets.get("APP_PASSWORD", DEFAULT_PASSWORD)
    except Exception:
        pass
    return hmac.compare_digest(pw.encode(), str(initial).encode())


def login_page():
    header("Zubair Hall Mess Manager", "Secure login")
    locked = st.session_state.get("lock_until", 0) - time.time()
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        go = st.form_submit_button("Log in", type="primary", icon=":material/login:")
    if go:
        if locked > 0:
            st.error(f"Too many wrong attempts. Try again in {int(locked)} seconds.")
        elif check_login(pw):
            st.session_state.auth = True
            st.session_state.fails = 0
            st.rerun()
        else:
            st.session_state.fails = st.session_state.get("fails", 0) + 1
            if st.session_state.fails >= 5:
                st.session_state.lock_until = time.time() + 60
                st.session_state.fails = 0
            st.error("Incorrect password.")


# ----------------------------------------------------------------------
# Calculations
# ----------------------------------------------------------------------
def money(x) -> str:
    return f"Rs. {float(x):,.0f}"


def pretty_date(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%a %d %b %Y")


@st.cache_data(ttl=600, show_spinner=False)
def build_report(mess: str, d1: str, d2: str) -> dict:
    data = load_all()

    def window(df):
        return df[(df["mess"] == mess) & (df["mdate"] >= d1) & (df["mdate"] <= d2)]

    meals = window(data["meals"]).sort_values(["mdate", "mtype"]).reset_index(drop=True)
    ingr = window(data["ingr"]).sort_values(["mdate", "mtype", "name"]).reset_index(drop=True)
    extras = window(data["extras"]).sort_values(["mdate", "category"]).reset_index(drop=True)
    ingr["amount"] = (ingr["quantity"].fillna(0) * ingr["unit_price"].fillna(0)).round(2)
    meal_cost = ingr.groupby("meal_id")["amount"].sum() if len(ingr) else pd.Series(dtype=float)
    meals["cost"] = meals["id"].map(meal_cost).fillna(0.0)
    meals["at_rate"] = (meals["students"].fillna(0) * meals["rate"].fillna(0)).round(2)

    dates = sorted(set(meals["mdate"]) | set(extras["mdate"]))
    rows = []
    for d in dates:
        m = meals[meals["mdate"] == d]
        lunch = m[m["mtype"] == "LUNCH"]
        dinner = m[m["mtype"] == "DINNER"]
        ls = int(lunch["students"].sum()) if len(lunch) else 0
        ds = int(dinner["students"].sum()) if len(dinner) else 0
        lc = float(lunch["cost"].sum())
        dc = float(dinner["cost"].sum())
        de = extras[extras["mdate"] == d]
        lx = float(de[de["mtype"] == "LUNCH"]["amount"].sum())
        dx = float(de[de["mtype"] == "DINNER"]["amount"].sum())
        ex = lx + dx
        exp = lc + dc + ex
        at = float(m["at_rate"].sum())
        rows.append({
            "date": d, "lunch_students": ls, "dinner_students": ds, "students": ls + ds,
            "lunch_cost": round(lc, 2), "dinner_cost": round(dc, 2),
            "lunch_extras": round(lx, 2), "dinner_extras": round(dx, 2), "extras": round(ex, 2),
            "expenditure": round(exp, 2), "at_rate": round(at, 2), "surplus": round(at - exp, 2),
            "cost_per_student": round(exp / (ls + ds), 2) if (ls + ds) else 0.0,
        })
    day = pd.DataFrame(rows, columns=[
        "date", "lunch_students", "dinner_students", "students", "lunch_cost", "dinner_cost",
        "lunch_extras", "dinner_extras", "extras", "expenditure", "at_rate", "surplus", "cost_per_student"])

    ing_total = float(ingr["amount"].sum())
    ex_total = float(extras["amount"].sum())
    expenditure = ing_total + ex_total
    at_rate = float(meals["at_rate"].sum())
    student_meals = int(meals["students"].sum()) if len(meals) else 0
    overall = {
        "days": len(day), "student_meals": student_meals, "ingredients": round(ing_total, 2),
        "extras": round(ex_total, 2), "expenditure": round(expenditure, 2),
        "at_rate": round(at_rate, 2), "surplus": round(at_rate - expenditure, 2),
        "avg_cost": round(expenditure / student_meals, 2) if student_meals else 0.0,
    }

    cat_rows = []
    if len(ingr):
        for c, a in ingr.groupby("category")["amount"].sum().items():
            cat_rows.append({"category": c or "Uncategorised", "type": "Ingredients", "amount": round(a, 2)})
    if len(extras):
        for c, a in extras.groupby("category")["amount"].sum().items():
            cat_rows.append({"category": c or "Uncategorised", "type": "Extra expense", "amount": round(a, 2)})
    cats = pd.DataFrame(cat_rows, columns=["category", "type", "amount"])
    if len(cats):
        cats["share_%"] = (cats["amount"] / cats["amount"].sum() * 100).round(1)
        cats = cats.sort_values("amount", ascending=False).reset_index(drop=True)
    else:
        cats["share_%"] = []

    if len(ingr):
        items = (ingr.groupby(["name", "unit"], as_index=False)
                 .agg(quantity=("quantity", "sum"), amount=("amount", "sum"))
                 .sort_values("amount", ascending=False).reset_index(drop=True))
    else:
        items = pd.DataFrame(columns=["name", "unit", "quantity", "amount"])

    return {"meals": meals, "ingr": ingr, "extras": extras, "day": day,
            "overall": overall, "cats": cats, "items": items, "from": d1, "to": d2}


# ----------------------------------------------------------------------
# Exports (Excel and PDF)
# ----------------------------------------------------------------------
def nice_day(day: pd.DataFrame) -> pd.DataFrame:
    return day.rename(columns={
        "date": "Date", "lunch_students": "Lunch students", "dinner_students": "Dinner students",
        "students": "Total students", "lunch_cost": "Lunch cost", "dinner_cost": "Dinner cost",
        "lunch_extras": "Lunch extras", "dinner_extras": "Dinner extras", "extras": "Extras", "expenditure": "Expenditure", "at_rate": "Amount at rate",
        "surplus": "Surplus / (deficit)", "cost_per_student": "Cost per student"})


def records_table(rep: dict) -> pd.DataFrame:
    ing = rep["ingr"]
    if not len(ing):
        return pd.DataFrame(columns=["Date", "Meal", "Category", "Item", "Quantity", "Unit", "Unit price", "Amount", "Note"])
    out = ing[["mdate", "mtype", "category", "name", "quantity", "unit", "unit_price", "amount", "note"]].copy()
    out.columns = ["Date", "Meal", "Category", "Item", "Quantity", "Unit", "Unit price", "Amount", "Note"]
    return out


def meal_split(rep: dict) -> pd.DataFrame:
    """Lunch / Dinner / Total: students, cost, amount at rate and saving or loss."""
    meals, extras = rep["meals"], rep["extras"]
    rows = []
    for mt, label in (("LUNCH", "Lunch"), ("DINNER", "Dinner")):
        m = meals[meals["mtype"] == mt]
        ing = float(m["cost"].sum())
        ex = float(extras[extras["mtype"] == mt]["amount"].sum())
        at = float(m["at_rate"].sum())
        rows.append({"Meal": label, "Students": int(m["students"].sum()) if len(m) else 0,
                     "Ingredients": round(ing, 2), "Extra expenses": round(ex, 2), "Expenditure": round(ing + ex, 2),
                     "Amount at rate": round(at, 2), "Saving / (loss)": round(at - ing - ex, 2)})
    df = pd.DataFrame(rows)
    tot = {"Meal": "Total"}
    for c in df.columns[1:]:
        tot[c] = df[c].sum()
    tot["Students"] = int(tot["Students"])
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def final_summary(rep: dict, label: str) -> dict:
    sp = meal_split(rep)
    L, D, T = sp.iloc[0], sp.iloc[1], sp.iloc[2]

    def verdict(x):
        return "SAVING" if float(x) >= 0 else "LOSS"

    when = f"On {pretty_date(rep['from'])}" if label == "day" else f"This {label}"
    head = (f"{when}, {int(T['Students']):,} students ate in total ({int(L['Students']):,} at lunch and "
            f"{int(D['Students']):,} at dinner). Total expenditure was {money(T['Expenditure'])} against "
            f"{money(T['Amount at rate'])} at the mess rate. "
            f"Net result: {verdict(T['Saving / (loss)'])} of {money(abs(float(T['Saving / (loss)'])))}.")
    lines = [f"{r['Meal']}: {int(r['Students']):,} students ate, expenditure {money(r['Expenditure'])}, "
             f"{verdict(r['Saving / (loss)'])} of {money(abs(float(r['Saving / (loss)'])))}." for r in (L, D)]
    return {"split": sp, "headline": head, "lines": lines, "good": float(T["Saving / (loss)"]) >= 0,
            "line_good": [float(L["Saving / (loss)"]) >= 0, float(D["Saving / (loss)"]) >= 0]}


def render_final(rep: dict, label: str) -> None:
    f = final_summary(rep, label)
    cards = "".join(f"<div class='mini {'good' if g else 'bad'}'>{html.escape(t)}</div>"
                    for t, g in zip(f["lines"], f["line_good"]))
    st.markdown(
        f"<div class='final {'good' if f['good'] else 'bad'}'><div class='final-title'>FINAL SUMMARY</div>"
        f"<div class='final-main'>{html.escape(f['headline'])}</div><div class='final-meals'>{cards}</div></div>",
        unsafe_allow_html=True)
    st.dataframe(f["split"], width="stretch", hide_index=True)


def excel_bytes(rep: dict, title: str, label: str = "period") -> bytes:
    o = rep["overall"]
    summary = pd.DataFrame([
        ("Report", title), ("Period", f"{rep['from']} to {rep['to']}"), ("Days recorded", o["days"]),
        ("Student-meals served", o["student_meals"]), ("Ingredients total (Rs.)", o["ingredients"]),
        ("Extra expenses (Rs.)", o["extras"]), ("Total expenditure (Rs.)", o["expenditure"]),
        ("Amount at rate (Rs.)", o["at_rate"]), ("Surplus / (deficit) (Rs.)", o["surplus"]),
        ("Average cost per student-meal (Rs.)", o["avg_cost"]),
    ], columns=["Item", "Value"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        fin = final_summary(rep, label)
        pd.DataFrame({"Final summary": [fin["headline"]] + fin["lines"]}).to_excel(xw, sheet_name="Final summary", index=False)
        fin["split"].to_excel(xw, sheet_name="Final summary", index=False, startrow=6)
        nice_day(rep["day"]).to_excel(xw, sheet_name="Day-wise", index=False)
        rep["cats"].to_excel(xw, sheet_name="Categories", index=False)
        rep["items"].to_excel(xw, sheet_name="Items", index=False)
        records_table(rep).to_excel(xw, sheet_name="Daily records", index=False)
        ex = rep["extras"][["mdate", "mtype", "category", "description", "amount"]] if len(rep["extras"]) else pd.DataFrame(
            columns=["mdate", "mtype", "category", "description", "amount"])
        ex.to_excel(xw, sheet_name="Extra expenses", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                if ws.title == "Final summary" and col[0].column_letter == "A":
                    width = 20
                ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 48)
    return buf.getvalue()


def pdf_bytes(rep: dict, title: str, cfg: dict, s: dict, detailed: bool, label: str = "period") -> bytes:
    from fpdf import FPDF

    def L(x) -> str:
        return str(x if x is not None else "").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(orientation="L" if detailed else "P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, L(s.get("hostelName") or "Zubair Hall"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, L(s.get("hostelLine") or "University of Engineering & Technology, Lahore"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, L(f"{cfg['name']} - {title}"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, L(f"Period: {rep['from']} to {rep['to']}"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def heading(t):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, L(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    def table(df: pd.DataFrame, widths=None):
        if not len(df):
            pdf.cell(0, 6, "No records.", new_x="LMARGIN", new_y="NEXT")
            return
        from fpdf.fonts import FontFace

        pdf.set_font("Helvetica", "", 8)
        aligns = ("LEFT",) + ("CENTER",) * (len(df.columns) - 1)
        with pdf.table(col_widths=widths, text_align=aligns, line_height=5, first_row_as_headings=True) as t:
            r = t.row()
            for c in df.columns:
                r.cell(L(c), style=FontFace(emphasis="BOLD"))
            for row in df.astype(object).itertuples(index=False):
                r = t.row()
                for v in row:
                    if isinstance(v, float):
                        v = f"{v:,.2f}"
                    elif isinstance(v, int):
                        v = f"{v:,}"
                    r.cell(L(v))
        pdf.set_font("Helvetica", "", 9)

    o = rep["overall"]
    heading("Overall summary")
    table(pd.DataFrame([
        ["Days recorded", o["days"]], ["Student-meals served", o["student_meals"]],
        ["Ingredients total (Rs.)", o["ingredients"]], ["Extra expenses (Rs.)", o["extras"]],
        ["Total expenditure (Rs.)", o["expenditure"]], ["Amount at rate (Rs.)", o["at_rate"]],
        ["Surplus / (deficit) (Rs.)", o["surplus"]], ["Average cost per student-meal (Rs.)", o["avg_cost"]],
    ], columns=["Item", "Value"], dtype=object), widths=(110, 50) if not detailed else (150, 60))

    heading("Day-wise summary")
    d = nice_day(rep["day"])
    if not detailed:
        d = d[["Date", "Lunch students", "Dinner students", "Total students", "Expenditure", "Amount at rate", "Surplus / (deficit)"]]
    table(d)

    heading("Category-wise expenditure")
    table(rep["cats"].rename(columns={"category": "Category", "type": "Type", "amount": "Amount", "share_%": "Share %"}))

    if detailed:
        heading("Item-wise consolidated usage")
        table(rep["items"].rename(columns={"name": "Item", "unit": "Unit", "quantity": "Quantity", "amount": "Amount"}))
        heading("Daily records (every ingredient row)")
        table(records_table(rep).drop(columns=["Note"]))
    else:
        for mt in ["LUNCH", "DINNER"]:
            sub = rep["ingr"][rep["ingr"]["mtype"] == mt]
            heading(f"{mt.title()} ingredients (consolidated)")
            if len(sub):
                g = sub.groupby(["name", "unit"], as_index=False).agg(Quantity=("quantity", "sum"), Amount=("amount", "sum"))
                table(g.rename(columns={"name": "Item", "unit": "Unit"}))
            else:
                table(pd.DataFrame())
    for mt in ["LUNCH", "DINNER"]:
        heading(f"{mt.title()} extra expenses")
        sub = rep["extras"][rep["extras"]["mtype"] == mt]
        table(sub[["mdate", "category", "description", "amount"]].rename(
            columns={"mdate": "Date", "category": "Category", "description": "Description", "amount": "Amount"})
            if len(sub) else pd.DataFrame())

    fin = final_summary(rep, label)
    if pdf.get_y() > pdf.h - 95:
        pdf.add_page()
    pdf.ln(4)
    green, red = (4, 120, 87), (185, 28, 28)
    w_all = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_draw_color(*(green if fin["good"] else red))
    pdf.set_line_width(0.7)
    pdf.set_text_color(*(green if fin["good"] else red))
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(w_all, 6, "FINAL SUMMARY", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(w_all, 7, L(fin["headline"]), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for text_line, good in zip(fin["lines"], fin["line_good"]):
        pdf.set_text_color(*(green if good else red))
        pdf.set_draw_color(*(green if good else red))
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(w_all, 7, L(text_line), border=1, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.ln(2)
    table(fin["split"])
    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.ln(14)
    pdf.set_font("Helvetica", "", 9)
    w = (pdf.w - pdf.l_margin - pdf.r_margin) / 3
    for label, who in [("Mess Incharge", cfg["incharge"]), ("Munshi", cfg["munshi"]), ("Resident Tutor", s.get("residentTutor", ""))]:
        pdf.cell(w, 5, "______________________", align="C")
    pdf.ln(5)
    for label, who in [("Mess Incharge", cfg["incharge"]), ("Munshi", cfg["munshi"]), ("Resident Tutor", s.get("residentTutor", ""))]:
        pdf.cell(w, 5, L(f"{label}{': ' + who if who else ''}"), align="C")
    return bytes(pdf.output())


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
def chart_title(t):
    st.markdown(f"**{t}**")


def date_axis(title=""):
    return alt.X("date:N", title=title, sort=None, axis=alt.Axis(labelAngle=-45))


def page_dashboard(mess, cfg):
    header("Dashboard", cfg["name"])
    today = dt.date.today()
    c1, c2, _ = st.columns([1, 1, 4])
    year = c1.number_input("Year", 2020, 2100, today.year, step=1)
    month = c2.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                         format_func=lambda m: dt.date(2000, m, 1).strftime("%B"))
    first = dt.date(int(year), int(month), 1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    rep = build_report(mess, first.isoformat(), last.isoformat())
    day, o = rep["day"], rep["overall"]

    if day.empty:
        st.info("No records for this month. Add entries in Daily Entry, or load sample data from Settings > Data and password.")
        return

    prev_end = first - dt.timedelta(days=1)
    po = build_report(mess, prev_end.replace(day=1).isoformat(), prev_end.isoformat())["overall"]
    has_prev = po["days"] > 0

    def dl(cur, old, rs=True):
        if not has_prev:
            return None
        return f"{cur - old:+,.0f}"

    k = st.columns(3) + st.columns(3)
    k[0].metric("Total expenditure", money(o["expenditure"]), dl(o["expenditure"], po["expenditure"]), delta_color="inverse",
                help="Change compared with the previous month")
    k[1].metric("Amount at rate", money(o["at_rate"]), dl(o["at_rate"], po["at_rate"]))
    k[2].metric("Surplus" if o["surplus"] >= 0 else "Deficit", money(abs(o["surplus"])), dl(o["surplus"], po["surplus"]))
    k[3].metric("Days recorded", o["days"])
    k[4].metric("Student-meals", f"{o['student_meals']:,}", dl(o["student_meals"], po["student_meals"]))
    k[5].metric("Avg cost / student-meal", money(o["avg_cost"]), dl(o["avg_cost"], po["avg_cost"]), delta_color="inverse")

    if cfg["budget"] > 0:
        ratio = o["expenditure"] / cfg["budget"]
        st.progress(min(ratio, 1.0), text=f"Monthly budget used: {ratio * 100:.0f}% ({money(o['expenditure'])} of {money(cfg['budget'])})")
        if ratio >= 1:
            st.error(f"Budget exceeded by {money(o['expenditure'] - cfg['budget'])}.")
        elif ratio >= 0.9:
            st.warning("More than 90% of the monthly budget is already used.")

    st.divider()
    long = day.melt(id_vars="date", value_vars=["at_rate", "expenditure"], var_name="series", value_name="rs")
    long["series"] = long["series"].map({"at_rate": "Amount at rate", "expenditure": "Expenditure"})
    a, b = st.columns(2)
    with a:
        chart_title("Daily expenditure vs amount at rate")
        st.altair_chart(alt.Chart(long).mark_line(point=True).encode(
            x=date_axis(), y=alt.Y("rs:Q", title="Rs."),
            color=alt.Color("series:N", scale=alt.Scale(range=[GREEN, AMBER]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["date", "series", alt.Tooltip("rs:Q", format=",.0f")]).properties(height=300), width="stretch")
    with b:
        chart_title("Daily attendance (lunch vs dinner)")
        att = day.melt(id_vars="date", value_vars=["lunch_students", "dinner_students"], var_name="meal", value_name="count")
        att["meal"] = att["meal"].map({"lunch_students": "Lunch", "dinner_students": "Dinner"})
        st.altair_chart(alt.Chart(att).mark_bar().encode(
            x=date_axis(), y=alt.Y("count:Q", title="Students"),
            color=alt.Color("meal:N", scale=alt.Scale(domain=["Lunch", "Dinner"], range=[GREEN, BLUE]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["date", "meal", "count"]).properties(height=300), width="stretch")

    a, b = st.columns(2)
    with a:
        chart_title("Daily surplus / deficit")
        st.altair_chart(alt.Chart(day).mark_bar().encode(
            x=date_axis(), y=alt.Y("surplus:Q", title="Rs."),
            color=alt.condition(alt.datum.surplus >= 0, alt.value(GREEN), alt.value(RED)),
            tooltip=["date", alt.Tooltip("surplus:Q", format=",.0f")]).properties(height=300), width="stretch")
    with b:
        chart_title("Daily expenditure split (lunch and dinner, ingredients and extras)")
        sp = day.melt(id_vars="date", value_vars=["lunch_cost", "lunch_extras", "dinner_cost", "dinner_extras"], var_name="part", value_name="rs")
        sp["part"] = sp["part"].map({"lunch_cost": "Lunch ingredients", "lunch_extras": "Lunch extras",
                                     "dinner_cost": "Dinner ingredients", "dinner_extras": "Dinner extras"})
        st.altair_chart(alt.Chart(sp).mark_bar().encode(
            x=date_axis(), y=alt.Y("rs:Q", title="Rs."),
            color=alt.Color("part:N", scale=alt.Scale(domain=["Lunch ingredients", "Lunch extras", "Dinner ingredients", "Dinner extras"], range=[GREEN, AMBER, BLUE, PINK]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["date", "part", alt.Tooltip("rs:Q", format=",.0f")]).properties(height=300), width="stretch")

    a, b = st.columns(2)
    with a:
        chart_title("Cost per student-meal (daily trend)")
        st.altair_chart(alt.Chart(day).mark_line(point=True, color=BLUE).encode(
            x=date_axis(), y=alt.Y("cost_per_student:Q", title="Rs. per student"),
            tooltip=["date", alt.Tooltip("cost_per_student:Q", format=",.1f")]).properties(height=300), width="stretch")
    with b:
        chart_title("Spending share by category")
        cat = rep["cats"].groupby("category", as_index=False)["amount"].sum()
        st.altair_chart(alt.Chart(cat).mark_arc(innerRadius=60).encode(
            theta="amount:Q", color=alt.Color("category:N", legend=alt.Legend(orient="right", title=None)),
            tooltip=["category", alt.Tooltip("amount:Q", format=",.0f")]).properties(height=300), width="stretch")

    a, b = st.columns(2)
    with a:
        chart_title("Category-wise spending")
        st.altair_chart(alt.Chart(cat).mark_bar(color=GREEN).encode(
            y=alt.Y("category:N", sort="-x", title=None), x=alt.X("amount:Q", title="Rs."),
            tooltip=["category", alt.Tooltip("amount:Q", format=",.0f")]).properties(height=320), width="stretch")
    with b:
        chart_title("Top 10 items by spending")
        top = rep["items"].head(10)
        st.altair_chart(alt.Chart(top).mark_bar(color=AMBER).encode(
            y=alt.Y("name:N", sort="-x", title=None), x=alt.X("amount:Q", title="Rs."),
            tooltip=["name", "unit", alt.Tooltip("quantity:Q", format=",.1f"), alt.Tooltip("amount:Q", format=",.0f")]).properties(height=320),
            width="stretch")


def clean_ingredients(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["category", "name", "unit", "note"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    for c in ["quantity", "unit_price"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df[df["name"] != ""].reset_index(drop=True)


def save_meal(mess, dstr, mtype, menu, students, rate, ing, ex, rate_key):
    """Save one meal (meal row, ingredients, extras, last rate) in a single fast transaction."""
    mid = uid()
    ing_rows = [{"id": uid(), "meal_id": mid, "category": r["category"], "name": r["name"], "quantity": float(r["quantity"]),
                 "unit": r["unit"], "unit_price": float(r["unit_price"]), "note": r["note"]} for _, r in ing.iterrows()]
    ex_rows = [{"id": uid(), "mess": mess, "mdate": dstr, "mtype": mtype, "category": r["category"] or "Other",
                "description": r["description"], "amount": float(r["amount"])} for _, r in ex.iterrows()]
    p = {"m": mess, "d": dstr, "t": mtype}
    with engine().begin() as c:
        c.execute(text("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t)"), p)
        c.execute(text("DELETE FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t"), p)
        c.execute(text("DELETE FROM mm_extras WHERE mess=:m AND mdate=:d AND mtype=:t"), p)
        c.execute(insert(T_MEAL), [{"id": mid, "mess": mess, "mdate": dstr, "mtype": mtype, "menu": menu.strip(),
                                    "students": int(students), "rate": float(rate)}])
        if ing_rows:
            c.execute(insert(T_ING), ing_rows)
        if ex_rows:
            c.execute(insert(T_EXT), ex_rows)
        c.execute(text("DELETE FROM mm_settings WHERE k=:k"), {"k": rate_key})
        c.execute(insert(T_SET), [{"k": rate_key, "v": str(rate)}])
    st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False)
def frequent_items(mess: str) -> pd.DataFrame:
    ig = load_all()["ingr"]
    df = ig[ig["mess"] == mess][["name", "category", "unit", "unit_price", "mdate"]].sort_values("mdate", ascending=False)
    if df.empty:
        return pd.DataFrame(columns=["name", "category", "unit", "unit_price", "uses"])
    latest = df.drop_duplicates("name", keep="first").set_index("name")
    out = latest[["category", "unit", "unit_price"]].copy()
    out["uses"] = df.groupby("name").size()
    return out.sort_values("uses", ascending=False).head(60).reset_index()


@st.fragment
def meal_editor(mess, cfg, s, dstr, mtype):
    label = mtype.title()
    item_cats = get_list(s, "itemCategories", ITEM_CATEGORIES)
    units = get_list(s, "units", UNITS)
    ver_key = f"ver_{mess}_{dstr}_{mtype}"
    ver = st.session_state.get(ver_key, 0)
    seed_key = f"seed_{mess}_{dstr}_{mtype}"

    data = load_all()
    mm, ia = data["meals"], data["ingr_raw"]
    ing_cols = ["category", "name", "quantity", "unit", "unit_price", "note"]
    meal = mm[(mm["mess"] == mess) & (mm["mdate"] == dstr) & (mm["mtype"] == mtype)]
    if len(meal):
        ing0 = ia[ia["meal_id"] == meal.iloc[0]["id"]][ing_cols].sort_values("name").reset_index(drop=True)
        menu0, students0, rate0 = meal.iloc[0]["menu"] or "", int(meal.iloc[0]["students"] or 0), float(meal.iloc[0]["rate"] or 0)
    else:
        ing0 = pd.DataFrame(columns=["category", "name", "quantity", "unit", "unit_price", "note"])
        menu0, students0 = "", 0
        rate0 = cfg["last_lunch"] if mtype == "LUNCH" else cfg["last_dinner"]
        rate0 = rate0 or cfg["default_rate"]
    if seed_key in st.session_state:
        ing0 = st.session_state[seed_key]

    top = st.columns([3, 1, 1])
    menu = top[0].text_input(f"{label} menu", menu0, key=f"menu_{ver_key}")
    students = top[1].number_input("Students who ate", 0, 100000, students0, step=1, key=f"stu_{ver_key}")
    rate = top[2].number_input("Rate per student (Rs.)", 0.0, 100000.0, float(rate0), step=5.0, key=f"rate_{ver_key}")

    if st.button(f"Copy items from previous day ({label})", key=f"copy_{ver_key}", icon=":material/content_copy:"):
        prev = mm[(mm["mess"] == mess) & (mm["mtype"] == mtype) & (mm["mdate"] < dstr)].sort_values("mdate", ascending=False)
        if len(prev):
            st.session_state[seed_key] = ia[ia["meal_id"] == prev.iloc[0]["id"]][ing_cols].sort_values("name").reset_index(drop=True)
            st.session_state[ver_key] = ver + 1
            st.rerun()
        else:
            st.warning(f"No earlier {label.lower()} record found.")

    ea = data["extras"]
    ex0 = ea[(ea["mess"] == mess) & (ea["mdate"] == dstr) & (ea["mtype"] == mtype)][
        ["category", "description", "amount"]].sort_values("category").reset_index(drop=True)
    exp_cats = get_list(s, "expenseCategories", EXPENSE_CATEGORIES)
    cat_opts = item_cats + [c for c in ing0["category"].dropna().unique() if c not in item_cats]
    unit_opts = units + [u for u in ing0["unit"].dropna().unique() if u not in units]
    edited = st.data_editor(
        ing0, num_rows="dynamic", width="stretch", key=f"ed_{ver_key}_{ver}",
        column_config={
            "category": st.column_config.SelectboxColumn("Category", options=cat_opts, width="medium"),
            "name": st.column_config.TextColumn("Item", width="medium"),
            "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, format="%.2f"),
            "unit": st.column_config.SelectboxColumn("Unit", options=unit_opts),
            "unit_price": st.column_config.NumberColumn("Unit price (Rs.)", min_value=0.0, format="%.2f"),
            "note": st.column_config.TextColumn("Vendor / note"),
        })
    ing = clean_ingredients(edited)
    ing_cost = float((ing["quantity"] * ing["unit_price"]).sum())

    freq = frequent_items(mess)
    if len(freq):
        with st.expander("⚡ Quick add frequent items (uses the last price)"):
            picked = st.multiselect("Items", freq["name"].tolist(), key=f"qa_{ver_key}_{ver}", placeholder="Choose items")
            if st.button("Add selected items", key=f"qab_{ver_key}", icon=":material/playlist_add:") and picked:
                add = freq[freq["name"].isin(picked)][["category", "name", "unit", "unit_price"]].copy()
                add["quantity"], add["note"] = 0.0, ""
                add = add[["category", "name", "quantity", "unit", "unit_price", "note"]]
                add = add[~add["name"].isin(ing["name"])]
                st.session_state[seed_key] = pd.concat([ing, add], ignore_index=True)
                st.session_state[ver_key] = ver + 1
                st.rerun()

    st.markdown(f"**Extra expenses for {label}** (gas, salaries, repairs, transport...)")
    ex_opts = exp_cats + [c for c in ex0["category"].dropna().unique() if c not in exp_cats]
    ex_edit = st.data_editor(
        ex0, num_rows="dynamic", width="stretch", key=f"edx_{ver_key}_{ver}",
        column_config={
            "category": st.column_config.SelectboxColumn("Category", options=ex_opts),
            "description": st.column_config.TextColumn("Description", width="large"),
            "amount": st.column_config.NumberColumn("Amount (Rs.)", min_value=0.0, format="%.2f"),
        })
    ex = ex_edit.copy()
    ex["amount"] = pd.to_numeric(ex["amount"], errors="coerce").fillna(0.0)
    ex["description"] = ex["description"].fillna("").astype(str).str.strip()
    ex["category"] = ex["category"].fillna("").astype(str).str.strip()
    ex = ex[(ex["amount"] > 0) | (ex["description"] != "")].reset_index(drop=True)
    ex_cost = float(ex["amount"].sum())

    cost = ing_cost + ex_cost
    at_rate = students * rate
    m = st.columns(5)
    m[0].metric("Ingredients", money(ing_cost))
    m[1].metric("Extra expenses", money(ex_cost))
    m[2].metric("Amount at rate", money(at_rate))
    m[3].metric("Surplus / (deficit)", money(at_rate - cost))
    m[4].metric("Cost per student", money(cost / students) if students else "-")
    if students == 0:
        st.warning("Students count is 0 - attendance is missing.")
    if len(ing[ing["unit_price"] == 0]):
        st.warning("Some items have no unit price.")

    if st.button(f"Save {label} (meal and extra expenses)", type="primary", key=f"save_{ver_key}", icon=":material/save:"):
        save_meal(mess, dstr, mtype, menu, students, rate, ing, ex, f"{mess}.lastRate{label}")
        st.session_state.pop(seed_key, None)
        st.session_state[ver_key] = ver + 1
        st.session_state["flash"] = f"{label} saved for {pretty_date(dstr)}."
        st.rerun()


def page_entry(mess, cfg, s):
    header("Daily Entry", f"{cfg['name']} - lunch, dinner and extra expenses")
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    d = st.date_input("Date", value=st.session_state.get("entry_date", dt.date.today()), key="entry_date_widget")
    st.session_state["entry_date"] = d
    dstr = d.isoformat()
    t1, t2 = st.tabs(["Lunch", "Dinner"])
    with t1:
        meal_editor(mess, cfg, s, dstr, "LUNCH")
    with t2:
        meal_editor(mess, cfg, s, dstr, "DINNER")


def open_in_entry(dstr):
    st.session_state["entry_date"] = dt.date.fromisoformat(dstr)
    st.session_state["page"] = "Daily Entry"


def page_records(mess, cfg):
    header("Records", f"{cfg['name']} - browse, open or delete past days")
    today = dt.date.today()
    c1, c2, _ = st.columns([1, 1, 4])
    year = c1.number_input("Year", 2020, 2100, today.year, step=1, key="rec_year")
    month = c2.selectbox("Month", list(range(1, 13)), index=today.month - 1, key="rec_month",
                         format_func=lambda m: dt.date(2000, m, 1).strftime("%B"))
    first = dt.date(int(year), int(month), 1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    rep = build_report(mess, first.isoformat(), last.isoformat())
    if rep["day"].empty:
        st.info("No records in this month.")
        return
    st.dataframe(nice_day(rep["day"]), width="stretch", hide_index=True)
    pick = st.selectbox("Select a day", rep["day"]["date"].tolist(), format_func=pretty_date)
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.button("Open in Daily Entry", on_click=open_in_entry, args=(pick,), icon=":material/edit_note:")
    confirm = c3.checkbox("I confirm I want to delete this day", key=f"conf_{pick}")
    if c2.button("Delete this day", disabled=not confirm, icon=":material/delete:"):
        run("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate=:d)", m=mess, d=pick)
        run("DELETE FROM mm_meals WHERE mess=:m AND mdate=:d", m=mess, d=pick)
        run("DELETE FROM mm_extras WHERE mess=:m AND mdate=:d", m=mess, d=pick)
        st.success(f"Deleted {pretty_date(pick)}.")
        st.rerun()


def summary_text(rep: dict, cfg: dict, s: dict, label: str = "period") -> str:
    o, day = rep["overall"], rep["day"]
    lines = [
        f"*{s.get('hostelName') or 'Zubair Hall'} - {cfg['name']}*",
        f"Period: {pretty_date(rep['from'])} to {pretty_date(rep['to'])}",
        f"Days recorded: {o['days']}  |  Student-meals: {o['student_meals']:,}",
        f"Lunch avg: {day['lunch_students'].mean():.0f}  |  Dinner avg: {day['dinner_students'].mean():.0f}",
        f"Ingredients: {money(o['ingredients'])}",
        f"Extra expenses: {money(o['extras'])}",
        f"Total expenditure: {money(o['expenditure'])}",
        f"Amount at rate: {money(o['at_rate'])}",
        f"{'Surplus' if o['surplus'] >= 0 else 'Deficit'}: {money(abs(o['surplus']))}",
        f"Average cost per student-meal: {money(o['avg_cost'])}",
    ]
    top = rep["cats"].groupby("category")["amount"].sum().sort_values(ascending=False).head(3)
    if len(top):
        lines.append("Top spending: " + ", ".join(f"{c} {money(a)}" for c, a in top.items()))
    fin = final_summary(rep, label)
    lines += ["", "*FINAL SUMMARY*", fin["headline"]] + fin["lines"]
    return "\n".join(lines)


@st.cache_data(ttl=600, show_spinner=False)
def report_xlsx(mess: str, d1: str, d2: str, title: str, label: str) -> bytes:
    return excel_bytes(build_report(mess, d1, d2), title, label)


@st.cache_data(ttl=600, show_spinner=False)
def report_pdf(mess: str, d1: str, d2: str, detailed: bool, label: str) -> bytes:
    st_ = all_settings()
    return pdf_bytes(build_report(mess, d1, d2), "Detailed Report" if detailed else "Short Report",
                     mess_cfg(st_, mess), st_, detailed, label)


def page_reports(mess, cfg, s):
    header("Reports", f"{cfg['name']} - short and detailed reports with Excel and PDF")
    c1, c2, c3 = st.columns(3)
    kind = c1.radio("Report type", ["Short report", "Detailed report"], horizontal=True)
    period = c2.radio("Period", ["Single day", "Week (Mon-Sun)", "Month", "Custom range"], horizontal=True)
    ref = c3.date_input("Date", value=dt.date.today(), key="rep_date")
    if period == "Single day":
        d1 = d2 = ref
    elif period == "Week (Mon-Sun)":
        d1 = ref - dt.timedelta(days=ref.weekday())
        d2 = d1 + dt.timedelta(days=6)
    elif period == "Month":
        d1 = ref.replace(day=1)
        d2 = (d1.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    else:
        rng = st.date_input("From - to", value=(ref - dt.timedelta(days=6), ref), key="rep_range")
        if not isinstance(rng, tuple) or len(rng) != 2:
            st.info("Select both start and end dates.")
            return
        d1, d2 = rng
    detailed = kind == "Detailed report"
    label = {"Single day": "day", "Week (Mon-Sun)": "week", "Month": "month"}.get(period, "period")
    rep = build_report(mess, d1.isoformat(), d2.isoformat())
    st.caption(f"Period: {pretty_date(d1.isoformat())} to {pretty_date(d2.isoformat())}")
    if rep["day"].empty:
        st.info("No records in this period.")
        return
    o = rep["overall"]
    k = st.columns(5)
    k[0].metric("Expenditure", money(o["expenditure"]))
    k[1].metric("Amount at rate", money(o["at_rate"]))
    k[2].metric("Surplus / (deficit)", money(o["surplus"]))
    k[3].metric("Student-meals", f"{o['student_meals']:,}")
    k[4].metric("Avg cost / student-meal", money(o["avg_cost"]))

    with st.expander("📋 Text summary for WhatsApp (tap the copy icon)"):
        st.code(summary_text(rep, cfg, s, label), language=None, wrap_lines=True)

    st.markdown("**Day-wise summary**")
    dd = nice_day(rep["day"])
    if not detailed:
        dd = dd[["Date", "Lunch students", "Dinner students", "Total students", "Expenditure", "Amount at rate", "Surplus / (deficit)"]]
    st.dataframe(dd, width="stretch", hide_index=True)
    st.markdown("**Category-wise expenditure**")
    st.dataframe(rep["cats"], width="stretch", hide_index=True)
    if detailed:
        st.markdown("**Item-wise consolidated usage**")
        st.dataframe(rep["items"], width="stretch", hide_index=True)
        st.markdown("**Daily records (every ingredient row)**")
        st.dataframe(records_table(rep), width="stretch", hide_index=True)
    else:
        for mt in ["LUNCH", "DINNER"]:
            st.markdown(f"**{mt.title()} ingredients (consolidated)**")
            sub = rep["ingr"][rep["ingr"]["mtype"] == mt]
            if len(sub):
                st.dataframe(sub.groupby(["name", "unit"], as_index=False).agg(quantity=("quantity", "sum"), amount=("amount", "sum")),
                             width="stretch", hide_index=True)
            else:
                st.caption("No records.")
    for mt in ["LUNCH", "DINNER"]:
        st.markdown(f"**{mt.title()} extra expenses**")
        sub = rep["extras"][rep["extras"]["mtype"] == mt]
        if len(sub):
            st.dataframe(sub[["mdate", "category", "description", "amount"]], width="stretch", hide_index=True)
        else:
            st.caption("No records.")

    render_final(rep, label)

    title = "Detailed Report" if detailed else "Short Report"
    fname = f"{mess.lower()}-{'detailed' if detailed else 'short'}-{d1}-to-{d2}"
    e1, e2 = st.columns(2)
    e1.download_button("Download Excel", report_xlsx(mess, d1.isoformat(), d2.isoformat(), title, label), f"{fname}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_view:")
    e2.download_button("Download PDF", report_pdf(mess, d1.isoformat(), d2.isoformat(), detailed, label), f"{fname}.pdf",
                       "application/pdf", icon=":material/picture_as_pdf:")


SAMPLE_ITEMS = {
    "LUNCH": [("Grains & Flour", "Rice", "kg", 280), ("Meat & Chicken", "Chicken", "kg", 650), ("Vegetables", "Onion", "kg", 120),
              ("Oil & Spices", "Cooking oil", "litre", 520), ("Dairy & Eggs", "Yogurt", "kg", 240)],
    "DINNER": [("Grains & Flour", "Flour (atta)", "kg", 140), ("Vegetables", "Potato", "kg", 90), ("Vegetables", "Tomato", "kg", 110),
               ("Dairy & Eggs", "Eggs", "dozen", 330), ("Oil & Spices", "Spices", "packet", 180)],
}


def load_sample(mess, cfg):
    rnd = random.Random(42)
    today = dt.date.today()
    dates = [(today - dt.timedelta(days=9 - i)).isoformat() for i in range(10)]
    meals, ings, exs = [], [], []
    for d in dates:
        for mt, menu in [("LUNCH", "Chicken Pulao"), ("DINNER", "Aloo Anda Curry")]:
            mid = uid()
            students = rnd.randint(150, 190)
            meals.append({"id": mid, "mess": mess, "mdate": d, "mtype": mt, "menu": menu, "students": students,
                          "rate": 130.0 if mt == "LUNCH" else 110.0})
            for cat, name, unit, price in SAMPLE_ITEMS[mt]:
                q = round(students * rnd.uniform(0.035, 0.06), 1) if unit != "packet" else rnd.randint(8, 14)
                ings.append({"id": uid(), "meal_id": mid, "category": cat, "name": name, "quantity": float(q), "unit": unit,
                             "unit_price": float(round(price * rnd.uniform(0.95, 1.08), 2)), "note": ""})
        for mt, cat, desc, amount in [("LUNCH", "Gas", "LPG cylinder", rnd.choice([0, 0, 3200, 3400])),
                                      ("DINNER", "Transport", "Vegetable transport", rnd.choice([0, 500, 800]))]:
            if amount:
                exs.append({"id": uid(), "mess": mess, "mdate": d, "mtype": mt, "category": cat,
                            "description": desc, "amount": float(amount)})
    ds = bindparam("ds", expanding=True)
    with engine().begin() as c:
        c.execute(text("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate IN :ds)").bindparams(ds),
                  {"m": mess, "ds": dates})
        c.execute(text("DELETE FROM mm_meals WHERE mess=:m AND mdate IN :ds").bindparams(ds), {"m": mess, "ds": dates})
        c.execute(text("DELETE FROM mm_extras WHERE mess=:m AND mdate IN :ds").bindparams(ds), {"m": mess, "ds": dates})
        c.execute(insert(T_MEAL), meals)
        c.execute(insert(T_ING), ings)
        if exs:
            c.execute(insert(T_EXT), exs)
    st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False)
def backup_json() -> bytes:
    d = load_all()
    data = {
        "settings": d["settings"][d["settings"]["k"] != "pw_hash"].to_dict("records"),
        "meals": d["meals"].to_dict("records"),
        "ingredients": d["ingr_raw"].to_dict("records"),
        "extras": d["extras"].to_dict("records"),
        "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    return json.dumps(data, indent=2, default=str).encode()


@st.cache_data(ttl=600, show_spinner=False)
def full_excel(mess: str, name: str) -> bytes:
    return excel_bytes(build_report(mess, "2000-01-01", "2100-12-31"), f"All data - {name}")


def mark_backup() -> None:
    set_setting("lastBackup", dt.date.today().isoformat())


def restore_json(raw: bytes) -> None:
    data = json.loads(raw)
    for k in ["settings", "meals", "ingredients", "extras"]:
        if k not in data:
            raise ValueError(f"Backup file is missing '{k}'.")

    def pick(rows, tbl, fix=None):
        names = [c.name for c in tbl.c]
        out = []
        for r in rows:
            r = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()}
            if fix:
                r = fix(r)
            out.append({n: r.get(n) for n in names})
        return out

    sets = [r for r in data["settings"] if r.get("k") != "pw_hash"]
    meals = pick(data["meals"], T_MEAL)
    ings = pick(data["ingredients"], T_ING)
    exs = pick(data["extras"], T_EXT, fix=lambda r: {**r, "mtype": r.get("mtype") or "LUNCH"})
    with engine().begin() as c:
        for t in ("mm_ingredients", "mm_meals", "mm_extras"):
            c.execute(text(f"DELETE FROM {t}"))
        c.execute(text("DELETE FROM mm_settings WHERE k <> 'pw_hash'"))
        if sets:
            c.execute(insert(T_SET), pick(sets, T_SET))
        if meals:
            c.execute(insert(T_MEAL), meals)
        if ings:
            c.execute(insert(T_ING), ings)
        if exs:
            c.execute(insert(T_EXT), exs)
    st.cache_data.clear()


def page_analytics(mess, cfg):
    header("Analytics", f"{cfg['name']} - trends, weekday patterns and item price tracker")
    span = st.radio("Period", [30, 60, 90, 180], horizontal=True, format_func=lambda n: f"Last {n} days")
    end = dt.date.today()
    rep = build_report(mess, (end - dt.timedelta(days=span - 1)).isoformat(), end.isoformat())
    day = rep["day"]
    if day.empty:
        st.info("No records in this period.")
        return
    d = day.copy()
    d["dt"] = pd.to_datetime(d["date"])
    d["weekday"] = d["dt"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    a, b = st.columns(2)
    with a:
        chart_title("Average students per day, by weekday")
        wk = d.groupby("weekday", as_index=False).agg(avg_students=("students", "mean"))
        st.altair_chart(alt.Chart(wk).mark_bar(color=BLUE).encode(
            x=alt.X("weekday:N", sort=order, title=None), y=alt.Y("avg_students:Q", title="Students"),
            tooltip=["weekday", alt.Tooltip("avg_students:Q", format=".0f")]).properties(height=300), width="stretch")
    with b:
        chart_title("Weekly cost per student-meal")
        d["week"] = d["dt"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date().isoformat())
        w = d.groupby("week", as_index=False).agg(exp=("expenditure", "sum"), stu=("students", "sum"))
        w["cost_per_student"] = (w["exp"] / w["stu"].where(w["stu"] > 0)).round(2)
        st.altair_chart(alt.Chart(w).mark_line(point=True, color=GREEN).encode(
            x=alt.X("week:N", title="Week starting", sort=None), y=alt.Y("cost_per_student:Q", title="Rs."),
            tooltip=["week", alt.Tooltip("cost_per_student:Q", format=",.1f")]).properties(height=300), width="stretch")

    st.markdown("**Item price tracker**")
    ing = rep["ingr"]
    if ing.empty:
        st.caption("No ingredient records in this period.")
    else:
        pick = st.selectbox("Item", sorted(ing["name"].unique()))
        ser = ing[ing["name"] == pick].groupby("mdate", as_index=False).agg(price=("unit_price", "mean"), qty=("quantity", "sum"))
        unit = ing[ing["name"] == pick]["unit"].iloc[0]
        m = st.columns(4)
        m[0].metric("Latest price", f"Rs. {ser['price'].iloc[-1]:,.1f} / {unit}")
        m[1].metric("Lowest", f"Rs. {ser['price'].min():,.1f}")
        m[2].metric("Highest", f"Rs. {ser['price'].max():,.1f}")
        first_p = ser["price"].iloc[0]
        m[3].metric("Change since first", f"{(ser['price'].iloc[-1] - first_p) / first_p * 100:+.1f}%" if first_p else "-")
        st.altair_chart(alt.Chart(ser).mark_line(point=True, color=AMBER).encode(
            x=alt.X("mdate:N", title=None, sort=None, axis=alt.Axis(labelAngle=-45)), y=alt.Y("price:Q", title=f"Rs. per {unit}"),
            tooltip=["mdate", alt.Tooltip("price:Q", format=",.1f"), alt.Tooltip("qty:Q", format=",.1f")]).properties(height=280),
            width="stretch")

    a, b = st.columns(2)
    nd = nice_day(day)[["Date", "Total students", "Expenditure", "Amount at rate", "Surplus / (deficit)"]]
    with a:
        st.markdown("**Highest spending days**")
        st.dataframe(nd.sort_values("Expenditure", ascending=False).head(5), width="stretch", hide_index=True)
    with b:
        st.markdown("**Best surplus days**")
        st.dataframe(nd.sort_values("Surplus / (deficit)", ascending=False).head(5), width="stretch", hide_index=True)


def page_settings(mess, cfg, s):
    header("Settings", "Staff, lists, budget, password and data")
    t1, t2, t3 = st.tabs(["Mess and staff", "Lists", "Data and password"])
    with t1:
        with st.form("shared"):
            st.markdown("**Hostel (shared by both messes)**")
            hn = st.text_input("Hostel name", s.get("hostelName", "Zubair Hall"))
            hl = st.text_input("Hostel line", s.get("hostelLine", "University of Engineering & Technology, Lahore"))
            rt = st.text_input("Resident Tutor", s.get("residentTutor", ""))
            if st.form_submit_button("Save hostel details", icon=":material/save:"):
                set_settings({"hostelName": hn, "hostelLine": hl, "residentTutor": rt})
                st.success("Saved.")
                st.rerun()
        with st.form("messform"):
            st.markdown(f"**{cfg['name']}**")
            name = st.text_input("Display name", s.get(f"{mess}.displayName", ""), placeholder=cfg["name"])
            inc = st.text_input("Mess Incharge", cfg["incharge"])
            mun = st.text_input("Munshi", cfg["munshi"])
            c1, c2, c3 = st.columns(3)
            strength = c1.number_input("Mess strength (students)", 0, 100000, cfg["strength"])
            rate = c2.number_input("Default rate per student (Rs.)", 0.0, 100000.0, cfg["default_rate"], step=5.0)
            budget = c3.number_input("Monthly budget (Rs., 0 = off)", 0.0, 100000000.0, cfg["budget"], step=1000.0)
            if st.form_submit_button("Save mess details", icon=":material/save:"):
                set_settings({f"{mess}.{k}": v for k, v in [("displayName", name), ("messIncharge", inc), ("munshi", mun),
                                                            ("totalStudents", strength), ("defaultRate", rate), ("monthlyBudget", budget)]})
                st.success("Saved.")
                st.rerun()
    with t2:
        with st.form("lists"):
            ic = st.text_area("Item categories (one per line)", "\n".join(get_list(s, "itemCategories", ITEM_CATEGORIES)), height=160)
            ec = st.text_area("Extra expense categories (one per line)", "\n".join(get_list(s, "expenseCategories", EXPENSE_CATEGORIES)), height=140)
            un = st.text_area("Units (one per line)", "\n".join(get_list(s, "units", UNITS)), height=140)
            if st.form_submit_button("Save lists", icon=":material/save:"):
                set_settings({key: json.dumps([x.strip() for x in raw.splitlines() if x.strip()])
                              for key, raw in [("itemCategories", ic), ("expenseCategories", ec), ("units", un)]})
                st.success("Saved.")
                st.rerun()
    with t3:
        st.markdown("**Change password**")
        with st.form("pw"):
            cur = st.text_input("Current password", type="password")
            new = st.text_input("New password (min 8 characters)", type="password")
            new2 = st.text_input("Repeat new password", type="password")
            if st.form_submit_button("Change password", icon=":material/key:"):
                if not check_login(cur):
                    st.error("Current password is incorrect.")
                elif len(new) < 8:
                    st.error("New password must be at least 8 characters.")
                elif new != new2:
                    st.error("New passwords do not match.")
                else:
                    set_setting("pw_hash", hash_password(new))
                    st.success("Password changed.")
        st.divider()
        st.markdown("**Backup and restore**")
        st.caption("Your data lives in the Neon database. Download a backup once a month and keep it on your phone or Google Drive.")
        st.download_button("Download full backup (JSON)", backup_json(), f"mess-backup-{dt.date.today()}.json", "application/json",
                           on_click=mark_backup, icon=":material/cloud_download:")
        up = st.file_uploader("Restore from backup file (replaces all current data)", type="json")
        if up is not None and st.checkbox("I understand this replaces all current data"):
            if st.button("Restore now", icon=":material/restore:"):
                try:
                    restore_json(up.getvalue())
                    st.success("Backup restored.")
                except Exception as e:
                    st.error(f"Could not restore: {e}")
        st.download_button(f"Export all {cfg['name']} data to Excel", full_excel(mess, cfg["name"]), f"{mess.lower()}-all-data.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_view:")
        st.divider()
        st.markdown("**Sample data and reset**")
        if st.button(f"Load 10-day sample data into {cfg['name']}", icon=":material/science:"):
            load_sample(mess, cfg)
            st.success("Sample data loaded.")
        word = st.text_input("Type DELETE to clear ALL meals and expenses of both messes")
        if st.button("Clear all data", disabled=word != "DELETE", icon=":material/delete_forever:"):
            with engine().begin() as c:
                for t in ("mm_ingredients", "mm_meals", "mm_extras"):
                    c.execute(text(f"DELETE FROM {t}"))
            st.cache_data.clear()
            st.success("All records deleted.")


# ----------------------------------------------------------------------
# App shell
# ----------------------------------------------------------------------
def go_page(name: str) -> None:
    st.session_state["page"] = name


NAV = [("Dashboard", ":material/space_dashboard:"), ("Daily Entry", ":material/edit_note:"),
       ("Records", ":material/folder_open:"), ("Reports", ":material/summarize:"),
       ("Analytics", ":material/insights:"), ("Settings", ":material/settings:")]


def main():
    try:
        engine()
    except Exception as e:
        st.error("Could not connect to the database. Check DATABASE_URL in the app secrets.")
        msg = str(e)
        st.code(msg[:1500], wrap_lines=True)
        url = _database_url()
        if "*" in url.split("@")[0]:
            st.warning("The password in DATABASE_URL contains '*' characters. In Neon, click 'Show password' "
                       "before copying the connection string, so the real password is copied.")
        elif "password authentication failed" in msg:
            st.warning("Neon rejected the password. In Neon, use 'Reset password' and copy the new connection string.")
        st.stop()
    if not st.session_state.get("auth"):
        login_page()
        return
    s = all_settings()
    with st.sidebar:
        st.markdown(f"<div class='brand'>{html.escape(s.get('hostelName') or 'Zubair Hall')}</div>"
                    "<div class='brand-sub'>Mess Manager</div>", unsafe_allow_html=True)
        names = {m: mess_cfg(s, m)["name"] for m in MESS_KEYS}
        mess = st.selectbox("Mess", MESS_KEYS, format_func=lambda m: names[m])
        st.write("")
        page = st.session_state.setdefault("page", "Dashboard")
        for name, icon in NAV:
            st.button(name, icon=icon, key=f"nav_{name}", type="primary" if page == name else "secondary",
                      width="stretch", on_click=go_page, args=(name,))
        st.divider()
        last = s.get("lastBackup")
        try:
            age = (dt.date.today() - dt.date.fromisoformat(last)).days if last else None
        except ValueError:
            age = None
        if age is None:
            st.caption("No backup downloaded yet.")
        elif age >= 7:
            st.caption(f"Last backup: {age} days ago. Please back up.")
        else:
            st.caption(f"Last backup: {age} day(s) ago.")
        st.download_button("Backup now", backup_json(), f"mess-backup-{dt.date.today()}.json", "application/json",
                           on_click=mark_backup, icon=":material/cloud_download:", width="stretch")
        st.button("Refresh data", icon=":material/refresh:", on_click=st.cache_data.clear, width="stretch")
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            st.session_state.clear()
            st.rerun()
        try:
            if st.context.theme.type != "dark":
                st.warning("For the neon dark look, add the file .streamlit/config.toml to the GitHub repo.")
        except Exception:
            pass
    cfg = mess_cfg(s, mess)
    page = st.session_state["page"]
    if page == "Dashboard":
        page_dashboard(mess, cfg)
    elif page == "Daily Entry":
        page_entry(mess, cfg, s)
    elif page == "Records":
        page_records(mess, cfg)
    elif page == "Reports":
        page_reports(mess, cfg, s)
    elif page == "Analytics":
        page_analytics(mess, cfg)
    else:
        page_settings(mess, cfg, s)


main()
