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
            expiryDateTime: '',
            manufacturingDate: '',
            packageName: '',
        });
    }

    // Convert datetime-local value to DD-MM-YYYY HH:MM with -5h30m offset
    _formatExpiryDate(datetimeStr) {
        if (!datetimeStr) return '';

        const [datePart, timePart] = datetimeStr.split('T');
        const [year, month, day] = datePart.split('-').map(Number);
        const [hours, minutes] = timePart.split(':').map(Number);

        const dt = new Date(year, month - 1, day, hours, minutes, 0, 0);
        dt.setHours(dt.getHours() - 5);
        dt.setMinutes(dt.getMinutes() - 30);

        const dd = String(dt.getDate()).padStart(2, '0');
        const mm = String(dt.getMonth() + 1).padStart(2, '0');
        const yyyy = dt.getFullYear();
        const hh = String(dt.getHours()).padStart(2, '0');
        const mi = String(dt.getMinutes()).padStart(2, '0');

        return `${dd}-${mm}-${yyyy} ${hh}:${mi}`;
    }

    _formatManufacturingDate(dateStr) {
        if (!dateStr) return '';
        return dateStr;
    }

    async _onCalculate() {
        const lotNumber = this.state.lotNumber.trim();
        const qtyPerLot = parseInt(this.state.qtyPerLot) || 1;
        const expiryDateTime = this.state.expiryDateTime;
        const manufacturingDate = this.state.manufacturingDate;
        const packageName = this.state.packageName.trim();

        if (!lotNumber) {
            alert(_t("Please enter a Lot Number"));
            return;
        }

        if (qtyPerLot <= 0) {
            alert(_t("Qty/Lot must be greater than 0"));
            return;
        }

        if (!expiryDateTime) {
            alert(_t("Please enter an Expiry Date & Time"));
            return;
        }

        if (!manufacturingDate) {
            alert(_t("Please enter a Manufacturing Date"));
            return;
        }

        if (!packageName) {
            alert(_t("Please enter a Destination Package Name"));
            return;
        }

        const formattedExpiry = this._formatExpiryDate(expiryDateTime);
        const formattedMfg = this._formatManufacturingDate(manufacturingDate);

        // Generate text - SAME lot number repeated with dates & package
        let result = [];
        const totalQty = this.props.move.data.product_uom_qty || 0;
        const totalLines = Math.ceil(totalQty / qtyPerLot);

        for (let i = 0; i < totalLines; i++) {
            const qty = i === totalLines - 1 ? 
                totalQty - (i * qtyPerLot) : 
                qtyPerLot;
            // Format: LOT_NUMBER \t QTY \t EXPIRY \t MFG_DATE \t PACKAGE
            result.push(`${lotNumber}\t${qty}\t${formattedExpiry}\t${formattedMfg}\t${packageName}`);
        }

        const generatedText = result.join('\n');

        try {
            await navigator.clipboard.writeText(generatedText);
            this.props.close();
        } catch (err) {
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