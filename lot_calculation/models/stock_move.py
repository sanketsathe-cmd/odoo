from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    display_calculate_lot = fields.Boolean(
        compute='_compute_display_calculate_lot',
        string="Display Calculate Lot"
    )

    @api.depends('has_tracking', 'state', 'product_qty')
    def _compute_display_calculate_lot(self):
        for move in self:
            move.display_calculate_lot = (
                move.has_tracking and 
                move.state in ['draft', 'confirmed', 'assigned', 'partially_available'] and
                move.product_qty > 0
            )