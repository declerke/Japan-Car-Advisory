import pytest
from calculator.import_calculator import ImportCostCalculator, ImportCostBreakdown


@pytest.fixture
def calc():
    return ImportCostCalculator(usd_to_kes=130.0)


def test_basic_calculation_produces_positive_totals(calc):
    result = calc.calculate(
        purchase_price_usd=10_000,
        engine_size_cc=1500,
        year=2021,
        make="Toyota",
        model="Corolla",
    )
    assert isinstance(result, ImportCostBreakdown)
    assert result.total_landed_kes > 0
    assert result.import_duty_kes > 0
    assert result.excise_duty_kes > 0
    assert result.vat_kes > 0


def test_import_duty_is_35_percent_of_cif(calc):
    result = calc.calculate(
        purchase_price_usd=10_000,
        engine_size_cc=1500,
        year=2021,
        make="Toyota",
        model="Corolla",
        shipping_cost_usd=1_500,
    )
    cif_kes = (10_000 + 1_500) * 130.0
    expected_duty = cif_kes * 0.35
    assert abs(result.import_duty_kes - expected_duty) < 1.0


def test_excise_bracket_under_1000cc(calc):
    result = calc.calculate(10_000, 800, 2022, "Suzuki", "Alto")
    assert result.excise_duty_rate == 0.10


def test_excise_bracket_1001_to_2000cc(calc):
    result = calc.calculate(10_000, 1500, 2022, "Toyota", "Corolla")
    assert result.excise_duty_rate == 0.20


def test_excise_bracket_2001_to_3000cc(calc):
    result = calc.calculate(10_000, 2400, 2022, "Toyota", "Prado")
    assert result.excise_duty_rate == 0.25


def test_excise_bracket_above_3000cc(calc):
    result = calc.calculate(10_000, 3500, 2022, "Toyota", "Landcruiser")
    assert result.excise_duty_rate == 0.35


def test_higher_engine_means_higher_excise(calc):
    small = calc.calculate(10_000, 900, 2021, "Toyota", "Vitz")
    large = calc.calculate(10_000, 2000, 2021, "Toyota", "Harrier")
    assert large.excise_duty_kes > small.excise_duty_kes


def test_compare_with_local_import_cheaper(calc):
    result = calc.calculate(5_000, 1200, 2021, "Honda", "Fit")
    comparison = calc.compare_with_local(result, local_price_kes=2_500_000)
    assert "savings_kes" in comparison
    assert "verdict" in comparison
    assert "savings_pct" in comparison
    if result.total_landed_kes < 2_500_000:
        assert comparison["savings_kes"] > 0
        assert "CHEAPER" in comparison["verdict"]


def test_compare_with_local_import_more_expensive(calc):
    result = calc.calculate(15_000, 3000, 2022, "Toyota", "Prado")
    comparison = calc.compare_with_local(result, local_price_kes=1_000_000)
    assert comparison["savings_kes"] < 0


def test_age_warning_added_for_old_vehicle(calc):
    result = calc.calculate(3_000, 1000, 2010, "Honda", "Fit")
    assert any("WARNING" in note for note in result.notes)


def test_fixed_charges_present(calc):
    result = calc.calculate(8_000, 1500, 2021, "Nissan", "Note")
    assert result.port_charges_kes == 35_000
    assert result.clearing_fees_kes == 45_000
    assert result.ntsa_registration_kes == 15_000
    assert result.inspection_fees_kes == 10_000


def test_total_taxes_is_sum_of_components(calc):
    result = calc.calculate(10_000, 1500, 2021, "Toyota", "Corolla")
    computed = (
        result.import_duty_kes
        + result.excise_duty_kes
        + result.vat_kes
        + result.idf_kes
        + result.rdl_kes
    )
    assert abs(result.total_taxes_kes - computed) < 1.0
