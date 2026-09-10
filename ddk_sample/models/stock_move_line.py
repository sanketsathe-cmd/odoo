from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging
import re

logging.getLogger('odoo.http').setLevel(logging.ERROR)

_logger = logging.getLogger(__name__)

DATE_FORMATS = (
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
    '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%d-%m-%Y',
    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
)


def _try_parse_date(text):
    """Return a datetime if the text matches any known format, else None."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


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
                else:
                    record.expiration_date = False
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

    @api.constrains('lot_id', 'product_id')
    def _check_lot_product(self):
        for line in self:
            if line.lot_id:
                if not line.product_id:
                    if line.move_id and line.move_id.product_id:
                        line.product_id = line.move_id.product_id
                    elif line.picking_id and line.picking_id.move_ids:
                        move = line.picking_id.move_ids[:1]
                        if move and move.product_id:
                            line.product_id = move.product_id
                    elif line.lot_id.product_id:
                        line.product_id = line.lot_id.product_id

                if line.product_id and line.lot_id.product_id:
                    if line.product_id != line.lot_id.product_id:
                        product = line.product_id
                        product_code = product.default_code or product.name[:10]
                        new_lot_name = f"{line.lot_id.name}-{product_code}"

                        existing_lot = self.env['stock.lot'].search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', product.id)
                        ], limit=1)

                        if existing_lot:
                            line.lot_id = existing_lot.id
                        else:
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

    @api.model_create_multi
    def create(self, vals_list):
        processed_vals_list = []
        for vals in vals_list:
            new_vals = dict(vals)

            product_id = new_vals.get('product_id')
            if not product_id and new_vals.get('move_id'):
                move = self.env['stock.move'].browse(new_vals['move_id'])
                if move.exists() and move.product_id:
                    product_id = move.product_id.id
                    new_vals['product_id'] = product_id

            if not product_id and new_vals.get('picking_id'):
                picking = self.env['stock.picking'].browse(new_vals['picking_id'])
                if picking.exists():
                    move = picking.move_ids[:1]
                    if move and move.product_id:
                        product_id = move.product_id.id
                        new_vals['product_id'] = product_id

            if not product_id and new_vals.get('lot_id'):
                lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                if lot.exists() and lot.product_id:
                    product_id = lot.product_id.id
                    new_vals['product_id'] = product_id

            if new_vals.get('lot_id') and new_vals.get('product_id'):
                lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                product = self.env['product.product'].browse(new_vals['product_id'])

                if lot.exists() and lot.product_id.id != new_vals['product_id']:
                    product_code = product.default_code or product.name[:10]
                    new_lot_name = f"{lot.name}-{product_code}"

                    existing_new_lot = self.env['stock.lot'].search([
                        ('name', '=', new_lot_name),
                        ('product_id', '=', new_vals['product_id'])
                    ], limit=1)

                    if existing_new_lot:
                        new_vals['lot_id'] = existing_new_lot.id
                    else:
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

            if not new_vals.get('product_id'):
                if new_vals.get('lot_id'):
                    lot = self.env['stock.lot'].browse(new_vals['lot_id'])
                    if lot.exists() and lot.product_id:
                        new_vals['product_id'] = lot.product_id.id

            if not new_vals.get('product_id'):
                raise ValidationError("Cannot create move line: No product found.")

            processed_vals_list.append(new_vals)

        records = super().create(processed_vals_list)

        for record in records:
            if record.lot_id:
                record._compute_mfg_date()
                record._compute_expiration_date()

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

        return result

    def _sync_expiration_with_lot(self):
        for line in self:
            if line.lot_id:
                exp_date = line.lot_id.expiration_date if line.lot_id.expiration_date else False
                if line.expiration_date != exp_date:
                    line.expiration_date = exp_date

            if line.lot_id and hasattr(line.lot_id, 'x_studio_mfg_date_lot'):
                if line.x_studio_mfg_date_receipt != line.lot_id.x_studio_mfg_date_lot:
                    line.x_studio_mfg_date_receipt = line.lot_id.x_studio_mfg_date_lot


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def action_generate_lot_line_vals(self, *args, **kwargs):
        """
        OVERRIDE: Generate lot line values with expiration + MFG dates + result package.

        Import line format (tab-separated):
            lot_name <TAB> qty [<TAB> expiration_date [<TAB> mfg_date [<TAB> package_name]]]

        Date formats supported:
            2026-09-25, 2026-09-25 10:09, 25-09-2026, 25-09-2026 10:09, 25/09/2026 ...
        """
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

        context_data = context_data or {}
        mode = mode or 'import'
        first_lot = first_lot or ''
        count = count or 0
        lot_text = lot_text or ''

        move = self

        if isinstance(context_data, dict):
            if context_data.get('active_id'):
                move = self.browse(context_data.get('active_id'))
            elif context_data.get('default_product_id'):
                move = self.new({
                    'product_id': context_data.get('default_product_id'),
                    'location_id': context_data.get('default_location_id'),
                    'location_dest_id': context_data.get('default_location_dest_id'),
                    'company_id': self.env.company.id,
                    'product_uom': context_data.get('default_uom_id'),
                    'scheduled_date': context_data.get('default_scheduled_date'),
                })

        if not move or not move.id:
            if self and self.ids:
                move = self.browse(self.ids[0])

        if not move:
            raise UserError('Stock move not found')

        move_line_vals = []
        lot_obj = self.env['stock.lot']
        package_obj = self.env['stock.package']

        if mode == 'import':
            if not lot_text or not lot_text.strip():
                raise UserError('Please enter lot numbers and quantities.')

            lines = lot_text.strip().split('\n')

            for line in lines:
                if not line.strip():
                    continue

                # Prefer TAB split so "25-09-2026 10:09" stays a single token
                if '\t' in line:
                    parts = [p.strip() for p in line.strip().split('\t') if p.strip()]
                else:
                    parts = re.split(r'\s+', line.strip())

                _logger.info(f"Raw parts: {parts}")

                if len(parts) < 2:
                    raise UserError(
                        f'Invalid line: "{line}". '
                        f'Expected: lot_name<TAB>qty[<TAB>expiration_date[<TAB>mfg_date[<TAB>package]]]'
                    )

                lot_name = parts[0].strip()
                quantity = None
                expiration_date = None
                mfg_date = None
                package_name = None

                # Column 2: quantity (required)
                try:
                    quantity = float(parts[1])
                except ValueError:
                    raise UserError(
                        f'Invalid quantity "{parts[1]}" in line: "{line}". '
                        f'Expected a number in column 2.'
                    )

                # Column 3: expiration date (optional)
                if len(parts) >= 3 and parts[2]:
                    expiration_date = _try_parse_date(parts[2])
                    if not expiration_date:
                        raise UserError(
                            f'Invalid expiration date "{parts[2]}" in line: "{line}". '
                            f'Use format DD-MM-YYYY HH:MM or YYYY-MM-DD HH:MM.'
                        )

                # Column 4: MFG date (optional)
                if len(parts) >= 4 and parts[3]:
                    mfg_date = _try_parse_date(parts[3])
                    if not mfg_date:
                        raise UserError(
                            f'Invalid MFG date "{parts[3]}" in line: "{line}". '
                            f'Use format DD-MM-YYYY or YYYY-MM-DD.'
                        )

                # Column 5: result package name (optional)
                if len(parts) >= 5 and parts[4]:
                    package_name = parts[4].strip()

                _logger.info(
                    f"Processing lot: {lot_name}, qty: {quantity}, "
                    f"expiration: {expiration_date}, mfg: {mfg_date}, package: {package_name}"
                )

                if quantity is None or quantity <= 0:
                    raise UserError(f'Quantity must be greater than 0 for lot {lot_name}.')

                # Find or create the correct lot for this product
                lot = lot_obj.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)

                if not lot:
                    existing_lot = lot_obj.search([('name', '=', lot_name)], limit=1)

                    if existing_lot:
                        # Lot exists for another product → make a unique one
                        product_code = move.product_id.default_code or move.product_id.name[:10]
                        new_lot_name = f"{lot_name}-{product_code}"

                        lot = lot_obj.search([
                            ('name', '=', new_lot_name),
                            ('product_id', '=', move.product_id.id)
                        ], limit=1)

                        if not lot:
                            lot_vals = {
                                'name': new_lot_name,
                                'product_id': move.product_id.id,
                                'company_id': move.company_id.id,
                                'expiration_date': expiration_date or existing_lot.expiration_date or False,
                                'alert_date': expiration_date or existing_lot.alert_date or False,
                                'use_date': expiration_date or existing_lot.use_date or False,
                                'removal_date': expiration_date or existing_lot.removal_date or False,
                            }
                            if mfg_date:
                                lot_vals['x_studio_mfg_date_lot'] = mfg_date.date()
                            elif hasattr(existing_lot, 'x_studio_mfg_date_lot') and existing_lot.x_studio_mfg_date_lot:
                                lot_vals['x_studio_mfg_date_lot'] = existing_lot.x_studio_mfg_date_lot

                            lot = lot_obj.create(lot_vals)
                            _logger.info(f"Created new lot {new_lot_name} (ID: {lot.id})")
                    else:
                        # Brand new lot
                        lot_vals = {
                            'name': lot_name,
                            'product_id': move.product_id.id,
                            'company_id': move.company_id.id,
                            'expiration_date': False,
                            'alert_date': False,
                            'use_date': False,
                            'removal_date': False,
                        }
                        if expiration_date:
                            lot_vals['expiration_date'] = expiration_date
                            lot_vals['alert_date'] = expiration_date
                            lot_vals['use_date'] = expiration_date
                            lot_vals['removal_date'] = expiration_date
                        if mfg_date:
                            lot_vals['x_studio_mfg_date_lot'] = mfg_date.date()

                        lot = lot_obj.create(lot_vals)
                        _logger.info(f"Created new lot {lot_name} (ID: {lot.id})")
                else:
                    # Existing lot — update only missing fields
                    updates = {}
                    if expiration_date and not lot.expiration_date:
                        updates.update({
                            'expiration_date': expiration_date,
                            'alert_date': expiration_date,
                            'use_date': expiration_date,
                            'removal_date': expiration_date,
                        })
                    if mfg_date and hasattr(lot, 'x_studio_mfg_date_lot') and not lot.x_studio_mfg_date_lot:
                        updates['x_studio_mfg_date_lot'] = mfg_date.date()

                    if updates:
                        lot.write(updates)
                        _logger.info(f"Updated lot {lot_name} with {updates}")

                # Resolve or create result package
                package = None
                if package_name:
                    package = package_obj.search([('name', '=', package_name)], limit=1)
                    if not package:
                        package = package_obj.create({
                            'name': package_name,
                            'company_id': move.company_id.id or self.env.company.id,
                        })
                        _logger.info(f"Created package {package_name} (ID: {package.id})")
                    else:
                        _logger.info(f"Using existing package {package_name} (ID: {package.id})")

                # Build move line values
                vals = {
                    'lot_id': lot.id,
                    'quantity': quantity,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,
                }

                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date

                if hasattr(lot, 'x_studio_mfg_date_lot') and lot.x_studio_mfg_date_lot:
                    vals['x_studio_mfg_date_receipt'] = lot.x_studio_mfg_date_lot

                if package:
                    vals['result_package_id'] = package.id

                move_line_vals.append(vals)
                _logger.info(f"Added move line vals: {vals}")

        else:  # mode == 'generate'
            start_serial = first_lot or 'LOT001'
            count = int(count) if count else 1

            for i in range(count):
                if i == 0:
                    serial_number = start_serial
                else:
                    try:
                        serial_number = str(int(start_serial) + i)
                    except Exception:
                        serial_number = f"{start_serial}_{i+1}"

                lot = lot_obj.search([
                    ('name', '=', serial_number),
                    ('product_id', '=', move.product_id.id)
                ], limit=1)

                if not lot:
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
                    else:
                        lot = lot_obj.create({
                            'name': serial_number,
                            'product_id': move.product_id.id,
                            'company_id': move.company_id.id,
                            'expiration_date': False,
                            'alert_date': False,
                            'use_date': False,
                            'removal_date': False,
                        })

                vals = {
                    'lot_id': lot.id,
                    'quantity': 1.0,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                    'product_id': move.product_id.id,
                }

                if lot.expiration_date:
                    vals['expiration_date'] = lot.expiration_date

                if hasattr(lot, 'x_studio_mfg_date_lot') and lot.x_studio_mfg_date_lot:
                    vals['x_studio_mfg_date_receipt'] = lot.x_studio_mfg_date_lot

                move_line_vals.append(vals)

        # Format for web client
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
        for vals in vals_list:
            if not vals.get('expiration_date'):
                vals['expiration_date'] = False
                vals['alert_date'] = False
                vals['use_date'] = False
                vals['removal_date'] = False
            else:
                if 'alert_date' not in vals:
                    vals['alert_date'] = vals['expiration_date']
                if 'use_date' not in vals:
                    vals['use_date'] = vals['expiration_date']
                if 'removal_date' not in vals:
                    vals['removal_date'] = vals['expiration_date']

        return super().create(vals_list)

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

        if 'expiration_date' in vals or 'x_studio_mfg_date_lot' in vals:
            for lot in self:
                move_lines = self.env['stock.move.line'].search([('lot_id', '=', lot.id)])
                if move_lines:
                    move_lines._sync_expiration_with_lot()

        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _sync_move_line_dates(self):
        for picking in self:
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    if line.lot_id:
                        line._sync_expiration_with_lot()

    def action_confirm(self):
        result = super().action_confirm()
        self._sync_move_line_dates()
        return result

    def button_validate(self):
        self._sync_move_line_dates()
        result = super().button_validate()
        self._sync_move_line_dates()
        return result