export interface User {
  id: number;
  name: string;
  username?: string;
  is_authenticated: boolean;
  current_game_id?: string;
  is_host?: boolean;
}

export interface AuthRequest {
  name: string;
  user_id?: number;
}

export interface AuthResponse {
  user: User;
  token?: string;
  message: string;
}