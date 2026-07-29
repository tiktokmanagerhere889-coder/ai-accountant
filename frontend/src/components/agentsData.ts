import React from "react";
import {
  DollarSign, BookOpen, Layers, Calendar, Landmark, Scale, ShieldCheck,
  Settings as SettingsIcon, BarChart3, AlertCircle, FileText, ArrowRightLeft,
  PiggyBank, Percent, ChevronRight, HelpCircle, HardDrive, LayoutDashboard
} from "lucide-react";

export interface AgentDef {
  id: string;
  name: string;
  role: string;
  category: "operations" | "reporting" | "compliance" | "advisory";
  icon: React.ComponentType<any>;
  tools: {
    name: string;
    description: string;
    approval: boolean;
    inputs: { name: string; type: string; placeholder: string; required: boolean; default?: string }[];
  }[];
}

export const AGENTS_DATA: AgentDef[] = [
  {
    id: "daily-entry",
    name: "Daily Entry",
    role: "Handles daily cash/transaction capture",
    category: "operations",
    icon: DollarSign,
    tools: [
      {
        name: "check_cash_position",
        description: "Live cash balance from DB",
        approval: false,
        inputs: [
          { name: "as_of_date", type: "date", placeholder: "As of date", required: false },
          { name: "account_id", type: "text", placeholder: "Cash Account ID (e.g. 1000-Cash)", required: false }
        ]
      },
      {
        name: "record_transaction_nl",
        description: "Parses plain-English transaction and stores it",
        approval: false,
        inputs: [
          { name: "description", type: "text", placeholder: "e.g. Paid office rent 50000", required: true },
          { name: "posted_date", type: "date", placeholder: "Posting date", required: false },
          { name: "reference", type: "text", placeholder: "Invoice ref number", required: false }
        ]
      },
      {
        name: "process_receipt_image",
        description: "Vision extraction of amount/vendor from receipt photo",
        approval: true,
        inputs: [
          { name: "image_filename", type: "text", placeholder: "Filename (e.g. receipt.png)", required: true },
          { name: "image_data", type: "textarea", placeholder: "Base64 string data or mock prefix", required: true },
          { name: "suggested_account", type: "text", placeholder: "e.g. Office Rent", required: false }
        ]
      },
      {
        name: "check_bank_transactions",
        description: "Queries bank transaction records",
        approval: false,
        inputs: [
          { name: "account_id", type: "text", placeholder: "Account ID", required: false },
          { name: "from_date", type: "date", placeholder: "From Date", required: false },
          { name: "to_date", type: "date", placeholder: "To Date", required: false },
          { name: "status", type: "text", placeholder: "cleared/pending/reconciled", required: false }
        ]
      },
      {
        name: "manage_petty_cash",
        description: "Petty cash entries + replenishment triggers",
        approval: false,
        inputs: [
          { name: "action", type: "text", placeholder: "expense, add_fund, check_replenishment", required: true },
          { name: "fund_id", type: "text", placeholder: "Fund ID e.g. PC-001", required: false },
          { name: "amount", type: "text", placeholder: "Amount", required: false },
          { name: "description", type: "text", placeholder: "Description", required: false }
        ]
      }
    ]
  },
  {
    id: "ledger",
    name: "Ledger & Master Data",
    role: "Owns chart of accounts, journal entries, and subledgers",
    category: "operations",
    icon: BookOpen,
    tools: [
      {
        name: "create_journal_entry",
        description: "Manually construct double-entry ledger entry",
        approval: false,
        inputs: [
          { name: "description", type: "text", placeholder: "Entry Description", required: true },
          { name: "posted_date", type: "date", placeholder: "Date", required: false },
          { name: "debit_account", type: "text", placeholder: "Debit Account e.g. 6000-Office Rent", required: true },
          { name: "debit_amount", type: "text", placeholder: "Debit Amount", required: true },
          { name: "credit_account", type: "text", placeholder: "Credit Account e.g. 1000-Cash", required: true },
          { name: "credit_amount", type: "text", placeholder: "Credit Amount", required: true }
        ]
      },
      {
        name: "get_general_ledger",
        description: "Aggregated ledger views",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: false },
          { name: "to_date", type: "date", placeholder: "To Date", required: false },
          { name: "account_code_prefix", type: "text", placeholder: "Prefix e.g. 6000", required: false }
        ]
      },
      {
        name: "suggest_chart_of_accounts",
        description: "Recommends accounting chart structures",
        approval: true,
        inputs: [
          { name: "business_type", type: "text", placeholder: "e.g. tech_startup, retail", required: true },
          { name: "description", type: "text", placeholder: "Additional Details", required: false }
        ]
      },
      {
        name: "get_ap_subledger",
        description: "Accounts Payable status",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: false },
          { name: "to_date", type: "date", placeholder: "To Date", required: false },
          { name: "vendor_contact_id", type: "text", placeholder: "Vendor ID", required: false }
        ]
      },
      {
        name: "get_ar_subledger",
        description: "Accounts Receivable status",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: false },
          { name: "to_date", type: "date", placeholder: "To Date", required: false },
          { name: "customer_contact_id", type: "text", placeholder: "Customer ID", required: false }
        ]
      },
      {
        name: "get_payroll_ledger",
        description: "Aggregated salary distributions",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: false },
          { name: "to_date", type: "date", placeholder: "To Date", required: false },
          { name: "employee_name", type: "text", placeholder: "Employee Name Filter", required: false }
        ]
      },
      {
        name: "categorize_fixed_asset",
        description: "Add fixed asset & depreciation schemes",
        approval: true,
        inputs: [
          { name: "asset_name", type: "text", placeholder: "e.g. Delivery Van", required: true },
          { name: "purchase_cost", type: "text", placeholder: "Purchase Cost", required: true },
          { name: "purchase_date", type: "date", placeholder: "Purchase Date", required: false },
          { name: "asset_category", type: "text", placeholder: "building/vehicle/computer", required: false }
        ]
      },
      {
        name: "manage_contact",
        description: "CRUD vendor or customer contacts",
        approval: false,
        inputs: [
          { name: "action", type: "text", placeholder: "add, update, delete, search", required: true },
          { name: "contact_type", type: "text", placeholder: "vendor or customer", required: true },
          { name: "contact_name", type: "text", placeholder: "Name", required: true },
          { name: "phone", type: "text", placeholder: "Phone Number", required: false },
          { name: "email", type: "text", placeholder: "Email Address", required: false },
          { name: "address", type: "text", placeholder: "Address", required: false },
          { name: "tax_id", type: "text", placeholder: "Tax ID / NTN", required: false }
        ]
      }
    ]
  },
  {
    id: "reconciliation",
    name: "Reconciliation",
    role: "Matches bank statements & banking guarantees",
    category: "operations",
    icon: ArrowRightLeft,
    tools: [
      {
        name: "run_bank_reconciliation",
        description: "Matches bank statement lines against ledger entries",
        approval: true,
        inputs: [
          { name: "bank_account_id", type: "text", placeholder: "Bank ID e.g. BA-001", required: true },
          { name: "statement_date", type: "date", placeholder: "Statement Date", required: true },
          { name: "from_date", type: "date", placeholder: "From Match Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Match Date", required: true }
        ]
      },
      {
        name: "post_accrual_entry",
        description: "Post month-end accrual adjustments",
        approval: true,
        inputs: [
          { name: "accrual_type", type: "text", placeholder: "salary/utilities/rent", required: true },
          { name: "amount", type: "text", placeholder: "Amount", required: true },
          { name: "description", type: "text", placeholder: "Description", required: true },
          { name: "period_date", type: "date", placeholder: "Period Date", required: true }
        ]
      },
      {
        name: "reconcile_vendor_statement",
        description: "Match vendor reports against AP ledgers",
        approval: true,
        inputs: [
          { name: "vendor_contact_id", type: "text", placeholder: "Vendor ID", required: true },
          { name: "statement_date", type: "date", placeholder: "Statement Date", required: true },
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true },
          { name: "statement_lines", type: "textarea", placeholder: "JSON lines list", required: true }
        ]
      },
      {
        name: "track_cheque_clearing",
        description: "Monitor cheques lifecycles",
        approval: false,
        inputs: [
          { name: "action", type: "text", placeholder: "issue/clear/bounce/status", required: true },
          { name: "cheque_id", type: "text", placeholder: "Cheque Ref", required: false },
          { name: "vendor_name", type: "text", placeholder: "Vendor", required: false },
          { name: "amount", type: "text", placeholder: "Amount", required: false }
        ]
      },
      {
        name: "track_lc_bank_guarantee",
        description: "LC/BG guarantees monitoring",
        approval: true,
        inputs: [
          { name: "action", type: "text", placeholder: "issue/amend/close/status", required: true },
          { name: "lc_id", type: "text", placeholder: "LC ID", required: false },
          { name: "lc_type", type: "text", placeholder: "LC or BG", required: false },
          { name: "beneficiary", type: "text", placeholder: "Beneficiary Name", required: false },
          { name: "amount", type: "text", placeholder: "Amount", required: false }
        ]
      }
    ]
  },
  {
    id: "month-end",
    name: "Month-End Reporting",
    role: "Period closing computations and cash flow forecasting",
    category: "reporting",
    icon: Calendar,
    tools: [
      {
        name: "review_unpaid_bills",
        description: "Get total overdue unpaid bills",
        approval: false,
        inputs: []
      },
      {
        name: "calculate_prepaid_adjustment",
        description: "Split advanced payments proportionally",
        approval: false,
        inputs: [
          { name: "prepaid_id", type: "text", placeholder: "Prepaid Entry ID", required: true },
          { name: "target_date", type: "date", placeholder: "Adjustment Date", required: true }
        ]
      },
      {
        name: "calculate_depreciation",
        description: "Fixed assets depreciation schedules",
        approval: false,
        inputs: [
          { name: "asset_id", type: "text", placeholder: "Asset ID", required: true },
          { name: "period_date", type: "date", placeholder: "Period Date", required: true }
        ]
      },
      {
        name: "analyze_budget_variance",
        description: "Compares projections against actual spendings",
        approval: false,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true },
          { name: "period", type: "number", placeholder: "Month 1-12", required: false }
        ]
      },
      {
        name: "forecast_cash_flow",
        description: "Generate forward liquidity projections",
        approval: true,
        inputs: [
          { name: "days", type: "number", placeholder: "e.g. 30", required: true }
        ]
      }
    ]
  },
  {
    id: "year-end",
    name: "Year-End Close",
    role: "Irreversible closed books, trial balance and carry-forwards",
    category: "reporting",
    icon: Landmark,
    tools: [
      {
        name: "generate_trial_balance",
        description: "Audit ledger balances equivalence",
        approval: false,
        inputs: [
          { name: "as_of_date", type: "date", placeholder: "Ending date", required: true }
        ]
      },
      {
        name: "generate_profit_loss",
        description: "Net revenue minus overall expenses",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true }
        ]
      },
      {
        name: "generate_balance_sheet",
        description: "Assess Assets, Liabilities, and Equity balances",
        approval: false,
        inputs: [
          { name: "as_of_date", type: "date", placeholder: "Reference Date", required: true }
        ]
      },
      {
        name: "generate_cash_flow_statement",
        description: "Financial activities cash distribution summary",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true }
        ]
      },
      {
        name: "close_fiscal_year",
        description: "Locks the fiscal accounts database",
        approval: true,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "e.g. 2026", required: true },
          { name: "closing_date", type: "date", placeholder: "Date of Close", required: true },
          { name: "confirm", type: "checkbox", placeholder: "Confirm Action", required: true }
        ]
      }
    ]
  },
  {
    id: "cost-budgeting",
    name: "Cost & Budgeting",
    role: "Management costing and standard allocation frameworks",
    category: "reporting",
    icon: Percent,
    tools: [
      {
        name: "calculate_breakeven",
        description: "Compute volume/revenue thresholds",
        approval: false,
        inputs: [
          { name: "fixed_costs", type: "text", placeholder: "Fixed Costs", required: true },
          { name: "variable_cost_per_unit", type: "text", placeholder: "Variable Cost/Unit", required: true },
          { name: "selling_price_per_unit", type: "text", placeholder: "Selling Price/Unit", required: true }
        ]
      },
      {
        name: "convert_foreign_currency",
        description: "Revalue foreign transactions",
        approval: false,
        inputs: [
          { name: "amount", type: "text", placeholder: "Amount", required: true },
          { name: "from_currency", type: "text", placeholder: "e.g. USD", required: true },
          { name: "to_currency", type: "text", placeholder: "e.g. PKR", required: true },
          { name: "transaction_date", type: "date", placeholder: "Date", required: false }
        ]
      },
      {
        name: "calculate_standard_costing_variance",
        description: "Track differences between standard vs actual rates",
        approval: true,
        inputs: [
          { name: "material_id", type: "text", placeholder: "Material ID", required: true },
          { name: "actual_qty", type: "text", placeholder: "Actual Qty Used", required: true },
          { name: "actual_cost", type: "text", placeholder: "Actual Cost", required: true }
        ]
      },
      {
        name: "allocate_overhead_cost",
        description: "Apportion company overhead expenses",
        approval: true,
        inputs: [
          { name: "total_overhead", type: "text", placeholder: "Total Overhead Amount", required: true },
          { name: "allocation_method", type: "text", placeholder: "e.g. square_footage, direct_labor", required: true },
          { name: "department_metrics", type: "textarea", placeholder: "JSON metric overrides", required: true }
        ]
      }
    ]
  },
  {
    id: "tax",
    name: "Tax & Filings",
    role: "Tax preparation drafts and deductions logs",
    category: "compliance",
    icon: FileText,
    tools: [
      {
        name: "calculate_withholding_tax",
        description: "WHT computations",
        approval: false,
        inputs: [
          { name: "amount", type: "text", placeholder: "Payment Amount", required: true },
          { name: "withholding_type", type: "text", placeholder: "rent/salary/service", required: true },
          { name: "transaction_date", type: "date", placeholder: "Date", required: false }
        ]
      },
      {
        name: "calculate_eobi_deductions",
        description: "Social security computations",
        approval: false,
        inputs: [
          { name: "gross_salary", type: "text", placeholder: "Gross Salary", required: true },
          { name: "period", type: "number", placeholder: "Month 1-12", required: true },
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true }
        ]
      },
      {
        name: "adjust_sales_tax_input_output",
        description: "Input/Output adjustments",
        approval: true,
        inputs: [
          { name: "period", type: "number", placeholder: "Month 1-12", required: true },
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true },
          { name: "output_tax_amount", type: "text", placeholder: "Output Tax Override", required: false },
          { name: "input_tax_amount", type: "text", placeholder: "Input Tax Override", required: false }
        ]
      },
      {
        name: "prepare_sales_tax_filing",
        description: "Draft FBR Sales Tax filing structure",
        approval: true,
        inputs: [
          { name: "period", type: "number", placeholder: "Month 1-12", required: true },
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true },
          { name: "confirm", type: "checkbox", placeholder: "Confirm data accuracy", required: true }
        ]
      }
    ]
  },
  {
    id: "audit",
    name: "Audit & Registers",
    role: "Fraud prevention, statutory books and change monitoring",
    category: "compliance",
    icon: ShieldCheck,
    tools: [
      {
        name: "detect_anomaly_transactions",
        description: "Flag round sums or weekend entries",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true },
          { name: "anomaly_types", type: "text", placeholder: "round_amount,weekend_posting", required: false }
        ]
      },
      {
        name: "get_compliance_deadlines",
        description: "Remind of SECP / FBR dates",
        approval: false,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "2026", required: false },
          { name: "status", type: "text", placeholder: "upcoming/overdue/completed", required: false }
        ]
      },
      {
        name: "support_internal_audit",
        description: "Runs system anomalies scan",
        approval: true,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true },
          { name: "period", type: "number", placeholder: "Month 1-12", required: false }
        ]
      },
      {
        name: "maintain_statutory_registers",
        description: "CRUD statutory registry records",
        approval: true,
        inputs: [
          { name: "action", type: "text", placeholder: "add/update/delete/view", required: true },
          { name: "register_type", type: "text", placeholder: "directors/members/charges", required: true },
          { name: "entry_date", type: "date", placeholder: "Date", required: true },
          { name: "description", type: "text", placeholder: "Record Description", required: true },
          { name: "register_id", type: "text", placeholder: "ID (Update/Delete)", required: false }
        ]
      }
    ]
  },
  {
    id: "advisory",
    name: "Advisory & Insights",
    role: "Financial ratios interpretation and cost cutting",
    category: "advisory",
    icon: BarChart3,
    tools: [
      {
        name: "analyze_spending_patterns",
        description: "Renders details of expenditures patterns",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true }
        ]
      },
      {
        name: "calculate_financial_ratios",
        description: "Calculates profitability, liquidity, and efficiency",
        approval: false,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true }
        ]
      },
      {
        name: "assess_financial_health",
        description: "Outputs a 0-100 system health evaluation",
        approval: false,
        inputs: [
          { name: "fiscal_year", type: "number", placeholder: "2026", required: true }
        ]
      },
      {
        name: "generate_cost_cutting_recommendations",
        description: "Rank expense reduction suggestions",
        approval: false,
        inputs: []
      },
      {
        name: "generate_custom_report",
        description: "Section-based financial review compilation",
        approval: true,
        inputs: [
          { name: "report_type", type: "text", placeholder: "summary/detailed/comparative", required: true },
          { name: "from_date", type: "date", placeholder: "From Date", required: true },
          { name: "to_date", type: "date", placeholder: "To Date", required: true }
        ]
      }
    ]
  },
  {
    id: "system-admin",
    name: "System Admin (Bonus)",
    role: "Core infrastructure, logs audit and configuration",
    category: "advisory",
    icon: SettingsIcon,
    tools: [
      {
        name: "check_system_status",
        description: "Check database & provider networks health",
        approval: false,
        inputs: []
      },
      {
        name: "get_usage_statistics",
        description: "Database transaction analytics",
        approval: false,
        inputs: [
          { name: "from_date", type: "date", placeholder: "Start Date", required: true },
          { name: "to_date", type: "date", placeholder: "End Date", required: true }
        ]
      },
      {
        name: "manage_system_preferences",
        description: "Company global parameters adjustment",
        approval: true,
        inputs: [
          { name: "action", type: "text", placeholder: "view/update/reset", required: true },
          { name: "setting_key", type: "text", placeholder: "Setting Key", required: false },
          { name: "value", type: "text", placeholder: "New Value (update)", required: false }
        ]
      },
      {
        name: "schedule_system_task",
        description: "Schedule system maintenance tasks",
        approval: true,
        inputs: [
          { name: "task_type", type: "text", placeholder: "backup/export_data/cleanup", required: true },
          { name: "schedule_time", type: "text", placeholder: "now/off_peak/datetime", required: false },
          { name: "notes", type: "text", placeholder: "Additional Notes", required: false }
        ]
      }
    ]
  }
];
