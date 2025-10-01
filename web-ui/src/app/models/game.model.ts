export interface Game {
  id: string;
  code: string;
  host_name: string;
  host_user_id: number;
  status: 'active' | 'ended' | 'expired';
  created_at: Date;
  ended_at?: Date;
}

export interface Player {
  user_id: number;
  name: string;
  active: boolean;
  is_host: boolean;
  quit: boolean;
  cashed_out: boolean;
  cashout_time?: Date;
  final_chips?: number;
  game_id: string;
}

export interface Transaction {
  id: string;
  game_id: string;
  user_id: number;
  type: 'buyin_cash' | 'buyin_register' | 'cashout';
  amount: number;
  confirmed: boolean;
  rejected: boolean;
  created_at: Date;
  former_host_cashout?: boolean;
}

export interface Debt {
  id: string;
  game_id: string;
  debtor_user_id: number;
  debtor_name: string;
  amount: number;
  status: 'pending' | 'assigned' | 'settled';
  creditor_user_id?: number;
  creditor_name?: string;
  created_at: Date;
  transferred_at?: Date;
}

export interface GameStatus {
  game: Game;
  active_players: number;
  total_cash: number;
  total_credit: number;
  total_buyins: number;
  total_cashed_out: number;
  total_debt_settled: number;
}

export interface PlayerSummary {
  cash_buyins: number;
  credit_buyins: number;
  total_buyins: number;
  pending_debt: number;
  transactions: Transaction[];
}

export interface CashoutRequest {
  game_id: string;
  user_id: number;
  amount: number;
}

export interface BuyinRequest {
  game_id: string;
  user_id: number;
  type: 'cash' | 'register';
  amount: number;
}

export interface GameLink {
  url: string;
  qr_code_data_url: string;
}