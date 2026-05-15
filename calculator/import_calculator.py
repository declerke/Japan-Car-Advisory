import json
import os
from dataclasses import dataclass, asdict
from typing import Optional
from loguru import logger

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "kra_rules.json")


@dataclass
class ImportCostBreakdown:
    make: str
    model: str
    year: int
    engine_size_cc: int
    purchase_price_usd: float
    shipping_cost_usd: float
    cif_value_usd: float
    cif_value_kes: float
    import_duty_kes: float
    excise_duty_kes: float
    vat_kes: float
    idf_kes: float
    rdl_kes: float
    port_charges_kes: float
    clearing_fees_kes: float
    ntsa_registration_kes: float
    inspection_fees_kes: float
    total_taxes_kes: float
    total_landed_kes: float
    total_landed_usd: float
    exchange_rate_usd_kes: float
    excise_duty_rate: float
    notes: list


def _load_kra_rules() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


class ImportCostCalculator:
    def __init__(self, usd_to_kes: float = 130.0):
        self.usd_to_kes = usd_to_kes
        self.rules = _load_kra_rules()
        logger.info(f"KRA Rules loaded (effective year: {self.rules['effective_year']})")

    def _get_excise_rate(self, engine_cc: int) -> float:
        for bracket in self.rules["excise_duty"]["brackets"]:
            if bracket["min_cc"] <= engine_cc <= bracket["max_cc"]:
                return bracket["rate"]
        return 0.35

    def _get_crsp_depreciation(self, year: int) -> float:
        current_year = 2026
        age = current_year - year
        schedule = self.rules["crsp_depreciation"]["schedule"]
        for entry in schedule:
            if "years_old_plus" in entry and age > entry["years_old_plus"]:
                return entry["depreciation"]
            elif "years_old" in entry and entry["years_old"] == age:
                return entry["depreciation"]
        if age <= 0:
            return 0.0
        return 0.70

    def calculate(
        self,
        purchase_price_usd: float,
        engine_size_cc: int,
        year: int,
        make: str = "Unknown",
        model: str = "Unknown",
        shipping_cost_usd: Optional[float] = None,
        use_crsp: bool = False,
        crsp_value_usd: Optional[float] = None,
    ) -> ImportCostBreakdown:
        notes = [
            "All figures are estimates. Consult KRA, a licensed clearing agent, or KEBS for official valuations.",
            f"Exchange rate used: 1 USD = {self.usd_to_kes} KES",
        ]

        if shipping_cost_usd is None:
            shipping_cost_usd = self.rules["other_charges"]["shipping_usd"]["default"]

        cif_usd = purchase_price_usd + shipping_cost_usd

        if use_crsp and crsp_value_usd:
            depreciation = self._get_crsp_depreciation(year)
            customs_value_usd = crsp_value_usd * (1 - depreciation)
            notes.append(
                f"CRSP depreciation of {depreciation*100:.0f}% applied for {2026 - year} year(s) old vehicle. "
                f"Customs value based on CRSP: USD {customs_value_usd:,.0f}"
            )
        else:
            customs_value_usd = cif_usd
            notes.append("Customs value = CIF (purchase price + shipping). CRSP may yield different results.")

        customs_value_kes = customs_value_usd * self.usd_to_kes

        import_duty_rate = self.rules["import_duty"]["rate"]
        import_duty_kes = customs_value_kes * import_duty_rate

        excise_rate = self._get_excise_rate(engine_size_cc)
        excise_base_kes = customs_value_kes + import_duty_kes
        excise_duty_kes = excise_base_kes * excise_rate

        vat_rate = self.rules["vat"]["rate"]
        vat_base_kes = customs_value_kes + import_duty_kes + excise_duty_kes
        vat_kes = vat_base_kes * vat_rate

        idf_rate = self.rules["idf"]["rate"]
        idf_kes = max(customs_value_kes * idf_rate, 5000)

        rdl_rate = self.rules["rdl"]["rate"]
        rdl_kes = customs_value_kes * rdl_rate

        port_charges_kes = self.rules["other_charges"]["port_charges_kes"]["value"]
        clearing_fees_kes = self.rules["other_charges"]["clearing_fees_kes"]["value"]
        ntsa_kes = self.rules["other_charges"]["ntsa_registration_kes"]["value"]
        inspection_kes = self.rules["other_charges"]["inspection_fees_kes"]["value"]

        total_taxes_kes = import_duty_kes + excise_duty_kes + vat_kes + idf_kes + rdl_kes
        total_landed_kes = (
            (purchase_price_usd * self.usd_to_kes)
            + (shipping_cost_usd * self.usd_to_kes)
            + total_taxes_kes
            + port_charges_kes
            + clearing_fees_kes
            + ntsa_kes
            + inspection_kes
        )
        total_landed_usd = total_landed_kes / self.usd_to_kes

        kenyan_rules = self.rules["kenyan_import_rules"]
        vehicle_age = 2026 - year
        if vehicle_age > kenyan_rules["max_age_years"]:
            notes.append(
                f"⚠ WARNING: This vehicle is {vehicle_age} years old. "
                f"Kenya limits imports to {kenyan_rules['max_age_years']} years. It may NOT be importable."
            )

        return ImportCostBreakdown(
            make=make,
            model=model,
            year=year,
            engine_size_cc=engine_size_cc,
            purchase_price_usd=round(purchase_price_usd, 2),
            shipping_cost_usd=round(shipping_cost_usd, 2),
            cif_value_usd=round(cif_usd, 2),
            cif_value_kes=round(cif_usd * self.usd_to_kes, 2),
            import_duty_kes=round(import_duty_kes, 2),
            excise_duty_kes=round(excise_duty_kes, 2),
            vat_kes=round(vat_kes, 2),
            idf_kes=round(idf_kes, 2),
            rdl_kes=round(rdl_kes, 2),
            port_charges_kes=round(port_charges_kes, 2),
            clearing_fees_kes=round(clearing_fees_kes, 2),
            ntsa_registration_kes=round(ntsa_kes, 2),
            inspection_fees_kes=round(inspection_kes, 2),
            total_taxes_kes=round(total_taxes_kes, 2),
            total_landed_kes=round(total_landed_kes, 2),
            total_landed_usd=round(total_landed_usd, 2),
            exchange_rate_usd_kes=self.usd_to_kes,
            excise_duty_rate=excise_rate,
            notes=notes,
        )

    def compare_with_local(
        self,
        breakdown: ImportCostBreakdown,
        local_price_kes: float,
    ) -> dict:
        savings_kes = local_price_kes - breakdown.total_landed_kes
        savings_pct = (savings_kes / local_price_kes) * 100 if local_price_kes > 0 else 0

        return {
            "import_total_kes": breakdown.total_landed_kes,
            "local_price_kes": local_price_kes,
            "savings_kes": round(savings_kes, 2),
            "savings_pct": round(savings_pct, 2),
            "verdict": "Importing is CHEAPER" if savings_kes > 0 else "Buying locally is CHEAPER",
            "recommendation": (
                f"Importing saves KES {savings_kes:,.0f} ({savings_pct:.1f}%) vs buying locally."
                if savings_kes > 0
                else f"Buying locally saves KES {abs(savings_kes):,.0f} ({abs(savings_pct):.1f}%) vs importing."
            ),
        }

    def to_dict(self, breakdown: ImportCostBreakdown) -> dict:
        return asdict(breakdown)