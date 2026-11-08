"""Zubair Hall Mess Manager (Streamlit edition).

Mess register and reports for the East Wing and West Wing messes of
Zubair Hall, UET Lahore. Data is stored in PostgreSQL (Neon) when
DATABASE_URL is provided, otherwise in a local SQLite file.
"""
import datetime as dt
import hashlib
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
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Zubair Hall Mess Manager", page_icon="🍽️", layout="wide")

GREEN, AMBER, RED, BLUE = "#047857", "#B45309", "#DC2626", "#1D4ED8"
MESS_KEYS = ["EAST", "WEST"]
DEFAULT_PASSWORD = "Hadi2750"
ITEM_CATEGORIES = ["Grains & Flour", "Meat & Chicken", "Vegetables", "Dairy & Eggs", "Oil & Spices", "Fuel / Gas", "Other"]
EXPENSE_CATEGORIES = ["Gas", "Salaries", "Repairs", "Transport", "Utilities", "Other"]
UNITS = ["kg", "g", "litre", "ml", "dozen", "piece", "packet", "bag"]

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; max-width: 1400px;}
    div[data-testid="stMetric"] {background: rgba(128,128,128,0.08); padding: 0.7rem 0.9rem; border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)


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
            id TEXT PRIMARY KEY, mess TEXT NOT NULL, mdate TEXT NOT NULL, category TEXT,
            description TEXT, amount DOUBLE PRECISION)""",
    ]
    with eng.begin() as c:
        for stmt in ddl:
            c.execute(text(stmt))
    return eng


def qdf(sql: str, **params) -> pd.DataFrame:
    with engine().connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def run(sql: str, **params) -> None:
    with engine().begin() as c:
        c.execute(text(sql), params)


def uid() -> str:
    return uuid.uuid4().hex


# ----------------------------------------------------------------------
# Settings and authentication
# ----------------------------------------------------------------------
def all_settings() -> dict:
    df = qdf("SELECT k, v FROM mm_settings")
    return dict(zip(df["k"], df["v"]))


def set_setting(key: str, value: str) -> None:
    run(
        "INSERT INTO mm_settings (k, v) VALUES (:k, :v) "
        "ON CONFLICT (k) DO UPDATE SET v = excluded.v",
        k=key,
        v=value,
    )


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
    st.title("🍽️ Zubair Hall Mess Manager")
    st.caption("Please log in to continue.")
    locked = st.session_state.get("lock_until", 0) - time.time()
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        go = st.form_submit_button("Log in", type="primary")
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


def build_report(mess: str, d1: str, d2: str) -> dict:
    meals = qdf(
        "SELECT * FROM mm_meals WHERE mess=:m AND mdate>=:a AND mdate<=:b ORDER BY mdate, mtype",
        m=mess, a=d1, b=d2,
    )
    ingr = qdf(
        "SELECT i.*, m.mdate, m.mtype FROM mm_ingredients i JOIN mm_meals m ON m.id=i.meal_id "
        "WHERE m.mess=:m AND m.mdate>=:a AND m.mdate<=:b ORDER BY m.mdate, m.mtype, i.name",
        m=mess, a=d1, b=d2,
    )
    extras = qdf(
        "SELECT * FROM mm_extras WHERE mess=:m AND mdate>=:a AND mdate<=:b ORDER BY mdate, category",
        m=mess, a=d1, b=d2,
    )
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
        ex = float(extras[extras["mdate"] == d]["amount"].sum())
        exp = lc + dc + ex
        at = float(m["at_rate"].sum())
        rows.append({
            "date": d, "lunch_students": ls, "dinner_students": ds, "students": ls + ds,
            "lunch_cost": round(lc, 2), "dinner_cost": round(dc, 2), "extras": round(ex, 2),
            "expenditure": round(exp, 2), "at_rate": round(at, 2), "surplus": round(at - exp, 2),
            "cost_per_student": round(exp / (ls + ds), 2) if (ls + ds) else 0.0,
        })
    day = pd.DataFrame(rows, columns=[
        "date", "lunch_students", "dinner_students", "students", "lunch_cost", "dinner_cost",
        "extras", "expenditure", "at_rate", "surplus", "cost_per_student"])

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
        "extras": "Extras", "expenditure": "Expenditure", "at_rate": "Amount at rate",
        "surplus": "Surplus / (deficit)", "cost_per_student": "Cost per student"})


def records_table(rep: dict) -> pd.DataFrame:
    ing = rep["ingr"]
    if not len(ing):
        return pd.DataFrame(columns=["Date", "Meal", "Category", "Item", "Quantity", "Unit", "Unit price", "Amount", "Note"])
    out = ing[["mdate", "mtype", "category", "name", "quantity", "unit", "unit_price", "amount", "note"]].copy()
    out.columns = ["Date", "Meal", "Category", "Item", "Quantity", "Unit", "Unit price", "Amount", "Note"]
    return out


def excel_bytes(rep: dict, title: str) -> bytes:
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
        nice_day(rep["day"]).to_excel(xw, sheet_name="Day-wise", index=False)
        rep["cats"].to_excel(xw, sheet_name="Categories", index=False)
        rep["items"].to_excel(xw, sheet_name="Items", index=False)
        records_table(rep).to_excel(xw, sheet_name="Daily records", index=False)
        ex = rep["extras"][["mdate", "category", "description", "amount"]] if len(rep["extras"]) else pd.DataFrame(
            columns=["mdate", "category", "description", "amount"])
        ex.to_excel(xw, sheet_name="Extra expenses", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 48)
    return buf.getvalue()


def pdf_bytes(rep: dict, title: str, cfg: dict, s: dict, detailed: bool) -> bytes:
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
    heading("Extra expenses")
    table(rep["extras"][["mdate", "category", "description", "amount"]].rename(
        columns={"mdate": "Date", "category": "Category", "description": "Description", "amount": "Amount"})
        if len(rep["extras"]) else pd.DataFrame())

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
    st.subheader(f"Dashboard - {cfg['name']}")
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
        st.info("No records for this month. Add entries in Daily Entry, or load sample data from Settings > Data.")
        return

    k = st.columns(6)
    k[0].metric("Total expenditure", money(o["expenditure"]))
    k[1].metric("Amount at rate", money(o["at_rate"]))
    k[2].metric("Surplus" if o["surplus"] >= 0 else "Deficit", money(abs(o["surplus"])))
    k[3].metric("Days recorded", o["days"])
    k[4].metric("Student-meals", f"{o['student_meals']:,}")
    k[5].metric("Avg cost / student-meal", money(o["avg_cost"]))

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
            color=alt.Color("meal:N", scale=alt.Scale(range=[GREEN, BLUE]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["date", "meal", "count"]).properties(height=300), width="stretch")

    a, b = st.columns(2)
    with a:
        chart_title("Daily surplus / deficit")
        st.altair_chart(alt.Chart(day).mark_bar().encode(
            x=date_axis(), y=alt.Y("surplus:Q", title="Rs."),
            color=alt.condition(alt.datum.surplus >= 0, alt.value(GREEN), alt.value(RED)),
            tooltip=["date", alt.Tooltip("surplus:Q", format=",.0f")]).properties(height=300), width="stretch")
    with b:
        chart_title("Daily expenditure split (lunch, dinner, extras)")
        sp = day.melt(id_vars="date", value_vars=["lunch_cost", "dinner_cost", "extras"], var_name="part", value_name="rs")
        sp["part"] = sp["part"].map({"lunch_cost": "Lunch", "dinner_cost": "Dinner", "extras": "Extras"})
        st.altair_chart(alt.Chart(sp).mark_bar().encode(
            x=date_axis(), y=alt.Y("rs:Q", title="Rs."),
            color=alt.Color("part:N", scale=alt.Scale(range=[GREEN, BLUE, AMBER]), legend=alt.Legend(orient="bottom", title=None)),
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


def meal_editor(mess, cfg, s, dstr, mtype):
    label = mtype.title()
    item_cats = get_list(s, "itemCategories", ITEM_CATEGORIES)
    units = get_list(s, "units", UNITS)
    ver_key = f"ver_{mess}_{dstr}_{mtype}"
    ver = st.session_state.get(ver_key, 0)
    seed_key = f"seed_{mess}_{dstr}_{mtype}"

    meal = qdf("SELECT * FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t", m=mess, d=dstr, t=mtype)
    if len(meal):
        ing0 = qdf("SELECT category, name, quantity, unit, unit_price, note FROM mm_ingredients WHERE meal_id=:i ORDER BY name",
                   i=meal.iloc[0]["id"])
        menu0, students0, rate0 = meal.iloc[0]["menu"] or "", int(meal.iloc[0]["students"] or 0), float(meal.iloc[0]["rate"] or 0)
    else:
        ing0 = pd.DataFrame(columns=["category", "name", "quantity", "unit", "unit_price", "note"])
        menu0, students0 = "", 0
        rate0 = cfg["last_lunch"] if mtype == "LUNCH" else cfg["last_dinner"]
        rate0 = rate0 or cfg["default_rate"]
    if seed_key in st.session_state:
        ing0 = st.session_state[seed_key]

    top = st.columns([3, 1, 1])
    menu = top[0].text_input(f"{label} menu", menu0, key=f"menu_{ver_key}_{ver}")
    students = top[1].number_input("Students who ate", 0, 100000, students0, step=1, key=f"stu_{ver_key}_{ver}")
    rate = top[2].number_input("Rate per student (Rs.)", 0.0, 100000.0, float(rate0), step=5.0, key=f"rate_{ver_key}_{ver}")

    if st.button(f"Copy items from previous day ({label})", key=f"copy_{ver_key}"):
        prev = qdf(
            "SELECT id FROM mm_meals WHERE mess=:m AND mtype=:t AND mdate<:d ORDER BY mdate DESC LIMIT 1",
            m=mess, t=mtype, d=dstr)
        if len(prev):
            st.session_state[seed_key] = qdf(
                "SELECT category, name, quantity, unit, unit_price, note FROM mm_ingredients WHERE meal_id=:i ORDER BY name",
                i=prev.iloc[0]["id"])
            st.session_state[ver_key] = ver + 1
            st.rerun()
        else:
            st.warning(f"No earlier {label.lower()} record found.")

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
    cost = float((ing["quantity"] * ing["unit_price"]).sum())
    at_rate = students * rate
    m = st.columns(4)
    m[0].metric("Ingredients cost", money(cost))
    m[1].metric("Amount at rate", money(at_rate))
    m[2].metric("Surplus / (deficit)", money(at_rate - cost))
    m[3].metric("Cost per student", money(cost / students) if students else "-")
    if students == 0:
        st.warning("Students count is 0 - attendance is missing.")
    if len(ing[ing["unit_price"] == 0]):
        st.warning("Some items have no unit price.")

    if st.button(f"Save {label}", type="primary", key=f"save_{ver_key}"):
        run("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t)",
            m=mess, d=dstr, t=mtype)
        run("DELETE FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t", m=mess, d=dstr, t=mtype)
        mid = uid()
        run("INSERT INTO mm_meals (id, mess, mdate, mtype, menu, students, rate) VALUES (:i,:m,:d,:t,:menu,:s,:r)",
            i=mid, m=mess, d=dstr, t=mtype, menu=menu.strip(), s=int(students), r=float(rate))
        for _, r in ing.iterrows():
            run("INSERT INTO mm_ingredients (id, meal_id, category, name, quantity, unit, unit_price, note) "
                "VALUES (:i,:mid,:c,:n,:q,:u,:p,:no)",
                i=uid(), mid=mid, c=r["category"], n=r["name"], q=float(r["quantity"]), u=r["unit"],
                p=float(r["unit_price"]), no=r["note"])
        set_setting(f"{mess}.lastRate{label}", str(rate))
        st.session_state.pop(seed_key, None)
        st.session_state[ver_key] = ver + 1
        st.session_state["flash"] = f"{label} saved for {pretty_date(dstr)}."
        st.rerun()


def extras_editor(mess, s, dstr):
    cats = get_list(s, "expenseCategories", EXPENSE_CATEGORIES)
    ver_key = f"ver_x_{mess}_{dstr}"
    ver = st.session_state.get(ver_key, 0)
    ex0 = qdf("SELECT category, description, amount FROM mm_extras WHERE mess=:m AND mdate=:d ORDER BY category", m=mess, d=dstr)
    opts = cats + [c for c in ex0["category"].dropna().unique() if c not in cats]
    edited = st.data_editor(
        ex0, num_rows="dynamic", width="stretch", key=f"edx_{ver_key}_{ver}",
        column_config={
            "category": st.column_config.SelectboxColumn("Category", options=opts),
            "description": st.column_config.TextColumn("Description", width="large"),
            "amount": st.column_config.NumberColumn("Amount (Rs.)", min_value=0.0, format="%.2f"),
        })
    e = edited.copy()
    e["amount"] = pd.to_numeric(e["amount"], errors="coerce").fillna(0.0)
    e = e[(e["amount"] > 0) | (e["description"].fillna("") != "")]
    st.metric("Extra expenses total", money(e["amount"].sum()))
    if st.button("Save extra expenses", type="primary", key=f"savex_{ver_key}"):
        run("DELETE FROM mm_extras WHERE mess=:m AND mdate=:d", m=mess, d=dstr)
        for _, r in e.iterrows():
            run("INSERT INTO mm_extras (id, mess, mdate, category, description, amount) VALUES (:i,:m,:d,:c,:de,:a)",
                i=uid(), m=mess, d=dstr, c=(r["category"] or "Other"), de=(r["description"] or ""), a=float(r["amount"]))
        st.session_state[ver_key] = ver + 1
        st.session_state["flash"] = f"Extra expenses saved for {pretty_date(dstr)}."
        st.rerun()


def page_entry(mess, cfg, s):
    st.subheader(f"Daily Entry - {cfg['name']}")
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    d = st.date_input("Date", value=st.session_state.get("entry_date", dt.date.today()), key="entry_date_widget")
    st.session_state["entry_date"] = d
    dstr = d.isoformat()
    t1, t2, t3 = st.tabs(["Lunch", "Dinner", "Extra expenses"])
    with t1:
        meal_editor(mess, cfg, s, dstr, "LUNCH")
    with t2:
        meal_editor(mess, cfg, s, dstr, "DINNER")
    with t3:
        extras_editor(mess, s, dstr)


def open_in_entry(dstr):
    st.session_state["entry_date"] = dt.date.fromisoformat(dstr)
    st.session_state["nav"] = "Daily Entry"


def page_records(mess, cfg):
    st.subheader(f"Records - {cfg['name']}")
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
    c1.button("Open in Daily Entry", on_click=open_in_entry, args=(pick,))
    confirm = c3.checkbox("I confirm I want to delete this day", key=f"conf_{pick}")
    if c2.button("Delete this day", disabled=not confirm):
        run("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate=:d)", m=mess, d=pick)
        run("DELETE FROM mm_meals WHERE mess=:m AND mdate=:d", m=mess, d=pick)
        run("DELETE FROM mm_extras WHERE mess=:m AND mdate=:d", m=mess, d=pick)
        st.success(f"Deleted {pretty_date(pick)}.")
        st.rerun()


def page_reports(mess, cfg, s):
    st.subheader(f"Reports - {cfg['name']}")
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
    st.markdown("**Extra expenses**")
    st.dataframe(rep["extras"][["mdate", "category", "description", "amount"]] if len(rep["extras"]) else pd.DataFrame(),
                 width="stretch", hide_index=True)

    title = "Detailed Report" if detailed else "Short Report"
    fname = f"{mess.lower()}-{'detailed' if detailed else 'short'}-{d1}-to-{d2}"
    e1, e2 = st.columns(2)
    e1.download_button("Download Excel", excel_bytes(rep, title), f"{fname}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    e2.download_button("Download PDF", pdf_bytes(rep, title, cfg, s, detailed), f"{fname}.pdf", "application/pdf")


SAMPLE_ITEMS = {
    "LUNCH": [("Grains & Flour", "Rice", "kg", 280), ("Meat & Chicken", "Chicken", "kg", 650), ("Vegetables", "Onion", "kg", 120),
              ("Oil & Spices", "Cooking oil", "litre", 520), ("Dairy & Eggs", "Yogurt", "kg", 240)],
    "DINNER": [("Grains & Flour", "Flour (atta)", "kg", 140), ("Vegetables", "Potato", "kg", 90), ("Vegetables", "Tomato", "kg", 110),
               ("Dairy & Eggs", "Eggs", "dozen", 330), ("Oil & Spices", "Spices", "packet", 180)],
}


def load_sample(mess, cfg):
    rnd = random.Random(42)
    today = dt.date.today()
    for i in range(10):
        d = (today - dt.timedelta(days=9 - i)).isoformat()
        for mt, menu in [("LUNCH", "Chicken Pulao"), ("DINNER", "Aloo Anda Curry")]:
            run("DELETE FROM mm_ingredients WHERE meal_id IN (SELECT id FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t)", m=mess, d=d, t=mt)
            run("DELETE FROM mm_meals WHERE mess=:m AND mdate=:d AND mtype=:t", m=mess, d=d, t=mt)
            mid = uid()
            students = rnd.randint(150, 190)
            run("INSERT INTO mm_meals (id, mess, mdate, mtype, menu, students, rate) VALUES (:i,:m,:d,:t,:menu,:s,:r)",
                i=mid, m=mess, d=d, t=mt, menu=menu, s=students, r=130.0 if mt == "LUNCH" else 110.0)
            for cat, name, unit, price in SAMPLE_ITEMS[mt]:
                q = round(students * rnd.uniform(0.035, 0.06), 1) if unit != "packet" else rnd.randint(8, 14)
                run("INSERT INTO mm_ingredients (id, meal_id, category, name, quantity, unit, unit_price, note) VALUES (:i,:mid,:c,:n,:q,:u,:p,'')",
                    i=uid(), mid=mid, c=cat, n=name, q=float(q), u=unit, p=float(price * rnd.uniform(0.95, 1.08)))
        run("DELETE FROM mm_extras WHERE mess=:m AND mdate=:d", m=mess, d=d)
        run("INSERT INTO mm_extras (id, mess, mdate, category, description, amount) VALUES (:i,:m,:d,'Gas','LPG cylinder',:a)",
            i=uid(), m=mess, d=d, a=float(rnd.choice([0, 0, 3200, 3400])))


def backup_json() -> bytes:
    data = {
        "settings": qdf("SELECT k, v FROM mm_settings WHERE k <> 'pw_hash'").to_dict("records"),
        "meals": qdf("SELECT * FROM mm_meals").to_dict("records"),
        "ingredients": qdf("SELECT * FROM mm_ingredients").to_dict("records"),
        "extras": qdf("SELECT * FROM mm_extras").to_dict("records"),
        "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    return json.dumps(data, indent=2, default=str).encode()


def restore_json(raw: bytes) -> None:
    data = json.loads(raw)
    for k in ["settings", "meals", "ingredients", "extras"]:
        if k not in data:
            raise ValueError(f"Backup file is missing '{k}'.")
    run("DELETE FROM mm_ingredients")
    run("DELETE FROM mm_meals")
    run("DELETE FROM mm_extras")
    run("DELETE FROM mm_settings WHERE k <> 'pw_hash'")
    for r in data["settings"]:
        set_setting(r["k"], r["v"])
    for r in data["meals"]:
        run("INSERT INTO mm_meals (id, mess, mdate, mtype, menu, students, rate) VALUES (:id,:mess,:mdate,:mtype,:menu,:students,:rate)", **r)
    for r in data["ingredients"]:
        r = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()}
        run("INSERT INTO mm_ingredients (id, meal_id, category, name, quantity, unit, unit_price, note) VALUES (:id,:meal_id,:category,:name,:quantity,:unit,:unit_price,:note)", **r)
    for r in data["extras"]:
        run("INSERT INTO mm_extras (id, mess, mdate, category, description, amount) VALUES (:id,:mess,:mdate,:category,:description,:amount)", **r)


def page_settings(mess, cfg, s):
    st.subheader("Settings")
    t1, t2, t3 = st.tabs(["Mess and staff", "Lists", "Data and password"])
    with t1:
        with st.form("shared"):
            st.markdown("**Hostel (shared by both messes)**")
            hn = st.text_input("Hostel name", s.get("hostelName", "Zubair Hall"))
            hl = st.text_input("Hostel line", s.get("hostelLine", "University of Engineering & Technology, Lahore"))
            rt = st.text_input("Resident Tutor", s.get("residentTutor", ""))
            if st.form_submit_button("Save hostel details"):
                set_setting("hostelName", hn); set_setting("hostelLine", hl); set_setting("residentTutor", rt)
                st.success("Saved."); st.rerun()
        with st.form("messform"):
            st.markdown(f"**{cfg['name']}**")
            name = st.text_input("Display name", s.get(f"{mess}.displayName", ""), placeholder=cfg["name"])
            inc = st.text_input("Mess Incharge", cfg["incharge"])
            mun = st.text_input("Munshi", cfg["munshi"])
            c1, c2 = st.columns(2)
            strength = c1.number_input("Mess strength (students)", 0, 100000, cfg["strength"])
            rate = c2.number_input("Default rate per student (Rs.)", 0.0, 100000.0, cfg["default_rate"], step=5.0)
            if st.form_submit_button("Save mess details"):
                for k, v in [("displayName", name), ("messIncharge", inc), ("munshi", mun), ("totalStudents", strength), ("defaultRate", rate)]:
                    set_setting(f"{mess}.{k}", str(v))
                st.success("Saved."); st.rerun()
    with t2:
        with st.form("lists"):
            ic = st.text_area("Item categories (one per line)", "\n".join(get_list(s, "itemCategories", ITEM_CATEGORIES)), height=160)
            ec = st.text_area("Extra expense categories (one per line)", "\n".join(get_list(s, "expenseCategories", EXPENSE_CATEGORIES)), height=140)
            un = st.text_area("Units (one per line)", "\n".join(get_list(s, "units", UNITS)), height=140)
            if st.form_submit_button("Save lists"):
                for key, raw in [("itemCategories", ic), ("expenseCategories", ec), ("units", un)]:
                    set_setting(key, json.dumps([x.strip() for x in raw.splitlines() if x.strip()]))
                st.success("Saved."); st.rerun()
    with t3:
        st.markdown("**Change password**")
        with st.form("pw"):
            cur = st.text_input("Current password", type="password")
            new = st.text_input("New password (min 8 characters)", type="password")
            new2 = st.text_input("Repeat new password", type="password")
            if st.form_submit_button("Change password"):
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
        st.download_button("Download full backup (JSON)", backup_json(), f"mess-backup-{dt.date.today()}.json", "application/json")
        up = st.file_uploader("Restore from backup file (replaces all current data)", type="json")
        if up is not None and st.checkbox("I understand this replaces all current data"):
            if st.button("Restore now"):
                try:
                    restore_json(up.getvalue())
                    st.success("Backup restored.")
                except Exception as e:
                    st.error(f"Could not restore: {e}")
        full = build_report(mess, "2000-01-01", "2100-12-31")
        st.download_button(f"Export all {cfg['name']} data to Excel", excel_bytes(full, "All data"), f"{mess.lower()}-all-data.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.divider()
        st.markdown("**Sample data and reset**")
        if st.button(f"Load 10-day sample data into {cfg['name']}"):
            load_sample(mess, cfg)
            st.success("Sample data loaded.")
        word = st.text_input("Type DELETE to clear ALL meals and expenses of both messes")
        if st.button("Clear all data", disabled=word != "DELETE"):
            run("DELETE FROM mm_ingredients"); run("DELETE FROM mm_meals"); run("DELETE FROM mm_extras")
            st.success("All records deleted.")


# ----------------------------------------------------------------------
# App shell
# ----------------------------------------------------------------------
def main():
    try:
        engine()
    except Exception as e:
        st.error("Could not connect to the database. Check DATABASE_URL in the app secrets.")
        st.code(str(e)[:400])
        st.stop()
    if not st.session_state.get("auth"):
        login_page()
        return
    s = all_settings()
    with st.sidebar:
        st.markdown(f"### {s.get('hostelName', 'Zubair Hall')}")
        names = {m: mess_cfg(s, m)["name"] for m in MESS_KEYS}
        mess = st.selectbox("Mess", MESS_KEYS, format_func=lambda m: names[m])
        page = st.radio("Menu", ["Dashboard", "Daily Entry", "Records", "Reports", "Settings"], key="nav")
        st.divider()
        if st.button("Log out"):
            st.session_state.clear()
            st.rerun()
    cfg = mess_cfg(s, mess)
    if page == "Dashboard":
        page_dashboard(mess, cfg)
    elif page == "Daily Entry":
        page_entry(mess, cfg, s)
    elif page == "Records":
        page_records(mess, cfg)
    elif page == "Reports":
        page_reports(mess, cfg, s)
    else:
        page_settings(mess, cfg, s)


main()
