// ── Enums ──────────────────────────────────────────────────────────────────

export enum GameStatus {
  OPEN = 'OPEN',
  SETTLING = 'SETTLING',
  CLOSED = 'CLOSED',
}

export enum RequestType {
  CASH = 'CASH',
  CREDIT = 'CREDIT',
}

export enum RequestStatus {
  PENDING = 'PENDING',
  APPROVED = 'APPROVED',
  DECLINED = 'DECLINED',
  EDITED = 'EDITED',
}

export enum CheckoutStatus {
  PENDING = 'PENDING',
  SUBMITTED = 'SUBMITTED',
  VALIDATED = 'VALIDATED',
  CREDIT_DEDUCTED = 'CREDIT_DEDUCTED',
  AWAITING_DISTRIBUTION = 'AWAITING_DISTRIBUTION',
  DISTRIBUTED = 'DISTRIBUTED',
  DONE = 'DONE',
}

export enum NotificationType {
  REQUEST_CREATED = 'REQUEST_CREATED',
  REQUEST_APPROVED = 'REQUEST_APPROVED',
  REQUEST_DECLINED = 'REQUEST_DECLINED',
  REQUEST_EDITED = 'REQUEST_EDITED',
  CHECKOUT_READY = 'CHECKOUT_READY',
  GAME_CLOSING = 'GAME_CLOSING',
}

// ── Core Domain Types ──────────────────────────────────────────────────────

export interface Game {
  game_id: string;
  game_code: string;
  status: GameStatus;
  manager_name: string;
  manager_player_id: string;
  created_at: string;
  closed_at: string | null;
  player_count: number;
}

export interface Player {
  player_id: string;
  name: string;
  is_manager: boolean;
  current_chips: number;
  total_cash_in: number;
  total_credit_in: number;
  credits_owed: number;
  is_active: boolean;
  checked_out: boolean;
  joined_at: string;
  checkout_status?: CheckoutStatus | null;
  submitted_chip_count?: number | null;
  validated_chip_count?: number | null;
  preferred_cash?: number | null;
  preferred_credit?: number | null;
  chips_after_credit?: number | null;
  credit_repaid?: number | null;
  profit_loss?: number | null;
  distribution?: PlayerDistribution | null;
  actions?: PlayerAction[] | null;
  input_locked?: boolean;
  frozen_buy_in?: FrozenBuyIn | null;
}

export interface ChipRequest {
  request_id: string;
  player_id: string;
  player_name: string;
  type: RequestType;
  amount: number;
  original_amount: number | null;
  status: RequestStatus;
  created_at: string;
  processed_at: string | null;
  processed_by: string | null;
  processed_by_name: string | null;
  note: string | null;
  auto_approved: boolean;
}

export interface Notification {
  notification_id: string;
  type: NotificationType;
  message: string;
  data: {
    request_id?: string | null;
    amount?: number | null;
    player_name?: string | null;
  };
  created_at: string;
  is_read: boolean;
}

export interface BankSummary {
  total_cash_in: number;
  total_credit_in: number;
  total_in_play: number;
  total_checked_out: number;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
  checks: {
    database: 'ok' | 'degraded' | 'down';
    cache: 'ok' | 'down';
  };
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, string>;
    request_id?: string;
    timestamp?: string;
  };
}

// ── Auth Types ─────────────────────────────────────────────────────────────

export interface AdminLoginRequest {
  username: string;
  password: string;
}

export interface AdminLoginResponse {
  access_token: string;
  token_type: string;
  user: {
    user_id: string;
    role: 'ADMIN';
    username: string;
  };
}

export interface ValidateTokenResponse {
  valid: boolean;
  user?: {
    user_id: string;
    role: 'ADMIN' | 'MANAGER' | 'PLAYER';
    username?: string;
    player_id?: string;
    game_id?: string;
    game_code?: string;
    is_manager?: boolean;
    display_name?: string;
  };
  error?: string;
}

// ── Game Types ─────────────────────────────────────────────────────────────

export interface CreateGameRequest {
  manager_name: string;
  max_players?: number | null;
}

export interface CreateGameResponse {
  game_id: string;
  game_code: string;
  manager_player_id: string;
  player_token: string;
  created_at: string;
}

export interface GameStatusResponse {
  game: {
    game_id: string;
    game_code: string;
    status: GameStatus;
    manager_name: string;
    created_at: string;
  };
  players: {
    total: number;
    active: number;
    checked_out: number;
  };
  chips: BankSummary;
  pending_requests: number;
  credits_outstanding: number;
}

export interface GameByCodeResponse {
  game_id: string;
  game_code: string;
  status: GameStatus;
  manager_name: string;
  player_count: number;
  can_join: boolean;
}

// ── Player Types ───────────────────────────────────────────────────────────

export interface JoinGameRequest {
  player_name: string;
}

export interface JoinGameResponse {
  player_id: string;
  player_token: string;
  game: {
    game_id: string;
    game_code: string;
    manager_name: string;
    status: GameStatus;
  };
}

export interface PlayerMeResponse {
  player_id: string;
  name: string;
  is_manager: boolean;
  chips: {
    current_balance: number;
    total_cash_in: number;
    total_credit_in: number;
    credits_owed: number;
    total_checked_out: number;
  };
  status: {
    is_active: boolean;
    checked_out: boolean;
    checked_out_at: string | null;
  };
  joined_at: string;
}

export interface PlayersListResponse {
  players: Player[];
  total_count: number;
}

// ── Notification Types ─────────────────────────────────────────────────────

export interface NotificationsResponse {
  notifications: Notification[];
  unread_count: number;
  server_time: string;
}

// ── Chip Request Types ─────────────────────────────────────────────────────

export interface CreateChipRequestPayload {
  type: RequestType;
  amount: number;
  on_behalf_of_token?: string | null;
  note?: string | null;
}

export interface PendingRequestsResponse {
  requests: ChipRequest[];
  total_count: number;
  total_amount: {
    cash: number;
    credit: number;
  };
}

export interface ChipRequestHistoryResponse {
  requests: ChipRequest[];
  total_count: number;
  pagination: {
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

// ── Admin Types ──────────────────────────────────────────────────────────

export interface AdminStats {
  total_games: number;
  active_games: number;
  settling_games: number;
  closed_games: number;
  total_players: number;
}

export interface AdminGameSummary {
  game_id: string;
  game_code: string;
  status: GameStatus;
  manager_name: string;
  player_count: number;
  created_at: string;
  bank: BankSummary;
}

export interface AdminGamesResponse {
  games: AdminGameSummary[];
  total: number;
}

export interface AdminBankDetail {
  cash_balance: number;
  total_cash_in: number;
  total_cash_out: number;
  total_credits_issued: number;
  total_credits_repaid: number;
  total_chips_issued: number;
  total_chips_returned: number;
  chips_in_play: number;
}

export interface AdminGameInfo {
  game_id: string;
  game_code: string;
  status: GameStatus;
  manager_player_token: string;
  created_at: string;
  closed_at: string | null;
  expires_at: string;
  bank: AdminBankDetail;
}

export interface AdminPlayerInfo {
  player_id: string;
  player_token: string;
  display_name: string;
  is_manager: boolean;
  is_active: boolean;
  credits_owed: number;
  checked_out: boolean;
  joined_at: string;
}

export interface AdminGameDetail {
  game: AdminGameInfo;
  players: AdminPlayerInfo[];
  request_stats: {
    total: number;
    pending: number;
    approved: number;
    declined: number;
  };
}

// ── Settlement Types ────────────────────────────────────────────────────────

export interface FrozenBuyIn {
  total_cash_in: number;
  total_credit_in: number;
  total_buy_in: number;
}

export interface CreditAssignment {
  from: string;
  amount: number;
}

export interface PlayerDistribution {
  cash: number;
  credit_from: CreditAssignment[];
}

export interface PlayerAction {
  type: 'receive_cash' | 'receive_credit' | 'pay_credit';
  amount: number;
  from?: string;
  to?: string;
}

export interface StartSettlingResponse {
  game_id: string;
  status: string;
  cash_pool: number;
  player_count: number;
}

export interface PoolStateResponse {
  cash_pool: number;
  credit_pool: number;
  settlement_state: string;
}

export interface DistributionSuggestion {
  [playerToken: string]: PlayerDistribution;
}
