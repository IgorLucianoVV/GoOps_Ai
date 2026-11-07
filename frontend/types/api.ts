export interface Envelope<T> { data: T; meta: Record<string, any>; }
export interface ApiErrorBody { code: string; message: string; details?: any; }
export interface User { id: string; name: string; role: string; role_label?: string; domains: string[]; permissions?: string[]; email?: string; }
export interface MetricMeta { metric_key: string; version: string; scope: string; domain: string; unit: string; formula_text: string; relationship: string; filters_applied?: Record<string, any>; }
export interface NpsResult { value: number | null; n: number; promoters: number; neutrals: number; detractors: number; promoter_pct: number | null; neutral_pct: number | null; detractor_pct: number | null; invalid_excluded?: number; }
export interface Incident {
  id: string; title: string; description: string; category: string; domain: string; severity: string; status: string;
  detected_at: string; source: string; signal: any; related_metrics: string[]; evidence: any[]; agents: string[];
  root_cause: string | null; summary?: string | null; hypotheses: any[] | null; recommendation: any; result: any; is_demo: boolean;
  operations?: Operation[]; workflows?: any[];
}
export interface IncidentEvent { id: string; seq: number; ts: string; actor_type: string; actor: string; event_type: string; message: string; data: any; is_demo: boolean; }
export interface Operation {
  id: string; incident_id: string | null; action_type: string; title: string; description: string; params: any;
  impacted_areas: string[]; risk: string; expected_impact: any; requires_approval: boolean; approver_roles: string[];
  status: string; proposed_by: string; approved_by: string | null; approved_at: string | null; decision_note: string | null;
  executed_at: string | null; execution_mode: string | null; result: any; created_at: string;
}
