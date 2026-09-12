/**
 * TypeScript mirrors of app/schemas/{admin,customer,call,common}.py
 * (Phase 9 — T-6). Kept as one file, by hand, the same way the rest of
 * this frontend has no codegen step from the backend's Pydantic models
 * — see contexts/AuthContext.tsx's CurrentUser type for the existing
 * precedent. If a backend schema field changes, this file has to be
 * updated by hand to match; nothing enforces that automatically.
 */

export type PageMeta = { limit: number; offset: number; total: number; has_more: boolean };

export type PassengerOut = {
  id: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  passenger_type: string;
  meal_preference: string | null;
  seat_preference: string | null;
  special_assistance: string | null;
  frequent_flyer_number: string | null;
  passport_on_file: boolean;
  passport_number_masked: string | null;
};

// Matches app/schemas/admin.py::AdminBookingOut — BookingOut plus the
// staff-only id/customer_id/customer_email fields; see that schema's
// docstring for why the customer-facing BookingOut doesn't have them.
export type AdminBookingOut = {
  id: string;
  customer_id: string;
  customer_email: string | null;
  pnr: string;
  status: string;
  payment_status: string;
  origin: string;
  destination: string;
  flight_number: string;
  aircraft_type: string;
  departure_time: string;
  arrival_time: string;
  currency: string;
  total_price: number;
  passengers: PassengerOut[];
  cancellation_deadline: string | null;
};

export type AdminBookingListOut = { items: AdminBookingOut[]; page: PageMeta };

export type PaymentSummaryOut = {
  id: string;
  status: string;
  amount: number;
  currency: string;
  provider_name: string;
  provider_payment_intent_id: string | null;
  refunded_amount: number | null;
  refund_status: string | null;
  refund_reason: string | null;
  failure_code: string | null;
  failure_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type AuditLogEntryOut = {
  id: string;
  actor: string;
  actor_type: string;
  action: string;
  resource: string;
  resource_id: string | null;
  call_id: string | null;
  event_metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AdminBookingDetailOut = {
  booking: AdminBookingOut;
  payments: PaymentSummaryOut[];
  audit_trail: AuditLogEntryOut[];
};

export type DailyRevenuePointOut = { day: string; currency: string; net_amount: number };

// See app/core/admin/analytics.py's module docstring: this deliberately
// has no "quote conversion rate" field — that isn't computable from
// what's persisted today. payment_conversion_rate/cancellation_rate are
// the honest substitutes; see that file for exactly what each measures.
export type AnalyticsSummaryOut = {
  total_bookings: number;
  bookings_by_status: Record<string, number>;
  paid_bookings: number;
  cancelled_bookings: number;
  payment_conversion_rate: number;
  cancellation_rate: number;
  gross_revenue_by_currency: Record<string, number>;
  net_revenue_by_currency: Record<string, number>;
  revenue_by_day: DailyRevenuePointOut[];
};

export type CustomerOut = {
  id: string;
  email: string | null;
  phone: string | null;
  first_name: string | null;
  last_name: string | null;
  preferred_language: string;
  created_at: string;
};

export type CustomerDetailOut = CustomerOut & { bookings: AdminBookingOut[] };
export type CustomerListOut = { items: CustomerOut[]; page: PageMeta };
export type CustomerUpdateRequest = Partial<{
  email: string;
  phone: string;
  first_name: string;
  last_name: string;
}>;

export type CallOut = {
  id: string;
  vapi_call_id: string;
  assistant_id: string | null;
  direction: string | null;
  customer_phone_number: string | null;
  status: string;
  ended_reason: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
};

export type ToolExecutionOut = {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  authorization_result: string;
  denial_reason: string | null;
  outcome: string | null;
  error_code: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type CallDetailOut = CallOut & { tool_executions: ToolExecutionOut[] };
export type CallListOut = { items: CallOut[]; page: PageMeta };
