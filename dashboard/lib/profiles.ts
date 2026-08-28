import type { CustomerSignals } from "./types";

// The two head-to-head demo shoppers from the brief. Same product
// (Nike Pegasus 41, listed at Rs 4,999), very different trust profiles.

export const PRODUCT = {
  name: "Nike Pegasus 41 Running Shoes",
  brand: "Nike",
  list_price: 4999,
  category: "fashion" as const,
  image_alt: "Nike Pegasus 41",
};

export const CUSTOMER_A: CustomerSignals = {
  session_id: "demo-customer-a",
  ip: "49.36.128.5", // Reliance Jio broadband range (whitelisted -> residential)
  list_price: PRODUCT.list_price,
  product_category: PRODUCT.category,
  device_type: "iPhone",
  city_tier: 1,
  payment_method_preference: "Credit_Card",
  referral_source: "organic",
  cross_merchant_trust_score: 92,
  return_rate: 0.05,
  payment_success_rate: 0.98,
  cod_completion_rate: 0.9,
  num_merchants_transacted: 24,
  account_age_days: 1095, // ~3 years
  historical_aov: 6200,
};

export const CUSTOMER_B: CustomerSignals = {
  session_id: "demo-customer-b",
  ip: "146.70.0.5", // commercial VPN egress block
  list_price: PRODUCT.list_price,
  product_category: PRODUCT.category,
  device_type: "Android_budget",
  city_tier: 3,
  payment_method_preference: "COD",
  referral_source: "social",
  cross_merchant_trust_score: 31,
  return_rate: 0.34,
  payment_success_rate: 0.81,
  cod_completion_rate: 0.62,
  num_merchants_transacted: 2,
  account_age_days: 180, // ~6 months
  historical_aov: 1400,
};

export const CITY_LABEL: Record<number, string> = {
  1: "Mumbai (Tier 1)",
  2: "Jaipur (Tier 2)",
  3: "Patna (Tier 3)",
};

export const DEVICE_LABEL: Record<string, string> = {
  Android_budget: "Budget Android",
  Android_premium: "Premium Android",
  iPhone: "iPhone",
  Desktop: "Desktop",
};

export const IP_SAMPLES: Record<string, string> = {
  residential: "49.36.128.5",
  mobile_carrier: "42.110.10.5",
  vpn: "146.70.0.5",
  datacenter: "13.234.20.10",
  public_wifi: "14.139.45.9",
  tor: "185.220.101.1",
};
