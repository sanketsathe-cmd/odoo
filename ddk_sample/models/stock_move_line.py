from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    x_studio_mfg_date_receipt = fields.Date(
        string='MFG Date',
        compute='_compute_mfg_date',
        inverse='_inverse_mfg_date',
        store=True,
        help='Manufacturing date from the lot/serial number'
    )

    expiration_date = fields.Datetime(
        string='Expiration Date',
        readonly=False,
        compute='_compute_expiration_date',
        inverse='_inverse_expiration_date',
        store=True,
        help="This is the date on which the goods with this Serial Number may become dangerous and must not be consumed."
    )

    # @api.depends('lot_id')  # Only depend on lot_id, not on specific fields
    def _compute_mfg_date(self):
        for record in self:
            if record.lot_id and hasattr(record.lot_id, 'x_studio_mfg_date_lot'):
                record.x_studio_mfg_date_receipt = record.lot_id.x_studio_mfg_date_lot
            else:
                record.x_studio_mfg_date_receipt = False

    def _inverse_mfg_date(self):
        for record in self:
            if record.lot_id and record.x_studio_mfg_date_receipt:
                if hasattr(record.lot_id, 'x_studio_mfg_date_lot'):
                    record.lot_id.x_studio_mfg_date_lot = record.x_studio_mfg_date_receipt

    @api.depends('lot_id')  # Only depend on lot_id, not on expiration_date
    def _compute_expiration_date(self):
        for record in self:
            if record.lot_id:
                # Check if lot has expiration_date field
                if hasattr(record.lot_id, 'expiration_date'):
                    record.expiration_date = record.lot_id.expiration_date
                # If not, try life_date (standard Odoo field)
                elif hasattr(record.lot_id, 'life_date'):
                    record.expiration_date = record.lot_id.life_date
                else:
                    record.expiration_date = False
            else:
                record.expiration_date = False

    def _inverse_expiration_date(self):
        for record in self:
            if record.lot_id and record.expiration_date:
                expiration = record.expiration_date
                if isinstance(expiration, str):
                    try:
                        expiration = datetime.strptime(expiration, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            expiration = datetime.strptime(expiration, '%Y-%m-%d')
                        except ValueError:
                            raise UserError(('Invalid expiration date format'))
                
                # Try to set the field if it exists
                if hasattr(record.lot_id, 'expiration_date'):
                    record.lot_id.expiration_date = expiration
                elif hasattr(record.lot_id, 'life_date'):
                    record.lot_id.life_date = expiration

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        
        for record in records:
            if record.lot_id:
                # Sync MFG date
                if hasattr(record.lot_id, 'x_studio_mfg_date_lot') and record.lot_id.x_studio_mfg_date_lot:
                    record.x_studio_mfg_date_receipt = record.lot_id.x_studio_mfg_date_lot
                
                # Sync expiration date
                if hasattr(record.lot_id, 'expiration_date') and record.lot_id.expiration_date:
                    record.expiration_date = record.lot_id.expiration_date
                elif hasattr(record.lot_id, 'life_date') and record.lot_id.life_date:
                    record.expiration_date = record.lot_id.life_date
        
        return records

    def write(self, vals):
        result = super().write(vals)
        
        for record in self:
            if record.lot_id:
                # Sync MFG date
                if hasattr(record.lot_id, 'x_studio_mfg_date_lot') and record.lot_id.x_studio_mfg_date_lot:
                    if not record.x_studio_mfg_date_receipt or record.x_studio_mfg_date_receipt != record.lot_id.x_studio_mfg_date_lot:
                        record.x_studio_mfg_date_receipt = record.lot_id.x_studio_mfg_date_lot
                
                # Sync expiration date
                exp_date = False
                if hasattr(record.lot_id, 'expiration_date'):
                    exp_date = record.lot_id.expiration_date
                elif hasattr(record.lot_id, 'life_date'):
                    exp_date = record.lot_id.life_date
                
                if exp_date:
                    if not record.expiration_date or record.expiration_date != exp_date:
                        record.expiration_date = exp_date
        
        return result