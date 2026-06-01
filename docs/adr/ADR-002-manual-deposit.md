# ADR-002: Phase 1 uses manual deposit marking

Status: accepted.

Phase 1 needs to validate willingness to pay without spending engineering time on automatic WeChat Pay, Alipay, refunds, invoices, and order reconciliation. Payment is therefore handled by manual transfer or an internal QR code, then marked by an authorized admin user.

The backend stores `payment_status`, `payment_cents`, `payment_method`, `payment_reference`, `payment_marked_by_admin_id`, and `payment_at`. Interview sessions are blocked until the project is paid or waived.
