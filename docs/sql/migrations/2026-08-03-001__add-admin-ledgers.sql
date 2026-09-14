-- 新增后台账本：一月一账单，支出明细逐项录入，编辑操作留痕。
-- 回滚思路：确认无需保留数据后，按依赖顺序 DROP TABLE admin_ledger_logs、admin_ledger_expenses、admin_ledgers。

CREATE TABLE IF NOT EXISTS admin_ledgers (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    business_id VARCHAR(32) NOT NULL,
    ledger_month DATE NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    description TEXT NOT NULL,
    screenshot_urls_json TEXT NOT NULL,
    income_snapshot_json TEXT NOT NULL,
    online_revenue_fen INTEGER NOT NULL DEFAULT 0,
    redeem_revenue_fen INTEGER NOT NULL DEFAULT 0,
    offline_revenue_fen INTEGER NOT NULL DEFAULT 0,
    total_income_fen INTEGER NOT NULL DEFAULT 0,
    total_expense_fen INTEGER NOT NULL DEFAULT 0,
    net_income_fen INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER NOT NULL,
    updated_by INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_ledgers_business_id (business_id),
    UNIQUE KEY uq_admin_ledgers_ledger_month (ledger_month),
    KEY ix_admin_ledgers_created_by (created_by),
    KEY ix_admin_ledgers_updated_by (updated_by),
    CONSTRAINT fk_admin_ledgers_created_by FOREIGN KEY (created_by) REFERENCES users (id),
    CONSTRAINT fk_admin_ledgers_updated_by FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_ledger_expenses (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    business_id VARCHAR(32) NOT NULL,
    ledger_id INTEGER NOT NULL,
    expense_type VARCHAR(30) NOT NULL DEFAULT 'other',
    title VARCHAR(200) NOT NULL DEFAULT '',
    amount_fen INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    description TEXT NOT NULL,
    screenshot_urls_json TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER NOT NULL,
    updated_by INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_admin_ledger_expenses_business_id (business_id),
    KEY ix_admin_ledger_expenses_ledger_id (ledger_id),
    KEY ix_admin_ledger_expenses_expense_type (expense_type),
    KEY ix_admin_ledger_expenses_created_by (created_by),
    KEY ix_admin_ledger_expenses_updated_by (updated_by),
    CONSTRAINT fk_admin_ledger_expenses_ledger_id FOREIGN KEY (ledger_id) REFERENCES admin_ledgers (id),
    CONSTRAINT fk_admin_ledger_expenses_created_by FOREIGN KEY (created_by) REFERENCES users (id),
    CONSTRAINT fk_admin_ledger_expenses_updated_by FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_ledger_logs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    ledger_id INTEGER NOT NULL,
    operator_id INTEGER NOT NULL,
    action VARCHAR(40) NOT NULL,
    summary VARCHAR(500) NOT NULL DEFAULT '',
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_admin_ledger_logs_ledger_id (ledger_id),
    KEY ix_admin_ledger_logs_operator_id (operator_id),
    KEY ix_admin_ledger_logs_action (action),
    KEY ix_admin_ledger_logs_created_at (created_at),
    CONSTRAINT fk_admin_ledger_logs_ledger_id FOREIGN KEY (ledger_id) REFERENCES admin_ledgers (id),
    CONSTRAINT fk_admin_ledger_logs_operator_id FOREIGN KEY (operator_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
