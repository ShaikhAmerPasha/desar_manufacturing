from frappe.model.document import Document

from desar_manufacturing.services import inspection_service


class RollInspection(Document):
    def before_validate(self):
        inspection_service.prepare(self)

    def validate(self):
        inspection_service.calculate(self)

    def before_submit(self):
        inspection_service.ensure_unique(self)
        inspection_service.require_reasons(self)

    def on_submit(self):
        inspection_service.publish_to_roll_ticket(self)

    def on_cancel(self):
        inspection_service.withdraw_from_roll_ticket(self)
