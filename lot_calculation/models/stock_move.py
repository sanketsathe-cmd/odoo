from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    show_calculate_lot = fields.Boolean(
        string="Show Calculate Lot",
        compute='_compute_show_calculate_lot',
        store=False,
    )

    @api.depends('has_tracking', 'state')
    def _compute_show_calculate_lot(self):
        for move in self:
            move.show_calculate_lot = bool(move.has_tracking and move.state != 'done')