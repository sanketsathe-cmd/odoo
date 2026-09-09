import { _t } from "@web/core/l10n/translation";
import { x2ManyCommands } from "@web/core/orm_service";
import { Dialog } from '@web/core/dialog/dialog';
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { getId } from "@web/model/relational_model/utils";
import { Component, useState, onMounted } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class CalculateLotDialog extends Component {
    static template = "stock.calculate_lot_dialog";
    static components = { Dialog };
    static props = {
        move: { type: Object },
        close: { type: Function },
    };

    setup() {
        this.size = 'lg';
        
        this.state = useState({
            startingNumber: 1,
            lotsPerPackage: 1,
            packagesCount: 1,
            previewLots: [],
        });

        onMounted(() => {
            this._calculatePreview();
        });
    }

    get title() {
        return this.props.move.data.has_tracking === 'lot' 
            ? _t("Calculate Lot Distribution") 
            : _t("Calculate Serial Distribution");
    }

    _calculatePreview() {
        const totalQty = this.props.move.data.product_uom_qty || 0;
        const tracking = this.props.move.data.has_tracking;
        const startNum = parseInt(this.state.startingNumber) || 1;
        const lotsPerPkg = parseInt(this.state.lotsPerPackage) || 1;
        const pkgCount = parseInt(this.state.packagesCount) || 1;

        let preview = [];
        let currentNum = startNum;

        if (tracking === 'lot') {
            const totalLotsNeeded = pkgCount * lotsPerPkg;
            const qtyDistribution = totalQty / totalLotsNeeded;

            for (let pkg = 1; pkg <= pkgCount; pkg++) {
                const packageLots = [];
                for (let lot = 1; lot <= lotsPerPkg; lot++) {
                    if (currentNum > totalLotsNeeded) break;
                    packageLots.push({
                        name: `LOT-${String(currentNum).padStart(6, '0')}`,
                        quantity: Math.round(qtyDistribution * 100) / 100,
                    });
                    currentNum++;
                }
                if (packageLots.length) {
                    preview.push({
                        package: pkg,
                        lots: packageLots,
                    });
                }
            }
        } else {
            const totalUnits = Math.floor(totalQty);
            let pkgCounter = 1;
            let lotCounter = 0;
            let packageLots = [];
            
            for (let i = 0; i < totalUnits; i++) {
                packageLots.push({
                    name: `SER-${String(currentNum).padStart(8, '0')}`,
                    quantity: 1,
                });
                currentNum++;
                lotCounter++;
                
                if (lotCounter >= lotsPerPkg || i === totalUnits - 1) {
                    if (packageLots.length) {
                        preview.push({
                            package: pkgCounter,
                            lots: [...packageLots],
                        });
                        pkgCounter++;
                        lotCounter = 0;
                        packageLots = [];
                    }
                }
            }
        }

        this.state.previewLots = preview;
    }

    async _onGenerate() {
        try {
            const moveLineVals = this._generateMoveLines();
            
            if (moveLineVals && moveLineVals.length > 0) {
                await this._applyMoveLines(moveLineVals);
                this.props.close();
            } else {
                alert(_t("No lines were generated. Please check your parameters."));
            }
        } catch (error) {
            console.error("Error:", error);
            alert(_t("Error calculating lots. Please try again."));
        }
    }

    _generateMoveLines() {
        const move = this.props.move.data;
        const tracking = move.has_tracking;
        const totalQty = move.product_uom_qty || 0;
        const startNum = parseInt(this.state.startingNumber) || 1;
        const lotsPerPkg = parseInt(this.state.lotsPerPackage) || 1;
        const pkgCount = parseInt(this.state.packagesCount) || 1;

        const move_line_vals = [];
        let currentNum = startNum;

        if (tracking === 'lot') {
            const totalLotsNeeded = pkgCount * lotsPerPkg;
            const qtyDistribution = totalQty / totalLotsNeeded;

            for (let pkg = 1; pkg <= pkgCount; pkg++) {
                for (let lot = 1; lot <= lotsPerPkg; lot++) {
                    if (currentNum > totalLotsNeeded) break;
                    move_line_vals.push({
                        'product_id': move.product_id.id,
                        'lot_name': `LOT-${String(currentNum).padStart(6, '0')}`,
                        'quantity': Math.round(qtyDistribution * 100) / 100,
                        'product_uom_id': move.product_uom ? move.product_uom.id : false,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                    });
                    currentNum++;
                }
            }
        } else {
            const totalUnits = Math.floor(totalQty);
            for (let i = 0; i < totalUnits; i++) {
                move_line_vals.push({
                    'product_id': move.product_id.id,
                    'lot_name': `SER-${String(currentNum).padStart(8, '0')}`,
                    'quantity': 1.0,
                    'product_uom_id': move.product_uom ? move.product_uom.id : false,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                });
                currentNum++;
            }
        }

        return move_line_vals;
    }

    async _applyMoveLines(move_line_vals) {
        const move = this.props.move;
        const lines = move.data.move_line_ids;

        if (!lines || !lines._currentIds) {
            return;
        }

        if (lines._currentIds.length > 0) {
            await lines._applyCommands(
                lines._currentIds.map((id) => [x2ManyCommands.DELETE, id])
            );
        }

        const newlines = [];
        for (const values of move_line_vals) {
            try {
                const record = lines._createRecordDatapoint(values, {
                    mode: 'readonly',
                    virtualId: getId("virtual"),
                    manuallyAdded: false,
                });
                newlines.push(record);
            } catch (e) {
                console.warn("Could not create record:", e);
            }
        }

        if (newlines.length > 0) {
            lines.records.push(...newlines);
            lines._commands.push(...newlines.map((r) => [x2ManyCommands.CREATE, r._virtualId]));
            lines._currentIds.push(...newlines.map((r) => r._virtualId));
            await lines._onUpdate();
        }
    }

    onInputChange() {
        this._calculatePreview();
    }
}

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

registry.category("view_widgets").add("calculate_lot", { 
    component: CalculateLot 
});