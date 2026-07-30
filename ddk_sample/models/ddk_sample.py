from odoo import models, fields

class DdkSample(models.Model):
    _name = 'ddk.sample'
    _description = 'DDK Sample'

    ddk_name = fields.Char(string="Name")