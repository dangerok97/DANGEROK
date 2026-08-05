/** Action Engine client types */

export type ActionFlow =
  | 'study'
  | 'event'
  | 'travel'
  | 'medical'
  | 'admin'
  | 'generic'
  | string;

export type AnswerOption = {
  id: string;
  label: string;
  value?: unknown;
};

export type QuestionTurn = {
  id: string;
  question: string;
  explanation?: string | null;
  input_kind: 'chips' | 'chips_or_text' | 'text';
  options: AnswerOption[];
  allow_skip?: boolean;
  required?: boolean;
  brain_key?: string | null;
};

export type ProposedAction = {
  id: string;
  kind: string;
  label: string;
  detail?: string | null;
  status: 'proposed' | 'done' | 'skipped' | 'blocked';
  meta?: Record<string, unknown>;
};

export type ActionSession = {
  id: string;
  status: 'active' | 'completed' | 'cancelled';
  flow: ActionFlow;
  engine_version: string;
  title: string;
  description?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  home_item_id?: string | null;
  home_item_type?: string | null;
  current_turn: QuestionTurn | null;
  answers: Record<string, unknown>;
  progress: number;
  done: boolean;
  proposed_actions: ProposedAction[];
  project?: {
    project_id: string;
    title: string;
    created: boolean;
    merge_candidate_id?: string | null;
    merge_candidate_title?: string | null;
  } | null;
  brain_node_id?: string | null;
  effects?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  meta?: Record<string, unknown>;
};

export type OpenActionResult = {
  session: ActionSession;
  resumed?: boolean;
  merge_proposal?: { project_id: string; title?: string } | null;
};

export type AnswerResult = {
  ok: boolean;
  session: ActionSession;
  completed?: boolean;
  home_invalidate?: boolean;
  next_focus_hint?: string | null;
  error?: string;
};
