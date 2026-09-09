from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging
import re

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
                if hasattr(record.lot_id, 'expiration_date'):
                    record.lot_id.expiration_date = record.expiration_date
                if hasattr(record.lot_id, 'alert_date'):
                    record.lot_id.alert_date = record.expiration_date
                if hasattr(record.lot_id, 'use_date'):
                    record.lot_id.use_date = record.expiration_date
                if hasattr(record.lot_id, 'removal_date'):
                    record.lot_id.removal_date = record.expiration_date

    # OVERRIDE THE CONSTRAINT TO HANDLE THE ISSUE
    @api.constrains('lot_id', 'product_id')
    def _check_lot_product(self):
        """Override the constraint to properly handle product_id"""
        for line in self:
            if line.lot_id:
                # If product_id is False, try to get it from the move or picking
                if not line.product_id:
                    if line.move_id and line.move_id.product_id:
                        line.product_id = line.move_id.product_id
                        _logger.info(f"Fixed missing product_id from move for lot {line.lot_id.name}")
                    elif line.picking_id and line.picking_id.move_ids:
                        move = line.picking_id.move_ids[:1]
                        if move and move.product_id:
                            line.product_id = move.product_id
                            _logger.info(f"Fixed missing product_id from picking for lot {line.lot_id.name}")
                    elif line.lot_id.product_id:
                        line.product_id = line.lot_id.product_id
                        _logger.info(f"Fixed missing product_id from lot for lot {line.lot_id.name}")
                
                # Now check compatibility
                if line.product_id and line.lot_id.product_id:
                    if line.product_id != line.lot_id.product_id:
                        # Instead of raising error, create a new lot with correct product
                        _logger.warning(
                            f"Lot {line.lot_id.name} is for product {line.lot_id.product_id.name} but "
                            f"move line is for {line.product_id.name}. Attempting to fix..."
                        )
                        
                        # Try to find or create a lot with the correct product
                        product = line.product_id
                        product_code = product.default_code or product.name[:10]
                        new_lot_name = f"{line.lot_id.name}-{product_code}"
                        
                        existing_lot = self.env['stock.lot'].search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', product.id)
                        ], limit=1)
                        
                        if existing_lot:
                            line.lot_id = existing_lot.id
                            _logger.info(f"Fixed: Using existing lot {new_lot_name}")
                        else:
                            # Create new lot with copied dates
                            new_lot = self.env['stock.lot'].create({
                                'name': new_lot_name,
                                'product_id': product.id,
                                'company_id': line.company_id.id,
                                'expiration_date': line.lot_id.expiration_date or False,
                                'alert_date': line.lot_id.alert_date or False,
                                'use_date': line.lot_id.use_date or False,
                                'removal_date': line.lot_id.removal_date or False,
                            })
                            if hasattr(line.lot_id, 'x_studio_mfg_date_lot') and line.lot_id.x_studio_mfg_date_lot:
                                new_lot.write({'x_studio_mfg_date_lot': line.lot_id.x_studio_mfg_date_lot})
                            
                            line.lot_id = new_lot.id
                            _logger.info(f"Fixed: Created new lot {new_lot_name} for product {product.name}")

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("=== OVERRIDING StockMoveLine.create ===")
        
        processed_vals_list = []
        for vals in vals_list:
            _logger.info(f"Original vals: {vals}")
            
            # Create a copy to modify
            new_vals = dict(vals)
            
            # CRITICAL: Ensure product_id is set
            product_id = new_vals.get('product_id')
            
            # If no product_id, try to get from move_id
            if not product_id and new_vals.get('move_id'):
                move = self.env['stock.move'].browse(new_vals['move_id'])
                if move.exists() and move.product_id:
                    product_id = move.product_id.id
                    new_vals['product_id'] = product_id
                    _logger.info(f"Got product_id {product_id} from move")
            
            # If still no product_id, try to get from picking_id
            if not product_id and new_vals.get('picking_id'):
                picking = self.env['stock.picking'].browse(new_vals['picking_id'])
                if picking.exists():
                    move = picking.move_ids[:1]
                    if move and move.product_id:
                        product_id = move.product_id.id
                        new_vals['product_id'] = product_id
                        _logger.info(f"Got product_id {product_id} from picking")
            
            # If still no product_id and lot_id exists, get from lot
            if not product_id and new_vals.get('lot_id'):
                lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                if lot.exists() and lot.product_id:
                    product_id = lot.product_id.id
                    new_vals['product_id'] = product_id
                    _logger.info(f"Got product_id {product_id} from lot")
            
            # Now handle lot compatibility with the product
            if new_vals.get('lot_id') and new_vals.get('product_id'):
                lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                product = self.env['product.product'].browse(new_vals['product_id'])
                
                _logger.info(f"Lot {lot.name} has product_id: {lot.product_id.id if lot else 'None'}")
                _logger.info(f"Move expects product_id: {new_vals['product_id']}")
                
                if lot.exists() and lot.product_id.id != new_vals['product_id']:
                    _logger.warning(
                        f"Lot {lot.name} is for product {lot.product_id.name} but move is for {product.name}"
                    )
                    
                    # Create a new lot with the correct product and unique name
                    product_code = product.default_code or product.name[:10]
                    new_lot_name = f"{lot.name}-{product_code}"
                    
                    # Check if this new lot already exists
                    existing_new_lot = self.env['stock.lot'].search([
                        ('name', '=', new_lot_name),
                        ('product_id', '=', new_vals['product_id'])
                    ], limit=1)
                    
                    if existing_new_lot:
                        _logger.info(f"Using existing lot {new_lot_name} (ID: {existing_new_lot.id})")
                        new_vals['lot_id'] = existing_new_lot.id
                    else:
                        # Copy all date fields from existing lot
                        new_lot = self.env['stock.lot'].create({
                            'name': new_lot_name,
                            'product_id': new_vals['product_id'],
                            'company_id': new_vals.get('company_id', self.env.company.id),
                            'expiration_date': lot.expiration_date or False,
                            'alert_date': lot.alert_date or False,
                            'use_date': lot.use_date or False,
                            'removal_date': lot.removal_date or False,
                        })
                        
                        if hasattr(lot, 'x_studio_mfg_date_lot') and lot.x_studio_mfg_date_lot:
                            new_lot.write({'x_studio_mfg_date_lot': lot.x_studio_mfg_date_lot})
                        
                        new_vals['lot_id'] = new_lot.id
                        _logger.info(f"Created new lot {new_lot_name} (ID: {new_lot.id}) for product {product.name}")
            
            # Ensure product_id is set before creating
            if not new_vals.get('product_id'):
                _logger.error(f"CRITICAL: No product_id found for vals: {new_vals}")
                # Try to get from lot one more time
                if new_vals.get('lot_id'):
                    lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                    if lot.exists() and lot.product_id:
                        new_vals['product_id'] = lot.product_id.id
                        _logger.info(f"Final attempt: Got product_id {lot.product_id.id} from lot")
            
            # If still no product_id, raise error
            if not new_vals.get('product_id'):
                raise ValidationError("Cannot create move line: No product found.")
            
            processed_vals_list.append(new_vals)
            _logger.info(f"Processed vals: {new_vals}")

        records = super().create(processed_vals_list)

        for record in records:
            if record.lot_id:
                record._compute_mfg_date()
                record._compute_expiration_date()
                _logger.info(f"Created move line with lot {record.lot_id.name}, product: {record.product_id.name}, expiration: {record.expiration_date}")

        return records

    def write(self, vals):
        result = super().write(vals)

        if 'lot_id' in vals:
            for record in self:
                record._compute_mfg_date()
                record._compute_expiration_date()
        else:
            for record in self:
                if record.lot_id:
                    if hasattr(record.lot_id, 'x_studio_mfg_date_lot'):
                        mfg_date = record.lot_id.x_studio_mfg_date_lot
                        if mfg_date and record.x_studio_mfg_date_receipt != mfg_date:
                            record.x_studio_mfg_date_receipt = mfg_date

                    exp_date = False
                    if hasattr(record.lot_id, 'expiration_date') and record.lot_id.expiration_date:
                        exp_date = record.lot_id.expiration_date

                    if record.expiration_date != exp_date:
                        record.expiration_date = exp_date
                        _logger.info(f"Synced expiration_date for move line {record.id} to: {exp_date}")

        return result

    def _sync_expiration_with_lot(self):
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
        """
        _logger.info("=== OVERRIDING action_generate_lot_line_vals ===")
        _logger.info(f"args: {args}")
        _logger.info(f"kwargs: {kwargs}")

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
        _logger.info(f"Product ID: {move.product_id.id if move.product_id else 'Unknown'}")

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

                # Split by whitespace (handles tabs and spaces)
                parts = re.split(r'\s+', line.strip())
                _logger.info(f"Raw parts: {parts}")

                if len(parts) < 2:
                    raise UserError(f'Invalid line format: "{line}". Expected: lot_number quantity [expiration_date]')

                # Try to identify which part is the lot name, quantity, and date
                # First part is always the lot name
                lot_name = parts[0].strip()
                
                # Try to find quantity and expiration date from remaining parts
                quantity = None
                expiration_date = None
                
                # Check each remaining part to identify quantity (float) and date
                for part in parts[1:]:
                    try:
                        # Try to convert to float - if successful and quantity is None, it's the quantity
                        float_val = float(part)
                        if quantity is None:
                            quantity = float_val
                        else:
                            # If we already have a quantity, this might be something else (ignore)
                            _logger.warning(f"Multiple numeric values found, using first: {quantity}, ignoring: {part}")
                    except ValueError:
                        # If it's not a number, it might be a date
                        try:
                            # Try to parse as date
                            datetime.strptime(part, '%Y-%m-%d')
                            expiration_date = part
                        except ValueError:
                            # Try other common date formats
                            try:
                                datetime.strptime(part, '%Y-%m-%d %H:%M')
                                expiration_date = part
                            except ValueError:
                                _logger.warning(f"Unrecognized value: {part}")

                # If quantity is still None, use default
                if quantity is None:
                    quantity = 1.0
                    _logger.info(f"No quantity found, using default: {quantity}")

                _logger.info(f"Processing lot: {lot_name}, quantity: {quantity}, expiration_date: {expiration_date}")

                if quantity <= 0:
                    raise UserError(f'Quantity must be greater than 0 for lot {lot_name}.')

                # CRITICAL: First try to find lot with the correct product
                lot = lot_obj.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)

                # If not found, check if it exists for a different product
                if not lot:
                    existing_lot = lot_obj.search([('name', '=', lot_name)], limit=1)

                    if existing_lot:
                        # Lot exists for a different product - create new one with unique name
                        product_code = move.product_id.default_code or move.product_id.name[:10]
                        new_lot_name = f"{lot_name}-{product_code}"
                        
                        # Check if this new lot already exists
                        lot = lot_obj.search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', move.product_id.id)
                        ], limit=1)

                        if not lot:
                            _logger.warning(
                                f"Lot {lot_name} exists for product {existing_lot.product_id.name}. "
                                f"Creating {new_lot_name} for {move.product_id.name}"
                            )

                            # Copy all date fields from existing lot
                            lot_vals = {
                                'name': new_lot_name,
                                'product_id': move.product_id.id,
                                'company_id': move.company_id.id,
                                'expiration_date': existing_lot.expiration_date or False,
                                'alert_date': existing_lot.alert_date or False,
                                'use_date': existing_lot.use_date or False,
                                'removal_date': existing_lot.removal_date or False,
                            }
                            lot = lot_obj.create(lot_vals)

                            # Copy MFG date if exists
                            if hasattr(existing_lot, 'x_studio_mfg_date_lot') and existing_lot.x_studio_mfg_date_lot:
                                lot.write({'x_studio_mfg_date_lot': existing_lot.x_studio_mfg_date_lot})
                                _logger.info(f"Copied MFG date: {existing_lot.x_studio_mfg_date_lot}")

                            _logger.info(f"Created new lot {new_lot_name} (ID: {lot.id}) for {move.product_id.name}")
                        else:
                            _logger.info(f"Using existing lot {new_lot_name} (ID: {lot.id})")
                    else:
                        # Lot doesn't exist at all - create brand new
                        lot_vals = {
                            'name': lot_name,
                            'product_id': move.product_id.id,
                            'company_id': move.company_id.id,
                            'expiration_date': False,
                            'alert_date': False,
                            'use_date': False,
                            'removal_date': False,
                        }
                        
                        # If expiration date was provided, use it
                        if expiration_date:
                            try:
                                exp_datetime = datetime.strptime(expiration_date, '%Y-%m-%d')
                                lot_vals['expiration_date'] = exp_datetime
                                lot_vals['alert_date'] = exp_datetime
                                lot_vals['use_date'] = exp_datetime
                                lot_vals['removal_date'] = exp_datetime
                                _logger.info(f"Setting expiration_date from input: {exp_datetime}")
                            except ValueError:
                                try:
                                    exp_datetime = datetime.strptime(expiration_date, '%Y-%m-%d %H:%M')
                                    lot_vals['expiration_date'] = exp_datetime
                                    lot_vals['alert_date'] = exp_datetime
                                    lot_vals['use_date'] = exp_datetime
                                    lot_vals['removal_date'] = exp_datetime
                                    _logger.info(f"Setting expiration_date from input: {exp_datetime}")
                                except ValueError:
                                    _logger.warning(f"Could not parse expiration date: {expiration_date}")
                        
                        lot = lot_obj.create(lot_vals)
                        _logger.info(f"Created new lot {lot_name} (ID: {lot.id}) for {move.product_id.name}")
                else:
                    _logger.info(f"Found existing lot {lot_name} (ID: {lot.id}) for {move.product_id.name}")
                    
                    # If expiration date was provided and lot has no expiration, update it
                    if expiration_date and not lot.expiration_date:
                        try:
                            exp_datetime = datetime.strptime(expiration_date, '%Y-%m-%d')
                            lot.write({
                                'expiration_date': exp_datetime,
                                'alert_date': exp_datetime,
                                'use_date': exp_datetime,
                                'removal_date': exp_datetime
                            })
                            _logger.info(f"Updated lot {lot_name} with expiration_date: {exp_datetime}")
                        except ValueError:
                            try:
                                exp_datetime = datetime.strptime(expiration_date, '%Y-%m-%d %H:%M')
                                lot.write({
                                    'expiration_date': exp_datetime,
                                    'alert_date': exp_datetime,
                                    'use_date': exp_datetime,
                                    'removal_date': exp_datetime
                                })
                                _logger.info(f"Updated lot {lot_name} with expiration_date: {exp_datetime}")
                            except ValueError:
                                _logger.warning(f"Could not parse expiration date: {expiration_date}")

                # Now create move line values
                vals = {
                    'lot_id': lot.id,
                    'quantity': quantity,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,  # Explicitly set product_id
                }

                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date
                    _logger.info(f"Setting expiration_date from lot: {lot.expiration_date}")
                else:
                    vals['expiration_date'] = False
                    _logger.info(f"No expiration date for lot {lot_name} - keeping empty")

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
                    # Check if exists for another product
                    existing_lot = lot_obj.search([('name', '=', serial_number)], limit=1)
                    if existing_lot:
                        product_code = move.product_id.default_code or move.product_id.name[:10]
                        new_lot_name = f"{serial_number}-{product_code}"
                        
                        lot = lot_obj.search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', move.product_id.id)
                        ], limit=1)
                        
                        if not lot:
                            lot_vals = {
                                'name': new_lot_name,
                                'product_id': move.product_id.id,
                                'company_id': move.company_id.id,
                                'expiration_date': existing_lot.expiration_date or False,
                                'alert_date': existing_lot.alert_date or False,
                                'use_date': existing_lot.use_date or False,
                                'removal_date': existing_lot.removal_date or False,
                            }
                            lot = lot_obj.create(lot_vals)
                            if hasattr(existing_lot, 'x_studio_mfg_date_lot') and existing_lot.x_studio_mfg_date_lot:
                                lot.write({'x_studio_mfg_date_lot': existing_lot.x_studio_mfg_date_lot})
                            _logger.info(f"Created new lot {new_lot_name} for {move.product_id.name}")
                    else:
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
                        _logger.info(f"Created new lot {serial_number} for {move.product_id.name}")

                vals = {
                    'lot_id': lot.id,
                    'quantity': 1.0,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,  # Explicitly set product_id
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
                        record = self.env[field.comodel_name].browse(value)
                        formatted[key] = (value, record.display_name)
                    else:
                        formatted[key] = False
                else:
                    formatted[key] = value
            formatted_vals.append(formatted)

        _logger.info(f"Returning {len(formatted_vals)} move line values")
        
        """
        OVERRIDE: Generate lot line values with proper expiration dates from lots.
        """
        _logger.info("=== OVERRIDING action_generate_lot_line_vals ===")
        _logger.info(f"args: {args}")
        _logger.info(f"kwargs: {kwargs}")

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
        _logger.info(f"Product ID: {move.product_id.id if move.product_id else 'Unknown'}")

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

                # CRITICAL: First try to find lot with the correct product
                lot = lot_obj.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)

                # If not found, check if it exists for a different product
                if not lot:
                    existing_lot = lot_obj.search([('name', '=', lot_name)], limit=1)

                    if existing_lot:
                        # Lot exists for a different product - create new one with unique name
                        product_code = move.product_id.default_code or move.product_id.name[:10]
                        new_lot_name = f"{lot_name}-{product_code}"
                        
                        # Check if this new lot already exists
                        lot = lot_obj.search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', move.product_id.id)
                        ], limit=1)

                        if not lot:
                            _logger.warning(
                                f"Lot {lot_name} exists for product {existing_lot.product_id.name}. "
                                f"Creating {new_lot_name} for {move.product_id.name}"
                            )

                            # Copy all date fields from existing lot
                            lot_vals = {
                                'name': new_lot_name,
                                'product_id': move.product_id.id,
                                'company_id': move.company_id.id,
                                'expiration_date': existing_lot.expiration_date or False,
                                'alert_date': existing_lot.alert_date or False,
                                'use_date': existing_lot.use_date or False,
                                'removal_date': existing_lot.removal_date or False,
                            }
                            lot = lot_obj.create(lot_vals)

                            # Copy MFG date if exists
                            if hasattr(existing_lot, 'x_studio_mfg_date_lot') and existing_lot.x_studio_mfg_date_lot:
                                lot.write({'x_studio_mfg_date_lot': existing_lot.x_studio_mfg_date_lot})
                                _logger.info(f"Copied MFG date: {existing_lot.x_studio_mfg_date_lot}")

                            _logger.info(f"Created new lot {new_lot_name} (ID: {lot.id}) for {move.product_id.name}")
                        else:
                            _logger.info(f"Using existing lot {new_lot_name} (ID: {lot.id})")
                    else:
                        # Lot doesn't exist at all - create brand new
                        lot_vals = {
                            'name': lot_name,
                            'product_id': move.product_id.id,
                            'company_id': move.company_id.id,
                            'expiration_date': False,
                            'alert_date': False,
                            'use_date': False,
                            'removal_date': False,
                        }
                        lot = lot_obj.create(lot_vals)
                        _logger.info(f"Created new lot {lot_name} (ID: {lot.id}) for {move.product_id.name}")
                else:
                    _logger.info(f"Found existing lot {lot_name} (ID: {lot.id}) for {move.product_id.name}")

                # Now create move line values
                vals = {
                    'lot_id': lot.id,
                    'quantity': quantity,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,  # Explicitly set product_id
                }

                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date
                    _logger.info(f"Setting expiration_date from lot: {lot.expiration_date}")
                else:
                    vals['expiration_date'] = False
                    _logger.info(f"No expiration date for lot {lot_name} - keeping empty")

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
                    # Check if exists for another product
                    existing_lot = lot_obj.search([('name', '=', serial_number)], limit=1)
                    if existing_lot:
                        product_code = move.product_id.default_code or move.product_id.name[:10]
                        new_lot_name = f"{serial_number}-{product_code}"
                        
                        lot = lot_obj.search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', move.product_id.id)
                        ], limit=1)
                        
                        if not lot:
                            lot_vals = {
                                'name': new_lot_name,
                                'product_id': move.product_id.id,
                                'company_id': move.company_id.id,
                                'expiration_date': existing_lot.expiration_date or False,
                                'alert_date': existing_lot.alert_date or False,
                                'use_date': existing_lot.use_date or False,
                                'removal_date': existing_lot.removal_date or False,
                            }
                            lot = lot_obj.create(lot_vals)
                            if hasattr(existing_lot, 'x_studio_mfg_date_lot') and existing_lot.x_studio_mfg_date_lot:
                                lot.write({'x_studio_mfg_date_lot': existing_lot.x_studio_mfg_date_lot})
                            _logger.info(f"Created new lot {new_lot_name} for {move.product_id.name}")
                    else:
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
                        _logger.info(f"Created new lot {serial_number} for {move.product_id.name}")

                vals = {
                    'lot_id': lot.id,
                    'quantity': 1.0,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,  # Explicitly set product_id
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

    expiration_date = fields.Datetime(
        string='Expiration Date',
        default=False,
        help="This is the date on which the goods with this Serial Number may become dangerous and must not be consumed."
    )

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(f"=== OVERRIDING StockLot.create ===")
        _logger.info(f"Creating lot with vals: {vals_list}")

        for vals in vals_list:
            if 'expiration_date' not in vals:
                vals['expiration_date'] = False
            elif vals.get('expiration_date'):
                _logger.info(f"expiration_date provided: {vals['expiration_date']}")
            else:
                vals['expiration_date'] = False

            if vals.get('expiration_date'):
                if 'alert_date' not in vals:
                    vals['alert_date'] = vals['expiration_date']
                if 'use_date' not in vals:
                    vals['use_date'] = vals['expiration_date']
                if 'removal_date' not in vals:
                    vals['removal_date'] = vals['expiration_date']
            else:
                vals['alert_date'] = False
                vals['use_date'] = False
                vals['removal_date'] = False

        result = super().create(vals_list)

        for lot in result:
            if lot.expiration_date:
                lot.write({'expiration_date': False})
            if hasattr(lot, 'alert_date') and lot.alert_date:
                lot.write({'alert_date': False})
            if hasattr(lot, 'use_date') and lot.use_date:
                lot.write({'use_date': False})
            if hasattr(lot, 'removal_date') and lot.removal_date:
                lot.write({'removal_date': False})

        return result

    def write(self, vals):
        if 'expiration_date' in vals:
            if vals['expiration_date']:
                if 'alert_date' not in vals:
                    vals['alert_date'] = vals['expiration_date']
                if 'use_date' not in vals:
                    vals['use_date'] = vals['expiration_date']
                if 'removal_date' not in vals:
                    vals['removal_date'] = vals['expiration_date']
            else:
                if 'alert_date' not in vals:
                    vals['alert_date'] = False
                if 'use_date' not in vals:
                    vals['use_date'] = False
                if 'removal_date' not in vals:
                    vals['removal_date'] = False

        result = super().write(vals)

        if 'expiration_date' in vals:
            for lot in self:
                move_lines = self.env['stock.move.line'].search([
                    ('lot_id', '=', lot.id)
                ])
                if move_lines:
                    move_lines._sync_expiration_with_lot()

        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_confirm(self):
        _logger.info("=== OVERRIDING stock.picking.action_confirm ===")
        result = super().action_confirm()

        for picking in self:
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

        for picking in self:
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                        if line.expiration_date != exp_date:
                            line.write({'expiration_date': exp_date})
                            _logger.info(f"Fixed expiration before validation for line {line.id}: {exp_date}")

        result = super().button_validate()

        for picking in self:
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                        if line.expiration_date != exp_date:
                            line.write({'expiration_date': exp_date})
                            _logger.info(f"Fixed expiration after validation for line {line.id}: {exp_date}")

        return result