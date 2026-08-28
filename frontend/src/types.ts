export type ConversationState =
  | "new"
  | "recommended"
  | "review"
  | "saved"
  | "responded"
  | "discarded"
  | "expired";

export type RecommendedAction =
  | "respond_now"
  | "review_today"
  | "help_without_mentioning"
  | "ask_question"
  | "observe"
  | "discard";

export type PromotionRisk = "low" | "medium" | "high";

export interface Profile {
  id: string;
  account_id: string;
  email: string;
  display_name: string;
}

export interface ConversationListItem {
  id: string;
  subreddit: string;
  title: string;
  summary: string;
  problem_detected: string;
  language: string;
  state: ConversationState;
  score_total: number | null;
  recommended_action: RecommendedAction | null;
  promotion_risk: PromotionRisk | null;
  topic_id: string | null;
  topic_name: string | null;
  published_at: string | null;
  detected_at: string;
  num_comments: number;
  url: string;
  source_mode: "demo" | "manual" | "reddit_api";
  is_demo: boolean;
  raw_purged: boolean;
}

export interface ScoreBreakdown {
  audience_fit: number;
  problem_fit: number;
  request_intent: number;
  value_potential: number;
  recency: number;
  low_competition: number;
  community_priority: number;
  promotion_risk_penalty: number;
  total: number;
  classification: string;
}

export interface Analysis {
  audience_type: string;
  problem_detected: string;
  intent: string;
  can_add_value: boolean;
  value_angle: string;
  tool_request: boolean;
  radarin_fit: string;
  promotion_risk: PromotionRisk;
  recommended_action: RecommendedAction;
  mention_radarin: "no" | "soft" | "transparent_direct";
  reasoning_summary: string;
  confidence: number;
}

export interface Draft {
  id: string;
  variant: "educational" | "soft_mention" | "direct_transparent";
  language: string;
  body: string;
  is_edited: boolean;
  is_recommended: boolean;
}

export interface Outcome {
  responded_at: string | null;
  final_text_used: string;
  notes: string;
  upvotes: number | null;
  reply_count: number | null;
  attributed_visits: number | null;
  attributed_signups: number | null;
  result: string;
}

export interface ConversationDetail extends ConversationListItem {
  raw_title: string | null;
  raw_body: string | null;
  community_notes: string | null;
  community_rules_url: string | null;
  analysis: Analysis | null;
  score_breakdown: ScoreBreakdown | null;
  drafts: Draft[];
  outcome: Outcome | null;
  expires_at: string | null;
}

export interface Community {
  id: string;
  name: string;
  is_active: boolean;
  group: string;
  priority: "high" | "medium" | "low";
  primary_language: string;
  allows_links: "yes" | "no" | "unknown";
  allows_self_promo: "yes" | "no" | "limited" | "unknown";
  notes: string;
  rules_url: string;
  rules_last_reviewed_at: string | null;
  opportunities_found: number;
  responses_made: number;
  historical_outcome: string;
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  languages: string;
  priority: "high" | "medium" | "low";
  is_active: boolean;
  keywords: string[];
  exclusions: string[];
  positive_examples: string[];
  negative_examples: string[];
}

export interface AlertSettings {
  id: string;
  email_recipient: string;
  timezone: string;
  daily_digest_enabled: boolean;
  daily_digest_time: string;
  min_score_threshold: number;
  urgent_alerts_enabled: boolean;
  urgent_score_threshold: number;
  max_urgent_per_day: number;
  weekly_digest_enabled: boolean;
}

export interface AlertDelivery {
  id: string;
  kind: string;
  subject: string;
  body_html: string;
  to_address: string;
  provider: string;
  sent: boolean;
  created_at: string;
}

export interface JobRun {
  id: string;
  job_name: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  processed_count: number;
  error_count: number;
  error_message: string;
  duration_ms: number | null;
  metrics: Record<string, unknown>;
}

export interface IntegrationsStatus {
  reddit_api_enabled: boolean;
  reddit_connected: boolean;
  ai_analysis_enabled: boolean;
  ai_provider: string;
  email_provider: string;
  email_configured: boolean;
  auth_mode: "development" | "supabase";
  dev_auth_bypass: boolean;
  supabase_configured: boolean;
  raw_content_retention_hours: number;
  reddit_credentials_configured: boolean;
  reddit_last_run_at: string | null;
  reddit_last_success: boolean;
  reddit_posts_retrieved: number;
  reddit_new_conversations: number;
  reddit_duplicates: number;
  reddit_communities_reviewed: number;
  reddit_errors: number;
  reddit_rate_remaining: number | null;
  reddit_rate_used: number | null;
  reddit_rate_reset_seconds: number | null;
  reddit_next_run_frequency: string;
}

export interface JobDiagnostics {
  registered_jobs: string[];
  frequencies: Record<string, string>;
  worker: { state: string; scheduler_managed: boolean };
  latest_runs: JobRun[];
}

export interface Dashboard {
  found_today: number;
  respond_now: number;
  review_today: number;
  saved: number;
  responded: number;
  discarded: number;
  last_run_at: string | null;
}

export interface HistoryData {
  responded_conversations: ConversationListItem[];
  best_communities: { name: string; opportunities_found: number; responses_made: number }[];
  top_topics: { name: string; count: number }[];
  average_score: number;
  conversations_started: number;
  attributed_signups: number;
  attributed_visits: number;
}

export interface CSVImportResult {
  imported: number;
  duplicates: number;
  errors: string[];
}
