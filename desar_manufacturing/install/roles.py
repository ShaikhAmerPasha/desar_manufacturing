"""
DESAR Manufacturing — Role + Workspace Setup v3.5

Creates 4 roles, sets DocType permissions, and creates
role-specific workspaces so each user sees only what they need.

Roles:
  DESAR Operator     → Plant Floor only
  DESAR Supervisor   → Production overview
  DESAR QC Inspector → Quality Inspections + Roll Ticket
  DESAR Store Manager→ Stock Entries

Run: bench --site excel execute desar_manufacturing.install.roles.setup_roles
"""
import frappe


# ── Role definitions ─────────────────────────────────────────────────────────

ROLES = [
    {"role_name": "DESAR Operator",      "desk_access": 1},
    {"role_name": "DESAR Supervisor",    "desk_access": 1},
    {"role_name": "DESAR QC Inspector",  "desk_access": 1},
    {"role_name": "DESAR Store Manager", "desk_access": 1},
]

# (DocType, role, read, write, create, submit, cancel, amend)
PERMISSIONS = [
    # ── Plant Floor ────────────────────────────────────────
    ("Plant Floor",        "DESAR Operator",      1, 0, 0, 0, 0, 0),
    ("Plant Floor",        "DESAR Supervisor",    1, 0, 0, 0, 0, 0),

    # ── Job Card ───────────────────────────────────────────
    ("Job Card",           "DESAR Operator",      1, 1, 1, 1, 0, 0),
    ("Job Card",           "DESAR Supervisor",    1, 1, 1, 1, 0, 0),
    ("Job Card",           "DESAR QC Inspector",  1, 0, 0, 0, 0, 0),

    # ── Work Order ─────────────────────────────────────────
    ("Work Order",         "DESAR Supervisor",    1, 1, 1, 1, 0, 0),
    ("Work Order",         "DESAR QC Inspector",  1, 0, 0, 0, 0, 0),
    ("Work Order",         "DESAR Store Manager", 1, 0, 0, 0, 0, 0),

    # ── Production Plan ────────────────────────────────────
    ("Production Plan",    "DESAR Supervisor",    1, 1, 1, 1, 0, 0),

    # ── Quality Inspection ─────────────────────────────────
    ("Quality Inspection", "DESAR QC Inspector",  1, 1, 1, 1, 0, 0),
    ("Quality Inspection", "DESAR Supervisor",    1, 0, 0, 0, 0, 0),

    # ── Roll Ticket ────────────────────────────────────────
    ("Roll Ticket",        "DESAR QC Inspector",  1, 1, 0, 0, 0, 0),
    ("Roll Ticket",        "DESAR Supervisor",    1, 0, 0, 0, 0, 0),

    # ── Stock Entry ────────────────────────────────────────
    ("Stock Entry",        "DESAR Store Manager", 1, 1, 1, 1, 0, 0),
    ("Stock Entry",        "DESAR Supervisor",    1, 0, 0, 0, 0, 0),

    # ── BOM / Design Master ────────────────────────────────
    ("BOM",                "DESAR Supervisor",    1, 0, 0, 0, 0, 0),
    ("Design Master",      "DESAR Supervisor",    1, 0, 0, 0, 0, 0),
    ("Sales Order",        "DESAR Supervisor",    1, 0, 0, 0, 0, 0),
]


# ── Workspace definitions ────────────────────────────────────────────────────

WORKSPACES = [
    {
        "name": "DESAR Operator",
        "title": "My Jobs",
        "icon": "manufacturing",
        "roles": ["DESAR Operator"],
        "shortcuts": [
            {"type": "Page", "label": "Plant Floor", "link_to": "plant-floor",
             "color": "#2E86AB", "format": "card"},
        ],
        "cards": [
            {
                "label": "How to work",
                "items": [
                    {"type": "Page", "label": "🏭 Open Plant Floor", "link_to": "plant-floor"},
                ]
            }
        ]
    },
    {
        "name": "DESAR Supervisor",
        "title": "Production",
        "icon": "manufacturing",
        "roles": ["DESAR Supervisor"],
        "shortcuts": [
            {"type": "Page", "label": "📊 Production Status", "link_to": "desar-supervisor",
             "color": "#2E86AB", "format": "card"},
            {"type": "List", "label": "Work Orders", "link_to": "Work Order",
             "color": "#A23B72", "format": "card"},
            {"type": "List", "label": "Production Plans", "link_to": "Production Plan",
             "color": "#F18F01", "format": "card"},
            {"type": "Page", "label": "Plant Floor", "link_to": "plant-floor",
             "color": "#C73E1D", "format": "card"},
        ],
        "cards": [
            {
                "label": "Production",
                "items": [
                    {"type": "List", "label": "Work Orders", "link_to": "Work Order"},
                    {"type": "List", "label": "Production Plans", "link_to": "Production Plan"},
                    {"type": "List", "label": "Job Cards", "link_to": "Job Card"},
                    {"type": "Page", "label": "Plant Floor", "link_to": "plant-floor"},
                ]
            },
            {
                "label": "Design",
                "items": [
                    {"type": "List", "label": "Design Masters", "link_to": "Design Master"},
                    {"type": "List", "label": "BOMs", "link_to": "BOM"},
                ]
            }
        ]
    },
    {
        "name": "DESAR QC Inspector",
        "title": "Quality Control",
        "icon": "quality",
        "roles": ["DESAR QC Inspector"],
        "shortcuts": [
            {"type": "Page", "label": "🔍 Pending Inspections", "link_to": "desar-production-workspace",
             "color": "#2E86AB", "format": "card"},
            {"type": "List", "label": "Quality Inspections", "link_to": "Quality Inspection",
             "color": "#A23B72", "format": "card"},
            {"type": "List", "label": "Roll Tickets", "link_to": "Roll Ticket",
             "color": "#F18F01", "format": "card"},
        ],
        "cards": [
            {
                "label": "Quality",
                "items": [
                    {"type": "List", "label": "Quality Inspections", "link_to": "Quality Inspection"},
                    {"type": "List", "label": "Roll Tickets", "link_to": "Roll Ticket"},
                    {"type": "List", "label": "Job Cards (to create QI)", "link_to": "Job Card"},
                ]
            }
        ]
    },
    {
        "name": "DESAR Store Manager",
        "title": "Store",
        "icon": "stock",
        "roles": ["DESAR Store Manager"],
        "shortcuts": [
            {"type": "List", "label": "Stock Entries", "link_to": "Stock Entry",
             "color": "#2E86AB", "format": "card"},
            {"type": "List", "label": "Pending Repack", "link_to": "Stock Entry",
             "color": "#C73E1D", "format": "card",
             "filters": '[["stock_entry_type","=","Repack"],["docstatus","=","0"]]'},
        ],
        "cards": [
            {
                "label": "Stock",
                "items": [
                    {"type": "List", "label": "All Stock Entries", "link_to": "Stock Entry"},
                    {"type": "List", "label": "Pending Repack SEs", "link_to": "Stock Entry"},
                ]
            }
        ]
    },
]


# ── Setup function ───────────────────────────────────────────────────────────

def setup_roles():
    """Create roles, permissions and workspaces. Safe to run multiple times."""
    frappe.set_user("Administrator")

    _create_roles()
    _set_permissions()
    _create_workspaces()

    frappe.db.commit()
    print("\n✅ DESAR roles, permissions and workspaces configured")
    print("Roles: DESAR Operator | DESAR Supervisor | DESAR QC Inspector | DESAR Store Manager")


def _create_roles():
    for r in ROLES:
        if not frappe.db.exists("Role", r["role_name"]):
            frappe.get_doc({"doctype": "Role", **r}).insert(ignore_permissions=True)
            print(f"  Created role: {r['role_name']}")
        else:
            print(f"  Role exists: {r['role_name']}")


def _set_permissions():
    for perm in PERMISSIONS:
        dt, role, r, w, c, s, ca, am = perm
        existing = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": dt, "role": role, "permlevel": 0},
            "name"
        )
        data = {"read": r, "write": w, "create": c, "submit": s, "cancel": ca, "amend": am}
        if existing:
            frappe.db.set_value("Custom DocPerm", existing, data)
        else:
            frappe.get_doc({
                "doctype": "Custom DocPerm",
                "parent": dt, "role": role, "permlevel": 0, **data
            }).insert(ignore_permissions=True)
    print(f"  Permissions set for {len(PERMISSIONS)} rules")


def _create_workspaces():
    for ws in WORKSPACES:
        name = ws["name"]
        exists = frappe.db.exists("Workspace", {"label": name})
        if exists:
            doc = frappe.get_doc("Workspace", exists)
        else:
            doc = frappe.new_doc("Workspace")
            doc.label = name

        doc.title = ws["title"]
        doc.icon = ws.get("icon", "")
        doc.is_hidden = 0
        doc.public = 1

        doc.set("roles", [])
        for role in ws["roles"]:
            doc.append("roles", {"role": role})

        doc.set("shortcuts", [])
        for sc in ws.get("shortcuts", []):
            doc.append("shortcuts", {
                "type": sc["type"],
                "label": sc["label"],
                "link_to": sc["link_to"],
                "color": sc.get("color", ""),
                "format": sc.get("format", "card"),
            })

        doc.set("content", "[]")
        doc.flags.ignore_links = True
        doc.flags.ignore_mandatory = True

        if exists:
            doc.save(ignore_permissions=True)
        else:
            doc.insert(ignore_permissions=True)
        print(f"  Workspace: {name}")
