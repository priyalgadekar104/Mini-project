import contextlib
import io
import os
import streamlit as st
from lendlocal import LendLocal, load_default_data, MAX_RENTAL_DAYS

DATA_FILE = "lendlocal_data.json"

st.set_page_config(page_title="LendLocal | Community Sharing", page_icon="🤝", layout="wide")


def run_and_capture(func, *args, **kwargs) -> str:
    """Captures print() output from existing LendLocal methods without changing them."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue().strip()


# Initialize or load state
if "app" not in st.session_state:
    if os.path.exists(DATA_FILE):
        st.session_state.app = LendLocal.load_from_json(DATA_FILE)
    else:
        backend = LendLocal()
        load_default_data(backend)
        backend.save_to_json(DATA_FILE)
        st.session_state.app = backend

app: LendLocal = st.session_state.app

# --- Sidebar Filters & Data Controls ---
st.sidebar.title("🏘️ LendLocal")
st.sidebar.caption("Hyperlocal Renting & Lending")

communities = ["All"] + sorted({item.community for item in app.items})
selected_community = st.sidebar.selectbox("Community Region", communities)
selected_mode = st.sidebar.radio("Mode", ["All", "Rent", "Lend"], horizontal=True)
only_available = st.sidebar.checkbox("Show Available Only", value=False)

st.sidebar.divider()
if st.sidebar.button("🔄 Reset Demo Data"):
    backend = LendLocal()
    load_default_data(backend)
    backend.save_to_json(DATA_FILE)
    st.session_state.app = backend
    st.rerun()

# --- Main Tabs ---
tab_browse, tab_request, tab_list, tab_insights, tab_log = st.tabs(
    ["📦 Browse Items", "🤝 Borrow / Return", "➕ List an Item", "📊 Community Insights", "📜 Activity Log"]
)

# 1. BROWSE ITEMS
with tab_browse:
    st.subheader("Community Listings")
    comm_arg = None if selected_community == "All" else selected_community
    mode_arg = None if selected_mode == "All" else selected_mode

    df = app.to_dataframe(community_filter=comm_arg, mode_filter=mode_arg)

    if df.empty:
        st.info("No items match the current filters.")
    else:
        if only_available:
            df = df[df["available"] == True]

        if df.empty:
            st.info("No available items match the current filters.")
        else:
            display_df = df.copy()
            display_df["Pricing"] = display_df.apply(
                lambda r: f"₹{r['rate_per_day']}/day" if r["mode"] == "Rent" else "Free (Lend)", axis=1
            )
            display_df["Owner"] = display_df.apply(lambda r: f"{r['owner']} ({r['owner_phone']})", axis=1)
            display_df["Status"] = display_df.apply(
                lambda r: "✅ Available"
                if r["available"]
                else (
                    f"⏳ With {r['borrower']} ({r['borrower_phone']}) | Due {r['due_at']}"
                    + (" 🚨 [OVERDUE]" if app.is_overdue(r["due_at"]) else "")
                ),
                axis=1,
            )
            cols = ["item_id", "community", "title", "category", "mode", "Pricing", "Owner", "Status"]
            st.dataframe(
                display_df[cols].rename(
                    columns={
                        "item_id": "ID",
                        "community": "Community",
                        "title": "Item",
                        "category": "Category",
                        "mode": "Mode",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

# 2. BORROW / RETURN
with tab_request:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Request an Item")
        available_items = [i for i in app.items if i.available]
        if not available_items:
            st.warning("All items are currently borrowed.")
        else:
            item_map = {
                f"#{i.item_id} - {i.title} [{i.community}] ({'₹' + str(i.rate_per_day) + '/day' if i.mode == 'Rent' else 'Free'})": i
                for i in available_items
            }
            chosen_label = st.selectbox("Select Available Item", list(item_map.keys()))
            chosen_item = item_map[chosen_label]

            with st.form("request_form"):
                b_name = st.text_input("Your Name")
                b_phone = st.text_input("Your Phone Number")
                days = st.number_input("Duration (days)", min_value=1, max_value=MAX_RENTAL_DAYS, value=1)

                if chosen_item.mode == "Rent":
                    st.caption(f"Estimated Total: **₹{chosen_item.rate_per_day * days}**")

                if st.form_submit_button("Confirm Request"):
                    output = run_and_capture(
                        app.request_item,
                        item_id=chosen_item.item_id,
                        borrower=b_name,
                        borrower_phone=b_phone,
                        days=int(days),
                    )
                    if "RENTED:" in output or "BORROWED:" in output:
                        app.save_to_json(DATA_FILE)
                        st.success(output)
                        st.rerun()
                    else:
                        st.error(output)

    with col2:
        st.subheader("Return an Item")
        borrowed_items = [i for i in app.items if not i.available]
        if not borrowed_items:
            st.info("No items are currently checked out.")
        else:
            ret_map = {
                f"#{i.item_id} - {i.title} (With {i.borrower}, Due {i.due_at})": i.item_id
                for i in borrowed_items
            }
            ret_label = st.selectbox("Select Borrowed Item", list(ret_map.keys()))
            if st.button("Mark as Returned"):
                output = run_and_capture(app.return_item, ret_map[ret_label])
                app.save_to_json(DATA_FILE)
                st.success(output)
                st.rerun()

# 3. LIST AN ITEM
with tab_list:
    st.subheader("List a New Item")
    with st.form("add_item_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        title = c1.text_input("Item Title", placeholder="e.g., Bosch Hammer Drill")
        category = c2.selectbox(
            "Category", ["Tools", "Electronics", "Books", "Sports", "Outdoors", "Household", "Recreation"]
        )
        community = c1.text_input("Community / Area", value="Kothrud West")
        mode = c2.radio("Listing Mode", ["Rent", "Lend"], horizontal=True)
        owner = c1.text_input("Owner Name")
        owner_phone = c2.text_input("Owner Contact Number")
        rate = st.number_input("Daily Rental Rate (₹) — ignored if Lend", min_value=0, step=10, value=100)

        if st.form_submit_button("Add Listing"):
            if not title.strip() or not owner.strip() or not community.strip():
                st.error("Title, Community, and Owner Name are required.")
            else:
                try:
                    new_item = app.add_item(
                        title=title,
                        category=category,
                        community=community,
                        owner=owner,
                        owner_phone=owner_phone,
                        mode=mode,
                        rate_per_day=int(rate),
                    )
                    app.save_to_json(DATA_FILE)
                    st.success(f"Listed #{new_item.item_id} '{new_item.title}' in {new_item.community}!")
                except ValueError as e:
                    st.error(str(e))

# 4. COMMUNITY INSIGHTS (mirrors community_summary)
with tab_insights:
    st.subheader("Community Overview")
    full_df = app.to_dataframe()
    if full_df.empty:
        st.info("No data available.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Listings", len(full_df))
        m2.metric("Available Now", int(full_df["available"].sum()))
        m3.metric("Active Loans", int((~full_df["available"]).sum()))

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Listings by Community & Mode**")
            counts = full_df.pivot_table(
                index="community", columns="mode", values="item_id", aggfunc="count", fill_value=0
            )
            st.dataframe(counts, use_container_width=True)

        with col_b:
            st.markdown("**Average Daily Rental Rate by Community (₹)**")
            rent_only = full_df[full_df["mode"] == "Rent"]
            if not rent_only.empty:
                avg_rates = rent_only.groupby("community")["rate_per_day"].mean().round(1).rename("Avg Rate (₹)")
                st.dataframe(avg_rates, use_container_width=True)

# 5. ACTIVITY LOG
with tab_log:
    st.subheader("Community Activity Log")
    if not app.history:
        st.info("No activity recorded yet.")
    else:
        for entry in reversed(app.history):
            st.text(entry)