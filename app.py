import html
import io
import os
import pickle
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Distributors Account", page_icon="📊", layout="wide")

PKT = ZoneInfo("Asia/Karachi")
DATA_DIR = "data"
DATA_PATH = os.path.join(DATA_DIR, "processed.pkl")
os.makedirs(DATA_DIR, exist_ok=True)

QTY_LABELS = ["Br", "Lim", "A", "B", "C", "6x4", "V", "Vin"]


# ------------------------------------------------------------------ helpers
def get_secret(name, default):
    try:
        return st.secrets[name]
    except Exception:
        return default


def clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def num(v):
    v = clean(v)
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def as_text(v):
    v = clean(v)
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def as_date(v):
    v = clean(v)
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d-%m-%Y")
    return str(v).strip()


def short_num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def money(v):
    return f"{v:,.0f}"


def rate(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def signed(v):
    return f"+{v:,.0f}" if v > 0 else (f"-{abs(v):,.0f}" if v < 0 else "0")


def details_lines(r):
    """Line 1: V.No. Veh. GP   |   Line 2: Qty@Rate"""
    parts = []
    if r["V.No"]:
        parts.append(r["V.No"])
    if r["Veh"]:
        parts.append(f"Veh {r['Veh']}" if r["Veh"].replace(" ", "").isdigit() else r["Veh"])
    if r["GP"]:
        parts.append(f"GP {r['GP']}")
    line1 = ". ".join(parts)
    rt = r["Rate"]
    rt = None if rt is None or pd.isna(rt) else short_num(rt)
    if r["Qty"] and rt:
        line2 = f"{r['Qty']}@{rt}"
    else:
        line2 = r["Qty"] or (f"@{rt}" if rt else "")
    return [x for x in (line1, line2) if x]


def ledger_html(df):
    """Statement ki table: mobile par bina scroll ke fit ho (text wrap hota hai)."""
    esc = html.escape
    cell = (
        "padding:6px 5px;vertical-align:top;border-bottom:1px solid rgba(128,128,128,0.3);"
        "overflow-wrap:anywhere;"
    )
    head = (
        "padding:7px 5px;text-align:left;background:#f0f2f6;color:#31333f;"
        "position:sticky;top:0;"
    )
    right = "text-align:right;"
    out = [
        '<div style="max-height:600px;overflow-y:auto;overflow-x:hidden;'
        'border:1px solid rgba(128,128,128,0.3);border-radius:6px;">',
        '<table style="width:100%;border-collapse:collapse;font-size:13px;line-height:1.35;">',
        "<thead><tr>"
        f'<th style="{head}">Date</th>'
        f'<th style="{head}">Details</th>'
        f'<th style="{head}{right}">Amount</th>'
        f'<th style="{head}{right}">Balance</th>'
        "</tr></thead><tbody>",
    ]
    for r in df.to_dict("records"):
        dr, cr = r["Debit"], r["Credit"]
        dr_ok, cr_ok = pd.notna(dr), pd.notna(cr)
        amt_html = ""
        if dr_ok or cr_ok:
            amt = (dr if dr_ok else 0) - (cr if cr_ok else 0)
            color = "#e53935" if amt > 0 else ("#2e9e4f" if amt < 0 else "inherit")
            amt_html = f'<span style="color:{color};font-weight:600;">{signed(amt)}</span>'
        bal = r["Balance"]
        bal_txt = "" if pd.isna(bal) else f"{bal:,.0f}"
        d = r["Date"]
        if len(d) == 10 and d[2] == "-" and d[5] == "-":
            d = d[:6] + d[8:]  # 26-02-2026 -> 26-02-26
        lines = []
        if r["Particulars"]:
            lines.append(f'<b style="font-weight:600;">{esc(r["Particulars"])}</b>')
        lines += [f'<span style="opacity:0.85;">{esc(x)}</span>' for x in details_lines(r)]
        out.append(
            "<tr>"
            f'<td style="{cell}white-space:nowrap;">{esc(d)}</td>'
            f'<td style="{cell}">{"<br>".join(lines)}</td>'
            f'<td style="{cell}{right}white-space:nowrap;">{amt_html}</td>'
            f'<td style="{cell}{right}white-space:nowrap;">{bal_txt}</td>'
            "</tr>"
        )
    out.append("</tbody></table></div>")
    return "".join(out)


# ------------------------------------------------------------------ parsing
def parse_summary(raw):
    report_date = ""
    for v in raw.iloc[0].tolist():
        if isinstance(v, str) and v.strip().lower().startswith("date"):
            report_date = v.split(":", 1)[-1].strip()

    rows = []
    for r in raw.reindex(columns=range(6)).iloc[2:].values.tolist():
        name = clean(r[1])
        if not isinstance(name, str) or not name.strip():
            continue
        sno = num(r[0])
        rows.append(
            {
                "S.No": int(sno) if sno is not None else None,
                "Party": name.strip(),
                "City": as_text(r[2]),
                "Sales": num(r[3]),
                "Received": num(r[4]),
                "Total Balance": num(r[5]),
            }
        )
    df = pd.DataFrame(
        rows, columns=["S.No", "Party", "City", "Sales", "Received", "Total Balance"]
    )
    df["S.No"] = df["S.No"].astype("Int64")
    return df, report_date


def parse_ledger(raw, sheet_id):
    raw = raw.reindex(columns=range(18))
    name = clean(raw.iat[0, 1]) if raw.shape[0] > 0 else None
    name = name.strip() if isinstance(name, str) and name.strip() else f"Party {sheet_id}"

    body = raw.iloc[3:].astype(object).values.tolist()
    rows, total = [], None
    for r in body:
        first = clean(r[0])
        if isinstance(first, str) and first.strip().lower() == "total":
            total = {"debit": num(r[14]), "credit": num(r[15]), "balance": num(r[16])}
            break
        dr, cr, bal = num(r[14]), num(r[15]), num(r[16])
        has_text = any(as_text(x) for x in (r[0], r[1], r[2]))
        if not has_text and dr is None and cr is None:
            continue  # sirf balance dohrane wali khali rows
        qty = []
        for label, v in zip(QTY_LABELS, r[5:13]):
            q = num(v)
            if q:
                qty.append(f"{label} {short_num(q)}")
        rows.append(
            {
                "Date": as_date(r[0]),
                "Particulars": as_text(r[1]),
                "V.No": as_text(r[2]),
                "Veh": as_text(r[3]),
                "GP": as_text(r[4]),
                "Qty": ", ".join(qty),
                "Rate": num(r[13]),
                "Debit": dr,
                "Credit": cr,
                "Balance": bal,
                "Remarks": as_text(r[17]),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=["Date", "Particulars", "V.No", "Veh", "GP", "Qty",
                 "Rate", "Debit", "Credit", "Balance", "Remarks"],
    )
    balances = [x for x in df["Balance"].tolist() if pd.notna(x)]
    if total is None:
        total = {"debit": None, "credit": None, "balance": None}
    if total["balance"] is None and balances:
        total["balance"] = balances[-1]
    return {"id": sheet_id, "name": name, "df": df, "total": total}


def parse_workbook(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    if "Dist" not in xls.sheet_names:
        raise ValueError("File mein 'Dist' naam ki sheet nahi mili.")
    summary, report_date = parse_summary(xls.parse("Dist", header=None))

    parties = {}
    for sheet in xls.sheet_names:
        if sheet.strip().isdigit():
            parties[sheet.strip()] = parse_ledger(xls.parse(sheet, header=None), sheet.strip())
    if not parties:
        raise ValueError("File mein party ki sheets (1, 2, 3 ...) nahi milin.")
    return {"summary": summary, "report_date": report_date, "parties": parties}


def save_data(data, filename):
    data["filename"] = filename
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(data, f)
    os.replace(tmp, DATA_PATH)


@st.cache_resource
def load_data(mtime):
    with open(DATA_PATH, "rb") as f:
        return pickle.load(f)


# ------------------------------------------------------------------ login
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin123")
USER_PASSWORD = get_secret("USER_PASSWORD", "user123")

if "role" not in st.session_state:
    st.session_state.role = None

if st.session_state.role is None:
    st.title("📊 Distributors Account")
    pwd = st.text_input("Password likhein", type="password")
    if st.button("Login"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.rerun()
        elif pwd == USER_PASSWORD:
            st.session_state.role = "user"
            st.rerun()
        else:
            st.error("Password ghalat hai")
    st.stop()

# ------------------------------------------------------------------ admin upload
if st.session_state.role == "admin":
    st.sidebar.header("Admin: file upload")
    up = st.sidebar.file_uploader("Aaj ki Excel file (.xls / .xlsx)", type=["xls", "xlsx"])
    if up is None:
        st.session_state.pop("last_sig", None)
    else:
        sig = (up.name, up.size)
        if st.session_state.get("last_sig") != sig:
            st.session_state.last_sig = sig
            with st.spinner("File process ho rahi hai, 1 se 2 minute lag sakte hain..."):
                try:
                    save_data(parse_workbook(up.getvalue()), up.name)
                    st.session_state.upload_msg = ("ok", "File upload ho gayi. Purana data replace ho gaya.")
                except Exception as e:
                    st.session_state.upload_msg = (
                        "err",
                        f"File parh nahi saki, purana data wahi hai. ({e})",
                    )
    msg = st.session_state.get("upload_msg")
    if msg and up is not None:
        (st.sidebar.success if msg[0] == "ok" else st.sidebar.error)(msg[1])

if st.sidebar.button("Logout"):
    st.session_state.role = None
    st.rerun()

# ------------------------------------------------------------------ show data
st.title("📊 Distributors Account")

if not os.path.exists(DATA_PATH):
    st.info("Abhi koi file upload nahi hui.")
    st.stop()

mtime = os.path.getmtime(DATA_PATH)
data = load_data(mtime)
updated = datetime.fromtimestamp(mtime, PKT)
caption = f"Akhri update: {updated.strftime('%d-%m-%Y %I:%M %p')}"
if data.get("report_date"):
    caption += f"  |  Summary date: {data['report_date']}"
st.caption(caption)

tab_summary, tab_party = st.tabs(["📋 Distributor Summary", "👤 Party Statement"])

# ---- Summary tab
with tab_summary:
    summary = data["summary"]
    party_rows = summary[summary["S.No"].notna()]
    c1, c2 = st.columns(2)
    c1.metric("Total parties", len(party_rows))
    c2.metric("Total balance", money(party_rows["Total Balance"].sum()))

    q = st.text_input("🔍 Party ya shehar search karein", key="sum_q")
    view = summary
    if q:
        m = (
            view["Party"].str.contains(q, case=False, na=False)
            | view["City"].str.contains(q, case=False, na=False)
        )
        view = view[m]
    view = view[["S.No", "Party", "City", "Total Balance"]]
    st.write(f"Rows: {len(view)}")
    st.dataframe(
        view.style.format(na_rep="").format({"Total Balance": money}, na_rep=""),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

# ---- Party statement tab
with tab_party:
    parties = data["parties"]
    ids = sorted(parties, key=lambda i: parties[i]["name"].lower())
    pid = st.selectbox(
        "Party chunein (naam likh kar bhi dhoond sakte hain)",
        ids,
        index=None,
        placeholder="Party ka naam...",
        format_func=lambda i: parties[i]["name"],
    )
    if pid is None:
        st.info("Upar se party chunein, uska poora statement yahan nazar aayega.")
    else:
        p = parties[pid]
        st.subheader(p["name"])
        t = p["total"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance", money(t["balance"]) if t["balance"] is not None else "-")
        c2.metric("Total Debit", money(t["debit"]) if t["debit"] is not None else "-")
        c3.metric("Total Credit", money(t["credit"]) if t["credit"] is not None else "-")

        df = p["df"]
        if df.empty:
            st.info("Is party ki koi entry nahi hai.")
        else:
            col_a, col_b = st.columns([2, 1])
            show = col_a.radio(
                "Kitni entries dekhni hain",
                ["Aakhri 50", "Aakhri 200", "Sab"],
                horizontal=True,
            )
            newest_first = col_b.checkbox("Naya pehle", value=True)
            if show == "Aakhri 50":
                df = df.tail(50)
            elif show == "Aakhri 200":
                df = df.tail(200)
            if newest_first:
                df = df.iloc[::-1]
            st.caption(f"{len(df)} entries (kul {len(p['df'])})")
            st.caption("🔴 + Debit (sale)   |   🟢 - Credit (payment)")
            st.markdown(ledger_html(df), unsafe_allow_html=True)
