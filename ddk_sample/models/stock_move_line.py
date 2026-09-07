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
        compute='_compute_expiration_date',
        inverse='_inverse_expiration_date',
        store=True,
        help="This is the date on which the goods with this Serial Number may become dangerous and must not be consumed."
    )

    @api.depends('lot_id')
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

    @api.depends('lot_id')
    def _compute_expiration_date(self):
        for record in self:
            if record.lot_id:
                # Get from expiration_date field on lot
                if hasattr(record.lot_id, 'expiration_date') and record.lot_id.expiration_date:
                    record.expiration_date = record.lot_id.expiration_date
                else:
                    record.expiration_date = False
            else:
                record.expiration_date = False

    def _inverse_expiration_date(self):
        for record in self:
            if record.lot_id and record.expiration_date:
                # Update ALL date fields on the lot
                if hasattr(record.lot_id, 'expiration_date'):
                    record.lot_id.expiration_date = record.expiration_date
                
                if hasattr(record.lot_id, 'alert_date'):
                    record.lot_id.alert_date = record.expiration_date
                
                if hasattr(record.lot_id, 'use_date'):
                    record.lot_id.use_date = record.expiration_date
                
                if hasattr(record.lot_id, 'removal_date'):
                    record.lot_id.removal_date = record.expiration_date

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        
        # Force recompute for all created records
        for record in records:
            if record.lot_id:
                record._compute_mfg_date()
                record._compute_expiration_date()
        
        return records

    def write(self, vals):
        result = super().write(vals)
        
        # If lot_id was changed, recompute the fields
        if 'lot_id' in vals:
            for record in self:
                record._compute_mfg_date()
                record._compute_expiration_date()
        else:
            # Still sync data for existing lots
            for record in self:
                if record.lot_id:
                    # Check if MFG date needs updating
                    if hasattr(record.lot_id, 'x_studio_mfg_date_lot'):
                        mfg_date = record.lot_id.x_studio_mfg_date_lot
                        if mfg_date and record.x_studio_mfg_date_receipt != mfg_date:
                            record.x_studio_mfg_date_receipt = mfg_date
                    
                    # Check if expiration date needs updating
                    exp_date = False
                    if hasattr(record.lot_id, 'expiration_date') and record.lot_id.expiration_date:
                        exp_date = record.lot_id.expiration_date
                    
                    if exp_date and record.expiration_date != exp_date:
                        record.expiration_date = exp_date
                        
                        # Also sync all other date fields on the lot when expiration_date updates
                        if hasattr(record.lot_id, 'alert_date'):
                            record.lot_id.alert_date = exp_date
                        if hasattr(record.lot_id, 'use_date'):
                            record.lot_id.use_date = exp_date
                        if hasattr(record.lot_id, 'removal_date'):
                            record.lot_id.removal_date = exp_date
        
        return result