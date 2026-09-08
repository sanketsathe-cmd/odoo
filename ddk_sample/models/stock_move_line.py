from odoo import api, fields, models
from odoo.exceptions import UserError
from datetime import datetime
import logging
import re
import logging
# Reduce logging level for this specific logger
logging.getLogger('odoo.http').setLevel(logging.ERROR)

_logger = logging.getLogger(__name__)

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
                    _logger.info(f"Computed expiration_date for lot {record.lot_id.name}: {record.expiration_date}")
                else:
                    record.expiration_date = False
                    _logger.info(f"No expiration_date for lot {record.lot_id.name}, setting to False")
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
                _logger.info(f"Created move line with lot {record.lot_id.name}, expiration: {record.expiration_date}")
        
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
                    
                    if record.expiration_date != exp_date:
                        record.expiration_date = exp_date
                        _logger.info(f"Synced expiration_date for move line {record.id} to: {exp_date}")
        
        return result

    def _sync_expiration_with_lot(self):
        """
        Sync expiration dates between move lines and their lots.
        Can be called manually to fix any discrepancies.
        """
        for line in self:
            if line.lot_id:
                exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                if line.expiration_date != exp_date:
                    line.expiration_date = exp_date
                    _logger.info(f"Synced expiration date for move line {line.id} from lot {line.lot_id.name}: {exp_date}")
                    
            if line.lot_id and hasattr(line.lot_id, 'x_studio_mfg_date_lot'):
                if line.x_studio_mfg_date_receipt != line.lot_id.x_studio_mfg_date_lot:
                    line.x_studio_mfg_date_receipt = line.lot_id.x_studio_mfg_date_lot
                    _logger.info(f"Synced MFG date for move line {line.id} from lot {line.lot_id.name}")


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    @api.model
    def action_generate_lot_line_vals(self, *args, **kwargs):
        """
        OVERRIDE: Generate lot line values with proper expiration dates from lots.
        This completely overrides the default Odoo behavior to ensure expiration dates come from the lot.
        """
        _logger.info("=== OVERRIDING action_generate_lot_line_vals ===")
        _logger.info(f"args: {args}")
        _logger.info(f"kwargs: {kwargs}")
        
        # Extract arguments
        context_data = kwargs.get('context_data')
        mode = kwargs.get('mode')
        first_lot = kwargs.get('first_lot')
        count = kwargs.get('count')
        lot_text = kwargs.get('lot_text')
        
        if len(args) >= 1:
            context_data = args[0] if context_data is None else context_data
        if len(args) >= 2:
            mode = args[1] if mode is None else mode
        if len(args) >= 3:
            first_lot = args[2] if first_lot is None else first_lot
        if len(args) >= 4:
            count = args[3] if count is None else count
        if len(args) >= 5:
            lot_text = args[4] if lot_text is None else lot_text
        
        # Set defaults
        if context_data is None:
            context_data = {}
        if mode is None:
            mode = 'import'
        if first_lot is None:
            first_lot = ''
        if count is None:
            count = 0
        if lot_text is None:
            lot_text = ''
        
        _logger.info(f"Extracted parameters:")
        _logger.info(f"  context_data: {context_data}")
        _logger.info(f"  mode: {mode}")
        _logger.info(f"  first_lot: {first_lot}")
        _logger.info(f"  count: {count}")
        _logger.info(f"  lot_text: {lot_text}")
        
        # Get the move from context
        move = self
        
        if context_data and isinstance(context_data, dict):
            if context_data.get('active_id'):
                move = self.browse(context_data.get('active_id'))
                _logger.info(f"Found move with active_id: {move.id}")
            elif context_data.get('default_product_id'):
                _logger.info("Creating new move from context")
                move = self.new({
                    'product_id': context_data.get('default_product_id'),
                    'location_id': context_data.get('default_location_id'),
                    'location_dest_id': context_data.get('default_location_dest_id'),
                    'company_id': self.env.company.id,
                    'product_uom': context_data.get('default_uom_id'),
                    'scheduled_date': context_data.get('default_scheduled_date'),
                })
                _logger.info(f"Created new move: {move}")
        
        if not move or not move.id:
            if self and self.ids:
                move = self.browse(self.ids[0])
                _logger.info(f"Using first move in recordset: {move.id}")
        
        if not move:
            raise UserError('Stock move not found')
        
        _logger.info(f"Move ID: {move.id if move.id else 'New'}")
        _logger.info(f"Move scheduled_date: {move.scheduled_date if hasattr(move, 'scheduled_date') else None}")
        _logger.info(f"Product: {move.product_id.name if move.product_id else 'Unknown'}")
        
        move_line_vals = []
        lot_obj = self.env['stock.lot']
        
        if mode == 'import':
            _logger.info("Import mode: processing lot text")
            
            if not lot_text or not lot_text.strip():
                raise UserError('Please enter lot numbers and quantities.')
            
            lines = lot_text.strip().split('\n')
            _logger.info(f"Parsing {len(lines)} lines")
            
            for line in lines:
                if not line.strip():
                    continue
                
                parts = re.split(r'\s+', line.strip(), 1)
                lot_name = parts[0].strip()
                quantity = float(parts[1]) if len(parts) > 1 else 1.0
                
                _logger.info(f"Processing lot: {lot_name}, quantity: {quantity}")
                
                if quantity <= 0:
                    raise UserError(f'Quantity must be greater than 0 for lot {lot_name}.')
                
                # Find or create lot - WITHOUT any expiration date
                lot = lot_obj.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)
                
                if not lot:
                    # Create lot with explicitly NO expiration date
                    lot_vals = {
                        'name': lot_name,
                        'product_id': move.product_id.id,
                        'company_id': move.company_id.id,
                        'expiration_date': False,  # Explicitly set to False
                        'alert_date': False,
                        'use_date': False,
                        'removal_date': False,
                    }
                    lot = lot_obj.create(lot_vals)
                    
                    # Double-check and force clear if still set
                    if lot.expiration_date:
                        lot.write({'expiration_date': False})
                        _logger.info(f"FORCE CLEARED expiration_date for lot {lot_name}")
                    
                    _logger.info(f"Created new lot {lot_name} (ID: {lot.id}) with NO expiration date")
                else:
                    _logger.info(f"Found existing lot {lot_name} (ID: {lot.id}) with expiration: {lot.expiration_date}")
                
                # Create move line values - DO NOT set expiration_date if lot has none
                vals = {
                    'lot_id': lot.id,
                    'quantity': quantity,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                }
                
                # ONLY set expiration if the lot has one
                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date
                    _logger.info(f"Setting expiration_date from lot: {lot.expiration_date}")
                else:
                    # Explicitly set to False - do NOT set any date
                    vals['expiration_date'] = False
                    _logger.info(f"No expiration date for lot {lot_name} - keeping empty")
                
                # Set MFG date from lot if it exists
                if hasattr(lot, 'x_studio_mfg_date_lot') and lot.x_studio_mfg_date_lot:
                    vals['x_studio_mfg_date_receipt'] = lot.x_studio_mfg_date_lot
                    _logger.info(f"Setting MFG date from lot: {lot.x_studio_mfg_date_lot}")
                
                move_line_vals.append(vals)
                _logger.info(f"Added move line vals: {vals}")
                
        else:  # mode == 'generate'
            _logger.info("Generate mode: generating serial/lot numbers")
            start_serial = first_lot or 'LOT001'
            count = int(count) if count else 1
            
            _logger.info(f"Start serial: {start_serial}, Count: {count}")
            
            for i in range(count):
                if i == 0:
                    serial_number = start_serial
                else:
                    try:
                        serial_number = str(int(start_serial) + i)
                    except:
                        serial_number = f"{start_serial}_{i+1}"
                
                _logger.info(f"Generating serial #{i+1}: {serial_number}")
                
                lot = lot_obj.search([
                    ('name', '=', serial_number),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)
                
                if not lot:
                    lot_vals = {
                        'name': serial_number,
                        'product_id': move.product_id.id,
                        'company_id': move.company_id.id,
                        'expiration_date': False,
                        'alert_date': False,
                        'use_date': False,
                        'removal_date': False,
                    }
                    lot = lot_obj.create(lot_vals)
                    
                    if lot.expiration_date:
                        lot.write({'expiration_date': False})
                        _logger.info(f"CLEARED expiration_date for lot {serial_number}")
                    _logger.info(f"Created new lot {serial_number} WITHOUT expiration date")
                
                vals = {
                    'lot_id': lot.id,
                    'quantity': 1.0,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                }
                
                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date
                else:
                    vals['expiration_date'] = False
                
                move_line_vals.append(vals)
        
        # Format values for the web client
        formatted_vals = []
        for values in move_line_vals:
            formatted = {}
            for key, value in values.items():
                field = self.env['stock.move.line']._fields.get(key)
                if field and isinstance(field, fields.Many2one):
                    if value:
                        # For many2one fields, return as a tuple (id, display_name)
                        record = self.env[field.comodel_name].browse(value)
                        formatted[key] = (value, record.display_name)
                    else:
                        formatted[key] = False
                else:
                    formatted[key] = value
            formatted_vals.append(formatted)
        
        _logger.info(f"Returning {len(formatted_vals)} move line values")
        return formatted_vals


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    # Completely remove the default by redefining the field
    expiration_date = fields.Datetime(
        string='Expiration Date',
        default=False,  # Explicitly set default to False
        help="This is the date on which the goods with this Serial Number may become dangerous and must not be consumed."
    )
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to ensure expiration_date is ONLY set if explicitly provided.
        """
        _logger.info(f"=== OVERRIDING StockLot.create ===")
        _logger.info(f"Creating lot with vals: {vals_list}")
        
        # Process each vals dict
        for vals in vals_list:
            # Ensure expiration_date is explicitly set
            if 'expiration_date' not in vals:
                vals['expiration_date'] = False
                _logger.info("expiration_date not provided, setting to False")
            elif vals.get('expiration_date'):
                _logger.info(f"expiration_date provided: {vals['expiration_date']}")
            else:
                vals['expiration_date'] = False
                _logger.info("expiration_date set to False")
            
            # Only sync other date fields if expiration_date is explicitly set
            if vals.get('expiration_date'):
                if 'alert_date' not in vals:
                    vals['alert_date'] = vals['expiration_date']
                if 'use_date' not in vals:
                    vals['use_date'] = vals['expiration_date']
                if 'removal_date' not in vals:
                    vals['removal_date'] = vals['expiration_date']
                _logger.info(f"Setting all date fields from expiration_date: {vals['expiration_date']}")
            else:
                # Explicitly clear all date fields
                vals['alert_date'] = False
                vals['use_date'] = False
                vals['removal_date'] = False
                _logger.info("Creating lot with ALL date fields set to False")
        
        result = super().create(vals_list)
        
        # Final verification - ensure no date fields are set by default
        for lot in result:
            if lot.expiration_date:
                lot.write({'expiration_date': False})
                _logger.info(f"FINAL CLEAR: Cleared expiration_date for lot {lot.name}")
            if hasattr(lot, 'alert_date') and lot.alert_date:
                lot.write({'alert_date': False})
            if hasattr(lot, 'use_date') and lot.use_date:
                lot.write({'use_date': False})
            if hasattr(lot, 'removal_date') and lot.removal_date:
                lot.write({'removal_date': False})
        
        _logger.info(f"Created lot(s) with IDs: {result.ids}")
        return result
    
    def write(self, vals):
        """
        Override write to ensure all date fields are kept in sync.
        """
        _logger.info(f"=== OVERRIDING StockLot.write ===")
        _logger.info(f"Writing to lot {self.ids} with vals: {vals}")
        
        # If expiration_date is being updated, sync other date fields
        if 'expiration_date' in vals:
            if vals['expiration_date']:
                if 'alert_date' not in vals:
                    vals['alert_date'] = vals['expiration_date']
                if 'use_date' not in vals:
                    vals['use_date'] = vals['expiration_date']
                if 'removal_date' not in vals:
                    vals['removal_date'] = vals['expiration_date']
                _logger.info(f"Setting all date fields from expiration_date: {vals['expiration_date']}")
            else:
                # If expiration_date is being cleared, clear other date fields too
                if 'alert_date' not in vals:
                    vals['alert_date'] = False
                if 'use_date' not in vals:
                    vals['use_date'] = False
                if 'removal_date' not in vals:
                    vals['removal_date'] = False
                _logger.info("Clearing all date fields")
        
        result = super().write(vals)
        
        # If expiration_date was updated, sync with related move lines
        if 'expiration_date' in vals:
            for lot in self:
                _logger.info(f"Syncing move lines for lot {lot.name} with expiration {lot.expiration_date}")
                move_lines = self.env['stock.move.line'].search([
                    ('lot_id', '=', lot.id)
                ])
                if move_lines:
                    move_lines._sync_expiration_with_lot()
                    _logger.info(f"Synced {len(move_lines)} move lines")
        
        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_confirm(self):
        _logger.info("=== OVERRIDING stock.picking.action_confirm ===")
        result = super().action_confirm()
        
        for picking in self:
            _logger.info(f"Syncing expiration dates for picking {picking.name}")
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                        if line.expiration_date != exp_date:
                            line.write({'expiration_date': exp_date})
                            _logger.info(f"Fixed expiration for line {line.id}: {exp_date}")
        
        return result
    
    def button_validate(self):
        _logger.info("=== OVERRIDING stock.picking.button_validate ===")
        
        # Sync before validation
        for picking in self:
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                        if line.expiration_date != exp_date:
                            line.write({'expiration_date': exp_date})
                            _logger.info(f"Fixed expiration before validation for line {line.id}: {exp_date}")
        
        result = super().button_validate()
        
        # Sync after validation
        for picking in self:
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                        if line.expiration_date != exp_date:
                            line.write({'expiration_date': exp_date})
                            _logger.info(f"Fixed expiration after validation for line {line.id}: {exp_date}")
        
        return result