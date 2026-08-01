"""Tool registry - maps tool names to callable functions for direct execution.

Every registered tool can be called directly via POST /tools/execute,
bypassing the LLM orchestrator entirely.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from db.database import get_session

# --- Cash ---
from tools.cash_tools import (
    check_cash_position,
)
from tools.schemas import (
    CheckCashPositionInput,
    CheckCashPositionOutput,
)

# --- Bank ---
from tools.bank_tools import (
    check_bank_transactions,
    record_bank_transaction,
)
from tools.schemas import (
    CheckBankTransactionsInput,
    CheckBankTransactionsOutput,
    RecordBankTransactionInput,
    RecordBankTransactionOutput,
)

# --- Petty Cash ---
from tools.petty_cash_tools import (
    manage_petty_cash,
)
from tools.schemas import (
    ManagePettyCashInput,
    ManagePettyCashOutput,
)

# --- Transactions ---
from tools.transaction_tools import (
    record_transaction_nl,
)
from tools.schemas import (
    RecordTransactionNLInput,
    RecordTransactionNLOutput,
)

# --- Receipt ---
from tools.receipt_tools import (
    process_receipt_image,
)
from tools.schemas import (
    ProcessReceiptImageInput,
    ProcessReceiptImageOutput,
)

# --- Ledger ---
from tools.ledger_tools import (
    create_journal_entry,
    get_general_ledger,
    suggest_chart_of_accounts,
    get_ap_subledger,
    get_ar_subledger,
    get_payroll_ledger,
)
from tools.schemas import (
    CreateJournalEntryInput,
    CreateJournalEntryOutput,
    GetGeneralLedgerInput,
    GetGeneralLedgerOutput,
    SuggestChartOfAccountsInput,
    GetAPSubledgerInput,
    GetAPSubledgerOutput,
    GetARSubledgerInput,
    GetARSubledgerOutput,
    GetPayrollLedgerInput,
    GetPayrollLedgerOutput,
)

# --- Asset ---
from tools.asset_tools import (
    categorize_fixed_asset,
)
from tools.schemas import (
    CategorizeFixedAssetInput,
    CategorizeFixedAssetOutput,
)

# --- Contact ---
from tools.contact_tools import (
    manage_contact,
)
from tools.schemas import (
    ManageContactInput,
    ManageContactOutput,
)

# --- Reconciliation ---
from tools.reconciliation_tools import (
    run_bank_reconciliation,
    post_accrual_entry,
    track_cheque_clearing,
    track_lc_bank_guarantee,
    reconcile_vendor_statement,
    reconcile_customer_statement,
    reconcile_bank_charges,
)
from tools.schemas import (
    RunBankReconciliationInput,
    RunBankReconciliationOutput,
    PostAccrualEntryInput,
    PostAccrualEntryOutput,
    TrackChequeClearingInput,
    TrackChequeClearingOutput,
    TrackLCBGInput,
    TrackLCBGOutput,
    ReconcileVendorStatementInput,
    ReconcileVendorStatementOutput,
    ReconcileCustomerStatementInput,
    ReconcileCustomerStatementOutput,
    ReconcileBankChargesInput,
    ReconcileBankChargesOutput,
)

# --- Month-End ---
from tools.month_end_tools import (
    review_unpaid_bills,
    calculate_prepaid_adjustment,
    calculate_depreciation,
    calculate_amortization,
    reconcile_payroll,
    get_ap_aging_report,
    get_ar_aging_report,
    analyze_budget_variance,
    get_loan_debt_schedule,
    forecast_cash_flow,
)
from tools.schemas import (
    ReviewUnpaidBillsInput,
    ReviewUnpaidBillsOutput,
    CalculatePrepaidAdjustmentInput,
    CalculatePrepaidAdjustmentOutput,
    CalculateDepreciationInput,
    CalculateDepreciationOutput,
    CalculateAmortizationInput,
    CalculateAmortizationOutput,
    ReconcilePayrollInput,
    ReconcilePayrollOutput,
    GetAPAgingReportInput,
    GetAPAgingReportOutput,
    GetARAgingReportInput,
    GetARAgingReportOutput,
    AnalyzeBudgetVarianceInput,
    AnalyzeBudgetVarianceOutput,
    GetLoanDebtScheduleInput,
    GetLoanDebtScheduleOutput,
    ForecastCashFlowInput,
    ForecastCashFlowOutput,
)

# --- Year-End ---
from tools.year_end_tools import (
    generate_trial_balance,
    generate_profit_loss,
    generate_balance_sheet,
    generate_cash_flow_statement,
    transfer_retained_earnings,
    carry_forward_balances,
    draft_notes_to_financials,
    close_fiscal_year,
)
from tools.schemas import (
    GenerateTrialBalanceInput,
    GenerateTrialBalanceOutput,
    GenerateProfitLossInput,
    GenerateProfitLossOutput,
    GenerateBalanceSheetInput,
    GenerateBalanceSheetOutput,
    GenerateCashFlowInput,
    GenerateCashFlowOutput,
    TransferRetainedEarningsInput,
    TransferRetainedEarningsOutput,
    CarryForwardBalancesInput,
    CarryForwardBalancesOutput,
    DraftNotesToFinancialsInput,
    DraftNotesToFinancialsOutput,
    CloseFiscalYearInput,
    CloseFiscalYearOutput,
)

# --- Cost & Budgeting ---
from tools.cost_advanced_tools import (
    calculate_breakeven,
    convert_foreign_currency,
    prepare_budget_forecast,
    calculate_standard_costing_variance,
    allocate_overhead_cost,
    calculate_revenue_recognition,
    flag_provision_contingent_liability,
    flag_related_party_transaction,
)
from tools.schemas import (
    CalculateBreakevenInput,
    CalculateBreakevenOutput,
    ConvertForeignCurrencyInput,
    ConvertForeignCurrencyOutput,
    PrepareBudgetForecastInput,
    PrepareBudgetForecastOutput,
    CalculateStandardCostingVarianceInput,
    CalculateStandardCostingVarianceOutput,
    AllocateOverheadCostInput,
    AllocateOverheadCostOutput,
    CalculateRevenueRecognitionInput,
    CalculateRevenueRecognitionOutput,
    FlagProvisionContingentLiabilityInput,
    FlagProvisionContingentLiabilityOutput,
    FlagRelatedPartyTransactionInput,
    FlagRelatedPartyTransactionOutput,
)

# --- Tax ---
from tools.tax_tools import (
    calculate_withholding_tax,
    get_tax_planning_advice,
    calculate_advance_minimum_tax,
    calculate_eobi_deductions,
    adjust_sales_tax_input_output,
    flag_tax_exemption_zero_rating,
    prepare_sales_tax_filing,
    prepare_income_tax_filing,
)
from tools.schemas import (
    CalculateWithholdingTaxInput,
    CalculateWithholdingTaxOutput,
    GetTaxPlanningAdviceInput,
    GetTaxPlanningAdviceOutput,
    CalculateAdvanceMinimumTaxInput,
    CalculateAdvanceMinimumTaxOutput,
    CalculateEobiDeductionsInput,
    CalculateEobiDeductionsOutput,
    AdjustSalesTaxInputOutputInput,
    AdjustSalesTaxInputOutputOutput,
    FlagTaxExemptionZeroRatingInput,
    FlagTaxExemptionZeroRatingOutput,
    PrepareSalesTaxFilingInput,
    PrepareSalesTaxFilingOutput,
    PrepareIncomeTaxFilingInput,
    PrepareIncomeTaxFilingOutput,
)

# --- Audit ---
from tools.audit_tools import (
    detect_anomaly_transactions,
    get_compliance_deadlines,
    support_internal_audit,
    maintain_statutory_registers,
)
from tools.schemas import (
    DetectAnomalyTransactionsInput,
    DetectAnomalyTransactionsOutput,
    GetComplianceDeadlinesInput,
    GetComplianceDeadlinesOutput,
    SupportInternalAuditInput,
    SupportInternalAuditOutput,
    MaintainStatutoryRegistersInput,
    MaintainStatutoryRegistersOutput,
)

# --- Advisory ---
from tools.advisory_tools import (
    analyze_spending_patterns,
    calculate_financial_ratios,
    assess_financial_health,
    generate_cost_cutting_recommendations,
    generate_custom_report,
)
from tools.schemas import (
    AnalyzeSpendingPatternsInput,
    AnalyzeSpendingPatternsOutput,
    CalculateFinancialRatiosInput,
    CalculateFinancialRatiosOutput,
    AssessFinancialHealthInput,
    AssessFinancialHealthOutput,
    GenerateCostCuttingInput,
    GenerateCostCuttingOutput,
    GenerateCustomReportInput,
    GenerateCustomReportOutput,
)

# --- System Admin ---
from tools.system_admin_tools import (
    check_system_status,
    get_usage_statistics,
    manage_system_preferences,
    schedule_system_task,
)
from tools.schemas import (
    CheckSystemStatusInput,
    CheckSystemStatusOutput,
    GetUsageStatisticsInput,
    GetUsageStatisticsOutput,
    ManageSystemPreferencesInput,
    ManageSystemPreferencesOutput,
    ScheduleSystemTaskInput,
    ScheduleSystemTaskOutput,
)

# Tool entry: (function, input_schema_class, output_schema_class, ai_only)
# ai_only=True means the tool needs NLP/AI interpretation to work properly
ToolEntry = tuple[Callable, Any, Any, bool]

REGISTRY: dict[str, ToolEntry] = {
    # === Daily Entry (5 tools) ===
    "check_cash_position": (check_cash_position, CheckCashPositionInput, CheckCashPositionOutput, False),
    "record_transaction_nl": (record_transaction_nl, RecordTransactionNLInput, RecordTransactionNLOutput, True),
    "process_receipt_image": (process_receipt_image, ProcessReceiptImageInput, ProcessReceiptImageOutput, True),
    "check_bank_transactions": (check_bank_transactions, CheckBankTransactionsInput, CheckBankTransactionsOutput, False),
    "record_bank_transaction": (record_bank_transaction, RecordBankTransactionInput, RecordBankTransactionOutput, False),
    "manage_petty_cash": (manage_petty_cash, ManagePettyCashInput, ManagePettyCashOutput, False),

    # === Ledger & Master Data (7 tools) ===
    "create_journal_entry": (create_journal_entry, CreateJournalEntryInput, CreateJournalEntryOutput, False),
    "get_general_ledger": (get_general_ledger, GetGeneralLedgerInput, GetGeneralLedgerOutput, False),
    "suggest_chart_of_accounts": (suggest_chart_of_accounts, SuggestChartOfAccountsInput, dict, True),
    "get_ap_subledger": (get_ap_subledger, GetAPSubledgerInput, GetAPSubledgerOutput, False),
    "get_ar_subledger": (get_ar_subledger, GetARSubledgerInput, GetARSubledgerOutput, False),
    "get_payroll_ledger": (get_payroll_ledger, GetPayrollLedgerInput, GetPayrollLedgerOutput, False),
    "categorize_fixed_asset": (categorize_fixed_asset, CategorizeFixedAssetInput, CategorizeFixedAssetOutput, False),
    "manage_contact": (manage_contact, ManageContactInput, ManageContactOutput, False),

    # === Reconciliation (7 tools) ===
    "run_bank_reconciliation": (run_bank_reconciliation, RunBankReconciliationInput, RunBankReconciliationOutput, False),
    "post_accrual_entry": (post_accrual_entry, PostAccrualEntryInput, PostAccrualEntryOutput, False),
    "track_cheque_clearing": (track_cheque_clearing, TrackChequeClearingInput, TrackChequeClearingOutput, False),
    "track_lc_bank_guarantee": (track_lc_bank_guarantee, TrackLCBGInput, TrackLCBGOutput, False),
    "reconcile_vendor_statement": (reconcile_vendor_statement, ReconcileVendorStatementInput, ReconcileVendorStatementOutput, False),
    "reconcile_customer_statement": (reconcile_customer_statement, ReconcileCustomerStatementInput, ReconcileCustomerStatementOutput, False),
    "reconcile_bank_charges": (reconcile_bank_charges, ReconcileBankChargesInput, ReconcileBankChargesOutput, False),

    # === Month-End (10 tools) ===
    "review_unpaid_bills": (review_unpaid_bills, ReviewUnpaidBillsInput, ReviewUnpaidBillsOutput, False),
    "calculate_prepaid_adjustment": (calculate_prepaid_adjustment, CalculatePrepaidAdjustmentInput, CalculatePrepaidAdjustmentOutput, False),
    "calculate_depreciation": (calculate_depreciation, CalculateDepreciationInput, CalculateDepreciationOutput, False),
    "calculate_amortization": (calculate_amortization, CalculateAmortizationInput, CalculateAmortizationOutput, False),
    "reconcile_payroll": (reconcile_payroll, ReconcilePayrollInput, ReconcilePayrollOutput, False),
    "get_ap_aging_report": (get_ap_aging_report, GetAPAgingReportInput, GetAPAgingReportOutput, False),
    "get_ar_aging_report": (get_ar_aging_report, GetARAgingReportInput, GetARAgingReportOutput, False),
    "analyze_budget_variance": (analyze_budget_variance, AnalyzeBudgetVarianceInput, AnalyzeBudgetVarianceOutput, False),
    "get_loan_debt_schedule": (get_loan_debt_schedule, GetLoanDebtScheduleInput, GetLoanDebtScheduleOutput, False),
    "forecast_cash_flow": (forecast_cash_flow, ForecastCashFlowInput, ForecastCashFlowOutput, False),

    # === Year-End (8 tools) ===
    "generate_trial_balance": (generate_trial_balance, GenerateTrialBalanceInput, GenerateTrialBalanceOutput, False),
    "generate_profit_loss": (generate_profit_loss, GenerateProfitLossInput, GenerateProfitLossOutput, False),
    "generate_balance_sheet": (generate_balance_sheet, GenerateBalanceSheetInput, GenerateBalanceSheetOutput, False),
    "generate_cash_flow_statement": (generate_cash_flow_statement, GenerateCashFlowInput, GenerateCashFlowOutput, False),
    "transfer_retained_earnings": (transfer_retained_earnings, TransferRetainedEarningsInput, TransferRetainedEarningsOutput, False),
    "carry_forward_balances": (carry_forward_balances, CarryForwardBalancesInput, CarryForwardBalancesOutput, False),
    "draft_notes_to_financials": (draft_notes_to_financials, DraftNotesToFinancialsInput, DraftNotesToFinancialsOutput, False),
    "close_fiscal_year": (close_fiscal_year, CloseFiscalYearInput, CloseFiscalYearOutput, False),

    # === Cost & Budgeting (8 tools) ===
    "calculate_breakeven": (calculate_breakeven, CalculateBreakevenInput, CalculateBreakevenOutput, False),
    "convert_foreign_currency": (convert_foreign_currency, ConvertForeignCurrencyInput, ConvertForeignCurrencyOutput, False),
    "prepare_budget_forecast": (prepare_budget_forecast, PrepareBudgetForecastInput, PrepareBudgetForecastOutput, False),
    "calculate_standard_costing_variance": (calculate_standard_costing_variance, CalculateStandardCostingVarianceInput, CalculateStandardCostingVarianceOutput, False),
    "allocate_overhead_cost": (allocate_overhead_cost, AllocateOverheadCostInput, AllocateOverheadCostOutput, False),
    "calculate_revenue_recognition": (calculate_revenue_recognition, CalculateRevenueRecognitionInput, CalculateRevenueRecognitionOutput, False),
    "flag_provision_contingent_liability": (flag_provision_contingent_liability, FlagProvisionContingentLiabilityInput, FlagProvisionContingentLiabilityOutput, False),
    "flag_related_party_transaction": (flag_related_party_transaction, FlagRelatedPartyTransactionInput, FlagRelatedPartyTransactionOutput, False),

    # === Tax (8 tools) ===
    "calculate_withholding_tax": (calculate_withholding_tax, CalculateWithholdingTaxInput, CalculateWithholdingTaxOutput, False),
    "get_tax_planning_advice": (get_tax_planning_advice, GetTaxPlanningAdviceInput, GetTaxPlanningAdviceOutput, False),
    "calculate_advance_minimum_tax": (calculate_advance_minimum_tax, CalculateAdvanceMinimumTaxInput, CalculateAdvanceMinimumTaxOutput, False),
    "calculate_eobi_deductions": (calculate_eobi_deductions, CalculateEobiDeductionsInput, CalculateEobiDeductionsOutput, False),
    "adjust_sales_tax_input_output": (adjust_sales_tax_input_output, AdjustSalesTaxInputOutputInput, AdjustSalesTaxInputOutputOutput, False),
    "flag_tax_exemption_zero_rating": (flag_tax_exemption_zero_rating, FlagTaxExemptionZeroRatingInput, FlagTaxExemptionZeroRatingOutput, False),
    "prepare_sales_tax_filing": (prepare_sales_tax_filing, PrepareSalesTaxFilingInput, PrepareSalesTaxFilingOutput, False),
    "prepare_income_tax_filing": (prepare_income_tax_filing, PrepareIncomeTaxFilingInput, PrepareIncomeTaxFilingOutput, False),

    # === Audit (4 tools) ===
    "detect_anomaly_transactions": (detect_anomaly_transactions, DetectAnomalyTransactionsInput, DetectAnomalyTransactionsOutput, False),
    "get_compliance_deadlines": (get_compliance_deadlines, GetComplianceDeadlinesInput, GetComplianceDeadlinesOutput, False),
    "support_internal_audit": (support_internal_audit, SupportInternalAuditInput, SupportInternalAuditOutput, False),
    "maintain_statutory_registers": (maintain_statutory_registers, MaintainStatutoryRegistersInput, MaintainStatutoryRegistersOutput, False),

    # === Advisory (5 tools) ===
    "analyze_spending_patterns": (analyze_spending_patterns, AnalyzeSpendingPatternsInput, AnalyzeSpendingPatternsOutput, False),
    "calculate_financial_ratios": (calculate_financial_ratios, CalculateFinancialRatiosInput, CalculateFinancialRatiosOutput, False),
    "assess_financial_health": (assess_financial_health, AssessFinancialHealthInput, AssessFinancialHealthOutput, False),
    "generate_cost_cutting_recommendations": (generate_cost_cutting_recommendations, GenerateCostCuttingInput, GenerateCostCuttingOutput, True),
    "generate_custom_report": (generate_custom_report, GenerateCustomReportInput, GenerateCustomReportOutput, False),

    # === System Admin (4 tools) ===
    "check_system_status": (check_system_status, CheckSystemStatusInput, CheckSystemStatusOutput, False),
    "get_usage_statistics": (get_usage_statistics, GetUsageStatisticsInput, GetUsageStatisticsOutput, False),
    "manage_system_preferences": (manage_system_preferences, ManageSystemPreferencesInput, ManageSystemPreferencesOutput, False),
    "schedule_system_task": (schedule_system_task, ScheduleSystemTaskInput, ScheduleSystemTaskOutput, False),
}

logger = logging.getLogger("tool_registry")


def _to_dict(obj: Any) -> dict:
    """Convert a tool output to a JSON-serializable dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return {"result": str(obj)}


def execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a tool directly by name with given params.

    Args:
        tool_name: Name of the tool from REGISTRY.
        params: Dict of parameter names to values.

    Returns:
        Output dict (JSON-serializable).

    Raises:
        ValueError: If tool not found or execution fails.
    """
    if tool_name not in REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")

    fn, input_schema, output_schema, ai_only = REGISTRY[tool_name]

    # Validate input via Pydantic (strict type coercion)
    validated_input = input_schema(**params)

    # Most tools need a DB session
    db = get_session()
    try:
        result = fn(validated_input, db)
        return _to_dict(result)
    finally:
        db.close()


def get_tool_info(tool_name: str) -> dict:
    """Return metadata about a tool without executing it."""
    if tool_name not in REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")
    fn, input_schema, output_schema, ai_only = REGISTRY[tool_name]
    return {
        "name": tool_name,
        "ai_only": ai_only,
        "description": (fn.__doc__ or "").strip(),
        "input_fields": list(input_schema.model_fields.keys()) if hasattr(input_schema, "model_fields") else [],
    }


def list_all_tools() -> list[dict]:
    """List all registered tools with metadata."""
    result = []
    for name in sorted(REGISTRY.keys()):
        fn, input_schema, output_schema, ai_only = REGISTRY[name]
        result.append({
            "name": name,
            "ai_only": ai_only,
            "description": (fn.__doc__ or "").strip(),
        })
    return result
