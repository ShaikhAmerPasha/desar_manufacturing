import frappe
from desar_manufacturing.services.bom_service import BOMService

SPECS = [
    {"design_no": "701", "article_name": "Oasis", "size": "58", "sizes": "55,58",
     "warp_recipe": "WR-2026-0022", "finished_item": "Shemagh-OAS-58-A"},
    {"design_no": "702", "article_name": "Mirage", "size": "55", "sizes": "55,58",
     "warp_recipe": "WR-2026-0023", "finished_item": "Shemagh-MIR-55-A"},
    {"design_no": "702", "article_name": "Mirage", "size": "58", "sizes": "55,58",
     "warp_recipe": "WR-2026-0024", "finished_item": "Shemagh-MIR-58-A"},
]
PIECES_PER_ROLL = 115
CHEMICAL_QTY_KG = 9


def _stage_rows(finished_item):
    return [
        {"stage_seq": 1, "stage_name": "Warping", "output_item": "Warping Beam", "output_qty": 1},
        {"stage_seq": 2, "stage_name": "Beam Split", "output_item": "Beam Roll", "output_qty": 1,
         "roll_ticket_trigger": 1},
        {"stage_seq": 3, "stage_name": "Grey Roll", "output_item": "Grey Roll", "output_qty": 1,
         "qi_required": 1, "qi_template": "Grey Inspection - Shemagh", "sample_size_formula": "1",
         "roll_ticket_trigger": 1},
        {"stage_seq": 4, "stage_name": "Finished Roll", "output_item": "Finished Roll", "output_qty": 1,
         "qi_required": 1, "qi_template": "Finishing Inspection - Shemagh", "sample_size_formula": "1"},
        {"stage_seq": 5, "stage_name": "Packing", "output_item": finished_item, "output_qty": PIECES_PER_ROLL,
         "qi_required": 1, "qi_template": "Final Packing Inspection - Shemagh", "sample_size_formula": "wo_qty",
         "is_final_stage": 1},
    ]


def run():
    for spec in SPECS:
        existing = frappe.db.exists("Design Master", {"design_no": spec["design_no"], "default_size": spec["size"]})
        if existing:
            print(f"skip (exists): {existing}")
            dm_name = existing
        else:
            doc = frappe.get_doc({
                "doctype": "Design Master",
                "design_no": spec["design_no"], "article_name": spec["article_name"],
                "sizes": spec["sizes"], "default_size": spec["size"],
                "warp_recipe": spec["warp_recipe"], "pieces_per_roll": PIECES_PER_ROLL,
                "branded_box_item": "Boxes", "label_item": "Stamps", "sticker_item": "Stickers",
                "chemical_materials_qty_kg": CHEMICAL_QTY_KG,
                "wash_agent_qty": 3, "finish_chem_qty": 5, "flower_chem_qty": 2,
                "stage_configuration": _stage_rows(spec["finished_item"]),
            })
            doc.insert(ignore_permissions=True)
            dm_name = doc.name
            print(f"created {dm_name}  {spec['article_name']}/{spec['size']}")
        frappe.db.commit()

        # Bottom-up: create + submit one stage's BOM at a time, up to 5 rounds.
        for round_no in range(5):
            created = BOMService.create_all_boms(dm_name)
            if not created:
                break
            for stage_name, bom_name in created.items():
                bom = frappe.get_doc("BOM", bom_name)
                if bom.docstatus == 0:
                    bom.submit()
                print(f"  round {round_no+1}: {stage_name} -> {bom_name} submitted")
            frappe.db.commit()

    print("=== final check ===")
    for spec in SPECS:
        dm_name = frappe.db.exists("Design Master", {"design_no": spec["design_no"], "default_size": spec["size"]})
        rows = frappe.get_all("DESAR Stage Configuration", filters={"parent": dm_name},
                               fields=["stage_name", "bom_no"], order_by="stage_seq")
        print(dm_name, spec["article_name"], spec["size"], rows)
