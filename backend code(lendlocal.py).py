from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import pandas as pd

MAX_RENTAL_DAYS = 14
DATE_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class Item:
    item_id: int
    title: str
    category: str
    community: str
    owner: str
    owner_phone: str
    mode: str          # "Rent" or "Lend"
    rate_per_day: int  # 0 for "Lend"
    available: bool = True
    borrower: str = ""
    borrower_phone: str = ""
    borrowed_at: str = ""
    due_at: str = ""


@dataclass
class LendLocal:
    items: list[Item] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    _next_id: int = 1

    def add_item(
        self,
        title: str,
        category: str,
        community: str,
        owner: str,
        owner_phone: str,
        mode: str,
        rate_per_day: int = 0,
    ) -> Item:
        mode = mode.capitalize()
        if mode not in ("Rent", "Lend"):
            raise ValueError("Mode must be 'Rent' or 'Lend'.")
        if not owner_phone.strip():
            raise ValueError("Owner contact number is required.")

        fee = int(rate_per_day) if mode == "Rent" else 0
        item = Item(
            item_id=self._next_id,
            title=title.strip(),
            category=category.strip(),
            community=community.strip(),
            owner=owner.strip(),
            owner_phone=owner_phone.strip(),
            mode=mode,
            rate_per_day=fee,
        )
        self._next_id += 1
        self.items.append(item)
        self.history.append(
            f"[{self._now_str()}] LISTED: '{item.title}' ({item.mode}) in {item.community} "
            f"by {item.owner} ({item.owner_phone})"
        )
        return item

    def to_dataframe(self, community_filter: str | None = None, mode_filter: str | None = None) -> pd.DataFrame:
        rows = [asdict(item) for item in self.items]
        df = pd.DataFrame(rows)
        if df.empty:
            return df

        if community_filter:
            df = df[df["community"].str.lower() == community_filter.strip().lower()]
        if mode_filter:
            df = df[df["mode"].str.lower() == mode_filter.strip().lower()]

        return df.reset_index(drop=True)

    def show_items(self, community_filter: str | None = None, mode_filter: str | None = None) -> None:
        header = community_filter if community_filter else "All Community Regions"
        print(f"\n--- {header} Listings ---")
        found = False
        for item in self.items:
            if community_filter and item.community.lower() != community_filter.lower():
                continue
            if mode_filter and item.mode.lower() != mode_filter.lower():
                continue
            found = True
            if item.available:
                status = "Available"
            else:
                overdue_tag = " [OVERDUE]" if self.is_overdue(item.due_at) else ""
                status = (
                    f"With {item.borrower} ({item.borrower_phone}) | "
                    f"Due: {item.due_at}{overdue_tag}"
                )
            pricing = f"₹{item.rate_per_day}/day" if item.mode == "Rent" else "Free (Lend)"
            print(
                f"#{item.item_id} | [{item.community}] {item.title} ({item.category}) | "
                f"Mode: {item.mode} [{pricing}] | Owner: {item.owner} ({item.owner_phone}) | "
                f"Status: {status}"
            )
        if not found:
            print("No items found.")

    def show_items_df(self, community_filter: str | None = None, mode_filter: str | None = None) -> None:
        df = self.to_dataframe(community_filter=community_filter, mode_filter=mode_filter)
        header = community_filter if community_filter else "All Community Regions"
        print(f"\n--- {header} Listings (pandas Table) ---")

        if df.empty:
            print("No items found.")
            return

        df["pricing"] = df.apply(
            lambda r: f"₹{r['rate_per_day']}/day" if r["mode"] == "Rent" else "Free (Lend)",
            axis=1,
        )
        df["owner_contact"] = df.apply(lambda r: f"{r['owner']} ({r['owner_phone']})", axis=1)
        df["status"] = df.apply(
            lambda r: "Available"
            if r["available"]
            else (
                f"With {r['borrower']} ({r['borrower_phone']}) | Due {r['due_at']}"
                + (" [OVERDUE]" if self.is_overdue(r["due_at"]) else "")
            ),
            axis=1,
        )

        cols = ["item_id", "community", "title", "category", "mode", "pricing", "owner_contact", "status"]
        print(df[cols].to_string(index=False))

    def community_summary(self) -> None:
        df = self.to_dataframe()
        if df.empty:
            print("No items to summarize.")
            return

        print("\n--- Listings by Community & Mode ---")
        counts = df.pivot_table(
            index="community",
            columns="mode",
            values="item_id",
            aggfunc="count",
            fill_value=0,
        )
        print(counts)

        rent_only = df[df["mode"] == "Rent"]
        if not rent_only.empty:
            print("\n--- Average Daily Rental Rate by Community (₹) ---")
            avg_rates = rent_only.groupby("community")["rate_per_day"].mean().round(1)
            print(avg_rates)

    def request_item(
        self,
        item_id: int,
        borrower: str,
        borrower_phone: str,
        days: int = 1,
    ) -> None:
        if days < 1:
            print("Duration must be at least 1 day.")
            return
        if days > MAX_RENTAL_DAYS:
            print(f"Duration cannot exceed {MAX_RENTAL_DAYS} days.")
            return
        if not borrower.strip() or not borrower_phone.strip():
            print("Borrower name and contact number are required.")
            return

        item = self._find_item(item_id)
        if not item:
            print(f"Item #{item_id} not found.")
            return
        if not item.available:
            print(
                f"'{item.title}' is currently unavailable "
                f"(with {item.borrower}, {item.borrower_phone}, due {item.due_at})."
            )
            return

        start_dt = datetime.now()
        due_dt = start_dt + timedelta(days=days)
        start_str = start_dt.strftime(DATE_FORMAT)
        due_str = due_dt.strftime(DATE_FORMAT)

        total_cost = item.rate_per_day * days if item.mode == "Rent" else 0
        item.available = False
        item.borrower = borrower.strip()
        item.borrower_phone = borrower_phone.strip()
        item.borrowed_at = start_str
        item.due_at = due_str

        action = "RENTED" if item.mode == "Rent" else "BORROWED"
        msg = (
            f"[{start_str}] {action}: {item.borrower} ({item.borrower_phone}) took '{item.title}' "
            f"from {item.owner} ({item.owner_phone}) in {item.community} "
            f"for {days} day(s) | Due: {due_str} | Total: ₹{total_cost}"
        )
        self.history.append(msg)
        print(msg)

    def return_item(self, item_id: int) -> None:
        item = self._find_item(item_id)
        if not item:
            print(f"Item #{item_id} not found.")
            return
        if item.available:
            print(f"'{item.title}' is already available.")
            return

        prev_borrower = item.borrower
        prev_phone = item.borrower_phone
        overdue_note = " (returned past due date)" if self.is_overdue(item.due_at) else ""

        item.available = True
        item.borrower = ""
        item.borrower_phone = ""
        item.borrowed_at = ""
        item.due_at = ""

        msg = (
            f"[{self._now_str()}] RETURNED: '{item.title}' returned by {prev_borrower} ({prev_phone}) "
            f"to {item.owner} ({item.owner_phone}) in {item.community}{overdue_note}"
        )
        self.history.append(msg)
        print(msg)

    def show_history(self) -> None:
        print("\n--- Community Activity Log ---")
        if not self.history:
            print("No activity yet.")
            return
        for entry in self.history:
            print(entry)

    def save_to_json(self, filepath: str = "lendlocal_data.json") -> None:
        payload = {
            "saved_at": self._now_str(),
            "next_id": self._next_id,
            "items": [asdict(item) for item in self.items],
            "history": self.history,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {len(self.items)} items and {len(self.history)} log entries to '{filepath}'.")

    @classmethod
    def load_from_json(cls, filepath: str = "lendlocal_data.json") -> "LendLocal":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        app = cls()
        app._next_id = data.get("next_id", 1)
        app.items = [Item(**row) for row in data.get("items", [])]
        app.history = data.get("history", [])
        return app

    @staticmethod
    def is_overdue(due_at_str: str) -> bool:
        if not due_at_str:
            return False
        try:
            return datetime.now() > datetime.strptime(due_at_str, DATE_FORMAT)
        except ValueError:
            return False

    def _find_item(self, item_id: int) -> Item | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime(DATE_FORMAT)


def load_default_data(app: LendLocal) -> None:
    # Place 1: Kothrud West + 3 initial items
    app.add_item("Cordless Drill", "Tools", "Kothrud West", "Rohan", "9823011001", "Rent", rate_per_day=150)
    app.add_item("Python & Math Textbooks", "Books", "Kothrud West", "Ananya", "9823011002", "Lend")
    app.add_item("Camera Tripod", "Electronics", "Kothrud West", "Kabir", "9823011003", "Rent", rate_per_day=120)

    # First batch of 10 additional items (Kothrud West)
    app.add_item("Soldering Iron Kit", "Tools", "Kothrud West", "Aarav", "9823011004", "Rent", rate_per_day=80)
    app.add_item("Scientific Calculator", "Electronics", "Kothrud West", "Meera", "9823011005", "Lend")
    app.add_item("Badminton Racquet Pair", "Sports", "Kothrud West", "Siddharth", "9823011006", "Lend")
    app.add_item("2-Person Camping Tent", "Outdoors", "Kothrud West", "Neha", "9823011007", "Rent", rate_per_day=250)
    app.add_item("Extension Cord (10m)", "Household", "Kothrud West", "Vikram", "9823011008", "Lend")
    app.add_item("Measuring Tape & Spirit Level", "Tools", "Kothrud West", "Pooja", "9823011009", "Lend")
    app.add_item("Portable Bluetooth Speaker", "Electronics", "Kothrud West", "Dev", "9823011010", "Rent", rate_per_day=100)
    app.add_item("Board Game Collection", "Recreation", "Kothrud West", "Rhea", "9823011011", "Lend")
    app.add_item("Pressure Washer", "Household", "Kothrud West", "Kunal", "9823011012", "Rent", rate_per_day=300)
    app.add_item("Study Desk Lamp", "Household", "Kothrud West", "Tanvi", "9823011013", "Lend")

    # Place 2: Paud Road (4 items)
    app.add_item("Ring Light & Mic Set", "Electronics", "Paud Road", "Aditya", "9823022001", "Rent", rate_per_day=140)
    app.add_item("DSA & Algorithms Notes", "Books", "Paud Road", "Sneha", "9823022002", "Lend")
    app.add_item("Folding Step Ladder", "Tools", "Paud Road", "Manav", "9823022003", "Rent", rate_per_day=110)
    app.add_item("Yoga Mat & Block Set", "Sports", "Paud Road", "Ishita", "9823022004", "Lend")

    # Place 3: Bavdhan (3 items)
    app.add_item("Portable Projector", "Electronics", "Bavdhan", "Nikhil", "9823033001", "Rent", rate_per_day=350)
    app.add_item("Trekking Backpack (45L)", "Outdoors", "Bavdhan", "Kavya", "9823033002", "Lend")
    app.add_item("Electric Glue Gun", "Tools", "Bavdhan", "Harsh", "9823033003", "Lend")

    # Place 4: Karve Nagar (3 items)
    app.add_item("Sewing Machine", "Household", "Karve Nagar", "Sunita", "9823044001", "Rent", rate_per_day=130)
    app.add_item("Cricket Bat & Stumps", "Sports", "Karve Nagar", "Pranav", "9823044002", "Lend")
    app.add_item("Linear Algebra Workbook", "Books", "Karve Nagar", "Rutuja", "9823044003", "Lend")


def run_demo() -> None:
    app = LendLocal()
    load_default_data(app)

    app.show_items_df(community_filter="Kothrud West")
    app.community_summary()

    # Valid requests (<= 14 days) with contact numbers, plus one rejected (> 14 days)
    app.request_item(item_id=1, borrower="Aarav", borrower_phone="9765010001", days=2)
    app.request_item(item_id=14, borrower="Rhea", borrower_phone="9765010002", days=14)
    app.request_item(item_id=18, borrower="Meera", borrower_phone="9765010003", days=20)

    app.show_items_df(community_filter="Paud Road")
    app.show_history()

    # Save state to JSON and verify reload
    json_path = "lendlocal_data.json"
    app.save_to_json(json_path)
    reloaded = LendLocal.load_from_json(json_path)
    print(f"Reloaded {len(reloaded.items)} items from '{json_path}'.")


if __name__ == "__main__":
    # run_demo()
    pass