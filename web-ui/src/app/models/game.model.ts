export interface Game {
  id: string;
  code: string;
  host_name: string;
  host_user_id: number;
  status: 'active' | 'ending' | 'settled' | 'expired';
  settlement_phase?: 'credit_settlement' | 'final_cashout' | 'completed';
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

export interface UnpaidCredit {
  game_id: string;
  debtor_user_id: number;
  debtor_name: string;
  amount: number;
  amount_claimed: number;
  amount_available: number;
  created_at: Date;
}

export interface PlayerWithCredit {
  user_id: number;
  name: string;
  credits_owed: number;
  credits_repaid: number;
  remaining_credits: number;
}

export interface SettlementStatus {
  success: boolean;
  phase: 'credit_settlement' | 'final_cashout' | null;
  players_with_credits?: PlayerWithCredit[];
  available_cash?: number;
  unpaid_credits?: UnpaidCredit[];
  message?: string;
}

export interface SettlementSummary {
  player_name: string;
  totals: {
    cash_buyins: number;
    credit_buyins: number;
    total_buyins: number;
    cashouts: number;
    net: number;
  };
  owes_to_me: Array<{debtor_name: string; amount: number}>;
  i_owe: Array<{amount: number; note: string}>;
  transactions: Transaction[];
}

export interface AllSettlementSummaries {
  summaries: Array<{
    user_id: number;
    name: string;
    totals: {
      cash_buyins: number;
      credit_buyins: number;
      total_buyins: number;
      cashouts: number;
      net: number;
    };
    unpaid_credit_owed: number;
  }>;
}

export interface GameStatus {
  game: Game;
  active_players: number;
  total_cash: number;
  total_credit: number;
  total_buyins: number;
  total_cashed_out: number;
  total_credits_repaid: number;
}

export interface BankStatus {
  cash_balance: number;
  available_cash: number;
  outstanding_credits: number;
  chips_in_play: number;
  total_cash_in: number;
  total_cash_out: number;
  total_credits_issued: number;
  total_credits_repaid: number;
}

export interface PlayerSummary {
  cash_buyins: number;
  credit_buyins: number;
  total_buyins: number;
  credits_owed: number;
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