# Copyright © 2023 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

{
    'name': 'Odoo Google Tag Manager | Odoo GTM',
    'version': '16.0.1.1.0',
    'category': 'Website',
    'author': 'Garazd Creation',
    'website': 'https://garazd.biz/shop',
    'license': 'LGPL-3',
    'summary': 'Google Tag Manager - GTM script',
    'images': ['static/description/banner.png', 'static/description/icon.png'],
    'live_test_url': 'https://garazd.biz/r/VDB',
    'depends': [
        'website',
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/website_templates.xml',
    ],
    'support': 'support@garazd.biz',
    'application': True,
    'installable': True,
    'auto_install': False,
}
