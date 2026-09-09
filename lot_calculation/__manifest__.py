{
    'name': 'Lot Calculation',
    'version': '19.0.1.0',
    'category': 'Inventory',
    'summary': 'Advanced Lot/Serial Calculation for Stock Moves',
    'description': 'Add lot calculation dialog alongside import lots functionality for stock moves.',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_move_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lot_calculation/static/src/js/lot_calculation_widget.js',
            'lot_calculation/static/src/xml/lot_calculation_templates.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}