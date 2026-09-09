{
    'name': 'Lot Calculation',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Lot Calculation for Stock Moves',
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
}