{
    'name': 'DDK Sample',
    'version': '1.02.5',
    'category': 'Supply Chain',
    'summary': 'This is summary...',
    'description': 'This module has code regarding receipts > detailed operation > default odoo import lots',
    'author': 'Divya Kelaskar',
    'application': True,
    'depends': ['base', 'stock', 'stock_account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/ddk_sample_views.xml',
    ],
}