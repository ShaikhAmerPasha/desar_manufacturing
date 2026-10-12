import frappe

from desar_manufacturing.api import shop_floor
from desar_manufacturing.services import beam_service, job_card_service, piece_order_service
from desar_manufacturing.tests.piece_fixtures import PIECES, PieceBasedTestCase
from desar_manufacturing.tests.test_beams_and_job_cards import make_operation, make_workstation
from desar_manufacturing.tests.test_roll_inspection import make_roll_ticket


def make_user(prefix: str, role: str) -> str:
    email = f"{prefix}-{frappe.generate_hash(length=6)}@example.com"
    frappe.get_doc({"doctype": "User", "email": email, "first_name": prefix, "send_welcome_email": 0,
                    "roles": [{"role": role}]}).insert(ignore_permissions=True)
    return email


class TestShopFloorApi(PieceBasedTestCase):
    def setUp(self):
        super().setUp()
        tag = frappe.generate_hash(length=5)
        loom = make_workstation(f"TEST-SF-{tag}")
        process = frappe.get_doc({"doctype": "Production Process", "process_name": f"TEST-SF-{tag}", "steps": [
            {"sequence": 1, "operation": make_operation("TEST-SF-Weaving"), "workstation": loom,
             "time_in_mins": 60, "uses_beam_workstation": 1}]}).insert(ignore_permissions=True)
        self.design.db_set("production_process", process.name)
        order = self.make_order()
        beam_service.create_beams(order, [{"length_m": 500, "workstation": loom, "planned_pieces": PIECES}])
        self.cards = job_card_service.create_beam_job_cards(order)
        self.worker = make_user("worker", "DESAR Factory Worker")
        self.other_worker = make_user("other", "DESAR Factory Worker")
        self.supervisor = make_user("boss", "DESAR Supervisor")

    def as_user(self, user: str):
        frappe.set_user(user)
        self.addCleanup(frappe.set_user, "Administrator")

    def assign(self, card: str, user: str) -> None:
        frappe.set_user(self.supervisor)
        try:
            shop_floor.assign_job_card(card, user)
        finally:
            frappe.set_user("Administrator")

    def test_worker_sees_only_assigned_tasks(self):
        self.assign(self.cards[0], self.worker)
        self.as_user(self.worker)
        self.assertEqual([task["name"] for task in shop_floor.my_tasks()], [self.cards[0]])
        self.as_user(self.other_worker)
        self.assertEqual(shop_floor.my_tasks(), [])

    def test_unassigned_task_cannot_be_started(self):
        self.as_user(self.worker)
        with self.assertRaises(frappe.PermissionError):
            shop_floor.start_job(self.cards[0])

    def test_start_and_complete_job_submits_job_card_with_usage(self):
        self.assign(self.cards[0], self.worker)
        self.as_user(self.worker)
        with self.assertRaises(frappe.ValidationError):
            shop_floor.complete_job(self.cards[0])
        shop_floor.start_job(self.cards[0])
        shop_floor.complete_job(self.cards[0], consumption=frappe.as_json([{"item_code": self.yarn, "qty": 3}]))
        card = frappe.get_doc("Job Card", self.cards[0])
        self.assertEqual((card.docstatus, card.total_completed_qty), (1, PIECES))
        self.assertEqual([(row.item_code, row.qty) for row in card.custom_actual_consumption], [(self.yarn, 3)])
        self.assertEqual(shop_floor.my_tasks(), [])

    def test_reassigning_moves_the_task(self):
        self.assign(self.cards[0], self.worker)
        self.assign(self.cards[0], self.other_worker)
        self.as_user(self.worker)
        self.assertEqual(shop_floor.my_tasks(), [])
        self.as_user(self.other_worker)
        self.assertEqual(len(shop_floor.my_tasks()), 1)

    def test_only_supervisor_can_assign_and_only_to_workers(self):
        self.as_user(self.worker)
        with self.assertRaises(frappe.PermissionError):
            shop_floor.assign_job_card(self.cards[0], self.worker)
        self.as_user(self.supervisor)
        with self.assertRaises(frappe.ValidationError):
            shop_floor.assign_job_card(self.cards[0], self.supervisor)

    def test_inspection_assigned_filled_and_submitted_by_worker(self):
        roll = make_roll_ticket()
        self.as_user(self.supervisor)
        name = shop_floor.assign_inspection(roll, "Gray", self.worker)
        self.as_user(self.worker)
        task, = shop_floor.my_tasks()
        self.assertEqual((task["kind"], task["name"], task["station"]), ("Roll Inspection", name, "Gray"))
        form = shop_floor.get_inspection(name)
        self.assertEqual((form["entry_mode"], len(form["closing"])), ("Count", 3))
        counts = [{"grade_code": "A", "qty": 2}, {"grade_code": "B", "qty": 3}, {"grade_code": "C", "qty": 0}]
        shop_floor.save_inspection(name, closing=frappe.as_json(counts))
        shop_floor.submit_inspection(name)
        self.assertEqual(frappe.db.get_value("Roll Inspection", name, "total_pieces"), 5)
        self.assertEqual(shop_floor.my_tasks(), [])

    def test_inspection_of_someone_else_is_not_readable(self):
        roll = make_roll_ticket()
        self.as_user(self.supervisor)
        name = shop_floor.assign_inspection(roll, "Gray", self.worker)
        self.as_user(self.other_worker)
        with self.assertRaises(frappe.PermissionError):
            shop_floor.get_inspection(name)

    def test_user_without_a_shop_floor_role_is_blocked(self):
        self.as_user(make_user("clerk", "Sales User"))
        with self.assertRaises(frappe.PermissionError):
            shop_floor.my_tasks()

    def test_worker_role_has_no_desk_access(self):
        self.assertEqual(frappe.db.get_value("Role", "DESAR Factory Worker", "desk_access"), 0)

    def test_job_card_detail_lists_planned_materials_of_its_operation(self):
        self.assign(self.cards[0], self.worker)
        self.as_user(self.worker)
        detail = shop_floor.get_job_card(self.cards[0])
        self.assertEqual((detail["operation"], detail["qty"], detail["started_at"]), ("TEST-SF-Weaving", PIECES, None))
        self.assertIsInstance(detail["materials"], list)

    def test_inspection_candidates_follow_stage_order(self):
        roll = make_roll_ticket()
        frappe.db.set_value("Roll Ticket", roll, "work_order", frappe.db.get_value("Job Card", self.cards[0], "work_order"))
        self.as_user(self.supervisor)
        mine = [c for c in shop_floor.inspection_candidates() if c["roll_ticket"] == roll]
        self.assertEqual([c["stage"] for c in mine], ["Gray"])
        shop_floor.assign_inspection(roll, "Gray", self.worker)
        self.assertEqual([c for c in shop_floor.inspection_candidates() if c["roll_ticket"] == roll], [])
