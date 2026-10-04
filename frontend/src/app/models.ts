export interface ToolTrace {
  tool: string;
  args: Record<string, unknown>;
  status: 'success' | 'error';
  summary: string;
  result?: unknown;
}

export interface CalendarAction {
  event_id: string;
  title: string;
  start: string;
  end: string;
  location?: string | null;
  notes?: string | null;
  ics_url: string;
  google_calendar_url: string;
}

export interface AddressAction {
  query: string;
  display_name: string;
  latitude?: number | null;
  longitude?: number | null;
  map_url?: string | null;
}

export interface DeadlineAction {
  id: number;
  title: string;
  due_at: string;
  source?: string | null;
  notes?: string | null;
  is_duplicate: boolean;
  has_details: boolean;
}

export interface OfficialGuidance {
  organization: string;
  topic: string;
  summary: string;
  official_url: string;
  cautions: string[];
}

export interface ActionItem {
  action: string;
  deadline?: string | null;
  importance:
    | 'critical'
    | 'important'
    | 'optional';
}

export interface DutchTerm {
  term: string;
  meaning: string;
}

export interface LetterUnderstanding {
  category:
    | 'payment_required'
    | 'appointment_or_visit'
    | 'action_required'
    | 'information_only'
    | 'mixed'
    | 'needs_review';

  priority:
    | 'urgent'
    | 'important'
    | 'normal'
    | 'low';

  sender?: string | null;
  subject?: string | null;
  simple_summary: string;
  why_you_received_it?: string | null;

  action_required:
    | 'yes'
    | 'no'
    | 'unclear';

  can_ignore:
    | 'no'
    | 'probably_yes'
    | 'unclear';

  ignore_explanation: string;
  action_items: ActionItem[];
  payment_amount?: string | null;
  payment_reference?: string | null;
  primary_deadline?: string | null;
  appointment_time?: string | null;
  appointment_location?: string | null;
  what_to_bring: string[];
  consequence_if_ignored?: string | null;
  dutch_terms: DutchTerm[];

  confidence:
    | 'high'
    | 'medium'
    | 'low';
}

export interface AnalyzeResponse {
  source_kind: 'image' | 'pdf';
  total_pages: number;
  processed_pages: number;
  processing_warning?: string | null;
  understanding: LetterUnderstanding;
  tool_trace: ToolTrace[];
  calendar_actions: CalendarAction[];
  address_actions: AddressAction[];
  saved_deadlines: DeadlineAction[];
  official_guidance: OfficialGuidance[];
}

export interface HealthResponse {
  status: string;
  provider?: string;
  model: string;
  api_key_configured?: boolean;
}

export interface DeadlineListResponse {
  deadlines: DeadlineAction[];
}
