# Copyright 2020 Carlos Roca <carlos.roca@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from math import ceil

from odoo import api, fields, models


class ProductPrintingQty(models.TransientModel):
    _name = "stock.picking.line.print"
    _rec_name = "product_id"
    _description = "Print Picking Line"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain="[('id', '=', product_id)]",
    )
    quantity = fields.Float(digits="Product Unit of Measure", required=True)
    label_qty = fields.Integer("Quantity of Labels")
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="move_line_id.product_uom_id",
    )
    lot_id = fields.Many2one("stock.production.lot", string="Lot/Serial Number")
    result_package_id = fields.Many2one(
        comodel_name="stock.quant.package", string="Dest. package"
    )

    wizard_id = fields.Many2one("stock.picking.print", string="Wizard")
    move_line_id = fields.Many2one("stock.move.line", "Move", readonly=True)


class WizStockBarcodeSelectionPrinting(models.TransientModel):
    _name = "stock.picking.print"
    _description = "Wizard to select how many barcodes have to be printed"

    @api.model
    def default_get(self, fields):
        ctx = self.env.context.copy()
        res = super().default_get(fields)
        if ctx.get("active_ids") and ctx.get("active_model") == "stock.picking":
            picking_ids = self.env["stock.picking"].browse(ctx.get("active_ids"))
            res.update({"picking_ids": picking_ids.ids})
        return res

    def _default_barcode_report(self):
        barcode_report = self.env.company.barcode_default_report
        if not barcode_report:
            barcode_report = self.env.ref(
                "stock_picking_product_barcode_report.action_label_barcode_report"
            )
        return barcode_report

    picking_ids = fields.Many2many("stock.picking")
    product_print_moves = fields.One2many(
        "stock.picking.line.print", "wizard_id", "Moves"
    )
    barcode_format = fields.Selection(
        selection=[("gs1_128", "Display GS1_128 format for barcodes")],
        default=lambda self: self.env.company.barcode_report_default_format,
    )
    barcode_report = fields.Many2one(
        comodel_name="ir.actions.report",
        string="Report to print",
        domain=[("is_barcode_label", "=", True)],
        default=_default_barcode_report,
        required=True,
    )
    is_custom_label = fields.Boolean(compute="_compute_is_custom_label")
    html_content = fields.Html()
    label_qty = fields.Integer(default=1)

    @api.onchange("picking_ids", "barcode_report")
    def _onchange_picking_ids(self):
        product_print_moves = [(5, 0)]
        line_fields = [f for f in self.env["stock.picking.line.print"]._fields.keys()]
        product_print_moves_data_tmpl = self.env[
            "stock.picking.line.print"
        ].default_get(line_fields)
        for picking_id in self.picking_ids.ids:
            picking = self.env["stock.picking"].browse(picking_id)
            for move_line in self._get_move_lines(picking):
                product_print_moves_data = dict(product_print_moves_data_tmpl)
                product_print_moves_data.update(
                    self._prepare_data_from_move_line(move_line)
                )
                if product_print_moves_data:
                    product_print_moves.append((0, 0, product_print_moves_data))
        if self.picking_ids:
            self.product_print_moves = product_print_moves

    @api.model
    def _get_move_lines(self, picking):
        stock_move_line_to_print_id = self.env.context.get(
            "stock_move_line_to_print", False
        )
        if stock_move_line_to_print_id:
            return self.env["stock.move.line"].browse(stock_move_line_to_print_id)

        if self.barcode_report == self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report_quant_package"
        ):
            return picking.move_line_ids.filtered("result_package_id")
        elif self.barcode_report == self.env.ref(
            "stock_picking_product_barcode_report.action_label_barcode_report"
        ):
            return picking.move_line_ids.filtered("product_id.barcode")
        return picking.move_line_ids

    def _get_label_qty(self, move_line):
        label_copies = 1
        if (
            move_line.move_id.product_packaging_id
            and move_line.move_id.product_packaging_id.print_one_label_by_item
        ):
            factor = move_line.move_id.product_packaging_id.qty
            label_copies = ceil(move_line.qty_done / (factor or 1.0))
        return label_copies

    @api.model
    def _prepare_data_from_move_line(self, move_line):
        return {
            "product_id": move_line.product_id.id,
            "quantity": move_line.qty_done,
            "label_qty": self._get_label_qty(move_line),
            "move_line_id": move_line.id,
            "uom_id": move_line.product_uom_id.id,
            "lot_id": move_line.lot_id.id,
            "result_package_id": move_line.result_package_id.id,
        }

    def print_labels(self):
        if self.is_custom_label:
            return self.barcode_report.report_action(self)
        print_move = self.product_print_moves.filtered(lambda p: p.label_qty > 0)
        if print_move:
            return self.barcode_report.report_action(self.product_print_moves)

    @api.onchange("barcode_report")
    def _compute_is_custom_label(self):
        for record in self:
            record.is_custom_label = record.barcode_report.is_custom_label
