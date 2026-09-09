import { _t } from "@web/core/l10n/translation";
import { Dialog } from '@web/core/dialog/dialog';
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// ========== DIALOG COMPONENT ==========
export class CalculateLotDialog extends Component {
    static template = "stock.calculate_lot_dialog";
    static components = { Dialog };
    static props = {
        move: { type: Object },
        close: { type: Function },
    };

    setup() {
        this.state = useState({
            lotNumber: '',
            qtyPerLot: 1,
        });
    }

    async _onCalculate() {
        const lotNumber = this.state.lotNumber.trim();
        const qtyPerLot = parseInt(this.state.qtyPerLot) || 1;

        if (!lotNumber) {
            alert(_t("Please enter a Lot Number"));
            return;
        }

        if (qtyPerLot <= 0) {
            alert(_t("Qty/Lot must be greater than 0"));
            return;
        }

        // Generate text - SAME lot number repeated
        let result = [];
        const totalQty = this.props.move.data.product_uom_qty || 0;
        
        // Calculate how many lines needed
        const totalLines = Math.ceil(totalQty / qtyPerLot);

        for (let i = 0; i < totalLines; i++) {
            // Use the SAME lot number for all lines
            const qty = i === totalLines - 1 ? 
                totalQty - (i * qtyPerLot) : 
                qtyPerLot;
            result.push(`${lotNumber}\t${qty}`);
        }

        const generatedText = result.join('\n');

        // Copy to clipboard
        try {
            await navigator.clipboard.writeText(generatedText);
            this.props.close();
        } catch (err) {
            // Fallback
            const textArea = document.createElement('textarea');
            textArea.value = generatedText;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.props.close();
        }
    }
}

// ========== WIDGET COMPONENT ==========
export class CalculateLot extends Component {
    static template = "stock.CalculateLot";
    static props = { ...standardWidgetProps };

    setup() {
        this.dialog = useService("dialog");
    }

    openDialog() {
        this.dialog.add(CalculateLotDialog, {
            move: this.props.record,
        });
    }
}

// Register
registry.category("view_widgets").add("calculate_lot", { 
    component: CalculateLot 
});