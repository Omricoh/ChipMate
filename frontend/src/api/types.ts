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
  user: {
    user_id: string;
    role: 'ADMIN' | 'MANAGER' | 'PLAYER';
    player_id: string | null;
    game_id: string | null;
    game_code: string | null;
    is_manager: boolean | null;
  };
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
  on_behalf_of_player_id?: string | null;
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

// ── Settlement Types ─────────────────────────────────────────────────────

export interface SettleGameResponse {
  game_id: string;
  status: 'SETTLING';
  message: string;
}

export interface CheckoutPlayerResponse {
  player_id: string;
  player_name: string;
  final_chip_count: number;
  total_buy_in: number;
  profit_loss: number;
  credits_owed: number;
  has_debt: boolean;
  checked_out_at: string;
}

export interface CheckoutPlayerSummary {
  player_id: string;
  player_name: string;
  final_chip_count: number;
  profit_loss: number;
  has_debt: boolean;
}

export interface CheckoutAllResponse {
  checked_out: CheckoutPlayerSummary[];
  summary: {
    total_checked_out: number;
    debt_players_count: number;
    total_profit: number;
    total_loss: number;
  };
}

export interface SettleDebtResponse {
  player_id: string;
  player_name: string;
  previous_credits_owed: number;
  credits_owed: 0;
  settled: true;
}

export interface CloseGameResponse {
  game_id: string;
  status: 'CLOSED';
  closed_at: string;
  summary: {
    total_checked_out: number;
    debt_players_count: number;
    total_profit: number;
    total_loss: number;
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

export interface AdminGameDetail {
  game_id: string;
  game_code: string;
  status: GameStatus;
  manager_name: string;
  player_count: number;
  created_at: string;
  closed_at: string | null;
  bank: BankSummary;
  players: Player[];
  request_stats: {
    total: number;
    pending: number;
    approved: number;
    declined: number;
  };
}
