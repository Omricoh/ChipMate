export interface User {
  id: number;
  name: string;
  username?: string;
  is_authenticated: boolean;
  current_game_id?: string;
  is_host?: boolean;
  is_admin?: boolean;
}

export interface AuthRequest {
  name?: string;
  user_id?: number;
  username?: string;
  password?: string;
}

export interface AuthResponse {
  user: User;
  token?: string;
  message: string;
}