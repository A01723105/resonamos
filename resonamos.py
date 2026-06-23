import streamlit as st
import pandas as pd
import json
import gspread
from datetime import datetime, date

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Eventos Resonamos", page_icon="🧘🏻", layout="wide")

# ── Persistence (Google Sheets) ───────────────────────────────────────────────
# Each event is one row. The nested "costs" and "attendee_log" lists are stored
# as JSON strings inside their own cells, so the data structure stays identical
# to the old JSON-file version — only where it lives has changed.
SHEET_TAB = "events"
COLUMNS = [
    "id", "name", "date", "ticket_price", "expected_attendees",
    "confirmed_attendees", "earnings_goal", "costs", "attendee_log",
]

@st.cache_resource(show_spinner=False)
def _get_worksheet():
    """Connect to Google Sheets once and return the 'events' tab (creating it if missing)."""
    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    spreadsheet = gc.open_by_key(st.secrets["sheet_id"])
    try:
        ws = spreadsheet.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_TAB, rows=100, cols=len(COLUMNS))
        ws.update(values=[COLUMNS], range_name="A1", value_input_option="RAW")
    return ws

def load_data():
    """Read every event from the sheet and rebuild the nested Python structure."""
    ws = _get_worksheet()
    records = ws.get_all_records(numericise_ignore=["all"])  # all cells as strings
    events = []
    for r in records:
        if not str(r.get("id", "")).strip():
            continue  # skip blank rows
        events.append({
            "id":                  str(r["id"]),
            "name":                str(r.get("name", "")),
            "date":                str(r.get("date", "")),
            "ticket_price":        float(r.get("ticket_price") or 0),
            "expected_attendees":  int(float(r.get("expected_attendees") or 0)),
            "confirmed_attendees": int(float(r.get("confirmed_attendees") or 0)),
            "earnings_goal":       float(r.get("earnings_goal") or 0),
            "costs":               json.loads(r["costs"]) if r.get("costs") else [],
            "attendee_log":        json.loads(r["attendee_log"]) if r.get("attendee_log") else [],
        })
    return events

def save_data(events):
    """Overwrite the sheet with the current events (header row + one row per event)."""
    ws = _get_worksheet()
    rows = [COLUMNS]
    for e in events:
        rows.append([
            str(e["id"]),
            e.get("name", ""),
            e.get("date", ""),
            str(e.get("ticket_price", 0)),
            str(e.get("expected_attendees", 0)),
            str(e.get("confirmed_attendees", 0)),
            str(e.get("earnings_goal", 0)),
            json.dumps(e.get("costs", []), ensure_ascii=False),
            json.dumps(e.get("attendee_log", []), ensure_ascii=False),
        ])
    ws.clear()
    ws.update(values=rows, range_name="A1", value_input_option="RAW")

# ── Session state ─────────────────────────────────────────────────────────────
if "events" not in st.session_state:
    try:
        st.session_state.events = load_data()
    except Exception as err:
        st.error(
            "No pude conectar con Google Sheets. Revisa que:\n\n"
            "1. Los *secrets* `gcp_service_account` y `sheet_id` estén configurados "
            "(Settings → Secrets).\n"
            "2. La hoja de cálculo esté compartida (como Editor) con el "
            "`client_email` del service account.\n\n"
            f"Detalle técnico: {err}"
        )
        st.stop()
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "editing_log_id" not in st.session_state:
    st.session_state.editing_log_id = None  # (event_id, log_index)

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_event_totals(event):
    total_costs = sum(c["amount"] for c in event["costs"])
    price       = event["ticket_price"]
    confirmed   = event["confirmed_attendees"]
    # Cash collected = sum of amounts_paid across all positive log entries
    cash_collected = sum(
        e.get("amount_paid", price * e["count"])
        for e in event["attendee_log"]
        if e["count"] > 0
    )
    # Pending = what still needs to be paid (deposits only)
    pending = sum(
        (price * e["count"]) - e.get("amount_paid", price * e["count"])
        for e in event["attendee_log"]
        if e["count"] > 0
    )
    full_revenue    = confirmed * price
    profit_current  = cash_collected - total_costs
    profit_full     = full_revenue - total_costs
    breakeven = (
        int(total_costs / price) + (1 if total_costs % price else 0)
    ) if price > 0 else 0
    return total_costs, cash_collected, pending, full_revenue, profit_current, profit_full, breakeven

def compute_summary(events):
    if not events:
        return 0, 0.0, 0.0, 0.0, 0.0
    total_costs     = sum(sum(c["amount"] for c in e["costs"]) for e in events)
    total_cash      = 0.0
    total_pending   = 0.0
    be_vals, prices = [], []
    for e in events:
        tc, cash, pend, fr, pc, pf, be = get_event_totals(e)
        be_vals.append(be)
        prices.append(e["ticket_price"])
        total_cash    += cash
        total_pending += pend
    avg_be = sum(be_vals) / len(be_vals) if be_vals else 0
    return len(events), total_costs, total_cash, total_pending, avg_be

def find_event(eid):
    for i, e in enumerate(st.session_state.events):
        if e["id"] == eid:
            return i, e
    return None, None

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Blue canvas background ── */
.stApp { background-color: #d1e5f4; }
[data-testid="stHeader"] { background-color: transparent; }
[data-testid="stSidebar"] { background-color: #e3eef8; }

/* ── White cards float on the blue canvas for emphasis ── */
div[data-testid="stExpander"] {
    border: 1px solid #b8d2e8; border-radius: 10px; background-color: #ffffff;
}
/* Stat cards: keep metrics readable on the blue background */
div[data-testid="stMetric"] {
    background-color: #ffffff; border: 1px solid #cfe0f0;
    border-radius: 10px; padding: 12px 14px;
}
/* Tables on white for visual emphasis */
[data-testid="stDataFrame"] {
    background-color: #ffffff; border: 1px solid #cfe0f0;
    border-radius: 10px; padding: 4px;
}
/* Charts on white so bars stay easy to read */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
    background-color: #ffffff; border: 1px solid #cfe0f0;
    border-radius: 10px; padding: 12px;
}

.stProgress > div > div > div > div { background-color: #1D9E75; }
.section-title {
    font-size: 13px; color: #5a6b7d; text-transform: uppercase;
    letter-spacing: .06em; margin-bottom: 8px;
}
.status-ok   { background:#d1fae5;color:#065f46;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block; }
.status-warn { background:#fef3c7;color:#92400e;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block; }
.status-bad  { background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block; }
.badge-paid    { background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600; }
.badge-deposit { background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600; }
.badge-cancel  { background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🧘🏻 Eventos Resonamos")
st.caption("Ganancias esperadas y 'punto de quiebre'")
st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR  — collapsed sections so everything is one click away
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### Opciones")

    # ── ➕ CREATE EVENT ───────────────────────────────────────────────────────
    with st.expander("➕ Nuevo Evento", expanded=False):
        with st.form("new_event_form", clear_on_submit=True):
            ev_name     = st.text_input("Event name", placeholder="e.g. Workshop May 2025")
            ev_date     = st.date_input("Event date", value=datetime.today())
            ev_price    = st.number_input("Ticket price ($)", min_value=0.0, step=1.0, format="%.2f")
            ev_expected = st.number_input("Expected attendees", min_value=0, step=1)
            st.markdown("**Cost items**")
            st.caption("Agrega hasta 5 costos")
            costs = []
            for i in range(1, 6):
                c1, c2 = st.columns([2, 1])
                cname   = c1.text_input(f"Item {i}", placeholder="e.g. Salón", key=f"cn_{i}", label_visibility="collapsed")
                camount = c2.number_input("$", min_value=0.0, step=10.0, format="%.2f", key=f"ca_{i}", label_visibility="collapsed")
                if cname and camount > 0:
                    costs.append({"name": cname, "amount": camount})
            if st.form_submit_button("Agregar Evento", use_container_width=True, type="primary"):
                if not ev_name:
                    st.error("Please enter an event name.")
                elif ev_price <= 0:
                    st.error("Ticket price must be > 0.")
                else:
                    st.session_state.events.append({
                        "id":                  datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "name":                ev_name,
                        "date":                str(ev_date),
                        "ticket_price":        ev_price,
                        "expected_attendees":  int(ev_expected),
                        "confirmed_attendees": 0,
                        "earnings_goal":       0.0,
                        "costs":               costs,
                        "attendee_log":        [],
                    })
                    save_data(st.session_state.events)
                    st.success(f"'{ev_name}' created!")
                    st.rerun()

    # ── 👥 ADD ATTENDEES ─────────────────────────────────────────────────────
    with st.expander("👥 Add Attendees", expanded=False):
        if st.session_state.events:
            ev_names = [e["name"] for e in st.session_state.events]
            sel_ev   = st.selectbox("Event", ev_names, key="add_att_sel")

            # Resolve ticket price for the selected event
            sel_ev_obj  = next((e for e in st.session_state.events if e["name"] == sel_ev), None)
            ticket_price = sel_ev_obj["ticket_price"] if sel_ev_obj else 0.0

            add_n       = st.number_input("Number of attendees", min_value=1, step=1, value=1, key="add_n")
            add_note    = st.text_input("Note (optional)", placeholder="e.g. Group booking", key="add_note")

            payment_type = st.radio(
                "Payment status",
                ["Paid in full", "Deposit only"],
                horizontal=True,
                key="add_pay_type",
            )

            if payment_type == "Deposit only":
                deposit_amt = st.number_input(
                    f"Deposit per attendee ($)  — ticket is ${ticket_price:,.2f}",
                    min_value=0.0,
                    max_value=float(ticket_price) if ticket_price > 0 else 1e9,
                    step=10.0,
                    format="%.2f",
                    key="add_deposit",
                )
                amount_paid = deposit_amt * int(add_n)
            else:
                amount_paid = ticket_price * int(add_n)

            if st.button("Add Attendees", use_container_width=True, type="primary", key="btn_add_att"):
                for e in st.session_state.events:
                    if e["name"] == sel_ev:
                        e["confirmed_attendees"] += int(add_n)
                        e["attendee_log"].append({
                            "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "count":        int(add_n),
                            "note":         add_note or "—",
                            "payment_type": payment_type,
                            "amount_paid":  round(amount_paid, 2),
                        })
                save_data(st.session_state.events)
                st.success(f"+{add_n} added to '{sel_ev}'")
                st.rerun()
        else:
            st.info("Create an event first.")

    # ── ➖ REMOVE ATTENDEES ──────────────────────────────────────────────────
    with st.expander("➖ Remove Attendees", expanded=False):
        if st.session_state.events:
            ev_names_r = [e["name"] for e in st.session_state.events]
            sel_ev_r   = st.selectbox("Event", ev_names_r, key="rem_att_sel")
            rem_n      = st.number_input("Attendees to remove", min_value=1, step=1, value=1, key="rem_n")
            rem_note   = st.text_input("Reason (optional)", placeholder="e.g. Cancellation", key="rem_note")
            if st.button("Remove Attendees", use_container_width=True, key="btn_rem_att"):
                for e in st.session_state.events:
                    if e["name"] == sel_ev_r:
                        removed = min(int(rem_n), e["confirmed_attendees"])
                        e["confirmed_attendees"] = max(0, e["confirmed_attendees"] - int(rem_n))
                        e["attendee_log"].append({
                            "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "count":        -removed,
                            "note":         rem_note or "Cancelled",
                            "payment_type": "Cancelled",
                            "amount_paid":  0.0,
                        })
                save_data(st.session_state.events)
                st.success(f"−{rem_n} removed from '{sel_ev_r}'")
                st.rerun()
        else:
            st.info("Create an event first.")

# ═════════════════════════════════════════════════════════════════════════════
# EDIT EVENT  (shown inline when editing_id is set)
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.editing_id:
    eid = st.session_state.editing_id
    ei, ev = find_event(eid)
    if ev:
        st.subheader(f"✏️ Editing: {ev['name']}")
        with st.form("edit_event_form"):
            e_name     = st.text_input("Event name",           value=ev["name"])
            e_date     = st.date_input("Event date",           value=date.fromisoformat(ev["date"]))
            e_price    = st.number_input("Ticket price ($)",   value=float(ev["ticket_price"]),           min_value=0.0, step=1.0,   format="%.2f")
            e_expected = st.number_input("Expected attendees", value=int(ev["expected_attendees"]),        min_value=0,   step=1)
            e_goal     = st.number_input("Earnings goal ($)",  value=float(ev.get("earnings_goal", 0)),   min_value=0.0, step=100.0, format="%.2f")
            st.markdown("**Cost items** — clear a row to remove it")
            new_costs = []
            existing  = ev["costs"] + [{"name": "", "amount": 0.0}] * 3
            for i, c in enumerate(existing[:11]):
                c1, c2 = st.columns([2, 1])
                cn = c1.text_input(f"Cost {i+1}", value=c["name"],         key=f"ecn_{i}", label_visibility="collapsed", placeholder="Item name")
                ca = c2.number_input("$",          value=float(c["amount"]),key=f"eca_{i}", label_visibility="collapsed", min_value=0.0, step=10.0, format="%.2f")
                if cn and ca > 0:
                    new_costs.append({"name": cn, "amount": ca})
            sc1, sc2 = st.columns(2)
            save_edit   = sc1.form_submit_button("💾 Save changes", use_container_width=True, type="primary")
            cancel_edit = sc2.form_submit_button("Cancel",          use_container_width=True)

        if save_edit:
            if not e_name:
                st.error("Event name cannot be empty.")
            elif e_price <= 0:
                st.error("Ticket price must be > 0.")
            else:
                st.session_state.events[ei].update({
                    "name": e_name, "date": str(e_date),
                    "ticket_price": e_price, "expected_attendees": int(e_expected),
                    "earnings_goal": e_goal, "costs": new_costs,
                })
                save_data(st.session_state.events)
                st.session_state.editing_id = None
                st.success("Event updated!")
                st.rerun()
        if cancel_edit:
            st.session_state.editing_id = None
            st.rerun()
        st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# EDIT ATTENDEE LOG ENTRY
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.editing_log_id:
    log_eid, log_idx = st.session_state.editing_log_id
    ei, ev = find_event(log_eid)
    if ev and 0 <= log_idx < len(ev["attendee_log"]):
        entry        = ev["attendee_log"][log_idx]
        ticket_price = ev["ticket_price"]
        st.subheader(f"✏️ Edit log entry — {ev['name']}")
        with st.form("edit_log_form"):
            new_count = st.number_input(
                "Count (negative = cancellation)",
                value=int(entry["count"]), step=1
            )
            new_note  = st.text_input("Note", value=entry.get("note", "—"))

            # Payment fields — only for positive (add) entries
            if entry["count"] > 0:
                cur_pay_type = entry.get("payment_type", "Paid in full")
                pay_opts     = ["Paid in full", "Deposit only"]
                pay_idx      = pay_opts.index(cur_pay_type) if cur_pay_type in pay_opts else 0
                new_pay_type = st.radio("Payment status", pay_opts, index=pay_idx, horizontal=True, key="edit_pay_type")
                max_val      = float(ticket_price * abs(new_count)) if ticket_price > 0 else 1e9
                cur_paid     = float(entry.get("amount_paid", ticket_price * entry["count"]))
                new_amount_paid = st.number_input(
                    f"Total amount paid ($)  — full would be ${ticket_price * abs(new_count):,.2f}",
                    min_value=0.0, max_value=max_val,
                    value=min(cur_paid, max_val),
                    step=10.0, format="%.2f", key="edit_paid_amt"
                )
            else:
                new_pay_type    = "Cancelled"
                new_amount_paid = 0.0

            lc1, lc2, lc3 = st.columns(3)
            save_log   = lc1.form_submit_button("💾 Save",        use_container_width=True, type="primary")
            delete_log = lc2.form_submit_button("🗑 Delete entry", use_container_width=True)
            cancel_log = lc3.form_submit_button("Cancel",         use_container_width=True)

        if save_log:
            old_count = entry["count"]
            diff      = new_count - old_count
            st.session_state.events[ei]["attendee_log"][log_idx].update({
                "count":        new_count,
                "note":         new_note,
                "payment_type": new_pay_type,
                "amount_paid":  round(new_amount_paid, 2),
            })
            st.session_state.events[ei]["confirmed_attendees"] = max(
                0, st.session_state.events[ei]["confirmed_attendees"] + diff
            )
            save_data(st.session_state.events)
            st.session_state.editing_log_id = None
            st.success("Log entry updated.")
            st.rerun()

        if delete_log:
            old_count = entry["count"]
            st.session_state.events[ei]["attendee_log"].pop(log_idx)
            st.session_state.events[ei]["confirmed_attendees"] = max(
                0, st.session_state.events[ei]["confirmed_attendees"] - old_count
            )
            save_data(st.session_state.events)
            st.session_state.editing_log_id = None
            st.success("Log entry deleted and count adjusted.")
            st.rerun()

        if cancel_log:
            st.session_state.editing_log_id = None
            st.rerun()
        st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# FILTER + SUMMARY CARDS
# ═════════════════════════════════════════════════════════════════════════════
events    = st.session_state.events
all_names = ["All events"] + [e["name"] for e in events]
fc, _     = st.columns([2, 5])
with fc:
    sel_filter = st.selectbox("📊 View", all_names, key="filter_select")

filtered = events if sel_filter == "All events" else [e for e in events if e["name"] == sel_filter]

n_events, total_costs, total_cash, total_pending, avg_be = compute_summary(filtered)
total_full_rev = sum(e["confirmed_attendees"] * e["ticket_price"] for e in filtered)
net_current    = total_cash - total_costs

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total events",      n_events)
m2.metric("Total costs",       f"${total_costs:,.2f}")
m3.metric("Cash collected",    f"${total_cash:,.2f}",
          delta=f"{'+ ' if net_current >= 0 else ''}${net_current:,.2f} net",
          delta_color="normal" if net_current >= 0 else "inverse")
m4.metric("Pending (deposits)", f"${total_pending:,.2f}",
          help="Amount still owed by attendees who paid a deposit")
m5.metric("Avg. break-even",   f"{avg_be:.0f} attendees")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# EVENT CARDS
# ═════════════════════════════════════════════════════════════════════════════
if not filtered:
    st.info("No hay eventos aún. Crea uno con el menú lateral.")
else:
    st.subheader("Eventos")
    for event in filtered:
        tc, cash, pending, full_rev, profit_now, profit_full, breakeven = get_event_totals(event)
        confirmed    = event["confirmed_attendees"]
        expected     = event["expected_attendees"]
        price        = event["ticket_price"]
        goal         = event.get("earnings_goal", 0)
        goal_att     = int((tc + goal) / price) + 1 if price > 0 and goal > 0 else 0
        progress_pct = min(1.0, confirmed / breakeven) if breakeven > 0 else 1.0

        # Count fully paid vs deposit attendees
        n_full    = sum(e["count"] for e in event["attendee_log"] if e["count"] > 0 and e.get("payment_type") == "Paid in full")
        n_deposit = sum(e["count"] for e in event["attendee_log"] if e["count"] > 0 and e.get("payment_type") == "Deposit only")

        if confirmed >= breakeven:
            status_html = '<span class="status-ok">✔ Break-even reached</span>'
        elif expected >= breakeven:
            status_html = '<span class="status-warn">⚠ On track (not yet)</span>'
        else:
            status_html = '<span class="status-bad">✖ Below break-even</span>'

        with st.expander(
            f"**{event['name']}**  ·  {event['date']}  ·  ${price:.2f}/ticket",
            expanded=(len(filtered) == 1)
        ):
            hc1, hc2, hc3 = st.columns([5, 1, 1])
            with hc1:
                st.markdown(status_html, unsafe_allow_html=True)
            with hc2:
                if st.button("✏️ Editar", key=f"edit_{event['id']}"):
                    st.session_state.editing_id = event["id"]
                    st.rerun()
            with hc3:
                if st.button("🗑 Eliminar", key=f"del_{event['id']}"):
                    st.session_state.events = [e for e in st.session_state.events if e["id"] != event["id"]]
                    save_data(st.session_state.events)
                    st.rerun()

            st.markdown("---")
            left, right = st.columns(2)

            # ── Costs ──
            with left:
                st.markdown('<p class="section-title">Cost breakdown</p>', unsafe_allow_html=True)
                if event["costs"]:
                    cost_df = pd.DataFrame(event["costs"])
                    cost_df.columns = ["Item", "Amount ($)"]
                    cost_df["Amount ($)"] = cost_df["Amount ($)"].map("${:,.2f}".format)
                    st.dataframe(cost_df, hide_index=True, use_container_width=True)
                else:
                    st.caption("No costs recorded.")
                st.metric("Total costs", f"${tc:,.2f}")

            # ── Attendance & payment ──
            with right:
                st.markdown('<p class="section-title">Attendance & payments</p>', unsafe_allow_html=True)
                ac1, ac2, ac3 = st.columns(3)
                ac1.metric("Confirmed",  confirmed)
                ac2.metric("Expected",   expected)
                ac3.metric("Break-even", breakeven)
                st.progress(progress_pct, text=f"{confirmed}/{breakeven} to break-even")

                st.markdown("---")
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("Paid in full",     n_full,
                           help="Attendees who completed full payment")
                pc2.metric("Deposit only",      n_deposit,
                           help="Attendees who paid a partial deposit")
                pc3.metric("Pending balance",   f"${pending:,.2f}",
                           help="Total still owed by deposit attendees")

                pc4, pc5 = st.columns(2)
                pc4.metric("Cash collected",   f"${cash:,.2f}")
                pc5.metric("If all pay in full", f"${full_rev:,.2f}")

                if goal > 0:
                    st.caption(f"Earnings goal **${goal:,.2f}** → need **{goal_att}** attendees")

            st.markdown("---")

            # ── Projection table ──
            st.markdown('<p class="section-title">Projected outcomes</p>', unsafe_allow_html=True)
            milestones = sorted(set(filter(lambda x: x > 0, [
                max(1, breakeven // 2), breakeven,
                int(breakeven * 1.25),
                goal_att if goal > 0 else int(breakeven * 1.5),
                int(breakeven * 2),
            ])))
            proj_rows = []
            for att in milestones:
                rev = att * price
                pft = rev - tc
                proj_rows.append({
                    "Attendees":     att,
                    "Revenue":       f"${rev:,.2f}",
                    "Profit / Loss": f"{'+ ' if pft >= 0 else '− '}${abs(pft):,.2f}",
                    "Status":        "✔ Profit" if pft > 0 else ("⚡ Break-even" if pft == 0 else "✖ Loss"),
                })
            st.dataframe(pd.DataFrame(proj_rows), hide_index=True, use_container_width=True)

            # ── Revenue chart ──
            if confirmed > 0:
                st.markdown('<p class="section-title" style="margin-top:.5rem">Revenue progress</p>', unsafe_allow_html=True)
                chart_data = pd.DataFrame({
                    "Category": ["Cash collected", "Pending (deposits)", "Break-even target", "Expected (full pay)"],
                    "Amount":   [cash, pending, tc, expected * price],
                })
                st.bar_chart(chart_data.set_index("Category"), use_container_width=True,
                             height=220, color="#2c6e9b")

            # ── Attendee log ──
            if event["attendee_log"]:
                with st.expander("📋 Attendee log"):
                    hrow = st.columns([2, 1, 1, 2, 2, 2, 1])
                    for label in ["Time", "Count", "Payment", "Amount paid", "Pending amount", "Note", ""]:
                        hrow.pop(0).markdown(f"**{label}**")

                    for li, entry in enumerate(event["attendee_log"]):
                        lc = st.columns([2, 1, 1, 2, 2, 2, 1])
                        lc[0].write(entry["timestamp"])

                        count_val = entry["count"]
                        lc[1].write(f"+{count_val}" if count_val > 0 else str(count_val))

                        pay_type = entry.get("payment_type", "—")
                        if pay_type == "Paid in full":
                            lc[2].markdown('<span class="badge-paid">Full</span>', unsafe_allow_html=True)
                        elif pay_type == "Deposit only":
                            lc[2].markdown('<span class="badge-deposit">Deposit</span>', unsafe_allow_html=True)
                        else:
                            lc[2].markdown('<span class="badge-cancel">Cancel</span>', unsafe_allow_html=True)

                        amt = entry.get("amount_paid", 0.0)
                        lc[3].write(f"${amt:,.2f}" if count_val > 0 else "—")

                        # Pending amount = full ticket cost for this entry minus what was paid
                        if count_val > 0:
                            pending_entry = max(0.0, price * count_val - amt)
                            if pending_entry > 0:
                                lc[4].markdown(
                                    f'<span style="color:#b45309;font-weight:600">${pending_entry:,.2f}</span>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                lc[4].markdown(
                                    '<span style="color:#16a34a;font-weight:600">$0.00</span>',
                                    unsafe_allow_html=True,
                                )
                        else:
                            lc[4].write("—")

                        lc[5].write(entry.get("note", "—"))

                        if lc[6].button("✏️", key=f"editlog_{event['id']}_{li}", help="Edit entry"):
                            st.session_state.editing_log_id = (event["id"], li)
                            st.rerun()
