# Copyright © 2023 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/17.0/legal/licenses.html).

from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    gtm_container_key = fields.Char(string='Container ID')

    def gtm_get_key(self):
        self.ensure_one()
        return self.gtm_container_key or ''
