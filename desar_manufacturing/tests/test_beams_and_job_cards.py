import frappe

from desar_manufacturing.services import beam_service, closing_service, job_card_service, piece_order_service
from desar_manufacturing.tests.piece_fixtures import PIECES, PieceBasedTestCase


def make_workstation(name: str) -> str:
    if not frappe.db.exists("Workstation", name):
        frappe.get_doc({"doctype": "Workstation", "workstation_name": name, "hour_rate": 10}).insert(
            ignore_permissions=True)
    return name


def make_operation(name: str) -> str:
    if not frappe.db.exists("Operation", name):
        frappe.get_doc({"doctype": "Operation", "name": name}).insert(ignore_permissions=True)
    return name


class TestBeamsAndJobCards(PieceBasedTestCase):
    def setUp(self):
        super().setUp()
        self.loom_one, self.loom_two = make_workstation("TEST-LOOM-1"), make_workstation("TEST-LOOM-2")
        finishing = make_workstation("TEST-FINISHING")
        process = frappe.get_doc({"doctype": "Production Process", "process_name": "TEST-PROCESS-%s" % frappe.generate_hash(length=6), "steps": [
            {"sequence": 1, "operation": make_operation("TEST-Weaving"), "workstation": self.loom_one,
             "time_in_mins": 480, "uses_beam_workstation": 1},
            {"sequence": 2, "operation": make_operation("TEST-Finishing"), "workstation": finishing,
             "time_in_mins": 60},
        ]}).insert(ignore_permissions=True)
        self.design.db_set("production_process", process.name)
        self.design.reload()

    def beams(self, order: str) -> list:
        return beam_service.create_beams(order, [
            {"length_m": 1350, "workstation": self.loom_one, "planned_pieces": 60},
            {"length_m": 1400, "workstation": self.loom_two, "planned_pieces": 40},
        ])

    def test_bom_gets_operations_from_the_production_process(self):
        order = frappe.get_doc("Work Order", self.make_order())
        self.assertEqual([row.operation for row in order.operations], ["TEST-Weaving", "TEST-Finishing"])

    def test_beam_pieces_must_add_up_to_the_order_quantity(self):
        order = self.make_order()
        with self.assertRaises(frappe.ValidationError):
            beam_service.create_beams(order, [{"planned_pieces": 90, "workstation": self.loom_one}])

    def test_beams_cannot_be_created_twice(self):
        order = self.make_order()
        self.beams(order)
        with self.assertRaises(frappe.ValidationError):
            self.beams(order)

    def test_split_beam_makes_child_beams_and_marks_parent(self):
        order = self.make_order()
        first, _ = self.beams(order)
        children = beam_service.split_beam(first, [
            {"length_m": 700, "workstation": self.loom_one, "planned_pieces": 30},
            {"length_m": 650, "workstation": self.loom_two, "planned_pieces": 30},
        ])
        self.assertEqual(len(children), 2)
        self.assertEqual(frappe.db.get_value("Production Beam", first, "is_group"), 1)
        self.assertEqual(len(beam_service.leaf_beams(order)), 3)

    def test_split_beam_pieces_must_match_parent(self):
        order = self.make_order()
        first, _ = self.beams(order)
        with self.assertRaises(frappe.ValidationError):
            beam_service.split_beam(first, [{"planned_pieces": 10, "workstation": self.loom_one}])

    def test_create_rolls_links_beam_and_work_order(self):
        order = self.make_order()
        first, _ = self.beams(order)
        rolls = beam_service.create_rolls(first, 5)
        ticket = frappe.get_doc("Roll Ticket", rolls[0])
        self.assertEqual((ticket.work_order, ticket.production_beam, ticket.machine_no),
                         (order, first, self.loom_one))
        self.assertEqual(ticket.meters, 270)
        self.assertEqual(len(rolls), 5)

    def test_job_cards_are_one_per_leaf_beam_per_operation(self):
        order = self.make_order()
        first, second = self.beams(order)
        beam_service.split_beam(first, [
            {"workstation": self.loom_one, "planned_pieces": 30},
            {"workstation": self.loom_two, "planned_pieces": 30},
        ])
        cards = job_card_service.create_beam_job_cards(order)
        self.assertEqual(len(cards), 6)
        rows = frappe.get_all("Job Card", {"work_order": order}, ["operation", "for_quantity", "workstation",
                                                                     "custom_production_beam"])
        for operation in ("TEST-Weaving", "TEST-Finishing"):
            self.assertEqual(sum(r.for_quantity for r in rows if r.operation == operation), PIECES)
        weaving_workstations = {r.workstation for r in rows if r.operation == "TEST-Weaving"}
        self.assertEqual(weaving_workstations, {self.loom_one, self.loom_two})
        self.assertEqual({r.workstation for r in rows if r.operation == "TEST-Finishing"}, {"TEST-FINISHING"})
        self.assertTrue(all(r.custom_production_beam for r in rows))

    def test_beam_job_cards_need_beams_and_cannot_repeat(self):
        order = self.make_order()
        with self.assertRaises(frappe.ValidationError):
            job_card_service.create_beam_job_cards(order)
        self.beams(order)
        job_card_service.create_beam_job_cards(order)
        with self.assertRaises(frappe.ValidationError):
            job_card_service.create_beam_job_cards(order)

    def test_close_waits_for_job_cards_then_posts_two_entries(self):
        from frappe.utils import add_to_date, now_datetime
        from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing
        order = self.make_order()
        first, second = self.beams(order)
        piece_order_service.issue_materials(order)
        job_card_service.create_beam_job_cards(order)
        for beam, counts in ((first, {"A": 50, "B": 6, "C": 4}), (second, {"A": 30, "B": 6, "C": 4})):
            for roll in beam_service.create_rolls(beam, 1):
                self._submit_inspections(roll, counts)
        with self.assertRaises(frappe.ValidationError):
            closing_service.close_order(order)
        names = frappe.get_all("Job Card", filters={"work_order": order}, pluck="name", order_by="creation asc, name asc")
        for index, name in enumerate(names):
            card = frappe.get_doc("Job Card", name)
            start = add_to_date(now_datetime(), hours=-3 * (len(names) - index))
            card.append("time_logs", {"from_time": start, "to_time": add_to_date(start, hours=1),
                                      "completed_qty": card.for_quantity})
            card.save(ignore_permissions=True)
            card.submit()
        closing_service.close_order(order)
        purposes = frappe.get_all("Stock Entry", filters={"work_order": order, "docstatus": 1}, pluck="purpose")
        self.assertEqual(sorted(purposes), ["Manufacture", "Material Transfer for Manufacture"])

    def _submit_inspections(self, roll: str, counts: dict) -> None:
        from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing
        gray = make_inspection(roll, "Gray")
        gray.insert(ignore_permissions=True)
        set_closing(gray, counts)
        gray.save(ignore_permissions=True)
        gray.submit()
        make_inspection(roll, "Finishing").insert(ignore_permissions=True).submit()
        final = make_inspection(roll, "Final")
        final.insert(ignore_permissions=True)
        set_closing(final, counts)
        final.save(ignore_permissions=True)
        final.submit()

    def test_print_formats_render_for_beam_and_work_order(self):
        order = self.make_order()
        first, _ = self.beams(order)
        for doctype, name, print_format in (("Production Beam", first, "Loom Ticket"),
                                            ("Work Order", order, "Work Order Sheet")):
            html = frappe.get_print(doctype, name, print_format=print_format)
            self.assertIn("TEST-LOOM-1" if doctype == "Production Beam" else order, html)
